#!/usr/bin/env python3
"""
MCP Client for SAHOOL Supervisor Agent
Unified interface to all MCP servers with OAuth 2.1 + caching
"""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpx

from shared.helpers import retry_request


class MCPError(RuntimeError):
    """A safe MCP boundary failure; never contains vendor data or credentials."""


class MCPAuthenticationError(MCPError):
    pass


class MCPToolError(MCPError):
    pass


class MCPProtocolError(MCPError):
    pass


def classify_mcp_error(exc: BaseException) -> str:
    """Return a stable, non-sensitive error category for MCP failures.

    This prevents leaking internal URLs, stack traces, or vendor errors through
    agent responses while preserving enough signal for tests/telemetry.
    """
    if isinstance(exc, MCPAuthenticationError):
        return "authentication_error"
    if isinstance(exc, MCPToolError):
        return "tool_error"
    if isinstance(exc, MCPProtocolError):
        return "protocol_error"
    name = exc.__class__.__name__.lower()
    if "circuit" in name:
        return "circuit_open"
    if "timeout" in name:
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_error"
    if isinstance(exc, httpx.RequestError):
        return "network_error"
    return "unexpected_error"


class MCPClient:
    """
    Client for Model Context Protocol (MCP) 2026 servers.
    Supports OAuth 2.1, idempotency, and connection pooling.
    """

    def __init__(self, servers: dict[str, str], token: str | None = None):
        self.servers = {name: self._origin(url) for name, url in servers.items()}
        self._clients: dict[str, httpx.AsyncClient] = {}
        # Connection pools are shared, credentials are request-local. ContextVar
        # propagates to child tasks and resets even on cancellation/exception.
        self._credentials: ContextVar[tuple[str, str] | None] = ContextVar(
            "mcp_credentials", default=None
        )

    @property
    def token(self) -> str | None:
        """Legacy read accessor for RAG: only this request's verified token.

        The deprecated constructor token is intentionally never used as a
        credential. Internal service secrets cannot authorize an MCP caller.
        """
        identity = self._credentials.get()
        return identity[0] if identity else None

    @staticmethod
    def _origin(value: str) -> str:
        url = httpx.URL(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.path.rstrip("/") not in {"", "/mcp/v1", "/v1/mcp"}
        ):
            raise ValueError("MCP server URL must be an HTTP(S) origin")
        # Explicit migration compatibility for older compose overlays. Paths
        # belong to this client, not to the configured server origin.
        return str(url.copy_with(path="/"))

    @contextmanager
    def bind_credentials(self, token: str, tenant_id: str):
        """Bind the already verified caller's bearer token; never mint privileges.

        The remote MCP verifier checks signature, issuer, audience and scopes on
        every request. Only the authenticated HTTP dependency may supply these
        values, not AgentQuery.context or an opaque internal service token.
        """
        if not isinstance(token, str) or not token.strip() or not tenant_id:
            raise MCPAuthenticationError("Verified MCP caller credentials required")
        marker = self._credentials.set((token, str(tenant_id)))
        try:
            yield
        finally:
            self._credentials.reset(marker)

    def _request_identity(self) -> tuple[dict[str, str], str]:
        identity = self._credentials.get()
        if identity is None:
            raise MCPAuthenticationError("Verified MCP caller credentials required")
        token, tenant_id = identity
        return {"Authorization": f"Bearer {token}"}, tenant_id

    async def _get_client(self, server_name: str) -> httpx.AsyncClient:
        if server_name not in self._clients:
            self._clients[server_name] = httpx.AsyncClient(
                base_url=self.servers[server_name],
                headers={
                    "Content-Type": "application/json",
                    "Mcp-Protocol-Version": "2025-06-18",
                },
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._clients[server_name]

    @staticmethod
    def _response_payload(resp: httpx.Response) -> dict[str, Any]:
        resp.raise_for_status()
        try:
            result = resp.json()
        except ValueError as exc:
            raise MCPProtocolError("Invalid MCP JSON response") from exc
        if not isinstance(result, dict):
            raise MCPProtocolError("Invalid MCP response envelope")
        if result.get("isError") is True or result.get("error"):
            raise MCPToolError("MCP tool execution failed")
        if "isError" in result and not isinstance(result["isError"], bool):
            raise MCPProtocolError("Invalid MCP error flag")
        return result

    async def list_tools(self, server_name: str) -> list[dict]:
        """Discover tools with fresh authorization, including after token expiry."""
        headers, _ = self._request_identity()
        client = await self._get_client(server_name)
        resp = await retry_request(client.get, "/v1/mcp/tools", headers=headers)
        tools = self._response_payload(resp).get("tools")
        if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
            raise MCPProtocolError("Invalid MCP tool discovery response")
        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Call an MCP tool with idempotency + circuit breaker support.
        """
        headers, tenant_id = self._request_identity()
        # قاطع الدائرة: عزل الخدمات الفاشلة (fail-fast بدل إغراقها)
        from circuit_breaker import CircuitOpenError, mcp_breakers

        breaker = mcp_breakers.get(server_name)
        if not breaker.allow_request():
            raise CircuitOpenError(f"خدمة {server_name} متعطّلة (القاطع مفتوح) — تخطٍّ سريع")

        client = await self._get_client(server_name)

        bound_arguments = dict(arguments)
        if bound_arguments.get("tenant_id") not in (None, tenant_id):
            raise MCPAuthenticationError("MCP argument tenant does not match caller")
        bound_arguments["tenant_id"] = tenant_id
        payload = {"name": tool_name, "arguments": bound_arguments}

        if request_id:
            payload["request_id"] = request_id

        try:
            resp = await retry_request(
                client.post,
                "/v1/mcp/tools/call",
                json=payload,
                headers=headers,
                # Not every server implements durable write idempotency (market
                # does not). Never replay a possibly committed tool side effect.
                max_attempts=1,
            )
            result = self._response_payload(resp)
            if not isinstance(result.get("content"), list) or not result["content"]:
                raise MCPProtocolError("Missing MCP tool content")
        except httpx.HTTPStatusError as exc:
            # A caller's bad credentials/arguments must not open the global
            # service circuit for every other tenant.
            if exc.response.status_code >= 500:
                breaker.record_failure()
            raise
        except Exception:
            breaker.record_failure()  # سجّل الفشل (قد يفتح القاطع)
            raise
        breaker.record_success()  # نجاح → يُعافي القاطع تدريجيّاً
        return result

    async def call_tools_parallel(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Execute multiple MCP tool calls in parallel.
        calls = [{"server": "weather", "tool": "get_forecast", "args": {...}}, ...]
        """
        tasks = []
        for call in calls:
            task = self.call_tool(
                call["server"], call["tool"], call.get("args", {}), call.get("request_id")
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(
                    {
                        "server": calls[i]["server"],
                        "tool": calls[i]["tool"],
                        "error": "tool_call_failed",
                        "error_type": classify_mcp_error(result),
                        "status": "failed",
                    }
                )
            else:
                processed.append(
                    {
                        "server": calls[i]["server"],
                        "tool": calls[i]["tool"],
                        "result": result,
                        "status": "success",
                    }
                )

        return processed

    async def close(self):
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
