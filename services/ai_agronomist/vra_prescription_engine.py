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
    from .evidence_contract import evaluate_machine_readiness
    from .field_boundary_ai import area_ha_for_bbox, normalize_bbox
    from .productivity_zones import bbox_from_polygon
    from .soil_sampling_planner import _FULL_PANEL_ANALYTES, polygon_area_ha
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.evidence_contract import (  # type: ignore
        evaluate_machine_readiness,
    )
    from services.ai_agronomist.field_boundary_ai import (  # type: ignore
        area_ha_for_bbox,
        normalize_bbox,
    )
    from services.ai_agronomist.productivity_zones import bbox_from_polygon  # type: ignore
    from services.ai_agronomist.soil_sampling_planner import (  # type: ignore
        _FULL_PANEL_ANALYTES,
        polygon_area_ha,
    )

_ALLOWED_PRODUCTS = {"fertilizer", "lime", "seed", "irrigation"}
# The one canonical rate unit per product. Base rates (default or caller-supplied) are
# read in this unit; a caller unit that differs is rejected, never relabelled.
_DEFAULT_UNITS = {
    "fertilizer": "kg_ha",
    "lime": "t_ha",
    "seed": "seeds_m2",
    "irrigation": "mm",
}
_CLASS_RATE_FACTOR = {"high": 1.0, "medium": 0.82, "low": 1.16}
# Analyte names a soil lab record must carry (numerically) to count as lab evidence.
_LAB_ANALYTES = {a.lower() for a in _FULL_PANEL_ANALYTES}
_CLASS_RATIONALE_AR = {
    "high": "منطقة إنتاجية مرتفعة؛ تُحافظ الوصفة على المعدّل الأساسي مع مراقبة عدم الإفراط.",
    "medium": "منطقة إنتاجية متوسطة؛ تُستخدم جرعة محافظة حتى تظهر نتائج مختبر أدق.",
    "low": "منطقة إنتاجية منخفضة؛ تُرفع الجرعة نسبياً فقط إذا كان الهدف علاج نقص مثبت أو تقديري مقبول.",
}


def _available_export_formats() -> list[str]:
    """Advertised machine-export formats (V62.1 adapters); export stays approval-gated."""
    try:
        from .prescription_export_adapters import available_formats

        return available_formats()
    except Exception:  # noqa: BLE001 — تعذّر استيراد المحوّلات ⇒ الحدّ الأدنى الآمن
        return ["geojson"]


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


def _normalize_unit(value: Any) -> str | None:
    """Spelling-normalised unit (``"t/ha"`` -> ``"t_ha"``), or ``None`` when absent."""
    text = str(value or "").strip().lower().replace(" ", "").replace("/", "_")
    return text or None


def _zone_class(zone: dict[str, Any]) -> str | None:
    """The zone's stated productivity class, or ``None`` — never an invented one."""
    raw = str(zone.get("productivity_class") or zone.get("class") or "").strip().lower()
    return raw if raw in {"high", "medium", "low"} else None


def _zone_id(zone: dict[str, Any], idx: int) -> str:
    return str(zone.get("zone_id") or f"zone-{idx + 1}")


def _zone_area(zone: dict[str, Any]) -> float:
    area = _as_float(zone.get("area_ha"))
    if area is not None and area > 0:
        return area
    geom = zone.get("geometry")
    poly_area = polygon_area_ha(geom)
    if poly_area is not None:
        return poly_area
    bbox = bbox_from_polygon(geom) if isinstance(geom, dict) else None
    if bbox is None:
        bbox = normalize_bbox(zone.get("bbox"))
    return area_ha_for_bbox(bbox) if bbox else 0.0


def _zone_source_lineage(zone: dict[str, Any], evidence_context: dict[str, Any]) -> dict[str, Any]:
    """Preserve evidence identity; never turn it into an execution authorization."""
    lineage = zone.get("source_lineage") if isinstance(zone.get("source_lineage"), dict) else {}
    out = dict(lineage)
    for key in (
        "management_zone_id",
        "yield_processing_digest",
        "canonical_yield_state_digest",
        "spectral_state_digest",
        "soil_profile_hash",
    ):
        value = zone.get(key)
        if value is None:
            value = evidence_context.get(key)
        if value is not None:
            out[key] = value
    evidence_ids = zone.get("evidence_ids") or evidence_context.get("evidence_ids") or []
    if isinstance(evidence_ids, list):
        out["evidence_ids"] = [str(v) for v in evidence_ids if str(v)]
    return out


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


def _is_analyte_record(record: Any) -> bool:
    """A lab record counts only if it carries a numeric value for a known soil analyte.

    Accepted shapes: ``{"p": 12, "k": 20, ...}`` or ``{"analyte": "P", "value": 12}``.
    Strings, flags such as ``lab_results_available`` and records without a finite
    numeric analyte value are not lab evidence.
    """
    if not isinstance(record, dict):
        return False
    if str(record.get("analyte") or "").strip().lower() in _LAB_ANALYTES:
        if _as_float(record.get("value")) is not None:
            return True
    return any(
        str(key).strip().lower() in _LAB_ANALYTES and _as_float(value) is not None
        for key, value in record.items()
    )


