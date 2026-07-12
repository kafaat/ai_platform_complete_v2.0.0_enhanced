"""Governed bridge from canonical water-ledger deficit to decision/execution lifecycle.

Default-off and fail-closed. A deficit creates exactly one deterministic candidate. Optional
policy auto-approval can continue through plan, authorization, and execution request, but only
when explicitly enabled and a concrete target device/task is configured.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _stable(prefix: str, *parts: object, size: int = 24) -> str:
    raw = "|".join(str(p) for p in parts)
    return prefix + hashlib.sha256(raw.encode()).hexdigest()[:size]


def bridge_enabled() -> bool:
    return _bool("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", False)


def auto_execution_enabled() -> bool:
    return _bool("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", False)


def deficit_threshold_mm() -> float:
    try:
        return max(0.0, float(os.getenv("WATER_DEFICIT_DECISION_THRESHOLD_MM", "10")))
    except ValueError:
        return 10.0


def build_candidate(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    ledger_date: date,
    entry: dict[str, Any],
    policy_version: str,
) -> tuple[str, str, dict[str, Any]]:
    lineage = _stable("wtrlin_", tenant_id, field_id, ledger_date.isoformat(), policy_version)
    decision_id = _stable("wtrdec_", tenant_id, field_id, ledger_date.isoformat(), policy_version)
    payload = {
        "decision_id": decision_id,
        "field_id": field_id,
        "season_id": season_id,
        "decision_type": "irrigation_deficit",
        "stage": "candidate",
        "confidence": entry.get("confidence"),
        "created_by": "water-ledger-governed-bridge",
        "decision_value": {
            "candidate_lineage_id": lineage,
            "policy_version": policy_version,
            "source_type": "water_ledger",
            "source_id": f"{field_id}:{ledger_date.isoformat()}",
            "ledger_date": ledger_date.isoformat(),
            "deficit_mm": entry.get("deficit_mm"),
            "depletion_mm": entry.get("depletion_mm"),
            "taw_mm": entry.get("taw_mm"),
            "raw_mm": entry.get("raw_mm"),
            "recommended_irrigation_mm": entry.get("deficit_mm"),
            "requires_human_review": not auto_execution_enabled(),
        },
    }
    return decision_id, lineage, payload


async def process_water_deficit(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    ledger_date: date,
    entry: dict[str, Any],
) -> dict[str, Any]:
    if not bridge_enabled():
        return {"status": "disabled"}
    deficit = entry.get("deficit_mm")
    if deficit is None or float(deficit) < deficit_threshold_mm():
        return {"status": "below_threshold"}

    from api.decision_service_client import (
        authorize_dispatch,
        create_execution_plan,
        create_execution_request,
        record_decision,
        review_decision,
    )

    policy = os.getenv("WATER_DEFICIT_POLICY_VERSION", "water-deficit.v1")
    decision_id, lineage, candidate = build_candidate(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        ledger_date=ledger_date,
        entry=entry,
        policy_version=policy,
    )
    recorded = await record_decision(candidate, tenant_id=tenant_id)
    if not recorded.get("persisted") or not recorded.get("authoritative"):
        return {"status": "candidate_not_authoritative", "decision_id": decision_id}

    result: dict[str, Any] = {
        "status": "candidate_created",
        "decision_id": decision_id,
        "candidate_lineage_id": lineage,
    }
    if not auto_execution_enabled():
        return result

    target_id = os.getenv("WATER_DEFICIT_EXECUTION_TARGET_ID", "").strip()
    target_type = os.getenv("WATER_DEFICIT_EXECUTION_TARGET_TYPE", "equipment").strip()
    if not target_id or target_type not in {"equipment", "task"}:
        return {**result, "status": "awaiting_target_configuration"}

    actor = os.getenv("WATER_DEFICIT_POLICY_ACTOR", "water-deficit-policy")
    review = await review_decision(
        decision_id,
        {
            "action": "approve",
            "reason": "approved by explicit water-deficit automation policy",
            "expected_state": "pending_approval",
            "candidate_lineage_id": lineage,
            "idempotency_key": _stable("wtrrev_", decision_id),
            "policy_version": policy,
        },
        tenant_id=tenant_id,
        reviewed_by=actor,
    )
    review_id = review.get("review_id")
    if not review_id:
        return {**result, "status": "review_failed"}

    now = datetime.now(UTC)
    plan = await create_execution_plan(
        decision_id,
        {
            "review_id": review_id,
            "candidate_lineage_id": lineage,
            "operation_type": "irrigation",
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=2)).isoformat(),
            "target_zone_ids": [],
            "required_resources": [{"target_id": target_id}],
            "constraints": {"max_irrigation_mm": float(deficit)},
            "safety_conditions": {"killswitch_required": True, "stale_telemetry_forbidden": True},
            "idempotency_key": _stable("wtrplan_", decision_id),
        },
        tenant_id=tenant_id,
        created_by=actor,
    )
    plan_id = plan.get("execution_plan_id")
    if not plan_id:
        return {**result, "status": "plan_failed", "review_id": review_id}

    auth = await authorize_dispatch(
        plan_id,
        {
            "decision_id": decision_id,
            "review_id": review_id,
            "candidate_lineage_id": lineage,
            "expected_plan_state": "planned",
            "policy_version": policy,
            "weather_snapshot_id": f"weather:{field_id}:{ledger_date.isoformat()}",
            "resource_snapshot_id": f"resource:{target_id}:{ledger_date.isoformat()}",
            "authorization_reason": "explicit auto-execution policy",
            "idempotency_key": _stable("wtrauth_", plan_id),
        },
        tenant_id=tenant_id,
        authorized_by=actor,
    )
    auth_id = auth.get("dispatch_authorization_id")
    if not auth_id:
        return {**result, "status": "authorization_failed", "execution_plan_id": plan_id}

    req = await create_execution_request(
        auth_id,
        {
            "dispatch_authorization_id": auth_id,
            "execution_plan_id": plan_id,
            "decision_id": decision_id,
            "target_type": target_type,
            "target_id": target_id,
            "operation_type": "irrigation",
            "command_payload": {
                "operation": "irrigate",
                "field_id": field_id,
                "season_id": season_id,
                "amount_mm": float(deficit),
                "idempotency_key": _stable("wtrcmd_", decision_id),
            },
            "idempotency_key": _stable("wtrreq_", auth_id),
        },
        tenant_id=tenant_id,
        requested_by=actor,
    )
    return {
        **result,
        "status": "execution_queued",
        "review_id": review_id,
        "execution_plan_id": plan_id,
        "dispatch_authorization_id": auth_id,
        "execution_request_id": req.get("execution_request_id"),
    }
