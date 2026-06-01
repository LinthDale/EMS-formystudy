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
from .llm.factory import make_provider
from .llm.guardrail import MockGuardrail
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
    provider = make_provider(
        settings.llm_provider, api_key=settings.llm_api_key,
        model=settings.llm_model, base_url=settings.llm_base_url,
    )
    app.state.provider = provider
    app.state.classifier = Classifier(provider, MockGuardrail(), model=settings.llm_model)
    db = Database(
        host=settings.db_host, port=settings.db_port, name=settings.db_name,
        ai_password=settings.db_ai_password, ops_password=settings.db_ops_password,
    )
    await db.connect()
    app.state.db = db

    sub_task = None
    if settings.mqtt_enabled:
        sub_task = asyncio.create_task(run_subscriber(db, app.state.classifier, settings))
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