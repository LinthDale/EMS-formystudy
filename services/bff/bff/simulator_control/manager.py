"""Fixed adapters; no user-defined URLs, retries, shell or Docker privileges."""
from __future__ import annotations

import asyncio
import time
from pydantic import ValidationError
import httpx

from .audit import Audit, Conflict
from .contracts import Command, MODELS, Receipt, Snapshot, command_hash, validate_changes

HOP_TIMEOUT_S = 3.0

TARGETS = {
    "sim-001": "http://simulator:9000",
    "plc-001": "http://kc-modbus-sim:9000",
    "sensor-001": "http://kc-mqtt-sim:9000",
    "delta-sim-001": "http://delta-simulator:9000",
}


class InvalidTarget(Exception):
    pass


class Controller:
    def __init__(self, audit: Audit, client: httpx.AsyncClient):
        self.audit, self.client = audit, client
        self.locks = {sim: asyncio.Lock() for sim in TARGETS}

    async def _request(self, method: str, simulator_id: str, path: str,
                       payload: dict | None = None) -> httpx.Response:
        async with asyncio.timeout(HOP_TIMEOUT_S):
            async with self.client.stream(
                method, TARGETS[simulator_id] + path, json=payload,
                headers={"Accept-Encoding": "identity"},
            ) as response:
                # Control agents never compress JSON. Reject encoded bodies before
                # decompression, and never trust Content-Length as the sole bound.
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise InvalidTarget()
                length = response.headers.get("content-length")
                if length is not None and not 0 <= int(length) <= 16384:
                    raise InvalidTarget()
                content = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    content.extend(chunk)
                    if len(content) > 16384:
                        raise InvalidTarget()
                return httpx.Response(response.status_code, content=bytes(content),
                                      request=response.request)

    async def _get(self, simulator_id: str, path: str) -> httpx.Response:
        return await self._request("GET", simulator_id, path)

    async def snapshot(self, simulator_id: str) -> dict:
        response = await self._get(simulator_id, "/state")
        response.raise_for_status()
        state = Snapshot.model_validate(response.json()).model_dump(mode="json")
        if state["simulator_id"] != simulator_id:
            raise InvalidTarget()
        return state

    async def describe(self, simulator_id: str) -> dict:
        result = {"simulator_id": simulator_id,
                  "capabilities": {"configure": MODELS[simulator_id].model_json_schema()},
                  "blocked": self.audit.blocked(simulator_id)}
        try:
            return {**result, "available": True, **await self.snapshot(simulator_id)}
        except (httpx.HTTPError, ValueError, InvalidTarget, TimeoutError):
            return {**result, "available": False, "error": "target_unavailable"}

    def _receipt(self, simulator_id: str, body: Command, raw: dict,
                 before: dict | None = None) -> dict:
        receipt = Receipt.model_validate(raw).model_dump(mode="json")
        expected_instance = str(body.expected_instance_id)
        actual_before, after = receipt["before"], receipt["after"]
        expected_after = {**actual_before, "revision": body.expected_revision + 1,
                          "settings": {**actual_before["settings"], **body.changes}}
        if (receipt["request_id"] != str(body.request_id)
                or receipt["command_hash"] != command_hash(simulator_id, body)
                or receipt["changes"] != body.changes
                or actual_before["simulator_id"] != simulator_id
                or actual_before["instance_id"] != expected_instance
                or actual_before["revision"] != body.expected_revision
                or after != expected_after
                or (before is not None and actual_before != before)):
            raise InvalidTarget()
        return {"before": actual_before, "after": after, "error": None, "resolved": True}

    async def execute(self, actor: str, simulator_id: str, body: Command) -> dict:
        body = body.model_copy(update={"changes": validate_changes(simulator_id, body.changes)})
        request_id = str(body.request_id)
        if self.audit.get(request_id):
            return self.audit.reserve(actor, simulator_id, body)
        lock = self.locks[simulator_id]
        if lock.locked() or self.audit.blocked(simulator_id):
            raise Conflict("simulator busy or unresolved operation; reconcile first")
        async with lock:
            self.audit.reserve(actor, simulator_id, body)  # durable BEFORE any side effect
            before = None
            dispatched = False
            try:
                before = await self.snapshot(simulator_id)
                if (before["instance_id"] != str(body.expected_instance_id)
                        or before["revision"] != body.expected_revision):
                    return self.audit.append(request_id, "failed",
                                             {"before": before, "error": "state_conflict",
                                              "resolved": True})
                dispatched = True
                response = await self._request(
                    "POST", simulator_id, "/apply",
                    payload={**body.model_dump(mode="json"), "deadline": time.time() + 10},
                )
                if response.status_code in (400, 401, 403, 409, 410, 422, 429):
                    return self.audit.append(request_id, "failed",
                                             {"before": before, "error": "target_rejected",
                                              "resolved": True})
                response.raise_for_status()
                proof = self._receipt(simulator_id, body, response.json(), before)
            except asyncio.CancelledError:
                self.audit.append(request_id, "outcome_unknown" if dispatched else "failed",
                                  {"before": before, "error": "controller_interrupted",
                                   "resolved": not dispatched})
                raise
            except (httpx.HTTPError, ValueError, InvalidTarget, TimeoutError):
                return self.audit.append(
                    request_id, "outcome_unknown" if dispatched else "failed",
                    {"before": before, "error": "transport_or_receipt_error" if dispatched
                     else "target_unavailable", "resolved": not dispatched})
            return self.audit.append(request_id, "succeeded", proof)

    async def reconcile(self, request_id: str, actor: str, reason: str) -> dict | None:
        op = self.audit.get(request_id)
        if op is None or op["status"] not in ("pending", "outcome_unknown") or op["resolved"]:
            return op
        simulator_id = op["simulator_id"]
        lock = self.locks[simulator_id]
        if lock.locked():
            raise Conflict("command still running")
        async with lock:
            body = Command(**{k: op[k] for k in Command.model_fields})
            evidence = {"reconciled_by": actor, "reconcile_reason": reason}
            try:
                state = await self.snapshot(simulator_id)
                if state["instance_id"] != str(body.expected_instance_id):
                    # One fixed container endpoint, never load-balanced: the old instance
                    # is retired. Preserve uncertainty but permit commands to the new one.
                    return self.audit.append(
                        request_id, "outcome_unknown",
                        {**evidence, "resolved": True, "error": "instance_restarted",
                         "observed_instance_id": state["instance_id"]})
                response = await self._get(simulator_id, "/receipts/" + request_id)
                if response.status_code == 404:
                    return op  # Absence is NOT evidence that application never happened.
                response.raise_for_status()
                proof = self._receipt(simulator_id, body, response.json(), op["before"])
            except (httpx.HTTPError, ValueError, InvalidTarget, TimeoutError):
                return op
            return self.audit.append(request_id, "succeeded", {**proof, **evidence})