def _lab_zone_ids(params: dict[str, Any]) -> tuple[set[str], bool]:
    """Return (zone ids with their own analyte record, whether a field-level record exists).

    A record with a ``zone_id`` supports only that zone; a record without one is a
    field-level composite and supports every zone.
    """
    lab = params.get("lab_results") or params.get("soil_lab_results")
    records: list[Any]
    if isinstance(lab, list):
        records = lab
    elif isinstance(lab, dict):
        # Either one record, or a {zone_id: record} mapping.
        records = (
            [lab]
            if _is_analyte_record(lab)
            else [
                {**rec, "zone_id": rec.get("zone_id") or zid}
                for zid, rec in lab.items()
                if isinstance(rec, dict)
            ]
        )
    else:
        records = []
    zone_ids: set[str] = set()
    field_level = False
    for record in records:
        if not _is_analyte_record(record):
            continue
        zid = str(record.get("zone_id") or "").strip()
        if zid:
            zone_ids.add(zid)
        else:
            field_level = True
    return zone_ids, field_level


def _confidence(completeness_score: float, lab_supported: bool) -> float:
    """Module confidence rule: lab-supported output vs estimated output."""
    confidence = 0.62 + (0.18 if lab_supported else 0.0)
    confidence += min(max(completeness_score, 0), 1) * 0.12
    if not lab_supported:
        confidence -= 0.12
    return round(max(0.38, min(confidence, 0.88)), 2)


