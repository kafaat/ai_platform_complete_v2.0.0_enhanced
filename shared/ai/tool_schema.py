"""تعريفات أدوات الوكيل بصيغة function-calling (V56 — حلقة الأدوات الحيّة).

يحوّل سجلّ الأدوات (``tool_registry``) إلى تعريفات دوالّ يفهمها المزوّد (OpenAI-style
tools / Anthropic tools) — **مُصفّاةً بقدرات المستأجِر**: النموذج لا يرى حتى أداةً لا
يملك المستأجِر قدرتها (منع بالتصميم، لا بعد الطلب). خاصّيّة أمان قويّة: أضيق سطح ممكن.

عقد صرف حتميّ. الاستدعاء الحيّ للمزوّد يُبنى فوق هذا لاحقاً.
"""

from __future__ import annotations

from typing import Any

from shared.ai.capabilities import normalize_capabilities
from shared.ai.tool_registry import TOOLS

# تحويل نوع الوسيط المبسّط (str/int/str?) إلى JSON Schema.
_TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}

_TOOL_USAGE_GUIDANCE: dict[str, dict[str, Any]] = {
    # ── V58.2b — إرشاد استخدام أدوات V58 الأساسيّة (قراءة + مُعدِّلة + عالية) ──
    "get_field_state": {
        "when_to_use": "Use first to ground any answer in the field's current crop, stage, indices, and irrigation state.",
        "when_not_to_use": "Do not use for historical trends over time; use get_index_timeline or get_weather_history instead.",
        "examples": [{"field_id": "field-1"}],
    },
    "get_truecolor_scene": {
        "when_to_use": "Use to fetch a raw TrueColor scene (latest or by date) to visually inspect the field.",
        "when_not_to_use": "Do not use for vegetation-index trends; use get_index_timeline.",
        "examples": [{"field_id": "field-1"}],
    },
    "get_index_timeline": {
        "when_to_use": "Use to read a vegetation/moisture index (ndvi/ndmi…) as a time series over N days to spot trends or stress.",
        "when_not_to_use": "Do not use for a single current snapshot; use get_field_state.",
        "examples": [{"field_id": "field-1", "index": "ndvi", "days": 90}],
    },
    "get_weather_history": {
        "when_to_use": "Use to read historical temperature/rain/ET0 (up to 730 days) for agronomic context.",
        "when_not_to_use": "Do not use for spray/irrigation timing windows; use get_operation_windows.",
        "examples": [{"field_id": "field-1", "days": 30}],
    },
    "get_operation_windows": {
        "when_to_use": "Use to find suitable spray/irrigation windows given wind/rain/humidity.",
        "when_not_to_use": "Do not use to schedule an operation; that requires schedule_irrigation with human approval.",
        "examples": [{"field_id": "field-1"}],
    },
    "get_alerts": {
        "when_to_use": "Use to read the field's active alerts (stress/disease/frost…) before advising.",
        "when_not_to_use": "Do not use to send a recommendation; draft first, then send only after approval.",
        "examples": [{"field_id": "field-1"}],
    },
    "get_drawings_and_zones": {
        "when_to_use": "Use to read existing drawings, productivity zones, and axes for the field.",
        "when_not_to_use": "Do not use to create or save zones; propose via generate_productivity_zones.",
        "examples": [{"field_id": "field-1"}],
    },
    "open_map_layer": {
        "when_to_use": "Use to open a map layer (truecolor/index) at a date for the user to view — a UI action, no data change.",
        "when_not_to_use": "Do not treat as data retrieval; it does not return pixels, only opens a layer.",
        "examples": [{"field_id": "field-1", "layer": "ndvi"}],
    },
    "create_scouting_task": {
        "when_to_use": "Propose a field scouting task for a zone; requires explicit human approval before it is created.",
        "when_not_to_use": "Do not use to send advice to the farmer; use draft_recommendation then send_recommendation.",
        "examples": [{"field_id": "field-1", "zone": "north"}],
    },
    "request_imagery_backfill": {
        "when_to_use": "Propose backfilling historical imagery (months) for a field; requires explicit human approval.",
        "when_not_to_use": "Do not use for recent/current imagery already available; use get_truecolor_scene.",
        "examples": [{"field_id": "field-1", "months": 12}],
    },
    "draft_recommendation": {
        "when_to_use": "Create a reviewable DRAFT recommendation (never sent). Requires approval to draft; sending is a separate high-risk step.",
        "when_not_to_use": "Do not use to send the final recommendation; use send_recommendation after approval.",
        "examples": [{"field_id": "field-1"}],
    },
    "detect_field_boundaries": {
        "when_to_use": "Use when the user asks to discover, trace, or propose field boundaries from TrueColor/NDVI imagery or a bbox.",
        "when_not_to_use": "Do not use to save official boundaries; use save_detected_boundary only after explicit human confirmation.",
        "examples": [{"bbox": [44.1, 15.1, 44.2, 15.2], "source": "truecolor"}],
    },
    "generate_productivity_zones": {
        "when_to_use": "Use after a boundary/bbox exists and the user asks to split a field into high/medium/low productivity management zones.",
        "when_not_to_use": "Do not save zones or create prescriptions; this only proposes zones with evidence and confidence.",
        "examples": [{"field_id": "field-1", "zone_count": 3, "basis": "multi_index"}],
    },
    "plan_soil_sampling": {
        "when_to_use": "Use after productivity zones are proposed/approved and the user asks for representative soil sampling points.",
        "when_not_to_use": "Do not create tasks or send a VRA prescription; this only proposes a sampling plan.",
        "examples": [{"field_id": "field-1", "lab_panel": "fertility", "samples_per_zone": 3}],
    },
    "generate_vra_prescription": {
        "when_to_use": "Use after productivity zones and preferably soil lab evidence exist, and the user asks for variable-rate fertilizer/lime/seed/irrigation prescription rates.",
        "when_not_to_use": "Do not export machine files, save official prescription maps, or schedule application. Use create_prescription_map only after explicit approval and agronomist review.",
        "examples": [
            {
                "field_id": "field-1",
                "product_type": "fertilizer",
                "crop": "wheat",
                "allow_estimated": False,
            }
        ],
    },
}

