"""FastAPI app for device-service (PRD-0003). CRUD/lifecycle + healthz + (1.3) MQTT auto-discovery."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .classifier import Classifier
from .config import Settings
from .db import Database
from .llm.factory import make_guardrail, make_provider
from .mqtt_subscriber import run_subscriber
from .routes import devices, health, signals

_log = logging.getLogger("device_service")


async def db_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map uncaught asyncpg errors to safe status codes (no stack-trace / detail leak)."""
    if isinstance(exc, asyncpg.UniqueViolationError):
        code, detail = 409, "conflict"
    elif isinstance(exc, (asyncpg.CheckViolationError, asyncpg.NotNullViolationError, asyncpg.DataError)):
        code, detail = 422, "invalid value for a constrained field"
    else:
        code, detail = 500, "internal database error"
    _log.warning("db error -> %d: %s", code, type(exc).__name__)
    return JSONResponse(status_code=code, content={"detail": detail})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = getattr(app.state, "settings", None) or Settings()
    app.state.settings = settings
    if not settings.audit_hash_salt:
        # M-2: don't hard-fail boot (CRUD / human-review still work), but make the gap loud —
        # /ai-feedback fail-closes with 503 until AUDIT_HASH_SALT is set (§7.3a / FR-345).
        _log.warning("AUDIT_HASH_SALT is empty: /ai-feedback will return 503 until it is set")
    provider = make_provider(
        settings.llm_provider, api_key=settings.llm_api_key,
        model=settings.llm_model, base_url=settings.llm_base_url,
        max_tokens=settings.llm_max_output_tokens,
        default_model_anthropic=settings.llm_default_model_anthropic,
        default_model_openai=settings.llm_default_model_openai,
        default_model_local=settings.llm_default_model_local,
        local_base_url=settings.llm_local_base_url,
    )
    app.state.provider = provider
    if settings.guardrail_provider != "mock":
        # FR-340 (L2 budget metering) is a follow-up: a real guardrail's L2 token cost is
        # NOT yet capped by the budget gate. Make that explicit at boot.
        _log.warning(
            "GUARDRAIL_PROVIDER=%r: L2 guardrail uses a real model but its token cost is NOT "
            "budget-metered yet (FR-340 pending) -> L2 cost is UNCAPPED", settings.guardrail_provider)
        if not settings.guardrail_api_key:
            _log.warning(
                "GUARDRAIL_API_KEY not set -> L2 falls back to LLM_API_KEY; set it explicitly "
                "to isolate L2 billing and avoid silent failures if the L1 key rotates")
    guardrail = make_guardrail(
        settings.guardrail_provider, api_key=settings.guardrail_api_key or settings.llm_api_key,
        model=settings.guardrail_model, base_url=settings.guardrail_base_url,
        max_tokens=settings.guardrail_max_output_tokens,
        default_model_openai=settings.guardrail_default_model_openai,
        local_base_url=settings.llm_local_base_url,
    )
    app.state.classifier = Classifier(
        provider, guardrail, model=settings.llm_model,
        confidence_threshold=settings.llm_confidence_threshold,
        retries=settings.llm_retries, cache_max=settings.llm_cache_max,
    )
    db = Database(
        host=settings.db_host, port=settings.db_port, name=settings.db_name,
        ai_password=settings.db_ai_password, ops_password=settings.db_ops_password,
    )
    await db.connect()
    app.state.db = db

    sub_task = None
    if settings.mqtt_enabled:
        sub_task = asyncio.create_task(run_subscriber(db, app.state.classifier, settings))

        def _on_sub_done(task: asyncio.Task) -> None:
            if not task.cancelled() and task.exception() is not None:
                _log.error("MQTT subscriber task exited", exc_info=task.exception())

        sub_task.add_done_callback(_on_sub_done)
    try:
        yield
    finally:
        if sub_task is not None:
            sub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sub_task
        await db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="EMS device-service", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(asyncpg.PostgresError, db_error_handler)
    app.include_router(health.router)
    app.include_router(devices.router)
    app.include_router(signals.router)
    return app


app = create_app()