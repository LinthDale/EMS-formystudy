"""EMS BFF app factory (PRD-0005 §9 GATE-1 security baseline).

The BFF is the ONLY channel between the SPA and the backends:
browser --(HttpOnly Secure SameSite=Strict cookie)--> BFF
BFF --(X-API-Key, role-mapped, server-side only)--> device-service :8002
BFF --(no key, anonymous whitelist views)---------> PostgREST :3001

Test seams (and nothing else) are injectable: settings, upstream transport,
clock. Docs/openapi endpoints are disabled — the BFF is a browser-facing
facade, not a discoverable API surface.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Callable

import httpx
from fastapi import FastAPI

from .accounts import AccountAuth, AccountRepository, PostgresAccounts
from .config import Settings
from .oidc import OidcClient
from .oidc_state import InMemoryOidcStateStore, OidcStateManager
from .demo_alarms import DemoAlarms, protect_telegram_logs
from .routes import alarms, auth, device_measurements, devices, health, history, measurements, oidc
from .routes import simulators
from .simulator_control.audit import Audit
from .simulator_control.manager import Controller
from .simulator_control.body_limit import BodyLimitMiddleware
from .security import OriginCSRFMiddleware
from .sessions import InMemorySessionStore, SessionManager, run_sweep_loop


def create_app(
    settings: Settings | None = None,
    *,
    upstream_transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    telegram_transport: httpx.AsyncBaseTransport | None = None,
    oidc_client: "OidcClient | None" = None,
    simulator_transport: httpx.AsyncBaseTransport | None = None,
    account_repository: AccountRepository | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    logging.basicConfig(level=settings.log_level.upper())
    protect_telegram_logs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as resources:
            if settings.auth_mode == "local":
                repository = account_repository
                if repository is None:
                    dsn = settings.auth_db_dsn.get_secret_value()
                    if not dsn:
                        raise RuntimeError("BFF_AUTH_DB_DSN is required for local authentication")
                    try:
                        repository = await PostgresAccounts.connect(dsn)
                    except Exception:
                        raise RuntimeError("account database unavailable at startup") from None
                    resources.push_async_callback(repository.close)
                app.state.account_auth = AccountAuth(repository)
            app.state.http = httpx.AsyncClient(
                timeout=settings.upstream_timeout_s, transport=upstream_transport
            )
            resources.push_async_callback(app.state.http.aclose)
            app.state.telegram_http = httpx.AsyncClient(
                timeout=settings.telegram_timeout_s, transport=telegram_transport,
                trust_env=False, follow_redirects=False,
            )
            resources.push_async_callback(app.state.telegram_http.aclose)
            app.state.simulators = None
            simulator_http = None
            audit = None
            if settings.sim_control_enabled:
                audit = Audit(settings.sim_control_db, settings.sim_control_max_commands)
                resources.callback(audit.close)
                simulator_http = httpx.AsyncClient(
                    timeout=3.0, transport=simulator_transport, trust_env=False,
                    follow_redirects=False,
                    headers={"Authorization": "Bearer " + settings.sim_control_token.get_secret_value()},
                )
                resources.push_async_callback(simulator_http.aclose)
                app.state.simulators = Controller(audit, simulator_http)
            # OIDC (ADR-024): discover the IdP + cache JWKS once at startup so the
            # login/callback round-trip is fast and discovery failures surface early.
            # Discovery needs the async http client, so it happens here (not in the
            # factory body). Tests inject app.state.oidc_client directly to bypass a
            # live IdP — only auto-discover when oidc mode is selected and not preset.
            if settings.auth_mode == "oidc" and getattr(app.state, "oidc_client", None) is None:
                app.state.oidc_client = await OidcClient.discover(
                    settings, app.state.http, clock=clock
                )
            # Background janitor for the in-memory session store (code-review MED):
            # reap expired-but-never-re-accessed sessions on a fixed interval.
            sweep_task = asyncio.create_task(
                run_sweep_loop(
                    app.state.session_manager, settings.session_sweep_interval_s
                )
            )
            try:
                yield
            finally:
                sweep_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sweep_task  # await clean cancellation before teardown


    app = FastAPI(
        title="EMS BFF",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.demo_alarms = DemoAlarms(settings, clock)
    app.state.account_auth = None
    app.state.session_manager = SessionManager(InMemorySessionStore(), settings, clock)
    # OIDC transient login state (PKCE verifier / state / nonce), short-TTL,
    # server-side (ADR-024). Present regardless of mode so the route can rely on
    # it; only exercised in oidc mode. A pre-built client (tests) skips discovery.
    app.state.oidc_state_manager = OidcStateManager(
        InMemoryOidcStateStore(), settings.oidc_state_ttl_s, clock
    )
    app.state.oidc_client = oidc_client  # may be None -> lifespan discovers it

    app.state.simulators = None
    app.add_middleware(BodyLimitMiddleware, prefix="/api/simulators")
    app.add_middleware(OriginCSRFMiddleware, allowed_origins=settings.allowed_origins)

    app.include_router(simulators.router)
    app.include_router(alarms.router)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(oidc.router)                  # OIDC login/callback (ADR-024)
    app.include_router(devices.router)
    app.include_router(history.router)
    app.include_router(device_measurements.router)  # per-device facade (ADR-025)
    app.include_router(measurements.router)          # legacy /api/measurements/{domain}
    return app


app = create_app()
