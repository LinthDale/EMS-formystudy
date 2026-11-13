"""OPS-only unified simulator commands and audit queries (PRD-0022)."""
import asyncio
import sqlite3
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import Field
from ..roles import Role
from ..security import require_roles
from ..sessions import Session
from ..simulator_control.audit import Conflict, Unavailable
from ..simulator_control.contracts import Command, SimulatorId, StrictModel
from ..simulator_control.manager import TARGETS

router = APIRouter(prefix="/api/simulators", tags=["simulator control"])


def controller(request: Request):
    instance = request.app.state.simulators
    if instance is None:
        raise HTTPException(503, "simulator control is not configured")
    return instance


@contextmanager
def guarded():
    try:
        yield
    except Conflict as error:
        raise HTTPException(409, str(error)) from None
    except (Unavailable, sqlite3.Error, OSError):
        raise HTTPException(503, "audit unavailable; command not confirmed") from None
    except ValueError:
        raise HTTPException(422, "invalid simulator changes") from None


def no_query(request: Request):
    if request.query_params:
        raise HTTPException(422, "query parameters not supported")


@router.get("")
async def list_simulators(request: Request, session: Session = require_roles(Role.OPS)):
    no_query(request)
    with guarded():
        manager = controller(request)
        return {"items": await asyncio.gather(*(manager.describe(key) for key in TARGETS))}


@router.get("/operations")
async def operations(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                     before: Annotated[int | None, Query(ge=1)] = None,
                     simulator_id: SimulatorId | None = None,
                     session: Session = require_roles(Role.OPS)):
    if set(request.query_params) - {"limit", "before", "simulator_id"}:
        raise HTTPException(422, "unknown query parameter")
    with guarded():
        rows = controller(request).audit.list(limit, before, simulator_id)
        return {"items": rows, "next_before": rows[-1]["sequence"] if len(rows) == limit else None}


@router.get("/operations/{request_id}")
async def operation(request_id: UUID, request: Request,
                    session: Session = require_roles(Role.OPS)):
    no_query(request)
    with guarded():
        row = controller(request).audit.get(str(request_id))
        if row is None:
            raise HTTPException(404, "operation not found")
        return row


class ReconcileRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=200, pattern=r"\S")


@router.post("/operations/{request_id}/reconcile")
async def reconcile(request_id: UUID, body: ReconcileRequest, request: Request,
                    session: Session = require_roles(Role.OPS)):
    no_query(request)
    with guarded():
        row = await controller(request).reconcile(str(request_id), session.username, body.reason)
        if row is None:
            raise HTTPException(404, "operation not found")
        return row


@router.get("/{simulator_id}")
async def describe(simulator_id: SimulatorId, request: Request,
                   session: Session = require_roles(Role.OPS)):
    no_query(request)
    with guarded():
        return await controller(request).describe(simulator_id)


@router.post("/{simulator_id}/commands")
async def execute(simulator_id: SimulatorId, body: Command, request: Request, response: Response,
                  session: Session = require_roles(Role.OPS)):
    no_query(request)
    with guarded():
        row = await controller(request).execute(session.username, simulator_id, body)
        if row["status"] == "pending":
            response.status_code = 202
        return row
