"""Internal typed control API; no publicly mapped port or process operations."""
from __future__ import annotations

import hmac
import time
from typing import Callable
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from .body_limit import BodyLimitMiddleware
from .contracts import (ApplyCommand, Receipt, Snapshot, command_hash, validate_changes,
                        validate_settings)


class ControlAgent:
    def __init__(self, simulator_id: str, read: Callable, apply: Callable, token: str,
                 clock: Callable = time.time):
        self.simulator_id, self.read, self.apply = simulator_id, read, apply
        self.token, self.clock = token, clock
        self.instance_id = str(uuid4())
        self.revision = 0
        self.receipts: dict[str, dict] = {}
        self.max_receipts = 4096
        self.faulted = False

    def snapshot(self) -> dict:
        return Snapshot(simulator_id=self.simulator_id, instance_id=self.instance_id,
                        revision=self.revision, settings=self.read()).model_dump(mode="json")

    def execute(self, body: ApplyCommand) -> dict:
        # Called only on the ASGI event-loop thread. No await occurs across
        # CAS, apply, revision and receipt: a single atomic critical section.
        changes = validate_changes(self.simulator_id, body.changes)
        body = body.model_copy(update={"changes": changes})
        request_id = str(body.request_id)
        digest = command_hash(self.simulator_id, body)
        if request_id in self.receipts:
            receipt = self.receipts[request_id]
            if receipt["command_hash"] != digest:
                raise HTTPException(409, "request_id conflict")
            return receipt
        if self.faulted:
            raise HTTPException(503, "target requires restart")
        if not self.clock() <= body.deadline <= self.clock() + 15:
            raise HTTPException(410, "command deadline invalid or expired")
        if (str(body.expected_instance_id) != self.instance_id
                or body.expected_revision != self.revision):
            raise HTTPException(409, "state conflict")
        if len(self.receipts) >= self.max_receipts:
            raise HTTPException(429, "receipt capacity reached; restart target")
        before = self.snapshot()
        desired = validate_settings(self.simulator_id, {**before["settings"], **changes})
        try:
            self.apply(changes)
            actual = validate_settings(self.simulator_id, self.read())
            if actual != desired:
                raise RuntimeError("adapter did not apply the complete change")
            self.revision += 1
            receipt = Receipt(request_id=body.request_id, command_hash=digest, changes=changes,
                              before=before, after=self.snapshot()).model_dump(mode="json")
            self.receipts[request_id] = receipt
            return receipt
        except Exception:
            # A buggy adapter may have partially applied. Never label this a definite
            # rejection or allow more commands to race it; BFF records unknown.
            self.faulted = True
            raise HTTPException(503, "target result unknown; restart required") from None


def make_app(agent: ControlAgent, lifespan=None) -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimitMiddleware, prefix="/")

    async def authorize(request: Request):
        if len(agent.token) < 32:
            raise HTTPException(503, "control not configured")
        if not hmac.compare_digest(request.headers.get("Authorization", ""),
                                   "Bearer " + agent.token):
            raise HTTPException(401, "unauthorized")
        if request.query_params:
            raise HTTPException(422, "query parameters not supported")

    @app.get("/health")
    async def health():
        return {"status": "ok", "control_configured": len(agent.token) >= 32,
                "control_faulted": agent.faulted}

    @app.get("/state", dependencies=[Depends(authorize)])
    async def state():
        return agent.snapshot()

    @app.get("/receipts/{request_id}", dependencies=[Depends(authorize)])
    async def receipt(request_id: UUID):
        if str(request_id) not in agent.receipts:
            raise HTTPException(404, "receipt not found")
        return agent.receipts[str(request_id)]

    @app.post("/apply", dependencies=[Depends(authorize)])
    async def apply(body: ApplyCommand):
        try:
            return agent.execute(body)
        except ValueError:
            raise HTTPException(422, "invalid simulator changes") from None

    return app
