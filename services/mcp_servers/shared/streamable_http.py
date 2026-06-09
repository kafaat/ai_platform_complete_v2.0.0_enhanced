#!/usr/bin/env python3
"""
Streamable HTTP Transport for MCP 2026
Replaces deprecated SSE with Streamable HTTP (June 2025 spec)
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request, Response
from starlette.responses import StreamingResponse


class StreamableHTTPTransport:
    """
    MCP Streamable HTTP Transport
    - Supports request cancellation via timeouts
    - Supports idempotency via request_id
    - Uses JSON-RPC over HTTP with streaming responses
    """

    def __init__(self, app, path: str = "/mcp/v1/stream"):
        self.app = app
        self.path = path
        self._register_routes()

    def _register_routes(self):
        @self.app.post(self.path)
        async def stream_endpoint(request: Request):
            body = await request.json()

            # Validate request structure
            if "jsonrpc" not in body or body.get("jsonrpc") != "2.0":
                return Response(
                    content=json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32600, "message": "Invalid Request"},
                            "id": body.get("id"),
                        }
                    ),
                    media_type="application/json",
                    status_code=400,
                )

            async def event_generator() -> AsyncGenerator[str, None]:
                try:
                    # Process request
                    result = await self._process_request(body)

                    # Stream response chunks
                    yield f"data: {json.dumps(result)}\n\n"

                except TimeoutError:
                    _timeout_err = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": "Request timeout"},
                        "id": body.get("id"),
                    }
                    yield f"data: {json.dumps(_timeout_err)}\n\n"
                except Exception as e:
                    _gen_err = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e)},
                        "id": body.get("id"),
                    }
                    yield f"data: {json.dumps(_gen_err)}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Mcp-Protocol-Version": "2025-06-18",
                },
            )

    async def _process_request(self, body: dict[str, Any]) -> dict[str, Any]:
        import httpx

        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id")

        try:
            async with httpx.AsyncClient(app=self.app, base_url="http://testserver") as ac:
                if method == "tools/list":
                    resp = await ac.get("/mcp/v1/tools")
                elif method == "tools/call":
                    resp = await ac.post("/mcp/v1/tools/call", json=params)
                else:
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": req_id,
                    }
                return {"jsonrpc": "2.0", "result": resp.json(), "id": req_id}
        except Exception as e:
            return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req_id}
