"""Contracts for independent MCP service servers.

Each MCP server is an independently deployable FastAPI app exposing the same
/mcp/v1/tools and /mcp/v1/tools/call surface. Outputs are restricted to
observation/signal/annotation, never recommendations or prescriptions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    output_contract: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]

    def __post_init__(self) -> None:
        if self.output_contract not in {"observation", "signal", "annotation"}:
            raise ValueError("MCP tool output must be observation/signal/annotation")


@dataclass
class IndependentMCPServer:
    server_name: str
    service_name: str
    tools: dict[str, MCPTool]

    def list_tools(self) -> dict[str, Any]:
        return {
            "server": self.server_name,
            "service": self.service_name,
            "tools": [
                {"name": t.name, "description": t.description, "output_contract": t.output_contract}
                for t in self.tools.values()
            ],
        }

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.tools:
            raise KeyError(f"Unknown MCP tool: {name}")
        tool = self.tools[name]
        result = tool.handler(arguments)
        if result.get("type") not in {"observation", "signal", "annotation"}:
            raise ValueError("MCP server attempted to emit a non-context object")
        if "recommendation" in result or "prescription" in result:
            raise ValueError("MCP server must not emit recommendations or prescriptions")
        result["mcp_server"] = self.server_name
        result["output_contract"] = tool.output_contract
        return result
