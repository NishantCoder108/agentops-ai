"""Reject request bodies before they are parsed.

A document is at most 1 MB of text. The extra room covers multipart framing.
"""

import json

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES = 1_000_000 + 65_536

_TOO_LARGE = {
    "error": {
        "code": "request_too_large",
        "message": "Request is too large",
        "details": {"max_bytes": MAX_REQUEST_BYTES},
    }
}


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        raw_length = Headers(scope=scope).get("content-length")
        if raw_length is not None:
            if not raw_length.isdigit() or int(raw_length) > self.max_bytes:
                await _reject(send)
                return
            await self.app(scope, receive, send)
            return

        total = 0
        buffered: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                buffered.append(message)
                continue
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _reject(send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(buffered):
                current = buffered[index]
                index += 1
                return current
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


async def _reject(send: Send) -> None:
    body = json.dumps(_TOO_LARGE).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
