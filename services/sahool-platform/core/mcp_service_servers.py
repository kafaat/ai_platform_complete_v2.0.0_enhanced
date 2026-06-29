"""MCP-style server descriptors and dynamic discovery.

These descriptors are transport-neutral. They let deployment expose each service
as a real MCP/HTTP server later without changing the Field Context Coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    service: str
    tools: tuple[str, ...]
    endpoint: str
    output_contract: str
    required_permissions: tuple[str, ...] = ("FIELD_VIEW",)

    def __post_init__(self) -> None:
        if self.output_contract not in {"observation", "signal", "annotation"}:
            raise ValueError("MCP server output must be observation/signal/annotation")
        if self.service in {"rag", "knowledge-graph"} and self.output_contract != "annotation":
            raise ValueError("RAG/KG MCP servers must be annotation-only")


def default_mcp_servers() -> list[MCPServerSpec]:
    return [
        MCPServerSpec(
            "weather-mcp-server",
            "weather",
            ("get_daily_weather", "get_operation_window"),
            "/mcp/weather",
            "signal",
        ),
        MCPServerSpec(
            "lab-mcp-server", "lab", ("get_latest_soil", "get_latest_water"), "/mcp/lab", "signal"
        ),
        MCPServerSpec(
            "satellite-mcp-server",
            "satellite",
            ("get_indices", "get_anomalies"),
            "/mcp/satellite",
            "observation",
        ),
        MCPServerSpec("iot-mcp-server", "iot", ("get_sensor_snapshot",), "/mcp/iot", "signal"),
        MCPServerSpec("rag-mcp-server", "rag", ("hybrid_search",), "/mcp/rag", "annotation"),
        MCPServerSpec(
            "kg-mcp-server", "knowledge-graph", ("query_edges",), "/mcp/kg", "annotation"
        ),
    ]
