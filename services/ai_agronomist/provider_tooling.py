"""Provider-native tool schema and parsing for the SAHOOL agricultural harness (V58).

This module deliberately exposes **read-only** tools to external/local LLM providers.
Mutating tools remain represented as governed approval requests inside ``tool_loop`` and are
not advertised to providers by default. This keeps the model/harness boundary safe:

    model decides which read observation it needs -> harness executes/denies -> model answers.

The functions are pure and provider-agnostic. Network calls stay in ``ai_generation`` and side
effects stay in ``tool_loop``/``tool_executor``.
"""

from __future__ import annotations

from typing import Any

READ_ONLY_TOOL_NAMES: tuple[str, ...] = (
    "get_field_state",
    "get_truecolor_scene",
    "get_index_timeline",
    "get_weather_history",
    "get_water_productivity",
    "get_operation_windows",
    "get_alerts",
    "get_drawings_and_zones",
    "generate_report",
    "open_map_layer",
)

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_field_state": "Return the canonical field state and current agronomic context for one field.",
    "get_truecolor_scene": "Return metadata for a Sentinel-2 TrueColor scene for the selected field/date.",
    "get_index_timeline": "Return a vegetation/water index timeline such as NDVI, NDMI, NDRE, or MSAVI.",
    "get_weather_history": "Return historical weather context for the selected field and day range.",
    "get_water_productivity": "Return the field's water productivity / water-use efficiency (water consumed vs yield/biomass). Read-only.",
    "get_operation_windows": "Return agricultural operation windows such as spraying, irrigation, and harvesting.",
    "get_alerts": "Return active or recent field alerts.",
    "get_drawings_and_zones": "Return field drawings, pivots, management zones, and prescription zones.",
    "generate_report": "Compose a unified read-only field report (intelligence card, state, evidence) for display/export. Does not send.",
    "open_map_layer": "Request that the UI opens a map layer/date for the current field. Read-only UI intent.",
}

_BASE_PROPERTIES: dict[str, dict[str, Any]] = {
    "field_id": {
        "type": "string",
        "description": "Field identifier. Use the active field when omitted.",
    },
    "date": {"type": "string", "description": "Optional ISO date for imagery or map layer."},
    "index": {
        "type": "string",
        "enum": ["truecolor", "ndvi", "ndmi", "ndre", "msavi"],
        "description": "Raster/index layer.",
    },
    "days": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1095,
        "description": "History window in days.",
    },
    "layer": {"type": "string", "description": "Map layer to open in the UI."},
    "period": {
        "type": "string",
        "description": "Optional reporting period label or ISO range for the report.",
    },
}

_TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "get_field_state": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"]},
        "additionalProperties": False,
    },
    "get_truecolor_scene": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"], "date": _BASE_PROPERTIES["date"]},
        "additionalProperties": False,
    },
    "get_index_timeline": {
        "type": "object",
        "properties": {
            "field_id": _BASE_PROPERTIES["field_id"],
            "index": _BASE_PROPERTIES["index"],
            "days": _BASE_PROPERTIES["days"],
        },
        "additionalProperties": False,
    },
    "get_weather_history": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"], "days": _BASE_PROPERTIES["days"]},
        "additionalProperties": False,
    },
    "get_water_productivity": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"], "days": _BASE_PROPERTIES["days"]},
        "additionalProperties": False,
    },
    "generate_report": {
        "type": "object",
        "properties": {
            "field_id": _BASE_PROPERTIES["field_id"],
            "period": _BASE_PROPERTIES["period"],
        },
        "additionalProperties": False,
    },
    "get_operation_windows": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"]},
        "additionalProperties": False,
    },
    "get_alerts": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"]},
        "additionalProperties": False,
    },
    "get_drawings_and_zones": {
        "type": "object",
        "properties": {"field_id": _BASE_PROPERTIES["field_id"]},
        "additionalProperties": False,
    },
    "open_map_layer": {
        "type": "object",
        "properties": {
            "field_id": _BASE_PROPERTIES["field_id"],
            "layer": _BASE_PROPERTIES["layer"],
            "date": _BASE_PROPERTIES["date"],
        },
        "additionalProperties": False,
    },
}


def _tool_schema(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": _TOOL_DESCRIPTIONS[name],
        "parameters": _TOOL_PARAMETERS[name],
    }


def build_provider_tools(
    wire_format: str, *, tool_names: list[str] | tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
    """Return provider-native tool declarations for allowed read-only tools.

    ``wire_format='openai_chat'`` returns OpenAI/OpenRouter ``tools`` format.
    ``wire_format='messages'`` returns Anthropic-compatible ``tools`` format.
    Unknown/mutating names are ignored rather than broadened.
    """
    names = [n for n in (tool_names or READ_ONLY_TOOL_NAMES) if n in READ_ONLY_TOOL_NAMES]
    schemas = [_tool_schema(n) for n in names]
    if wire_format == "openai_chat":
        return [
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s["parameters"],
                },
            }
            for s in schemas
        ]
    return [
        {"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
        for s in schemas
    ]


def extract_tool_calls(wire_format: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse provider tool-use responses into harness ``{id, tool, params}`` calls.

    Supports OpenAI/OpenRouter function tool calls and Anthropic ``tool_use`` blocks.
    Malformed tool arguments degrade to empty params; unknown tool names are still returned
    so the harness can deny them explicitly and audit the attempt.
    """
    out: list[dict[str, Any]] = []
    if wire_format == "openai_chat":
        try:
            import json

            calls = data.get("choices", [])[0].get("message", {}).get("tool_calls") or []
            for c in calls:
                fn = c.get("function") or {}
                args_raw = fn.get("arguments") or "{}"
                try:
                    params = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
                except Exception:  # noqa: BLE001
                    params = {}
                out.append(
                    {
                        "id": c.get("id"),
                        "tool": fn.get("name"),
                        "params": params,
                        "provider_native": True,
                    }
                )
        except Exception:  # noqa: BLE001
            return []
        return [c for c in out if c.get("tool")]

    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            params = block.get("input") if isinstance(block.get("input"), dict) else {}
            out.append(
                {
                    "id": block.get("id"),
                    "tool": block.get("name"),
                    "params": params,
                    "provider_native": True,
                }
            )
    return [c for c in out if c.get("tool")]
