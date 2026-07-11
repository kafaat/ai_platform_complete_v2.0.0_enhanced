from __future__ import annotations

from typing import Any

_SCHEMA = "crop_recommendation_context.v1"


def build_recommendation_context(
    *,
    phenology: dict[str, Any],
    crop_water: dict[str, Any],
    stress_flags: list[dict[str, str]],
    stress_memory: dict[str, Any],
    component_status: dict[str, str],
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a decision-ready crop context without making a decision."""
    urgent_factors: list[str] = []
    if crop_water.get("irrigation_urgency") == "high":
        urgent_factors.append("water_urgency_high")
    urgent_factors.extend(
        flag["code"] for flag in stress_flags if flag.get("code") in {"heat_stress", "frost_risk"}
    )

    status = "available"
    limitations: list[str] = []
    if component_status.get("phenology") == "unavailable":
        status = "degraded"
        limitations.append("phenology_unavailable")
    if crop_water.get("status") == "unavailable":
        status = "degraded"
        limitations.append("crop_water_unavailable")

    return {
        "schema": _SCHEMA,
        "status": status,
        "stage": phenology.get("current_stage") or phenology.get("stage"),
        "season_progress": phenology.get("progress"),
        "crop_water": crop_water,
        "active_stress_codes": list(
            dict.fromkeys(flag.get("code") for flag in stress_flags if flag.get("code"))
        ),
        "stress_memory_state": stress_memory.get("recovery_state"),
        "urgency": "high" if urgent_factors else "normal",
        "urgent_factors": list(dict.fromkeys(urgent_factors)),
        "confidence": "medium" if status == "available" else "low",
        "evidence_ids": list(dict.fromkeys(source_ids or [])),
        "limitations": limitations,
        "decision_boundary": {
            "is_decision": False,
            "consumer": "decision-service",
            "approval_required": True,
        },
    }
