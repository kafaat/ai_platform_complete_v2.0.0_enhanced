"""Deterministic SoilProfileSnapshot composer from canonical evidence."""

from __future__ import annotations

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

POLICY_VERSION = "soil-profile-selection.v1"
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


def _score(row: dict[str, Any]) -> tuple[int, float, datetime, datetime]:
    quality = str(row.get("quality_status") or "")
    if quality == "rejected":
        return (-1, 0.0, datetime.min.replace(tzinfo=UTC), datetime.min.replace(tzinfo=UTC))
    quality_bonus = 10 if quality == "accepted" else 0
    property_name = str(row.get("property") or "")
    priorities = (
        _DYNAMIC_SOURCE_PRIORITY
        if property_name in _DYNAMIC_PROPERTIES
        else _STATIC_SOURCE_PRIORITY
    )
    return (
        priorities.get(str(row.get("source_type")), 0) + quality_bonus,
        float(row.get("confidence") or 0),
        row.get("observed_at") or datetime.min.replace(tzinfo=UTC),
        row.get("received_at") or datetime.min.replace(tzinfo=UTC),
    )


def compose_snapshot(
    *, tenant_id: str, field_id: str, observations: list[dict[str, Any]]
) -> SoilProfileSnapshot:
    usable = [
        row for row in observations if _score(row)[0] >= 0 and not bool(row.get("is_superseded"))
    ]
    groups: dict[tuple[float, float], dict[str, list[dict[str, Any]]]] = {}
    for row in usable:
        depth = (float(row.get("depth_from_cm") or 0), float(row.get("depth_to_cm") or 30))
        groups.setdefault(depth, {}).setdefault(str(row["property"]), []).append(row)

    layers: list[SoilLayer] = []
    evidence_ids: list[str] = []
    conflicts: list[dict[str, Any]] = []
    sources: set[str] = set()
    for (depth_from, depth_to), properties in sorted(groups.items()):
        projected: dict[str, SoilPropertyValue] = {}
        for property_name, candidates in properties.items():
            ranked = sorted(candidates, key=_score, reverse=True)
            selected = ranked[0]
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
                uncertainty=dict((selected.get("provenance") or {}).get("uncertainty") or {}),
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
    executable = all(
        [
            model_inputs.field_capacity is not None,
            model_inputs.wilting_point is not None,
            model_inputs.rootable_depth_cm is not None,
        ]
    )
    now = datetime.now(UTC)
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
            "passed": True,
            "executable": executable,
            "reasons": [] if executable else ["soil_hydraulic_inputs_incomplete"],
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
    draft["profile_hash"] = canonical_soil_profile_hash(draft)
    return SoilProfileSnapshot.model_validate(draft)