def _blocked(
    field_id: str | None,
    completeness: dict[str, Any],
    reason: str,
    required: list[str],
    **gate_extra: Any,
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "vra_prescription": None,
        "prescription_zones": [],
        "requires_user_confirmation": True,
        "ready_for_machine_export": False,
        "readiness_gate": {
            "status": "blocked",
            "reason": reason,
            "required_before_vra": required,
            **gate_extra,
        },
        "data_completeness": completeness,
        "method": "vra_prescription_readiness_gate",
    }


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
    used_zones = zones[:12]
    lab_zone_ids, field_level_lab = _lab_zone_ids(params)
    zone_has_lab = [
        field_level_lab or _zone_id(zone, idx) in lab_zone_ids
        for idx, zone in enumerate(used_zones)
    ]
    has_lab = any(zone_has_lab)
    completeness = _data_completeness(params, zones, has_lab)

    if not zones:
        return _blocked(
            field_id, completeness, "missing_productivity_zones", ["approved_productivity_zones"]
        )

    unit = _DEFAULT_UNITS[product_type]
    requested_unit = _normalize_unit(params.get("unit"))
    if requested_unit is not None and requested_unit != unit:
        return _blocked(
            field_id,
            completeness,
            "unit_mismatch_for_product",
            ["unit_matching_product_type"],
            requested_unit=requested_unit,
            expected_unit=unit,
        )

    zone_classes = [_zone_class(zone) for zone in used_zones]
    unclassified = [
        _zone_id(zone, idx) for idx, zone in enumerate(used_zones) if zone_classes[idx] is None
    ]
    if unclassified:
        return _blocked(
            field_id,
            completeness,
            "unclassified_productivity_zones",
            ["productivity_class_per_zone"],
            unclassified_zone_ids=unclassified,
        )

    if not has_lab and not allow_estimated:
        return _blocked(
            field_id,
            completeness,
            "missing_lab_results_or_estimation_consent",
            ["soil_lab_results", "or_explicit_allow_estimated"],
        )

    base_rate = _base_rate(params, product_type)
    crop = str(params.get("crop") or params.get("crop_hint") or "unspecified")
    target_yield = _as_float(params.get("target_yield"))
    lab_confidence = _confidence(completeness["score"], True)
    estimated_confidence = _confidence(_data_completeness(params, zones, False)["score"], False)

    classes = [c for c in zone_classes if c is not None]  # all classified past the gate
    ctx = evidence_context if isinstance(evidence_context, dict) else {}
    prescription_zones: list[dict[str, Any]] = []
    total_area = 0.0
    weighted_total = 0.0
    weighted_confidence = 0.0
    for idx, zone in enumerate(used_zones):
        zclass = classes[idx]
        zone_lab = zone_has_lab[idx]
        zone_confidence = lab_confidence if zone_lab else estimated_confidence
        area = round(_zone_area(zone), 3)
        factor = _CLASS_RATE_FACTOR[zclass]
        # Estimated low zones are capped to avoid unsafe over-application without lab proof.
        if zclass == "low" and not zone_lab:
            factor = min(factor, 1.08)
        rate = round(base_rate * factor, 2)
        total_area += max(area, 0.0)
        weighted_total += max(area, 0.0) * rate
        weighted_confidence += max(area, 0.0) * zone_confidence
        prescription_zones.append(
            {
                "zone_id": _zone_id(zone, idx),
                "productivity_class": zclass,
                "area_ha": area,
                "rate": rate,
                "unit": unit,
                "product_type": product_type,
                "geometry": zone.get("geometry"),
                "confidence": zone_confidence,
                "rationale_ar": _CLASS_RATIONALE_AR[zclass],
                "evidence_level": "lab_supported"
                if zone_lab
                else "estimated_requires_agronomist_review",
                "source_lineage": _zone_source_lineage(zone, ctx),
            }
        )

    avg_rate = round(weighted_total / total_area, 2) if total_area > 0 else base_rate
    # Prescription confidence is the area-weighted mean of the zone confidences, so a
    # lab record for one zone does not lift the whole map to lab-supported confidence.
    if total_area > 0:
        confidence = round(weighted_confidence / total_area, 2)
    else:
        confidence = round(
            sum(z["confidence"] for z in prescription_zones) / len(prescription_zones), 2
        )
    all_lab = all(zone_has_lab)
    # V62.2 — gate: zones derived from geometry only (no NDVI/index evidence) are too weak
    # to anchor a VRA prescription; flag and require stronger zoning before execution.
    _GEOM_SEEDED = {"geometry_seeded_zoning_fallback", "geometry_seeded_sampling_fallback"}
    zoning_evidence_backed = any(
        str(z.get("zoning_method") or "").strip() not in _GEOM_SEEDED for z in zones
    )
    readiness_status = "proposal_only" if not has_lab else "review_required_before_export"
    warnings: list[str] = []
    if not zoning_evidence_backed:
        warnings.append(
            "المناطق مشتقّة من الهندسة فقط (بلا NDVI/مؤشّرات)؛ الوصفة ضعيفة زراعياً — "
            "زوّد شبكة NDVI أو مناطق مؤكّدة قبل أي اعتماد أو تصدير."
        )
    if not has_lab:
        warnings.append(
            "الوصفة تقديرية لأن نتائج المختبر غير مرفقة؛ لا تُصدّر للآلة قبل مراجعة مهندس زراعي أو نتائج تربة."
        )
    elif not all_lab:
        missing = ", ".join(
            z["zone_id"] for z, lab in zip(prescription_zones, zone_has_lab, strict=True) if not lab
        )
        warnings.append(
            f"بعض المناطق بلا نتائج مختبر مطابقة ({missing})؛ معدّلاتها تقديرية وتحتاج مراجعة مهندس زراعي."
        )
    if crop == "unspecified":
        warnings.append(
            "المحصول غير محدد؛ استخدم هدفاً عاماً ولا تعتمد الوصفة للتنفيذ قبل تحديد المحصول والمرحلة."
        )

    # V62.3 — raster-quality machine-readiness gate. When an NDVI-grid evidence object is
    # supplied (v62.3 contract), evaluate valid-pixel/coverage/cloud/staleness and surface a
    # structured verdict. Fail-closed: missing/low quality ⇒ machine_ready=False. This never
    # relaxes the existing (always-False) export gate — it only makes the raster-quality
    # dimension explicit and adds an Arabic warning when the imagery is too weak/stale.
    ndvi_evidence = ctx.get("ndvi_grid_evidence")
    raster_quality: dict[str, Any] | None = None
    if isinstance(ndvi_evidence, dict):
        zm = (
            "ndvi_kmeans_clustering"
            if zoning_evidence_backed
            else "geometry_seeded_zoning_fallback"
        )
        raster_quality = evaluate_machine_readiness(ndvi_evidence, zoning_method=zm)
        if not raster_quality["machine_ready"]:
            warnings.append(
                "جودة الصور دون عتبة التنفيذ الآليّ (بكسلات صالحة/تغطية غير كافية أو مناطق "
                "هندسية فقط)؛ لا تُصدَّر الوصفة للآلة قبل مشهد أعلى جودة."
            )
        elif "stale_scene" in raster_quality["warnings"]:
            warnings.append(
                "المشهد المستخدم قديم (تجاوز عتبة الحداثة)؛ راجع صورة أحدث قبل اعتماد الوصفة."
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
            "machine_export_formats": _available_export_formats(),
            "requires_agronomist_review": True,
            "source_lineage": _zone_source_lineage({}, ctx),
        },
        "prescription_zones": prescription_zones,
        "data_completeness": completeness,
        "readiness_gate": {
            "status": readiness_status,
            "reason": "lab_supported"
            if all_lab
            else ("partial_lab_support" if has_lab else "estimated_with_user_consent"),
            "zoning_evidence_backed": zoning_evidence_backed,
            "ready_for_machine_export": False,
            "raster_quality": raster_quality,  # v62.3 verdict (None if no NDVI evidence)
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
