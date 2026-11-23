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
# G9 — the lab owner stores numeric analytes under these names (sahool-platform
# ``lab_store.soil_result_analytes``); its approved results arrive with them unchanged.
_LAB_ANALYTES |= {
    "ec_dsm",
    "organic_matter_pct",
    "nitrogen_mg_kg",
    "phosphorus_mg_kg",
    "potassium_mg_kg",
    "cec_cmol_kg",
    "calcium_carbonate_pct",
    "sand_pct",
    "silt_pct",
    "clay_pct",
}
# W0-12 — the only source of lab support: an evidence-context block built by the server
# from the lab owner's approved results. ``soil_lab_results`` is written by
# sahool-platform only (docs/architecture/db_ownership.yml).
_OWNER_LAB_BLOCK = "approved_soil_lab"
_LAB_RESULT_OWNER = "sahool-platform"
# Tool parameters the model may send that used to grant lab support; now ignored.
_MODEL_LAB_PARAMS = ("lab_results", "soil_lab_results")
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


def _zone_source_lineage(
    zone: dict[str, Any],
    evidence_context: dict[str, Any],
    lab_result_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Preserve evidence identity; never turn it into an execution authorization.

    ``lab_result_ids`` come only from the owner's lab block; a ``lab_result_ids`` key the
    model wrote into a zone's lineage is dropped, never repeated as lab provenance.
    """
    lineage = zone.get("source_lineage") if isinstance(zone.get("source_lineage"), dict) else {}
    out = dict(lineage)
    out.pop("lab_result_ids", None)
    if lab_result_ids:
        out["lab_result_ids"] = sorted(set(lab_result_ids))
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


def _owner_lab_records(
    evidence_context: dict[str, Any], field_id: str | None
) -> list[dict[str, Any]]:
    """Approved lab records the lab owner issued, read only from ``evidence_context``.

    W0-12: lab support is never taken from tool parameters. The model writes the
    parameters, so ``params["lab_results"]`` (or ``soil_lab_results``) is ignored. The
    only accepted source is the server-built context block
    ``evidence_context["approved_soil_lab"]``::

        {"owner": "sahool-platform", "field_id": "<field>",
         "results": [{"result_id": "...", "analyte": "p", "value": 12,
                      "quality_status": "approved", "zone_id": "<optional>"}]}

    ``owner`` must name the writer of ``soil_lab_results`` (docs/architecture/
    db_ownership.yml). A record counts only with a non-empty ``result_id``,
    ``quality_status == "approved"`` and a finite numeric value for a known analyte. A
    block for another field is ignored, and so is a block naming a tenant other than the
    context's ``tenant_id``. Anything else is no lab evidence (fail closed).
    """
    block = evidence_context.get(_OWNER_LAB_BLOCK)
    if not isinstance(block, dict) or block.get("owner") != _LAB_RESULT_OWNER:
        return []
    block_field = block.get("field_id")
    if block_field is not None and (field_id is None or str(block_field) != str(field_id)):
        return []
    block_tenant = block.get("tenant_id")
    context_tenant = evidence_context.get("tenant_id")
    if block_tenant is not None and (
        context_tenant is None or str(block_tenant) != str(context_tenant)
    ):
        return []
    results = block.get("results")
    if not isinstance(results, list):
        return []
    accepted: list[dict[str, Any]] = []
    for record in results:
        if not isinstance(record, dict):
            continue
        result_id = record.get("result_id")
        if not isinstance(result_id, str) or not result_id.strip():
            continue
        if record.get("quality_status") != "approved":
            continue
        if not _is_analyte_record(record):
            continue
        accepted.append(record)
    return accepted


def _lab_zone_ids(
    records: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({zone_id: result ids}, field-level composite result ids).

    A record with a ``zone_id`` supports only that zone; a record without one is a
    field-level composite and supports every zone.
    """
    zone_ids: dict[str, list[str]] = {}
    field_level: list[str] = []
    for record in records:
        result_id = str(record["result_id"]).strip()
        zid = str(record.get("zone_id") or "").strip()
        if zid:
            zone_ids.setdefault(zid, []).append(result_id)
        else:
            field_level.append(result_id)
    return zone_ids, field_level


_LAB_BASIS_FIELDS = (
    "result_id",
    "analyte",
    "value",
    "unit",
    "method_code",
    "sample_id",
    "sampled_on",
    "approved_at",
    "approval_ref",
    "zone_id",
)


def _laboratory_basis(records: list[dict[str, Any]], used_ids: set[str]) -> dict[str, Any]:
    """The approved lab results the prescription used, as the owner issued them.

    Each used record keeps its method, unit, sampling date and approval reference. No
    used record ⇒ the prescription says it was computed without laboratory data.
    """
    used = [
        {key: record.get(key) for key in _LAB_BASIS_FIELDS if record.get(key) is not None}
        for record in records
        if str(record["result_id"]).strip() in used_ids
    ]
    if used:
        return {
            "status": "approved_laboratory_results",
            "owner": _LAB_RESULT_OWNER,
            "results": used,
        }
    return {
        "status": "computed_without_laboratory_data",
        "statement_ar": "حُسبت هذه الوصفة دون بيانات مختبر تربة معتمدة لهذا الحقل.",
        "results": [],
    }


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
    ctx = evidence_context if isinstance(evidence_context, dict) else {}
    owner_lab = _owner_lab_records(ctx, field_id)
    lab_zone_ids, field_level_lab = _lab_zone_ids(owner_lab)
    zone_lab_ids = [
        field_level_lab + lab_zone_ids.get(_zone_id(zone, idx), [])
        for idx, zone in enumerate(used_zones)
    ]
    zone_has_lab = [bool(ids) for ids in zone_lab_ids]
    has_lab = any(zone_has_lab)
    model_lab_ignored = any(params.get(key) for key in _MODEL_LAB_PARAMS)
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
            model_lab_results_ignored=model_lab_ignored,
        )

    base_rate = _base_rate(params, product_type)
    crop = str(params.get("crop") or params.get("crop_hint") or "unspecified")
    target_yield = _as_float(params.get("target_yield"))
    lab_confidence = _confidence(completeness["score"], True)
    estimated_confidence = _confidence(_data_completeness(params, zones, False)["score"], False)

    classes = [c for c in zone_classes if c is not None]  # all classified past the gate
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
        if zone_lab_ids[idx]:
            prescription_zones[-1]["source_lineage"]["lab_result_ids"] = sorted(
                set(zone_lab_ids[idx])
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
    laboratory_basis = _laboratory_basis(owner_lab, {rid for ids in zone_lab_ids for rid in ids})
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
    if model_lab_ignored:
        warnings.append(
            "نتائج المختبر المرسلة في معاملات الأداة لا تُعتمد دليلاً؛ دعم المختبر يُقرأ فقط من "
            "النتائج المعتمدة الصادرة عن مالك بيانات المختبر."
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
            "source_lineage": _zone_source_lineage(
                {}, ctx, [rid for ids in zone_lab_ids for rid in ids]
            ),
            "laboratory_basis": laboratory_basis,
        },
        "prescription_zones": prescription_zones,
        "data_completeness": completeness,
        "readiness_gate": {
            "status": readiness_status,
            "reason": "lab_supported"
            if all_lab
            else ("partial_lab_support" if has_lab else "estimated_with_user_consent"),
            "zoning_evidence_backed": zoning_evidence_backed,
            "lab_evidence_source": _OWNER_LAB_BLOCK if has_lab else None,
            "laboratory_basis": laboratory_basis["status"],
            "model_lab_results_ignored": model_lab_ignored,
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