_PARAM_DESCRIPTIONS: dict[str, str] = {
    "field_id": "SAHOOL field identifier. Prefer the active field when available.",
    "bbox": "Bounding box in WGS84 order [lon_min, lat_min, lon_max, lat_max].",
    "source": "Imagery/data source to use. Prefer truecolor for boundary proposals; ndvi is allowed as fallback.",
    "date": "Optional ISO date YYYY-MM-DD; omit for latest/most suitable imagery.",
    "crop_hint": "Optional crop name to help interpret visual patterns; never required.",
    "boundary": "GeoJSON Polygon/MultiPolygon boundary to constrain the analysis.",
    "zone_count": "Requested number of productivity zones; use 3 unless evidence supports another value.",
    "basis": "Evidence basis such as multi_index, ndvi_stability, soil, yield, weather, or hybrid.",
    "zones": "Productivity zone proposal objects from generate_productivity_zones.",
    "lab_panel": "Soil test panel: fertility, salinity, micronutrients, irrigation_suitability, or comprehensive.",
    "samples_per_zone": "Target number of samples per productivity zone.",
    "soil_sampling_plan": "Soil sampling plan object from plan_soil_sampling; lab-backed plans are preferred for VRA.",
    "lab_results": "Optional soil lab result records. Required for stronger production-ready prescriptions unless allow_estimated is true.",
    "crop": "Crop name for agronomic rate interpretation.",
    "target_yield": "Optional target yield used to contextualize rates.",
    "product_type": "Prescription product type: fertilizer, lime, seed, or irrigation.",
    "base_rate": "Optional agronomist-provided base rate before zone adjustments.",
    "unit": "Rate unit such as kg_ha, t_ha, seeds_m2, or mm.",
    "allow_estimated": "Explicit consent to generate an estimated non-machine-exportable prescription without lab results.",
    "prescription_id": "Identifier of a previously displayed VRA proposal selected by the human user.",
    "proposal_id": "Identifier of a previously displayed proposal selected by the human user.",
    "plan_id": "Identifier of a previously displayed soil sampling plan selected by the human user.",
}


