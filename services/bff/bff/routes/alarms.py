"""PRD-0019 fixed-recipient Telegram demonstration, OPS only."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, UUID4

from ..roles import Role
from ..security import require_roles
from ..sessions import Session

router = APIRouter(prefix="/api/alarms", tags=["demo alarms"])


class DemoAlarmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID4


def no_query(request: Request) -> None:
    if request.query_params:
        raise HTTPException(422, "query parameters are not supported")


@router.get("/demo")
async def status(request: Request, session: Session = require_roles(Role.OPS)) -> dict:
    no_query(request)
    return request.app.state.demo_alarms.status()


@router.post("/demo")
async def trigger(body: DemoAlarmRequest, request: Request,
                  session: Session = require_roles(Role.OPS)) -> dict:
    no_query(request)
    return await request.app.state.demo_alarms.send(str(body.request_id), request.app.state.telegram_http)
