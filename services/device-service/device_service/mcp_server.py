"""Device-service MCP server (PRD-0003 §8.2, ADR-012).

A SEPARATE Streamable-HTTP endpoint on 127.0.0.1:8766 — runs as its own compose service
(same image, `uvicorn device_service.mcp_server:app`), NOT mounted into the REST app (:8002):
control/management-plane separation (§8.2 rationale). AI channel only (X-API-Key=$AI_API_KEY),
per-IP rate limit, per-tool-call structured audit log. Exposes exactly three read/reclassify
tools — NO confirm/override/reject (those are human/OPS REST actions, §8.6.7).

The official `mcp` SDK's FastMCP is used (stateless_http + json_response per MCP production
guidance); it runs on Python 3.10+ (no 3.12 bump needed).
"""
from __future__ import annotations

import hmac
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import mcp_tools
from .classifier import Classifier
from .config import Settings
from .db import Database
from .llm.factory import make_guardrail, make_provider

_log = logging.getLogger("device_service.mcp")
_audit = logging.getLogger("device_service.mcp.audit")

RATE_LIMIT_PER_MIN = 60   # §8.2 per-IP


@dataclass
class AppCtx:
    db: Database
    classifier: Classifier
    settings: Settings


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    """Build the AI-path DB pools + classifier once at startup; expose via the tool Context."""
    settings = Settings()
    provider = make_provider(
        settings.llm_provider, api_key=settings.llm_api_key, model=settings.llm_model,
        base_url=settings.llm_base_url, max_tokens=settings.llm_max_output_tokens,
        default_model_anthropic=settings.llm_default_model_anthropic,
        default_model_openai=settings.llm_default_model_openai,
        default_model_local=settings.llm_default_model_local,
        local_base_url=settings.llm_local_base_url)
    if settings.guardrail_provider != "mock":
        _log.info(
            "GUARDRAIL_PROVIDER=%r: real L2 guardrail active; L2 cost metered under budget %.2f USD/mo",
            settings.guardrail_provider, settings.guardrail_monthly_budget_usd)
        if not settings.guardrail_api_key:
            _log.warning(
                "GUARDRAIL_API_KEY not set -> L2 falls back to LLM_API_KEY; set it explicitly "
                "to isolate L2 billing and avoid silent failures if the L1 key rotates")
    guardrail = make_guardrail(
        settings.guardrail_provider, api_key=settings.guardrail_api_key or settings.llm_api_key,
        model=settings.guardrail_model, base_url=settings.guardrail_base_url,
        max_tokens=settings.guardrail_max_output_tokens,
        default_model_openai=settings.guardrail_default_model_openai,
        local_base_url=settings.llm_local_base_url)
    classifier = Classifier(
        provider, guardrail, model=settings.llm_model,
        confidence_threshold=settings.llm_confidence_threshold,
        retries=settings.llm_retries, cache_max=settings.llm_cache_max)
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    await db.connect()
    _log.info("MCP server ready (provider=%s)", settings.llm_provider)
    try:
        yield AppCtx(db, classifier, settings)
    finally:
        await db.close()


mcp = FastMCP("ems-device-service", lifespan=_lifespan, stateless_http=True, json_response=True)


def _caller_ip(ctx: Context) -> str:
    """Best-effort caller IP for the audit log. Behind the docker-proxy host mapping this is
    typically the bridge gateway IP, not the real client (see M-2 note) — still the connecting
    peer, which is what §8.2 caller_ip records."""
    try:
        req = ctx.request_context.request
        return req.client.host if req is not None and req.client else "unknown"
    except Exception:  # noqa: BLE001 — audit must never break the tool call
        return "unknown"


def _audit_call(tool: str, device_id: str, status: str, t0: float, ip: str, extra: str = "") -> None:
    # §8.2 per-tool-call structured audit log: tool_name / caller_ip / device_id / result_status
    # / latency_ms / args_summary.
    _audit.info("mcp_tool_call tool=%s caller_ip=%s device=%s status=%s latency_ms=%d %s",
                tool, ip, device_id, status, int((time.monotonic() - t0) * 1000), extra)


