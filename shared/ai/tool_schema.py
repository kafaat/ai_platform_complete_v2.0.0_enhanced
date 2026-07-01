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
                "description": "List of proposal objects such as productivity zones or sample points",
            }
        else:
            props[name] = {"type": _TYPE_MAP.get(base, "string")}
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
        out.append(
            {
                "name": t.name,
                "description": t.description_ar,
                "parameters": _param_schema(t.params),
                # بيانات حوكمة للواجهة/الحلقة (ليست جزءاً من عقد المزوّد القياسيّ).
                "x_sahool": {"risk": t.risk, "requires_approval": t.requires_approval},
            }
        )
    return out


def tool_names_for(allowed_capabilities: list[str] | None) -> list[str]:
    """أسماء الأدوات المتاحة للمستأجِر (اختصار)."""
    return [d["name"] for d in tool_definitions(allowed_capabilities)]
