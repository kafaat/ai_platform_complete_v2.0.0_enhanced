from shared.helpers import retry_request
#!/usr/bin/env python3
"""
MCP Client for SAHOOL Supervisor Agent
Unified interface to all MCP servers with OAuth 2.1 + caching
"""
import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx


class MCPClient:
    """
    Client for Model Context Protocol (MCP) 2026 servers.
    Supports OAuth 2.1, idempotency, and connection pooling.
    """

    def __init__(self, servers: Dict[str, str], token: str):
        self.servers = servers
        self.token = token
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._tool_cache: Dict[str, List[dict]] = {}

    async def _get_client(self, server_name: str) -> httpx.AsyncClient:
        if server_name not in self._clients:
            self._clients[server_name] = httpx.AsyncClient(
                base_url=self.servers[server_name],
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "Mcp-Protocol-Version": "2025-06-18"
                },
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
            )
        return self._clients[server_name]

    async def list_tools(self, server_name: str) -> List[dict]:
        """Discover available tools from MCP server."""
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]

        client = await self._get_client(server_name)
        resp = await retry_request(client.get, "/mcp/v1/tools")
        resp.raise_for_status()

        tools = resp.json().get("tools", [])
        self._tool_cache[server_name] = tools
        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call an MCP tool with idempotency + circuit breaker support.
        """
        # قاطع الدائرة: عزل الخدمات الفاشلة (fail-fast بدل إغراقها)
        from circuit_breaker import mcp_breakers, CircuitOpenError
        breaker = mcp_breakers.get(server_name)
        if not breaker.allow_request():
            raise CircuitOpenError(
                f"خدمة {server_name} متعطّلة (القاطع مفتوح) — تخطٍّ سريع")

        client = await self._get_client(server_name)

        payload = {
            "name": tool_name,
            "arguments": arguments
        }

        if request_id:
            payload["request_id"] = request_id

        try:
            resp = await retry_request(client.post, "/mcp/v1/tools/call", json=payload)
            resp.raise_for_status()
        except Exception:
            breaker.record_failure()   # سجّل الفشل (قد يفتح القاطع)
            raise
        breaker.record_success()       # نجاح → يُعافي القاطع تدريجيّاً
        return resp.json()

    async def call_tools_parallel(
        self,
        calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple MCP tool calls in parallel.
        calls = [{"server": "weather", "tool": "get_forecast", "args": {...}}, ...]
        """
        tasks = []
        for call in calls:
            task = self.call_tool(
                call["server"],
                call["tool"],
                call.get("args", {}),
                call.get("request_id")
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append({
                    "server": calls[i]["server"],
                    "tool": calls[i]["tool"],
                    "error": str(result),
                    "status": "failed"
                })
            else:
                processed.append({
                    "server": calls[i]["server"],
                    "tool": calls[i]["tool"],
                    "result": result,
                    "status": "success"
                })

        return processed

    async def close(self):
        for client in self._clients.values():
            await client.close()
