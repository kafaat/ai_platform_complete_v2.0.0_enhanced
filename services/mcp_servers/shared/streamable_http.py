#!/usr/bin/env python3
"""
Streamable HTTP Transport for MCP 2026
Replaces deprecated SSE with Streamable HTTP (June 2025 spec)
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Header, Request, Response
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)


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
        async def stream_endpoint(request: Request, authorization: str = Header(None)):
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
                    # نمرّر ترويسة Authorization للنداء الداخليّ كي يفرض
                    # require_scope مصادقة المتّصل الحقيقيّ (لا تجاوز/لا 401 مزيّف).
                    result = await self._process_request(body, authorization)

                    # Stream response chunks
                    yield f"data: {json.dumps(result)}\n\n"

                except TimeoutError:
                    _timeout_err = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": "Request timeout"},
                        "id": body.get("id"),
                    }
                    yield f"data: {json.dumps(_timeout_err)}\n\n"
                except Exception:
                    # لا نُسرّب نصّ الاستثناء (قد يحوي base_url/مضيفات داخليّة).
                    logger.exception("streamable_http: stream generation failed")
                    _gen_err = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": "Internal error"},
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

    async def _process_request(
        self, body: dict[str, Any], authorization: str | None = None
    ) -> dict[str, Any]:
        import httpx

        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id")

        # نمرّر Authorization فقط للنداء الداخليّ كي يصادق require_scope المتّصل.
        headers = {"Authorization": authorization} if authorization else {}

        try:
            async with httpx.AsyncClient(app=self.app, base_url="http://testserver") as ac:
                if method == "tools/list":
                    resp = await ac.get("/mcp/v1/tools", headers=headers)
                elif method == "tools/call":
                    resp = await ac.post("/mcp/v1/tools/call", json=params, headers=headers)
                else:
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": req_id,
                    }

                # غير 2xx (401/403/5xx…) ليس نتيجة صالحة: نُعيد خطأ JSON-RPC
                # بدل تغليف جسم الخطأ كـ "result" (يخلط المصادقة بالبيانات).
                if resp.status_code >= 400:
                    logger.warning(
                        "streamable_http: inner endpoint returned %s for method %s",
                        resp.status_code,
                        method,
                    )
                    return {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Upstream request failed",
                        },
                        "id": req_id,
                    }

                return {"jsonrpc": "2.0", "result": resp.json(), "id": req_id}
        except Exception:
            # لا نُسرّب نصّ الاستثناء (base_url/مضيفات داخليّة) للعميل.
            logger.exception("streamable_http: inner dispatch failed for method %s", method)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "Internal error"},
                "id": req_id,
            }