def _param_schema(params: dict[str, str]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, raw in params.items():
        optional = raw.endswith("?")
        base = raw[:-1] if optional else raw
        if base == "bbox":
            props[name] = {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "[lon_min, lat_min, lon_max, lat_max]",
            }
        elif base == "geojson":
            props[name] = {
                "type": "object",
                "description": "GeoJSON Polygon or MultiPolygon boundary",
                "additionalProperties": True,
            }
        elif base == "array":
            props[name] = {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
                "description": "List of proposal objects such as productivity zones, sample points, or lab results",
            }
        elif base == "object":
            props[name] = {
                "type": "object",
                "description": "Structured object produced by another SAHOOL agent tool",
                "additionalProperties": True,
            }
        else:
            props[name] = {"type": _TYPE_MAP.get(base, "string")}
        if name in _PARAM_DESCRIPTIONS:
            props[name]["description"] = _PARAM_DESCRIPTIONS[name]
        if name == "source":
            props[name]["enum"] = ["truecolor", "ndvi", "multi_index"]
        if name == "basis":
            props[name]["enum"] = [
                "multi_index",
                "ndvi_stability",
                "soil",
                "yield",
                "weather",
                "hybrid",
            ]
        if name == "lab_panel":
            props[name]["enum"] = [
                "fertility",
                "salinity",
                "micronutrients",
                "irrigation_suitability",
                "comprehensive",
            ]
        if name == "product_type":
            props[name]["enum"] = ["fertilizer", "lime", "seed", "irrigation"]
        if not optional:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def tool_definitions(allowed_capabilities: list[str] | None) -> list[dict[str, Any]]:
    """تعريفات function-calling للأدوات المسموحة للمستأجِر فقط (fail-closed).

    كلّ تعريف: ``{name, description, parameters(JSON Schema), x_sahool:{risk,
    requires_approval}}``. المستأجِر بلا قدرة أداة ⇒ الأداة غائبة تماماً من القائمة."""
    granted = set(normalize_capabilities(allowed_capabilities))
    out: list[dict[str, Any]] = []
    for t in TOOLS:
        if t.capability not in granted:
            continue  # لا يُعرَض للنموذج ما لا يملك المستأجِر قدرته.
        guidance = _TOOL_USAGE_GUIDANCE.get(t.name, {})
        description_parts = [t.description_ar]
        if guidance.get("when_to_use"):
            description_parts.append(f"When to use: {guidance['when_to_use']}")
        if guidance.get("when_not_to_use"):
            description_parts.append(f"When not to use: {guidance['when_not_to_use']}")
        if t.requires_approval:
            description_parts.append(
                "Requires explicit human approval; never execute as an autonomous write action."
            )
        out.append(
            {
                "name": t.name,
                "description": "\n".join(description_parts),
                "parameters": _param_schema(t.params),
                # بيانات حوكمة للواجهة/الحلقة (ليست جزءاً من عقد المزوّد القياسيّ).
                "x_sahool": {
                    "risk": t.risk,
                    "requires_approval": t.requires_approval,
                    "when_to_use": guidance.get("when_to_use"),
                    "when_not_to_use": guidance.get("when_not_to_use"),
                    "input_examples": guidance.get("examples", []),
                },
            }
        )
    return out


def tool_names_for(allowed_capabilities: list[str] | None) -> list[str]:
    """أسماء الأدوات المتاحة للمستأجِر (اختصار)."""
    return [d["name"] for d in tool_definitions(allowed_capabilities)]
