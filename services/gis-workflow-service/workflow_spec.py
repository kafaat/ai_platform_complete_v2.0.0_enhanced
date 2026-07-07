"""workflow_spec.py — تحقّق/حلّ عقد تشغيل الـWorkflow (الشريحة B) — منطق صرف.

يتحقّق من spec تعريفيّ (dict مُحمَّل من YAML/JSON) قبل أيّ تشغيل: الهدف/التحليل/المخرجات/
الفحوص الذاتيّة. **صدق:** spec ناقص/شاذّ ⇒ ``(False, reason)`` صريح (لا تشغيل أعمى).

**حظر صريح (الشريحة B):** لا مصادر خارجيّة — يعمل فقط على مخرجات ساهول الحاليّة
(``existing_raster_asset``/COG). أيّ مصدر GEE/earthaccess/WaPOR/WorldCereal/HLS ⇒ رفض.
"""

from __future__ import annotations

from typing import Any

_ALLOWED_INDICES = {"ndvi", "ndmi", "ndwi", "evi", "savi", "truecolor", "lst"}
_ALLOWED_SOURCES = {"existing_raster_asset", "existing_cog", "raster_service"}
# مصادر خارجيّة محظورة في الشريحة B (تُعالَج في شرائح لاحقة بانضباط active:false).
_FORBIDDEN_SOURCES = {
    "gee",
    "earthengine",
    "earthaccess",
    "earthdata",
    "wapor",
    "worldcereal",
    "hls",
}
_ALLOWED_TARGET_TYPES = {"field", "aoi"}


def validate_spec(spec: Any) -> tuple[bool, str | None]:
    """يتحقّق من بنية الـspec. يُرجِع ``(True, None)`` أو ``(False, reason)``.

    يفرض: ``workflow_id`` · ``target`` (نوع + معرّف) · ``analysis`` (index مسموح + مصدر
    داخليّ غير محظور) · ``outputs`` dict. الفحوص الذاتيّة اختياريّة (قائمة أسماء).
    """
    if not isinstance(spec, dict):
        return False, "spec must be a mapping"
    if not isinstance(spec.get("workflow_id"), str) or not spec["workflow_id"].strip():
        return False, "workflow_id is required (non-empty string)"

    target = spec.get("target")
    if not isinstance(target, dict):
        return False, "target is required (mapping)"
    ttype = target.get("type")
    if ttype not in _ALLOWED_TARGET_TYPES:
        return False, f"target.type must be one of {sorted(_ALLOWED_TARGET_TYPES)}"
    if ttype == "field" and not (isinstance(target.get("field_id"), str) and target["field_id"]):
        return False, "target.field_id is required when target.type=field"
    if ttype == "aoi" and not target.get("aoi"):
        return False, "target.aoi is required when target.type=aoi"

    analysis = spec.get("analysis")
    if not isinstance(analysis, dict):
        return False, "analysis is required (mapping)"
    index = analysis.get("index")
    if not isinstance(index, str) or index.lower() not in _ALLOWED_INDICES:
        return False, f"analysis.index must be one of {sorted(_ALLOWED_INDICES)}"
    source = str(analysis.get("source") or "").lower()
    if source in _FORBIDDEN_SOURCES:
        return False, f"external source '{source}' is forbidden in slice B (Sahool outputs only)"
    if source not in _ALLOWED_SOURCES:
        return False, f"analysis.source must be one of {sorted(_ALLOWED_SOURCES)}"

    if not isinstance(spec.get("outputs"), dict):
        return False, "outputs is required (mapping)"
    checks = spec.get("self_checks", [])
    if checks is not None and not isinstance(checks, (list, tuple)):
        return False, "self_checks must be a list of check names"
    return True, None


def resolve_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """يُطبّع الـspec إلى شكل محلول ثابت (index/source lowercase، افتراضات المخرجات).

    يُفترض أنّ ``validate_spec`` مرّ. لا I/O — يُكتب لاحقاً كـ``resolved_spec.json``.
    """
    analysis = dict(spec["analysis"])
    analysis["index"] = str(analysis["index"]).lower()
    analysis["source"] = str(analysis.get("source") or "existing_raster_asset").lower()
    outputs = {
        "publication_map": True,
        "quality_report": True,
        "methodology": True,
        **(spec.get("outputs") or {}),
    }
    return {
        "workflow_id": spec["workflow_id"],
        "target": dict(spec["target"]),
        "analysis": analysis,
        "outputs": outputs,
        "self_checks": list(spec.get("self_checks") or []),
    }
