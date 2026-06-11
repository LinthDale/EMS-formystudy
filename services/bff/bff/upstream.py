"""Upstream forwarding across the BFF trust boundary.

Rules enforced here (PRD-0005 §9):
- only an explicit header set crosses upstream — browser cookies / headers never
  do, and the X-API-Key is injected here, server-side, per validated role
- key material never appears in client responses, error bodies, or logs
- upstream 401/403 means the BFF's own channel key is misconfigured -> 502
  (never relay upstream auth detail to the browser)
- network failures map to a generic 502 without internal topology
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

_log = logging.getLogger("bff.upstream")

_PASSTHROUGH_ERROR_STATUSES = frozenset({400, 404, 409, 422, 429})


async def forward(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    api_key: str | None = None,
    json_body: dict | None = None,
) -> Response:
    headers = {"Accept": "application/json"}
    if api_key is not None:
        headers["X-API-Key"] = api_key  # exists only on this hop, never client-side
    try:
        upstream = await client.request(
            method, url, params=params, headers=headers, json=json_body
        )
    except httpx.HTTPError as exc:
        # log the class only — request/URL details could carry sensitive params
        _log.error("upstream request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="upstream unavailable") from exc

    if upstream.status_code in (401, 403):
        # the BFF chose the key; an upstream auth failure is OUR misconfig
        _log.error("upstream rejected the channel key (HTTP %d)", upstream.status_code)
        raise HTTPException(status_code=502, detail="upstream auth misconfigured")
    if upstream.status_code >= 500:
        _log.error("upstream server error (HTTP %d)", upstream.status_code)
        raise HTTPException(status_code=502, detail="upstream error")

    if upstream.status_code in _PASSTHROUGH_ERROR_STATUSES or upstream.is_success:
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )
    _log.warning("unexpected upstream status %d mapped to 502", upstream.status_code)
    raise HTTPException(status_code=502, detail="unexpected upstream response")
