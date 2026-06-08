"""Unit: MCP server AuthRateLimitMiddleware (no DB / no server). Drives the ASGI middleware
directly to assert auth (401), the unauthenticated /healthz bypass, valid forwarding, and the
per-IP rate limit (429)."""
import pytest

from device_service.mcp_server import AuthRateLimitMiddleware


class _Inner:
    """Dummy inner ASGI app that records calls and returns 200."""
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _drive(mw, *, path="/mcp", key=None, ip="10.0.0.1"):
    sent = []

    async def send(m):
        sent.append(m)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers = [(b"x-api-key", key.encode())] if key is not None else []
    scope = {"type": "http", "method": "POST", "path": path, "headers": headers, "client": (ip, 1)}
    await mw(scope, receive, send)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    return starts[0]["status"] if starts else None


async def test_missing_and_wrong_key_401():
    inner = _Inner()
    mw = AuthRateLimitMiddleware(inner, ai_key="secret")
    assert await _drive(mw, key=None) == 401
    assert await _drive(mw, key="nope") == 401
    assert inner.calls == 0  # never forwarded


async def test_empty_configured_key_denies_all():
    inner = _Inner()
    mw = AuthRateLimitMiddleware(inner, ai_key="")   # unconfigured -> fail-closed
    assert await _drive(mw, key="anything") == 401
    assert inner.calls == 0


async def test_healthz_bypasses_auth():
    inner = _Inner()
    mw = AuthRateLimitMiddleware(inner, ai_key="secret")
    assert await _drive(mw, path="/healthz", key=None) == 200  # no key needed
    assert inner.calls == 0  # handled by middleware, not forwarded


async def test_valid_key_forwards():
    inner = _Inner()
    mw = AuthRateLimitMiddleware(inner, ai_key="secret")
    assert await _drive(mw, key="secret") == 200
    assert inner.calls == 1


async def test_per_ip_rate_limit_429():
    inner = _Inner()
    mw = AuthRateLimitMiddleware(inner, ai_key="secret", rate_limit_per_min=1)
    assert await _drive(mw, key="secret", ip="9.9.9.9") == 200       # 1st allowed
    assert await _drive(mw, key="secret", ip="9.9.9.9") == 429       # 2nd over limit
    assert await _drive(mw, key="secret", ip="9.9.9.8") == 200       # different IP -> own bucket
    assert inner.calls == 2  # only the two allowed requests forwarded
