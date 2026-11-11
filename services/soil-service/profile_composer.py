"""Deterministic SoilProfileSnapshot composer from canonical evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from shared.contracts.soil import (
    SoilEvidenceClass,
    SoilEvidenceLevel,
    SoilLayer,
    SoilModelInputs,
    SoilProfileSnapshot,
    SoilProfileStatus,
    SoilPropertyValue,
    canonical_soil_profile_hash,
)
from shared.contracts.soil.moisture_policy import (
    DYNAMIC_PROPERTY_TTL_S,
    FRESH,
    QUALITY_ACCEPTED,
    classify_freshness,
    normalize_quality,
    quality_tier,
    reading_age_s,
)

#: v2 (SOIL-MOISTURE-ELIGIBILITY-01): dynamic properties rank freshness (shared sensor TTL)
#: > quality tier > recency > source > confidence; v1 ranked source+10·accepted, then
#: confidence, then recency — so a 30-day-old reading or an uncalibrated sensor could win.
POLICY_VERSION = "soil-profile-selection.v2"
_STATIC_SOURCE_PRIORITY = {
    "laboratory": 100,
    "field": 80,
    "sensor": 55,
    "analog_fields": 40,
    "soilgrids": 30,
    "smartphone": 25,
    "remote_sensing": 20,
    "model": 15,
}
_DYNAMIC_SOURCE_PRIORITY = {
    "sensor": 100,
    "field": 85,
    "model": 60,
    "remote_sensing": 45,
    "laboratory": 35,
    "smartphone": 25,
    "analog_fields": 15,
    "soilgrids": 10,
}
_DYNAMIC_PROPERTIES = {"soil_moisture", "soil_temperature", "pore_water_ec"}
_CLASS_BY_SOURCE = {
    "laboratory": SoilEvidenceClass.MEASURED,
    "sensor": SoilEvidenceClass.MEASURED,
    "field": SoilEvidenceClass.MEASURED,
    "smartphone": SoilEvidenceClass.PROXY,
    "analog_fields": SoilEvidenceClass.ANALOG_ESTIMATE,
    "soilgrids": SoilEvidenceClass.MODELLED,
    "remote_sensing": SoilEvidenceClass.PROXY,
    "model": SoilEvidenceClass.DERIVED,
}
_UNITS = {
    "soil_moisture": "%",
    "soil_temperature": "degC",
    "ph": "pH",
    "ec": "dS/m",
    "nitrogen": "mg/kg",
    "phosphorus": "mg/kg",
    "potassium": "mg/kg",
    "field_capacity": "m3/m3",
    "wilting_point": "m3/m3",
    "bulk_density": "g/cm3",
    "rootable_depth": "cm",
}


def _provenance_uncertainty(row: dict[str, Any]) -> dict[str, Any]:
    """Extract the uncertainty map from an observation's provenance.

    Provenance is a dict in-process but a JSONB string from PostgreSQL (no codec registered),
    so normalise before access to avoid ``'str' object has no attribute 'get'``.
    """
    prov = row.get("provenance") or {}
    if isinstance(prov, str):
        prov = json.loads(prov) if prov else {}
    return dict(prov.get("uncertainty") or {}) if isinstance(prov, dict) else {}


_MIN_TS = datetime.min.replace(tzinfo=UTC)


def _ts(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return _MIN_TS
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_rejected(row: dict[str, Any]) -> bool:
    return normalize_quality(row.get("quality_status")) == "rejected"


def _depth(row: dict[str, Any]) -> tuple[float, float] | None:
    """Layer bucket; a row without a declared depth is not silently bucketed into 0–30."""
    depth_from, depth_to = row.get("depth_from_cm"), row.get("depth_to_cm")
    if depth_from is None or depth_to is None:
        return None
    return (float(depth_from), float(depth_to))


def _dynamic_freshness(row: dict[str, Any], now: datetime) -> str:
    return classify_freshness(reading_age_s(row.get("observed_at"), now), DYNAMIC_PROPERTY_TTL_S)


def _score(row: dict[str, Any], now: datetime | None = None) -> tuple:
    """Ranking key (higher wins) within one property's candidates.

    Static properties keep v1 semantics. Dynamic properties (soil moisture/temperature,
    pore-water EC) rank a proven-fresh reading above any stale one, then quality tier
    (accepted > uncalibrated > suspect) above source priority, then recency — so an
    uncalibrated sensor no longer beats an accepted field reading, and a 30-day-old
    high-confidence reading no longer beats today's.
    """
    if _is_rejected(row):
        return (-1,)
    property_name = str(row.get("property") or "")
    confidence = float(row.get("confidence") or 0)
    if property_name in _DYNAMIC_PROPERTIES:
        fresh = _dynamic_freshness(row, now or datetime.now(UTC)) == FRESH
        return (
            1 if fresh else 0,
            quality_tier(row.get("quality_status")),
            _ts(row.get("observed_at")),
            _DYNAMIC_SOURCE_PRIORITY.get(str(row.get("source_type")), 0),
            confidence,
            _ts(row.get("received_at")),
        )
    quality_bonus = 10 if normalize_quality(row.get("quality_status")) == QUALITY_ACCEPTED else 0
    return (
        _STATIC_SOURCE_PRIORITY.get(str(row.get("source_type")), 0) + quality_bonus,
        confidence,
        _ts(row.get("observed_at")),
        _ts(row.get("received_at")),
    )


def _decision_eligible(row: dict[str, Any], now: datetime) -> bool:
    """Selected evidence that may back a decision: accepted, and fresh when dynamic."""
    if normalize_quality(row.get("quality_status")) != QUALITY_ACCEPTED:
        return False
    if str(row.get("property") or "") in _DYNAMIC_PROPERTIES:
        return _dynamic_freshness(row, now) == FRESH
    return True


def compose_snapshot(
    *,
    tenant_id: str,
    field_id: str,
    observations: list[dict[str, Any]],
    now: datetime | None = None,
) -> SoilProfileSnapshot:
    now = now or datetime.now(UTC)
    usable: list[dict[str, Any]] = []
    groups: dict[tuple[float, float], dict[str, list[dict[str, Any]]]] = {}
    for row in observations:
        depth = _depth(row)
        if depth is None or _is_rejected(row) or bool(row.get("is_superseded")):
            continue
        usable.append(row)
        groups.setdefault(depth, {}).setdefault(str(row["property"]), []).append(row)

    layers: list[SoilLayer] = []
    evidence_ids: list[str] = []
    conflicts: list[dict[str, Any]] = []
    sources: set[str] = set()
    eligible_selected = 0
    gate_reasons: list[str] = []
    for (depth_from, depth_to), properties in sorted(groups.items()):
        projected: dict[str, SoilPropertyValue] = {}
        for property_name, candidates in properties.items():
            ranked = sorted(candidates, key=lambda item: _score(item, now), reverse=True)
            selected = ranked[0]
            if _decision_eligible(selected, now):
                eligible_selected += 1
            elif property_name in _DYNAMIC_PROPERTIES:
                reason = (
                    f"{property_name}_not_fresh"
                    if _dynamic_freshness(selected, now) != FRESH
                    else f"{property_name}_quality_not_accepted"
                )
                if reason not in gate_reasons:
                    gate_reasons.append(reason)
            alternatives = [
                {
                    "observation_id": item["observation_id"],
                    "value": item.get("value_json"),
                    "source_type": item.get("source_type"),
                    "confidence": float(item.get("confidence") or 0),
                }
                for item in ranked[1:5]
            ]
            values = {str(item.get("value_json")) for item in ranked}
            if len(values) > 1:
                conflicts.append(
                    {
                        "property": property_name,
                        "depth_from_cm": depth_from,
                        "depth_to_cm": depth_to,
                        "selected_observation_id": selected["observation_id"],
                        "candidate_count": len(ranked),
                    }
                )
            source_type = str(selected["source_type"])
            sources.add(source_type)
            evidence_ids.append(str(selected["observation_id"]))
            projected[property_name] = SoilPropertyValue(
                value=selected.get("value_json"),
                unit=selected.get("unit") or _UNITS.get(property_name),
                evidence_class=_CLASS_BY_SOURCE.get(source_type, SoilEvidenceClass.DERIVED),
                selected_source=source_type,
                source_id=selected.get("source_id"),
                observed_at=selected.get("observed_at"),
                confidence=float(selected.get("confidence") or 0),
                verification_required=source_type not in {"laboratory", "sensor", "field"},
                uncertainty=_provenance_uncertainty(selected),
                alternatives=alternatives,
            )
        layers.append(
            SoilLayer(depth_from_cm=depth_from, depth_to_cm=depth_to, properties=projected)
        )

    if not layers:
        raise ValueError("soil_profile_no_usable_observations")

    property_names = {name for layer in layers for name in layer.properties}
    core = {"ph", "ec", "soil_moisture", "texture", "field_capacity", "wilting_point"}
    completeness = round(min(1.0, len(property_names & core) / len(core)), 4)

    if "laboratory" in sources:
        status = SoilProfileStatus.VERIFIED
        evidence_level = SoilEvidenceLevel.LAB_VERIFIED
    elif sources & {"sensor", "field"}:
        status = SoilProfileStatus.FIELD_GUIDED
        evidence_level = SoilEvidenceLevel.FIELD_OBSERVED
    elif "analog_fields" in sources:
        status = SoilProfileStatus.REGIONAL_GUIDED
        evidence_level = SoilEvidenceLevel.ANALOG_GUIDED
    elif sources & {"soilgrids", "remote_sensing", "model", "smartphone"}:
        status = SoilProfileStatus.ENHANCED_BASELINE
        evidence_level = SoilEvidenceLevel.MODELLED
    else:
        status = SoilProfileStatus.BASELINE
        evidence_level = SoilEvidenceLevel.BASELINE_ONLY

    flattened = {name: value for layer in layers for name, value in layer.properties.items()}

    def _num(name: str):
        item = flattened.get(name)
        return float(item.value) if item and isinstance(item.value, (int, float)) else None

    model_inputs = SoilModelInputs(
        field_capacity=_num("field_capacity"),
        wilting_point=_num("wilting_point"),
        rootable_depth_cm=_num("rootable_depth"),
        bulk_density=_num("bulk_density"),
    )
    # The gate passes only when at least one selected value is decision-eligible (accepted,
    # and fresh for dynamic properties) — it was hard-coded ``True``.
    passed = eligible_selected > 0
    if not passed:
        gate_reasons.insert(0, "soil_profile_no_decision_eligible_evidence")
    executable = passed and all(
        [
            model_inputs.field_capacity is not None,
            model_inputs.wilting_point is not None,
            model_inputs.rootable_depth_cm is not None,
        ]
    )
    # Irrigation scheduling reads current moisture; stale or non-accepted moisture cannot back it.
    moisture_blocks_schedule = any(r.startswith("soil_moisture_") for r in gate_reasons)
    draft = {
        "contract_version": "soil-profile.v1",
        "profile_id": f"sp_{uuid4().hex}",
        "profile_hash": "0" * 64,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "zone_id": None,
        "effective_at": max(row["observed_at"] for row in usable),
        "data_available_at": now,
        "status": status,
        "evidence_level": evidence_level,
        "layers": [layer.model_dump(mode="json") for layer in layers],
        "completeness_score": completeness,
        "quality_gate": {
            "passed": passed,
            "executable": executable,
            "reasons": gate_reasons + ([] if executable else ["soil_hydraulic_inputs_incomplete"]),
        },
        "conflicts": conflicts,
        "allowed_use": (
            [
                "baseline_profile",
                "sampling_plan",
                "preliminary_crop_suitability",
                "field_investigation",
            ]
            + (
                [
                    "conservative_irrigation_guidance",
                    "crop_selection",
                    "salinity_management_guidance",
                    "irrigation_schedule",
                ]
                if evidence_level
                in {
                    SoilEvidenceLevel.FIELD_OBSERVED,
                    SoilEvidenceLevel.LAB_VERIFIED,
                    SoilEvidenceLevel.OPERATIONAL_VERIFIED,
                }
                else []
            )
            + (
                [
                    "fertilizer_rate",
                    "gypsum_rate",
                    "leaching_requirement",
                    "subsurface_drainage_design",
                    "high_risk_reclamation",
                    "automatic_irrigation_execution",
                ]
                if evidence_level
                in {SoilEvidenceLevel.LAB_VERIFIED, SoilEvidenceLevel.OPERATIONAL_VERIFIED}
                and executable
                else []
            )
        ),
        "blocked_use": (
            []
            if evidence_level
            in {SoilEvidenceLevel.LAB_VERIFIED, SoilEvidenceLevel.OPERATIONAL_VERIFIED}
            and executable
            else [
                "fertilizer_rate",
                "gypsum_rate",
                "leaching_requirement",
                "subsurface_drainage_design",
                "high_risk_reclamation",
                "automatic_irrigation_execution",
            ]
        ),
        "evidence_ids": sorted(set(evidence_ids)),
        "selection_policy_version": POLICY_VERSION,
        "model_inputs": model_inputs.model_dump(mode="json"),
    }
    if moisture_blocks_schedule:
        draft["allowed_use"] = [u for u in draft["allowed_use"] if u != "irrigation_schedule"]
        draft["blocked_use"] = [*draft["blocked_use"], "irrigation_schedule"]
    draft["profile_hash"] = canonical_soil_profile_hash(draft)
    return SoilProfileSnapshot.model_validate(draft)