async def _run_tool(tool: str, device_id: str, ctx: Context, coro):
    """Run a tool body, audit it, and ensure the CLIENT only ever sees a safe message: a
    ToolError carries a stable code + a message built from client-supplied values only; any
    UNEXPECTED exception (DB error, bug, ...) is logged in full but surfaced to the MCP client
    as a generic 'internal error' so no internal/DB detail leaks across the transport."""
    t0, ip = time.monotonic(), _caller_ip(ctx)
    try:
        result = await coro
    except mcp_tools.ToolError as exc:
        _audit_call(tool, device_id, exc.code, t0, ip)
        raise
    except Exception:  # noqa: BLE001 — never leak internals to the client
        _log.exception("mcp_tool_internal_error tool=%s device=%s", tool, device_id)
        _audit_call(tool, device_id, "internal_error", t0, ip)
        raise mcp_tools.ToolError("internal_error", "internal error") from None
    _audit_call(tool, device_id, "ok", t0, ip)
    return result


@mcp.tool()
async def list_low_confidence_candidates(ctx: Context, limit: int = 20) -> list[dict]:
    """List candidate devices with ai_confidence <= 0.9 as human-review digests (§8.2)."""
    app: AppCtx = ctx.request_context.lifespan_context
    return await _run_tool("list_low_confidence_candidates", "-", ctx,
                           mcp_tools.list_low_confidence_candidates(app.db, limit=limit))


@mcp.tool()
async def get_device_digest(ctx: Context, device_id: str) -> dict:
    """Get one device's human-review digest (§8.2)."""
    app: AppCtx = ctx.request_context.lifespan_context
    return await _run_tool("get_device_digest", device_id, ctx,
                           mcp_tools.get_device_digest(app.db, device_id=device_id))


@mcp.tool()
async def classify_with_context(ctx: Context, device_id: str, hint: str) -> dict:
    """Re-classify a CANDIDATE device with a human hint — fresh LLM call, budget-gated (§8.2)."""
    app: AppCtx = ctx.request_context.lifespan_context
    return await _run_tool("classify_with_context", device_id, ctx,
                           mcp_tools.classify_with_context(
                               app.db, app.classifier, app.settings, device_id=device_id, hint=hint))


class AuthRateLimitMiddleware:
    """ASGI middleware: X-API-Key=AI auth + per-IP 60/min rate limit (§8.2). Forwards non-HTTP
    scopes (lifespan/websocket) untouched so the inner MCP app's session manager still starts.

    Trade-offs (documented; accepted for this single-AI-client loopback deployment):
      - Rate limit (M-2): behind the docker-proxy host mapping all callers share the bridge
        gateway IP, so the per-IP limit is effectively GLOBAL (60/min total). No trusted proxy
        sets X-Forwarded-For here, so we do not read it. Revisit (ADR) if multi-client.
      - Container bind (L-1): uvicorn binds 0.0.0.0 IN-container so the host loopback port
        mapping (127.0.0.1:8766) can reach it; --host 127.0.0.1 in-container would break that
        mapping. Host exposure stays loopback-only; X-API-Key is the access gate (same as kc-mcp).
      - Key rotation (L-3): the AI key is read once at build_app(); rotating AI_API_KEY needs a
        `docker compose restart device-service-mcp`."""

    def __init__(self, app, ai_key: str, rate_limit_per_min: int = RATE_LIMIT_PER_MIN):
        self._app = app
        self._ai_key = ai_key
        self._limit = rate_limit_per_min
        self._hits: dict[str, deque] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        # unauthenticated liveness probe for the container healthcheck (no secrets, no DB touch)
        if scope.get("path") == "/healthz":
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        request = Request(scope, receive)
        # auth: timing-safe compare (hmac.compare_digest); empty configured key -> deny all
        # (fail-closed, so an unconfigured AI_API_KEY can never leave the MCP open).
        presented = request.headers.get("x-api-key", "")
        if not self._ai_key or not hmac.compare_digest(presented, self._ai_key):
            await JSONResponse({"error": "invalid or missing X-API-Key"}, status_code=401)(scope, receive, send)
            return
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        dq = self._hits.setdefault(ip, deque())
        while dq and now - dq[0] >= 60.0:
            dq.popleft()
        if len(dq) >= self._limit:
            _log.warning("mcp_rate_limited ip=%s", ip)
            await JSONResponse({"error": "rate limit exceeded: 60/min per IP"}, status_code=429)(scope, receive, send)
            return
        dq.append(now)
        await self._app(scope, receive, send)


def build_app():
    """ASGI app for uvicorn: the MCP Streamable-HTTP app wrapped with auth + rate limit."""
    ai_key = Settings().ai_api_key
    return AuthRateLimitMiddleware(mcp.streamable_http_app(), ai_key)


app = build_app()
