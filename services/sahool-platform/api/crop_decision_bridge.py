"""Explicit Crop Intelligence -> Decision Service candidate bridge.

The bridge never approves or dispatches.  It only records a reviewable
candidate when the caller explicitly requests submission.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api.decision_service_client import record_decision

_ENGINE_DOWN_CODES = {502, 503, 504}


def build_crop_decision_candidate(crop_state: dict[str, Any]) -> dict[str, Any]:
    context = crop_state.get("recommendation_context")
    if not isinstance(context, dict):
        raise ValueError("crop recommendation context is missing")
    if context.get("is_decision") is not False:
        raise ValueError("crop recommendation context must not be a final decision")
    field_id = crop_state.get("field_id")
    season_id = crop_state.get("season_id")
    if not field_id or not season_id:
        raise ValueError("field_id and season_id are required")

    evidence_ids = list(
        dict.fromkeys((crop_state.get("evidence_ids") or []) + (context.get("evidence_ids") or []))
    )
    return {
        "decision_type": "crop_management",
        "field_id": field_id,
        "season_id": season_id,
        "recommendation": {
            "urgency": context.get("urgency"),
            "crop_health": context.get("crop_health"),
            "water_need": context.get("water_need"),
            "stress_summary": context.get("stress_summary"),
            "phenology": crop_state.get("phenology"),
        },
        "confidence": crop_state.get("confidence"),
        "evidence_ids": evidence_ids,
        "provenance": {
            "crop_engine_version": crop_state.get("engine_version"),
            "crop_schema": crop_state.get("schema"),
            "stress_memory_version": (crop_state.get("stress_memory") or {}).get("product_version"),
        },
        "status": "pending_approval",
        "approval_required": True,
        "calibrated": bool(crop_state.get("calibrated", False)),
    }


async def submit_crop_decision_candidate(
    crop_state: dict[str, Any],
    *,
    tenant_id: str | None,
    submit: bool = False,
) -> dict[str, Any]:
    """Return explicit approval state and submit only when ``submit=True``."""
    candidate = build_crop_decision_candidate(crop_state)
    if not submit:
        return {
            "approval_state": "not_submitted",
            "decision_id": None,
            "candidate": candidate,
            "limitations": [],
        }
    try:
        result = await record_decision(candidate, tenant_id=tenant_id)
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            return {
                "approval_state": "submit_unavailable",
                "decision_id": None,
                "candidate": candidate,
                "limitations": ["decision-service unavailable — candidate not submitted"],
            }
        raise
    return {
        "approval_state": "pending_approval",
        "decision_id": result.get("decision_id") or result.get("id"),
        "candidate": candidate,
        "limitations": [],
    }
