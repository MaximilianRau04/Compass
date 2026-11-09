"""Answer 413 once a request body grows past a limit, also for chunked uploads that send no
Content-Length. FastAPI reads a JSON body before a route's dependencies run (the bearer token of
/api/ingest/* among them), so without this an unauthenticated client could make it buffer any
amount. Caddy caps bodies at 25 MB as well, but it can only abort such an upload (502); the limit
here is lower, so the client gets a 413 first.
"""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The largest legitimate body is a Health Connect batch (app.ingestion.healthconnect.MAX_BYTES,
# 20 MiB); a little room for the JSON around it.
MAX_BODY_BYTES = 21 * 1024 * 1024


class _TooLarge(HTTPException):
    # An HTTPException, so FastAPI passes it on instead of turning it into "error parsing the body".
    def __init__(self) -> None:
        super().__init__(413, "request body is too large")


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        received = 0
        started = False

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge
            return message

        async def tracked(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except _TooLarge:
            if started:  # the route answered before reading everything; nothing left to say
                raise
            await self._refuse(scope, receive, send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"detail": "request body is too large"}, status_code=413)
        await response(scope, receive, send)
