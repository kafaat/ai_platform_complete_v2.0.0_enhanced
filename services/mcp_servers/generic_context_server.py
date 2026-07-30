"""Generic independent MCP-style context server for SAHOOL services."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="SAHOOL Independent MCP Context Server", version="2026.2")
SERVICE = os.getenv("MCP_SERVICE", "field")


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


def _base(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": kind,
        "service": SERVICE,
        "field_id": args.get("field_id"),
        "tenant_id": args.get("tenant_id"),
        "observed_at": datetime.now(UTC).isoformat(),
        "verified": kind == "signal" and SERVICE in {"lab", "weather"},
        "decision_authority": "none",
    }


def _field_state(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("signal", args),
        "name": "field_context_request",
        "value": {"field_id": args.get("field_id"), "crop": args.get("crop")},
    }


def _weather(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("signal", args),
        "name": "weather_snapshot",
        "value": {
            "et0_mm": args.get("et0_mm"),
            "rainfall_mm": args.get("rainfall_mm"),
            "wind_m_s": args.get("wind_m_s"),
        },
    }


def _lab(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("signal", args),
        "name": "lab_context",
        "value": {
            "soil_ec": args.get("soil_ec"),
            "soil_ph": args.get("soil_ph"),
            "water_ec": args.get("water_ec"),
            "sar": args.get("sar"),
        },
        "governing": True,
    }


def _satellite(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("observation", args),
        "name": "satellite_indices",
        "value": {
            "ndvi": args.get("ndvi"),
            "ndmi": args.get("ndmi"),
            "capture_date": args.get("capture_date"),
        },
        "evidence_class": "indication",
    }


def _iot(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("signal", args),
        "name": "sensor_snapshot",
        "value": {
            "soil_moisture": args.get("soil_moisture"),
            "battery_pct": args.get("battery_pct"),
        },
    }


def _rag(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("annotation", args),
        "name": "rag_annotation",
        "value": {"query": args.get("query"), "citations": args.get("citations", [])},
        "verified": False,
    }


def _kg(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("annotation", args),
        "name": "kg_annotation",
        "value": {"subject": args.get("subject"), "edges": args.get("edges", [])},
        "verified": False,
    }


TOOLSETS = {
    "field": {"get_field_state": _field_state},
    "weather": {"get_weather_signal": _weather},
    "lab": {"get_lab_context": _lab},
    "satellite": {"get_satellite_observation": _satellite},
    "iot": {"get_sensor_signal": _iot},
    "rag": {"search_rag_annotations": _rag},
    "knowledge-graph": {"query_kg_annotations": _kg},
}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if SERVICE not in TOOLSETS:
        raise HTTPException(503, f"Unsupported MCP_SERVICE={SERVICE}")
    return {"status": "ready", "service": SERVICE}


@app.get("/v1/mcp/tools")
async def list_tools() -> dict[str, Any]:
    if SERVICE not in TOOLSETS:
        raise HTTPException(503, f"Unsupported MCP_SERVICE={SERVICE}")
    return {
        "server": f"{SERVICE}-mcp-server",
        "service": SERVICE,
        "tools": [
            {
                "name": name,
                "description": f"Return {SERVICE} context as Observation/Signal/Annotation only",
            }
            for name in TOOLSETS[SERVICE]
        ],
    }


@app.post("/v1/mcp/tools/call")
async def call_tool(call: ToolCall) -> dict[str, Any]:
    tools = TOOLSETS.get(SERVICE)
    if not tools or call.name not in tools:
        raise HTTPException(404, "Unknown tool")
    result = tools[call.name](call.arguments)
    if result.get("type") not in {"observation", "signal", "annotation"}:
        raise HTTPException(500, "MCP output contract violation")
    if "recommendation" in result or "prescription" in result:
        raise HTTPException(500, "MCP servers cannot emit recommendations/prescriptions")
    return result
