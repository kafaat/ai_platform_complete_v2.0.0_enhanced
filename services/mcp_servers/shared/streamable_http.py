"""Stateless MCP 2025-06-18 HTTP adapter over the authenticated REST handlers.

JSON responses are a supported Streamable HTTP mode; this adapter does not offer
server-initiated SSE, resumability, sessions, or automatic tool-call retries.
Protocol: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
Lifecycle: https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, Request, Response
from starlette.responses import JSONResponse

from .oauth_middleware import require_scope

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = "2025-06-18"
MAX_REQUEST_BYTES = 64 * 1024


def _error(req_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}


def _reject_nonfinite(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _origin(value: str) -> str:
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid MCP origin")
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Invalid MCP origin")
    # Exact configured authority, never an origin inferred from untrusted Host.
    return f"{parts.scheme}://{parts.netloc}"


def _accepted_types(value: str) -> set[str]:
    accepted = set()
    for item in value.split(","):
        media_type, *parameters = [part.strip() for part in item.split(";")]
        quality = 1.0
        for parameter in parameters:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
        if 0 < quality <= 1:
            accepted.add(media_type.lower())
    return accepted


class StreamableHTTPTransport:
    """Preserve caller identity and delegate tools to their existing scope guards.

    ``allowed_tools`` is an optional explicit export allowlist, enforced on both
    discovery and calls. It is not a substitute for the inner handler's scopes.
    JSON-RPC IDs correlate replies; they are deliberately not idempotency keys.
    """

    def __init__(
        self,
        app,
        path: str = "/mcp/v1/stream",
        *,
        required_scope: str,
        allowed_tools: frozenset[str] | None = None,
        timeout_seconds: float = 30.0,
    ):
        self.app = app
        self.path = path
        self.allowed_tools = allowed_tools
        self.timeout_seconds = timeout_seconds
        self._authorize = require_scope(required_scope)
        self._allowed_origins = frozenset(
            _origin(value.strip())
            for value in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        )
        self._register_routes()

    def _validate_origin(self, request: Request) -> None:
        supplied = request.headers.get("origin")
        if supplied is None:
            return  # Native/server-to-server clients do not send Origin.
        try:
            allowed = _origin(supplied) in self._allowed_origins
        except ValueError:
            allowed = False
        if not allowed:
            raise HTTPException(403, "Origin not allowed")

    @staticmethod
    async def _read_body(request: Request) -> Any:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_REQUEST_BYTES:
                raise HTTPException(413, "MCP request too large")
            data.extend(chunk)
        return json.loads(
            data.decode("utf-8"), parse_constant=_reject_nonfinite, parse_float=_finite_float
        )

    def _register_routes(self) -> None:
        @self.app.get(self.path)
        @self.app.delete(self.path)
        async def no_stream(request: Request, user: dict = Depends(self._authorize)):
            self._validate_origin(request)
            if request.headers.get("mcp-protocol-version", PROTOCOL_VERSION) != PROTOCOL_VERSION:
                raise HTTPException(400, "Unsupported MCP-Protocol-Version")
            return Response(status_code=405, headers={"Allow": "POST"})

        @self.app.post(self.path)
        async def endpoint(request: Request, user: dict = Depends(self._authorize)):
            # Request-only body: FastAPI authenticates before any JSON is decoded.
            self._validate_origin(request)
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                raise HTTPException(415, "Content-Type must be application/json")
            accepted = _accepted_types(request.headers.get("accept", ""))
            if not {"application/json", "text/event-stream"}.issubset(accepted):
                raise HTTPException(
                    406, "Accept must include application/json and text/event-stream"
                )
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    body = await self._read_body(request)
            except TimeoutError:
                return JSONResponse(_error(None, -32000, "Request timeout"), status_code=408)
            except (UnicodeDecodeError, ValueError, RecursionError):
                return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
            if (
                not isinstance(body, dict)
                or body.get("jsonrpc") != "2.0"
                or not isinstance(body.get("method"), str)
                or not body["method"]
                or ("id" in body and type(body["id"]) not in {str, int})
            ):
                return JSONResponse(_error(None, -32600, "Invalid Request"), status_code=400)
            method = body["method"]
            version = request.headers.get("mcp-protocol-version")
            if (version is not None and version != PROTOCOL_VERSION) or (
                method != "initialize" and version is None
            ):
                raise HTTPException(400, "Unsupported or missing MCP-Protocol-Version")
            if not isinstance(body.get("params", {}), dict):
                return JSONResponse(
                    _error(body.get("id"), -32602, "Invalid params"), status_code=400
                )
            if "id" not in body:
                # Never execute tools/call without an ID. Notifications have no reply.
                if not method.startswith("notifications/"):
                    raise HTTPException(400, "Request ID required")
                return Response(status_code=202)
            if method.startswith("notifications/"):
                return JSONResponse(_error(body["id"], -32600, "Invalid Request"), status_code=400)
            result = await self._process_request(
                body, request.headers.get("authorization"), tenant_id=user["tenant_id"]
            )
            return JSONResponse(
                result,
                headers={"Cache-Control": "no-store", "MCP-Protocol-Version": PROTOCOL_VERSION},
            )

    async def _process_request(
        self,
        body: dict[str, Any],
        authorization: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id")
        if method == "initialize":
            client = params.get("clientInfo")
            if (
                not isinstance(params.get("protocolVersion"), str)
                or not params["protocolVersion"]
                or not isinstance(params.get("capabilities"), dict)
                or not isinstance(client, dict)
                or not all(
                    isinstance(client.get(key), str) and client[key] for key in ("name", "version")
                )
            ):
                return _error(req_id, -32602, "Invalid initialize params")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.app.title, "version": self.app.version},
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "result": {}, "id": req_id}
        if method not in {"tools/list", "tools/call"}:
            return _error(req_id, -32601, "Method not found")
        if method == "tools/list" and "cursor" in params:
            return _error(req_id, -32602, "This server returns one complete tool page")
        if method == "tools/call":
            name = params.get("name")
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(params.get("arguments", {}), dict)
            ):
                return _error(req_id, -32602, "Invalid tool arguments")
            if self.allowed_tools is not None and name not in self.allowed_tools:
                return _error(req_id, -32602, "Unknown or unavailable tool")
            arguments = dict(params.get("arguments", {}))
            if tenant_id is not None:
                if "tenant_id" in arguments and arguments["tenant_id"] != tenant_id:
                    return _error(req_id, -32602, "Tool tenant does not match caller")
                arguments["tenant_id"] = tenant_id
            # No body-selected credentials, upstream URL, or synthetic request_id.
            params = {"name": name, "arguments": arguments}

        headers = {"Authorization": authorization} if authorization else {}
        try:
            # HTTPX removed AsyncClient(app=...) in 0.28; use its supported API.
            # https://www.python-httpx.org/advanced/transports/#asgi-transport
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://mcp-internal", trust_env=False
                ) as client:
                    if method == "tools/list":
                        response = await client.get("/v1/mcp/tools", headers=headers)
                    else:
                        response = await client.post(
                            "/v1/mcp/tools/call", json=params, headers=headers
                        )
            if response.status_code >= 400:
                code = -32602 if response.status_code in {400, 404, 422} else -32603
                return _error(req_id, code, "Tool request failed")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid inner response")
            if method == "tools/list":
                listed = payload.get("tools")
                if not isinstance(listed, list) or any(
                    not isinstance(item, dict) for item in listed
                ):
                    raise ValueError("Invalid tool discovery")
                tools = []
                for item in listed:
                    if not isinstance(item.get("name"), str) or not item["name"]:
                        raise ValueError("Invalid tool name")
                    if self.allowed_tools is not None and item["name"] not in self.allowed_tools:
                        continue
                    tools.append({"inputSchema": {"type": "object"}, **item})
                payload = {"tools": tools}
            elif "content" not in payload:
                # REST-only context servers return JSON objects; preserve provenance.
                payload = {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                    "structuredContent": payload,
                    "isError": bool(payload.get("error")),
                }
            elif (
                not isinstance(payload["content"], list)
                or type(payload.get("isError", False)) is not bool
            ):
                raise ValueError("Invalid tool result")
            json.dumps(payload, allow_nan=False)  # Reject non-JSON upstream numbers.
            return {"jsonrpc": "2.0", "result": payload, "id": req_id}
        except TimeoutError:
            return _error(req_id, -32000, "Request timeout")
        except Exception:
            # Exception text can contain credentials, internal URLs, or vendor data.
            logger.warning("streamable_http: inner dispatch failed")
            return _error(req_id, -32603, "Internal error")
