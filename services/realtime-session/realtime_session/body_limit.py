"""Bound raw HTTP request bodies before framework parsing or authentication.

The limit applies to bytes actually received, including chunked requests. No
request headers or content are logged. A completed body is replayed once, while
later disconnect notifications retain the original ASGI receive semantics.
"""

from __future__ import annotations

import asyncio
import json
import math


class _BodyRejected(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code


class BodyLimitMiddleware:
    def __init__(self, app, max_body_bytes: int = 4096, read_timeout: float = 5.0):
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes < 1
            or isinstance(read_timeout, bool)
            or not isinstance(read_timeout, (int, float))
            or not math.isfinite(read_timeout)
            or read_timeout <= 0
        ):
            raise ValueError("Invalid HTTP body limits")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.read_timeout = read_timeout

    @staticmethod
    async def _reject(send, status: int, code: str) -> None:
        body = json.dumps({"detail": {"error": code}}, separators=(",", ":")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"pragma", b"no-cache"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        lengths = [value for key, value in headers if key.lower() == b"content-length"]
        transfer_encoding = any(key.lower() == b"transfer-encoding" for key, _ in headers)
        if len(lengths) > 1 or (lengths and transfer_encoding):
            await self._reject(send, 400, "request_body_invalid")
            return
        declared_length = None
        if lengths:
            raw_length = lengths[0]
            # Digits only, no signs, whitespace, comma lists or gigantic integers.
            if not raw_length or not raw_length.isdigit() or len(raw_length) > 20:
                await self._reject(send, 400, "request_body_invalid")
                return
            declared_length = int(raw_length)
            if declared_length > self.max_body_bytes:
                await self._reject(send, 413, "request_body_too_large")
                return

        chunks = []
        size = 0
        try:
            async with asyncio.timeout(self.read_timeout):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return  # The client has gone; never attempt a response.
                    if message["type"] != "http.request":
                        raise _BodyRejected(400, "request_body_invalid")
                    chunk = message.get("body", b"")
                    if not isinstance(chunk, bytes):
                        raise _BodyRejected(400, "request_body_invalid")
                    size += len(chunk)
                    if size > self.max_body_bytes:
                        raise _BodyRejected(413, "request_body_too_large")
                    if chunk:
                        chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
                    # Even an immediately-ready stream of empty chunks must let
                    # the total deadline run; actual network receives normally yield.
                    await asyncio.sleep(0)
        except _BodyRejected as exc:
            # Error writes occur outside the read deadline, avoiding a second
            # response start if a slow send outlives the body-read timeout.
            await self._reject(send, exc.status, exc.code)
            return
        except TimeoutError:
            await self._reject(send, 408, "request_body_timeout")
            return

        if declared_length is not None and declared_length != size:
            await self._reject(send, 400, "request_body_invalid")
            return
        body = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
