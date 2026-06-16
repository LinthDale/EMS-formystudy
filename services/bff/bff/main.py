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
from contextlib import asynccontextmanager
from typing import Callable

import httpx
from fastapi import FastAPI

from .auth_providers import build_auth_provider
from .config import Settings
from .credentials import parse_auth_users
from .routes import auth, device_measurements, devices, health, measurements
from .security import OriginCSRFMiddleware
from .sessions import InMemorySessionStore, SessionManager, run_sweep_loop


def create_app(
    settings: Settings | None = None,
    *,
    upstream_transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    logging.basicConfig(level=settings.log_level.upper())

    users = parse_auth_users(settings.auth_users)  # fail fast on malformed table
    if not users and settings.auth_mode == "local":
        logging.getLogger("bff").warning(
            "BFF_AUTH_USERS is empty - no local login possible (fail closed)"
        )
    # Select the auth provider by config (ADR-024); fail fast on unknown mode.
    auth_provider = build_auth_provider(settings, users)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient(
            timeout=settings.upstream_timeout_s, transport=upstream_transport
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
            await app.state.http.aclose()

    app = FastAPI(
        title="EMS BFF",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.users = users
    app.state.auth_provider = auth_provider
    app.state.session_manager = SessionManager(InMemorySessionStore(), settings, clock)

    app.add_middleware(OriginCSRFMiddleware, allowed_origins=settings.allowed_origins)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(devices.router)
    app.include_router(device_measurements.router)  # per-device facade (ADR-025)
    app.include_router(measurements.router)          # legacy /api/measurements/{domain}
    return app


app = create_app()
