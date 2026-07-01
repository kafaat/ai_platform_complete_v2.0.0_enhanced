"""VRA Prescription Engine (V62) — proposal-only variable-rate prescription planner.

This module converts approved/proposed productivity zones and soil-sampling/lab evidence
into a confirmable VRA prescription proposal. It deliberately does **not** persist maps,
export machine files, or schedule operations. The write/export step remains a separate
high-risk approval action through ``create_prescription_map``.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from .field_boundary_ai import area_ha_for_bbox, normalize_bbox
    from .productivity_zones import bbox_from_polygon
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.field_boundary_ai import (  # type: ignore
        area_ha_for_bbox,
        normalize_bbox,
    )
    from services.ai_agronomist.productivity_zones import bbox_from_polygon  # type: ignore

_ALLOWED_PRODUCTS = {"fertilizer", "lime", "seed", "irrigation"}
_DEFAULT_UNITS = {
    "fertilizer": "kg_ha",
    "lime": "t_ha",
    "seed": "seeds_m2",
    "irrigation": "mm",
}
_CLASS_RATE_FACTOR = {"high": 1.0, "medium": 0.82, "low": 1.16}
_CLASS_RATIONALE_AR = {
    "high": "منطقة إنتاجية مرتفعة؛ تُحافظ الوصفة على المعدّل الأساسي مع مراقبة عدم الإفراط.",
    "medium": "منطقة إنتاجية متوسطة؛ تُستخدم جرعة محافظة حتى تظهر نتائج مختبر أدق.",
    "low": "منطقة إنتاجية منخفضة؛ تُرفع الجرعة نسبياً فقط إذا كان الهدف علاج نقص مثبت أو تقديري مقبول.",
}


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _normalize_product_type(value: Any) -> str:
    product = str(value or "fertilizer").strip().lower()
    return product if product in _ALLOWED_PRODUCTS else "fertilizer"


def _zones_from_params(params: dict[str, Any]) -> list[dict[str, Any]]:
    raw = params.get("zones") or params.get("productivity_zones")
    if isinstance(raw, list):
        return [z for z in raw if isinstance(z, dict)]
    return []


def _zone_class(zone: dict[str, Any], idx: int) -> str:
    raw = str(zone.get("productivity_class") or zone.get("class") or "").strip().lower()
    if raw in {"high", "medium", "low"}:
        return raw
    return ("high", "medium", "low")[idx % 3]


def _zone_area(zone: dict[str, Any]) -> float:
    area = _as_float(zone.get("area_ha"))
    if area is not None and area > 0:
        return area
    geom = zone.get("geometry")
    bbox = bbox_from_polygon(geom) if isinstance(geom, dict) else None
    if bbox is None:
        bbox = normalize_bbox(zone.get("bbox"))
    return area_ha_for_bbox(bbox) if bbox else 0.0


def _base_rate(params: dict[str, Any], product_type: str) -> float:
    explicit = _as_float(params.get("base_rate"))
    if explicit is not None and explicit > 0:
        return explicit
    if product_type == "lime":
        return 1.2
    if product_type == "seed":
        return 280.0
    if product_type == "irrigation":
        return 18.0
    return 120.0


def _has_lab_evidence(params: dict[str, Any]) -> bool:
    lab = params.get("lab_results") or params.get("soil_lab_results")
    if isinstance(lab, list) and len(lab) > 0:
        return True
    if isinstance(lab, dict) and len(lab) > 0:
        return True
    plan = params.get("soil_sampling_plan") or params.get("sampling_plan")
    return isinstance(plan, dict) and bool(plan.get("lab_results_available"))


def _data_completeness(
    params: dict[str, Any], zones: list[dict[str, Any]], has_lab: bool
) -> dict[str, Any]:
    has_sampling_plan = isinstance(
        params.get("soil_sampling_plan") or params.get("sampling_plan"), dict
    )
    has_crop = bool(str(params.get("crop") or params.get("crop_hint") or "").strip())
    return {
        "zones": bool(zones),
        "soil_sampling_plan": has_sampling_plan,
        "lab_results": has_lab,
        "crop_target": has_crop,
        "score": round(
            (0.35 if zones else 0.0)
            + (0.2 if has_sampling_plan else 0.0)
            + (0.3 if has_lab else 0.0)
            + (0.15 if has_crop else 0.0),
            2,
        ),
    }


def generate_vra_prescription(
    params: dict[str, Any],
    *,
    field_id: str | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a confirmable VRA prescription proposal.

    Readiness gate:
    - zones are required;
    - lab data is preferred;
    - estimated prescriptions require ``allow_estimated=true`` and are clearly marked.
    """
    params = params if isinstance(params, dict) else {}
    zones = _zones_from_params(params)
    product_type = _normalize_product_type(params.get("product_type"))
    allow_estimated = bool(params.get("allow_estimated"))
    has_lab = _has_lab_evidence(params)
    completeness = _data_completeness(params, zones, has_lab)

    if not zones:
        return {
            "field_id": field_id,
            "vra_prescription": None,
            "prescription_zones": [],
            "requires_user_confirmation": True,
            "ready_for_machine_export": False,
            "readiness_gate": {
                "status": "blocked",
                "reason": "missing_productivity_zones",
                "required_before_vra": ["approved_productivity_zones"],
            },
            "data_completeness": completeness,
            "method": "vra_prescription_readiness_gate",
        }

    if not has_lab and not allow_estimated:
        return {
            "field_id": field_id,
            "vra_prescription": None,
            "prescription_zones": [],
            "requires_user_confirmation": True,
            "ready_for_machine_export": False,
            "readiness_gate": {
                "status": "blocked",
                "reason": "missing_lab_results_or_estimation_consent",
                "required_before_vra": ["soil_lab_results", "or_explicit_allow_estimated"],
            },
            "data_completeness": completeness,
            "method": "vra_prescription_readiness_gate",
        }

    base_rate = _base_rate(params, product_type)
    unit = str(params.get("unit") or _DEFAULT_UNITS[product_type])
    crop = str(params.get("crop") or params.get("crop_hint") or "unspecified")
    target_yield = _as_float(params.get("target_yield"))
    confidence = 0.62 + (0.18 if has_lab else 0.0) + min(max(completeness["score"], 0), 1) * 0.12
    if allow_estimated and not has_lab:
        confidence -= 0.12
    confidence = round(max(0.38, min(confidence, 0.88)), 2)

    prescription_zones: list[dict[str, Any]] = []
    total_area = 0.0
    weighted_total = 0.0
    for idx, zone in enumerate(zones[:12]):
        zclass = _zone_class(zone, idx)
        area = round(_zone_area(zone), 3)
        factor = _CLASS_RATE_FACTOR[zclass]
        # Estimated low zones are capped to avoid unsafe over-application without lab proof.
        if zclass == "low" and not has_lab:
            factor = min(factor, 1.08)
        rate = round(base_rate * factor, 2)
        total_area += max(area, 0.0)
        weighted_total += max(area, 0.0) * rate
        prescription_zones.append(
            {
                "zone_id": str(zone.get("zone_id") or f"zone-{idx + 1}"),
                "productivity_class": zclass,
                "area_ha": area,
                "rate": rate,
                "unit": unit,
                "product_type": product_type,
                "geometry": zone.get("geometry"),
                "confidence": confidence,
                "rationale_ar": _CLASS_RATIONALE_AR[zclass],
                "evidence_level": "lab_supported"
                if has_lab
                else "estimated_requires_agronomist_review",
            }
        )

    avg_rate = round(weighted_total / total_area, 2) if total_area > 0 else base_rate
    readiness_status = "proposal_only" if not has_lab else "review_required_before_export"
    warnings: list[str] = []
    if not has_lab:
        warnings.append(
            "الوصفة تقديرية لأن نتائج المختبر غير مرفقة؛ لا تُصدّر للآلة قبل مراجعة مهندس زراعي أو نتائج تربة."
        )
    if crop == "unspecified":
        warnings.append(
            "المحصول غير محدد؛ استخدم هدفاً عاماً ولا تعتمد الوصفة للتنفيذ قبل تحديد المحصول والمرحلة."
        )

    return {
        "field_id": field_id,
        "method": "map_based_vra_zone_prescription_v62",
        "vra_prescription": {
            "prescription_id": "vra-proposal-1",
            "product_type": product_type,
            "crop": crop,
            "target_yield": target_yield,
            "base_rate": base_rate,
            "average_rate": avg_rate,
            "unit": unit,
            "total_area_ha": round(total_area, 3),
            "confidence": confidence,
            "readiness_status": readiness_status,
            "machine_export_formats": ["geojson"],
            "requires_agronomist_review": True,
        },
        "prescription_zones": prescription_zones,
        "data_completeness": completeness,
        "readiness_gate": {
            "status": readiness_status,
            "reason": "lab_supported" if has_lab else "estimated_with_user_consent",
            "ready_for_machine_export": False,
            "required_before_export": [
                "human_approval",
                "agronomist_review",
                "equipment_adapter_selection",
            ],
        },
        "warnings": warnings,
        "requires_user_confirmation": True,
        "ready_for_machine_export": False,
        "persistence": "proposal_only_until_user_confirms",
        "next_step": "approve_create_prescription_map_or_refine_with_lab_results",
    }
