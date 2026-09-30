"""Bound request bodies before JSON parsing, including chunked requests."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, prefix: str, limit: int = 4096):
        self.app, self.prefix, self.limit = app, prefix, limit

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or not scope["path"].startswith(self.prefix)
                or scope["method"] not in ("POST", "PUT", "PATCH")):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"detail": "body too large"}, status_code=413)(
                    scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)
