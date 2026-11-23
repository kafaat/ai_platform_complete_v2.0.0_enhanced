"""Generic independent MCP-style context server for SAHOOL services."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from shared.oauth_middleware import MCPPreAuthMiddleware, require_scope
from shared.owner_telemetry import SENSOR_SCHEMA, platform_origin, sensor_signal
from shared.streamable_http import StreamableHTTPTransport

app = FastAPI(title="SAHOOL Independent MCP Context Server", version="2026.2")
SERVICE = os.getenv("MCP_SERVICE", "field")

# MCP-GENERIC-CONTEXT-AUTH-MISSING-01 — هذه الوحدة كانت **الوحيدة** بين خوادم MCP بلا
# أيّ مصادقة: لا `require_scope` ولا `Depends` ولا middleware، بينما تشتقّ منها **ستّ**
# خدمات منشورة (`field` · `lab` · `satellite` · `iot` · `rag` · `knowledge-graph`)
# في `docker-compose.rag-kg-mcp.yml`. الشبكة داخليّة بلا `ports:`، لكنّ «داخليّ» ليس
# «مُصادَق»: أيّ حِمل داخل الشبكة الموثوقة كان يقرأ سياق مستأجِرين بلا هويّة.
#
# **النطاق موحَّد لا مجاليّ:** بقيّة الخوادم تستعمل نطاق مجالها (`weather:read`…)، وهذه
# وحدة واحدة تخدم ستّة مجالات — فنطاق مجاليّ واحد سيكون كاذباً لخمسة منها، وستّة نطاقات
# ستجعل الحارس يعتمد على `MCP_SERVICE` وهو **مُدخَل بيئة** لا هويّة.
#
# **بلا bypass افتراضيّ ولا علم انتقال:** الجرد أثبت أنّ لا مستهلك مُهيّأ في المستودع
# (عميل المشرف الوحيد يستهدف الأربعة المحروسة)، فلا حاجة إلى فترة سماح — والافتراضيّ
# الآمن أصدق من علم مؤقّت يصير دائماً بالصمت.
MCP_CONTEXT_SCOPE = "mcp:context:read"
# One dependency object for both the route guard and the handler parameter, so
# FastAPI authenticates once per request and the handler sees the same claims.
_require_context_scope = require_scope(MCP_CONTEXT_SCOPE)

# Auth-first: this ASGI layer runs before request-body decoding/validation.
app.add_middleware(
    MCPPreAuthMiddleware,
    protected_paths={"/v1/mcp/tools/call": MCP_CONTEXT_SCOPE},
)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


def _base(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    # Every value below is the caller's own argument echoed back; nothing here was
    # read from a lab, weather or field source. It is therefore never "verified" and
    # never "governing". tenant_id is overwritten from the token by call_tool.
    return {
        "type": kind,
        "service": SERVICE,
        "field_id": args.get("field_id"),
        "tenant_id": args.get("tenant_id"),
        "observed_at": datetime.now(UTC).isoformat(),
        "verified": False,
        "decision_authority": "none",
        # F9: no search, lookup or computation runs behind these tools. Say so in the
        # answer itself, not only in the tool list, so a model cannot read an echo as
        # a retrieval result.
        "retrieval_performed": False,
        "source": "caller_supplied",
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
        "governing": False,
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
        # Caller-supplied citations are reference context only, never decision evidence.
        "evidence_class": "reference_context",
    }


def _kg(args: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base("annotation", args),
        "name": "kg_annotation",
        "value": {"subject": args.get("subject"), "edges": args.get("edges", [])},
        "verified": False,
        # Caller-supplied edges are reference context only, never decision evidence.
        "evidence_class": "reference_context",
    }


# F9 — tool names say what the tool does. Only ``iot`` reads an owner (the platform,
# via ``sensor_signal`` with the caller's own bearer); every other tool returns the
# caller's arguments wrapped as an Observation/Signal/Annotation. They were listed as
# ``search_*`` / ``query_*`` / ``get_*`` although no search, query or lookup ran, so
# a model took the caller's own citations/edges/readings for retrieved results. The
# echo tools are now named ``wrap_caller_*``; the old names stay accepted as
# deprecated aliases (per service) and are reported back in ``deprecated_alias_used``.
TOOLSETS = {
    "field": {"wrap_caller_field_context": _field_state},
    "weather": {"wrap_caller_weather_signal": _weather},
    "lab": {"wrap_caller_lab_context": _lab},
    "satellite": {"wrap_caller_satellite_observation": _satellite},
    "iot": {"get_sensor_signal": _iot},
    "rag": {"wrap_caller_rag_annotations": _rag},
    "knowledge-graph": {"wrap_caller_kg_annotations": _kg},
}

# service -> {deprecated name: canonical name}. Scoped per service so an alias never
# reaches a tool the deployed service does not serve.
TOOL_ALIASES = {
    "field": {"get_field_state": "wrap_caller_field_context"},
    "weather": {"get_weather_signal": "wrap_caller_weather_signal"},
    "lab": {"get_lab_context": "wrap_caller_lab_context"},
    "satellite": {"get_satellite_observation": "wrap_caller_satellite_observation"},
    "rag": {"search_rag_annotations": "wrap_caller_rag_annotations"},
    "knowledge-graph": {"query_kg_annotations": "wrap_caller_kg_annotations"},
}

# Whether a tool reads anything beyond the caller's arguments.
TOOL_RETRIEVAL = {"get_sensor_signal": True} | {
    name: False for service, tools in TOOLSETS.items() if service != "iot" for name in tools
}

_ECHO_DESCRIPTION = (
    "Wraps the {what} supplied by the caller as an {kind}; no retrieval, search or "
    "computation is performed (retrieval_performed=false, verified=false)."
)
TOOL_DESCRIPTIONS = {
    "wrap_caller_field_context": _ECHO_DESCRIPTION.format(
        what="field_id/crop", kind="unverified Signal"
    ),
    "wrap_caller_weather_signal": _ECHO_DESCRIPTION.format(
        what="weather values", kind="unverified Signal"
    ),
    "wrap_caller_lab_context": _ECHO_DESCRIPTION.format(
        what="lab values", kind="unverified, non-governing Signal"
    ),
    "wrap_caller_satellite_observation": _ECHO_DESCRIPTION.format(
        what="satellite index values", kind="unverified Observation"
    ),
    "wrap_caller_rag_annotations": _ECHO_DESCRIPTION.format(
        what="query and citations", kind="Annotation (reference context, never evidence)"
    ),
    "wrap_caller_kg_annotations": _ECHO_DESCRIPTION.format(
        what="subject and edges", kind="Annotation (reference context, never evidence)"
    ),
    "get_sensor_signal": (
        "Reads the latest owner-bound sensor signal from the platform for the "
        "caller's tenant (Signal only)."
    ),
}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if SERVICE not in TOOLSETS:
        raise HTTPException(503, f"Unsupported MCP_SERVICE={SERVICE}")
    if SERVICE == "iot":
        platform_origin(os.getenv("PLATFORM_API_URL", ""))
    return {"status": "ready", "service": SERVICE}


@app.get("/v1/mcp/tools", dependencies=[Depends(_require_context_scope)])
async def list_tools() -> dict[str, Any]:
    if SERVICE not in TOOLSETS:
        raise HTTPException(503, f"Unsupported MCP_SERVICE={SERVICE}")
    return {
        "server": f"{SERVICE}-mcp-server",
        "service": SERVICE,
        "tools": [
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "retrieval_performed": TOOL_RETRIEVAL[name],
                "deprecated_aliases": sorted(
                    old for old, new in TOOL_ALIASES.get(SERVICE, {}).items() if new == name
                ),
                **({"inputSchema": SENSOR_SCHEMA} if SERVICE == "iot" else {}),
            }
            for name in TOOLSETS[SERVICE]
        ],
    }


@app.post("/v1/mcp/tools/call", dependencies=[Depends(_require_context_scope)])
async def call_tool(
    call: ToolCall, request: Request, user: dict[str, Any] = Depends(_require_context_scope)
) -> dict[str, Any]:
    tools = TOOLSETS.get(SERVICE)
    name = TOOL_ALIASES.get(SERVICE, {}).get(call.name, call.name)
    if not tools or name not in tools:
        raise HTTPException(404, "Unknown tool")
    # The tenant is the token's, never the one in the (model-written) arguments.
    if SERVICE == "iot":
        arguments = dict(call.arguments)
        if "tenant_id" in arguments and arguments.pop("tenant_id") != user["tenant_id"]:
            raise HTTPException(403, "telemetry_identity_mismatch")
        result = await sensor_signal(
            arguments, user["tenant_id"], request.headers.get("authorization", "")
        )
    else:
        result = tools[name]({**call.arguments, "tenant_id": user["tenant_id"]})
        result["tool"] = name
        result["deprecated_alias_used"] = name != call.name
    if result.get("type") not in {"observation", "signal", "annotation"}:
        raise HTTPException(500, "MCP output contract violation")
    if "recommendation" in result or "prescription" in result:
        raise HTTPException(500, "MCP servers cannot emit recommendations/prescriptions")
    return result


transport = StreamableHTTPTransport(app, required_scope=MCP_CONTEXT_SCOPE)
