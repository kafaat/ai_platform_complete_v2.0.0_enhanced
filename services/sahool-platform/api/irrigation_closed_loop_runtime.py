"""Durable closed-loop return path for irrigation execution evidence.

Loads an authorized run, controller receipts and measured observations from the
server-owned database, derives canonical as-applied truth, then idempotently
reconciles only verified measured water into the daily water ledger.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from api.canonical_as_applied_irrigation import (
    as_applied_truth_to_water_ledger_event,
    build_as_applied_observation,
    build_authorized_irrigation_plan,
    build_canonical_as_applied_irrigation_truth,
    build_execution_receipt,
)
from api.event_bus import EventSource


def _rowdict(row: Any) -> dict[str, Any]:
    return dict(row or {})


async def _load_plan(conn, run_id: str):
    row = await conn.fetchrow("SELECT * FROM as_applied_irrigation_runs WHERE id=$1::uuid", run_id)
    if row is None:
        return None
    r = _rowdict(row)
    planned_start = r.get("planned_start_at") or r.get("created_at")
    planned_end = r.get("planned_end_at")
    if planned_end is None and planned_start is not None:
        planned_end = planned_start
        # Legacy run schema may not store the window; the caller must have persisted
        # an explicit end in a newer schema. Fail closed instead of inventing duration.
        return {"blocked": "AUTHORIZED_PLAN_TIME_WINDOW_REQUIRED"}
    return build_authorized_irrigation_plan(
        tenant_id=str(r["tenant_id"]),
        field_id=str(r["field_id"]),
        season_id=str(r["season_id"]),
        machine_id=str(r["machine_id"]),
        controller_id=str(r["controller_id"]),
        decision_id=str(r["decision_id"]),
        authorization_id=str(r["authorization_id"]),
        execution_plan_id=str(r["execution_plan_id"]),
        planned_start_at=planned_start,
        planned_end_at=planned_end,
        planned_depth_mm=float(r["planned_depth_mm"]),
        planned_volume_m3=float(
            r.get("planned_volume_m3")
            or float(r["planned_depth_mm"]) * float(r["planned_area_ha"]) * 10.0
        ),
        planned_area_ha=float(r["planned_area_ha"]),
        irrigation_capability_digest=str(r["irrigation_capability_digest"]),
        commissioning_certification_digest=str(r["commissioning_certification_digest"]),
        decision_content_digest=str(r["decision_content_digest"]),
    )


async def _load_receipts(conn, *, run_id: str, plan):
    rows = await conn.fetch(
        "SELECT * FROM as_applied_irrigation_receipts WHERE run_id=$1::uuid ORDER BY sequence_number",
        run_id,
    )
    return [
        build_execution_receipt(
            tenant_id=plan.tenant_id,
            field_id=plan.field_id,
            machine_id=plan.machine_id,
            controller_id=str(row["controller_id"]),
            execution_plan_id=plan.execution_plan_id,
            receipt_id=str(row["receipt_id"]),
            state=str(row["state"]),
            sequence_number=int(row["sequence_number"]),
            observed_at=row["observed_at"],
            controller_command_digest=str(row["controller_command_digest"]),
            payload_digest=str(row["payload_digest"]),
        )
        for row in rows
    ]


async def _load_observations(conn, *, run_id: str, plan):
    rows = await conn.fetch(
        "SELECT * FROM as_applied_irrigation_observations WHERE run_id=$1::uuid ORDER BY sequence_number",
        run_id,
    )
    return [
        build_as_applied_observation(
            tenant_id=plan.tenant_id,
            field_id=plan.field_id,
            machine_id=plan.machine_id,
            controller_id=str(row["controller_id"]),
            execution_plan_id=plan.execution_plan_id,
            observation_type=str(row["observation_type"]),
            sequence_number=int(row["sequence_number"]),
            observed_at=row["observed_at"],
            value=float(row["value"]),
            unit=str(row["unit"]),
            source_message_id=str(row["source_message_id"]),
            payload_digest=str(row["payload_digest"]),
        )
        for row in rows
    ]


async def reconcile_irrigation_run(
    conn,
    *,
    run_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Idempotently reconcile one execution run into canonical truth and ledger."""
    plan = await _load_plan(conn, run_id)
    if plan is None:
        return {"status": "blocked", "reason": "AS_APPLIED_RUN_NOT_FOUND"}
    if isinstance(plan, dict):
        return {"status": "blocked", "reason": plan["blocked"]}

    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"irrigation-run:{run_id}")
    existing = await conn.fetchrow(
        "SELECT payload FROM irrigation_water_ledger_reconciliations WHERE run_id=$1::uuid",
        run_id,
    )
    if existing is not None:
        payload = dict(existing["payload"] or {})
        payload["idempotent_replay"] = True
        return payload

    receipts = await _load_receipts(conn, run_id=run_id, plan=plan)
    observations = await _load_observations(conn, run_id=run_id, plan=plan)
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan,
        receipts=receipts,
        observations=observations,
        now=now or datetime.now(UTC),
    )
    truth_dict = truth.to_dict()
    await conn.execute(
        """
        INSERT INTO canonical_as_applied_irrigation_truths (
            tenant_id, run_id, status, verification_status, actual_start_at,
            actual_end_at, actual_runtime_minutes, actual_depth_mm, actual_area_ha,
            mean_flow_lps, mean_pressure_bar, position_coverage_percent,
            volume_variance_percent, depth_variance_mm, depth_variance_percent,
            completion_ratio, water_ledger_eligible, source_lineage,
            blocking_reasons, limitations, as_applied_digest, snapshot
        ) VALUES (
            current_setting('app.current_tenant')::uuid, $1::uuid, $2, $3, $4, $5,
            $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
            $17::jsonb, $18::jsonb, $19::jsonb, $20, $21::jsonb
        ) ON CONFLICT (tenant_id, as_applied_digest) DO NOTHING
        """,
        run_id,
        truth.status,
        truth.verification_status,
        truth.actual_start_at,
        truth.actual_end_at,
        truth.actual_runtime_minutes,
        truth.actual_depth_mm,
        truth.actual_area_ha,
        truth.mean_flow_lps,
        truth.mean_pressure_bar,
        truth.position_coverage_percent,
        truth.volume_variance_percent,
        truth.depth_variance_mm,
        truth.depth_variance_percent,
        truth.completion_ratio,
        truth.water_ledger_eligible,
        json.dumps(truth.source_lineage),
        json.dumps(truth.blocking_reasons),
        json.dumps(truth.limitations),
        truth.as_applied_digest,
        json.dumps(truth_dict, default=str),
    )

    ledger_event = as_applied_truth_to_water_ledger_event(truth)
    if ledger_event.get("status") != "available":
        return {
            "status": "blocked",
            "reason": "AS_APPLIED_TRUTH_NOT_LEDGER_ELIGIBLE",
            "truth": truth_dict,
        }

    observed = datetime.fromisoformat(str(ledger_event["observed_at"]).replace("Z", "+00:00"))
    ledger_date = observed.date()
    before = await conn.fetchval(
        "SELECT depletion_mm FROM water_ledger WHERE field_id=$1 ORDER BY ledger_date DESC LIMIT 1",
        plan.field_id,
    )
    applied_depth = float(ledger_event["applied_depth_mm"] or 0.0)
    depletion_after = None if before is None else max(0.0, float(before) - applied_depth)
    await conn.execute(
        """
        INSERT INTO water_ledger (
            tenant_id, field_id, ledger_date, irrigation_mm, depletion_mm,
            decision, created_by
        ) VALUES (
            current_setting('app.current_tenant')::uuid, $1, $2, $3, $4,
            'measured_as_applied', $5
        ) ON CONFLICT (field_id, ledger_date) DO UPDATE SET
            irrigation_mm = COALESCE(water_ledger.irrigation_mm, 0) + EXCLUDED.irrigation_mm,
            depletion_mm = EXCLUDED.depletion_mm,
            decision = EXCLUDED.decision,
            created_by = EXCLUDED.created_by,
            updated_at = now()
        """,
        plan.field_id,
        ledger_date,
        applied_depth,
        depletion_after,
        f"as_applied:{truth.as_applied_digest}",
    )
    result = {
        "status": "reconciled",
        "reconciled": True,
        "run_id": run_id,
        "field_id": plan.field_id,
        "season_id": plan.season_id,
        "execution_plan_id": plan.execution_plan_id,
        "as_applied_digest": truth.as_applied_digest,
        "water_ledger_event_digest": ledger_event["ledger_event_digest"],
        "authorization_digest": plan.plan_digest,
        "execution_plan_digest": plan.plan_digest,
        "ledger_date": ledger_date.isoformat(),
        "applied_depth_mm": applied_depth,
        "applied_volume_m3": float(ledger_event["applied_volume_m3"] or 0.0),
        "depletion_before_mm": None if before is None else float(before),
        "depletion_after_mm": depletion_after,
        "truth": truth_dict,
    }
    await conn.execute(
        """
        INSERT INTO irrigation_water_ledger_reconciliations (
            tenant_id, run_id, field_id, season_id, execution_plan_id,
            as_applied_digest, ledger_event_digest, ledger_date,
            applied_depth_mm, applied_volume_m3, depletion_before_mm,
            depletion_after_mm, status, payload, reconciled_at
        ) VALUES (
            current_setting('app.current_tenant')::uuid, $1::uuid, $2, $3, $4,
            $5, $6, $7, $8, $9, $10, $11, 'reconciled', $12::jsonb, now()
        ) ON CONFLICT (tenant_id, run_id) DO NOTHING
        """,
        run_id,
        plan.field_id,
        plan.season_id,
        plan.execution_plan_id,
        truth.as_applied_digest,
        ledger_event["ledger_event_digest"],
        ledger_date,
        applied_depth,
        float(ledger_event["applied_volume_m3"] or 0.0),
        before,
        depletion_after,
        json.dumps(result, default=str),
    )
    return result


async def finalize_irrigation_closed_loop(
    conn,
    *,
    run_id: str,
    measured_at: datetime,
    expected_depletion_after_mm: float,
    source_digests: dict[str, str],
    minimum_samples: int = 5,
    water_use_efficiency_kg_m3: float | None = None,
    energy_kwh: float | None = None,
    stress_days_observed: float | None = None,
    yield_t_ha: float | None = None,
) -> dict[str, Any]:
    """Complete the verified irrigation loop atomically without auto-adjusting models."""
    from api.irrigation_closed_loop_learning import (
        build_irrigation_closed_loop_record,
        build_irrigation_outcome_evidence,
        propose_governed_irrigation_learning,
    )

    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext($1))", f"irrigation-learning:{run_id}"
    )
    existing = await conn.fetchrow(
        "SELECT payload FROM irrigation_closed_loop_records WHERE execution_plan_id=(SELECT execution_plan_id FROM as_applied_irrigation_runs WHERE id=$1::uuid)",
        run_id,
    )
    if existing is not None:
        return {
            "status": "replayed",
            "idempotent_replay": True,
            "payload": dict(existing["payload"] or {}),
        }

    reconciliation = await reconcile_irrigation_run(conn, run_id=run_id, now=measured_at)
    if reconciliation.get("status") != "reconciled":
        return {
            "status": "blocked",
            "reason": reconciliation.get("reason", "IRRIGATION_RECONCILIATION_REQUIRED"),
        }

    plan = await _load_plan(conn, run_id)
    if plan is None or isinstance(plan, dict):
        return {"status": "blocked", "reason": "AUTHORIZED_PLAN_REQUIRED"}
    truth = reconciliation["truth"]
    ledger_event = {
        **reconciliation,
        "status": "persisted",
        "reconciled": True,
        "tenant_id": plan.tenant_id,
        "decision_id": plan.decision_id,
        "authorization_digest": reconciliation["authorization_digest"],
        "execution_plan_digest": reconciliation["execution_plan_digest"],
    }
    before = reconciliation.get("depletion_before_mm")
    after = reconciliation.get("depletion_after_mm")
    if before is None or after is None:
        return {"status": "blocked", "reason": "DEPLETION_MEASUREMENTS_REQUIRED"}

    outcome = build_irrigation_outcome_evidence(
        tenant_id=plan.tenant_id,
        field_id=plan.field_id,
        season_id=plan.season_id,
        decision_id=plan.decision_id,
        execution_plan_id=plan.execution_plan_id,
        measured_at=measured_at,
        planned_depth_mm=plan.planned_depth_mm,
        actual_depth_mm=float(reconciliation["applied_depth_mm"]),
        depletion_before_mm=float(before),
        depletion_after_mm=float(after),
        expected_depletion_after_mm=float(expected_depletion_after_mm),
        source_digests=source_digests,
        water_use_efficiency_kg_m3=water_use_efficiency_kg_m3,
        energy_kwh=energy_kwh,
        stress_days_observed=stress_days_observed,
        yield_t_ha=yield_t_ha,
    )
    await conn.execute(
        """INSERT INTO irrigation_outcome_evidence
        (tenant_id,field_id,season_id,decision_id,execution_plan_id,measured_at,outcome_status,source_digests,payload,outcome_evidence_digest)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9)
        ON CONFLICT (tenant_id,outcome_evidence_digest) DO NOTHING""",
        plan.field_id,
        plan.season_id,
        plan.decision_id,
        plan.execution_plan_id,
        measured_at,
        outcome.outcome_status,
        json.dumps(outcome.source_digests),
        json.dumps(outcome.to_dict(), default=str),
        outcome.outcome_evidence_digest,
    )
    closed = build_irrigation_closed_loop_record(
        tenant_id=plan.tenant_id,
        field_id=plan.field_id,
        season_id=plan.season_id,
        decision_id=plan.decision_id,
        authorization_id=plan.authorization_id,
        execution_plan_id=plan.execution_plan_id,
        decision_status="completed",
        approval_status="approved",
        execution_status="completed",
        as_applied_truth=truth,
        water_ledger_event=ledger_event,
        outcome_evidence=outcome,
    )
    closed_payload = closed.to_dict()
    await conn.execute(
        """INSERT INTO irrigation_closed_loop_records
        (tenant_id,field_id,season_id,decision_id,authorization_id,execution_plan_id,lifecycle_status,verified,water_ledger_reconciled,outcome_verified,learning_eligible,source_lineage,blocking_reasons,closed_loop_digest,payload)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb,$13,$14::jsonb)
        ON CONFLICT (tenant_id,execution_plan_id) DO NOTHING""",
        plan.field_id,
        plan.season_id,
        plan.decision_id,
        plan.authorization_id,
        plan.execution_plan_id,
        closed.lifecycle_status,
        closed.verified,
        closed.water_ledger_reconciled,
        closed.outcome_verified,
        closed.learning_eligible,
        json.dumps(closed.source_lineage),
        json.dumps(closed.blocking_reasons),
        closed.closed_loop_digest,
        json.dumps(closed_payload, default=str),
    )
    sample_count = int(
        await conn.fetchval(
            "SELECT count(*) FROM irrigation_closed_loop_records WHERE field_id=$1 AND season_id=$2 AND learning_eligible",
            plan.field_id,
            plan.season_id,
        )
        or 0
    )
    proposal = propose_governed_irrigation_learning(
        closed_loop=closed,
        outcome_evidence=outcome,
        minimum_samples=minimum_samples,
        sample_count=sample_count,
    )
    await conn.execute(
        """INSERT INTO irrigation_learning_proposals
        (tenant_id,field_id,season_id,proposal_id,status,review_required,auto_adjust,proposed_parameter_changes,source_lineage,evidence_digest,proposal_digest)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,TRUE,FALSE,$5::jsonb,$6::jsonb,$7,$8)
        ON CONFLICT (tenant_id,proposal_id) DO NOTHING""",
        plan.field_id,
        plan.season_id,
        proposal.proposal_id,
        proposal.status,
        json.dumps(proposal.proposed_parameter_changes),
        json.dumps(proposal.source_lineage),
        proposal.evidence_digest,
        proposal.proposal_digest,
    )
    from uuid import UUID

    event_id = await conn.fetchval(
        """SELECT emit_event($1::text,$2::text,$3::text,$4::uuid,$5::jsonb,$6::text,NULL::text,$7::uuid,now())""",
        "irrigation.closed_loop.completed",
        "irrigation_execution_plan",
        plan.execution_plan_id,
        UUID(plan.tenant_id),
        json.dumps(
            {"closed_loop": closed_payload, "learning_proposal": proposal.to_dict()}, default=str
        ),
        # ``source`` is the constrained enum, not a module name — see EventSource.
        EventSource.SYSTEM.value,
        None,
    )
    return {
        "status": "completed",
        "closed_loop": closed_payload,
        "learning_proposal": proposal.to_dict(),
        "event_id": str(event_id) if event_id else None,
    }
