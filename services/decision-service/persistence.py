"""Decision-service persistence adapter for the planned System-of-Record migration.

Default runtime remains safe mirror mode. Persistence is enabled only when both:
- DECISION_SERVICE_SOR_ENABLED=true
- DATABASE_URL is set

This lets Sahool migrate with a strangler pattern: platform keeps authoritative writes until
real Postgres integration tests and backfill prove decision-service can be promoted.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}


def sor_enabled() -> bool:
    return os.getenv("DECISION_SERVICE_SOR_ENABLED", "").strip().lower() in _TRUTHY and bool(
        os.getenv("DATABASE_URL", "").strip()
    )


def sor_requested_without_db() -> bool:
    return os.getenv("DECISION_SERVICE_SOR_ENABLED", "").strip().lower() in _TRUTHY and not bool(
        os.getenv("DATABASE_URL", "").strip()
    )


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _connect():
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in deploy/runtime only
        raise RuntimeError("asyncpg is required when DECISION_SERVICE_SOR_ENABLED=true") from exc
    return await asyncpg.connect(database_url(), statement_cache_size=0)


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


async def persist_decision_record(
    *, tenant_id: str, payload: Any, decision_id: str
) -> dict[str, Any]:
    # WX-10.7: a candidate carries operational review state in dedicated columns (not jsonb).
    is_candidate = payload.stage == "candidate"
    review_state = "pending_approval" if is_candidate else None
    candidate_lineage_id = (
        (payload.decision_value or {}).get("candidate_lineage_id") if is_candidate else None
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO decision_record
                  (decision_id, tenant_id, field_id, decision_type, region, stage,
                   decision_value, confidence, created_by, review_state, candidate_lineage_id)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11)
                ON CONFLICT (decision_id) DO UPDATE SET
                  stage = EXCLUDED.stage,
                  decision_value = EXCLUDED.decision_value,
                  confidence = EXCLUDED.confidence,
                  review_state = EXCLUDED.review_state,
                  candidate_lineage_id = EXCLUDED.candidate_lineage_id,
                  updated_at = now()
                """,
                decision_id,
                tenant_id,
                payload.field_id,
                payload.decision_type,
                payload.region,
                payload.stage,
                _json(payload.decision_value),
                payload.confidence,
                payload.created_by,
                review_state,
                candidate_lineage_id,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="DECISION_RECORDED",
                aggregate_type="decision_record",
                aggregate_id=decision_id,
                payload={"field_id": payload.field_id, "decision_type": payload.decision_type},
            )
        return {"decision_id": decision_id}
    finally:
        await conn.close()


async def persist_dispatch_decision(
    *, tenant_id: str, payload: Any, decision_id: str
) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO dispatch_decisions
                  (decision_id, tenant_id, recommendation_id, action_type, risk_level,
                   field_id, state, command, created_by)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9)
                ON CONFLICT (decision_id) DO UPDATE SET state = EXCLUDED.state
                """,
                decision_id,
                tenant_id,
                payload.recommendation_id,
                payload.action_type,
                payload.risk_level,
                payload.field_id,
                payload.state,
                _json(payload.command),
                payload.created_by,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="DISPATCH_DECISION_RECORDED",
                aggregate_type="dispatch_decisions",
                aggregate_id=decision_id,
                payload={"recommendation_id": payload.recommendation_id, "state": payload.state},
            )
        return {"decision_id": decision_id}
    finally:
        await conn.close()


async def persist_outcome_record(
    *, tenant_id: str, payload: Any, outcome_id: str
) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO outcome_record
                  (outcome_id, tenant_id, decision_id, field_id, region, planned, actual,
                   metrics, success, created_by, idempotency_key)
                VALUES ($1, $2::uuid, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9, $10, $11)
                ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                DO UPDATE SET actual = EXCLUDED.actual, metrics = EXCLUDED.metrics, success = EXCLUDED.success
                """,
                outcome_id,
                tenant_id,
                payload.decision_id,
                payload.field_id,
                payload.region,
                _json(payload.planned),
                _json(payload.actual),
                _json(payload.metrics),
                payload.success,
                payload.created_by,
                payload.idempotency_key,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="OUTCOME_RECORDED",
                aggregate_type="outcome_record",
                aggregate_id=outcome_id,
                payload={"decision_id": payload.decision_id, "success": payload.success},
            )
        return {"outcome_id": outcome_id}
    finally:
        await conn.close()


async def persist_recommendation_outcome(*, tenant_id: str, payload: Any) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO recommendation_outcomes
                  (tenant_id, recommendation_id, decision_id, field_id, season_id, outcome,
                   confidence, metadata)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb)
                ON CONFLICT (tenant_id, recommendation_id) DO UPDATE SET
                  decision_id = EXCLUDED.decision_id,
                  outcome = EXCLUDED.outcome,
                  confidence = EXCLUDED.confidence,
                  metadata = EXCLUDED.metadata
                """,
                tenant_id,
                payload.recommendation_id,
                payload.decision_id,
                payload.field_id,
                payload.season_id,
                payload.outcome,
                payload.confidence,
                _json(payload.metadata),
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="RECOMMENDATION_OUTCOME_RECORDED",
                aggregate_type="recommendation_outcomes",
                aggregate_id=payload.recommendation_id,
                payload={"decision_id": payload.decision_id, "outcome": payload.outcome},
            )
        return {"recommendation_id": payload.recommendation_id}
    finally:
        await conn.close()


async def persist_learning_update(
    *, tenant_id: str, payload: Any, update_id: str, traceability_status: str
) -> dict[str, Any]:
    if traceability_status == "rejected_untraceable":
        raise ValueError("learning update must be traceable to source_type/source_id or lineage id")
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO online_learning_updates
                  (update_id, tenant_id, model_id, feature_set_id, learning_rate, sample_count,
                   label_summary, drift_score, action, source_type, source_id, field_id,
                   season_id, recommendation_id, decision_id, evidence_snapshot_id)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT (update_id) DO NOTHING
                """,
                update_id,
                tenant_id,
                payload.model_id,
                payload.feature_set_id,
                payload.learning_rate,
                payload.sample_count,
                _json(payload.label_summary),
                payload.drift_score,
                payload.action,
                payload.source_type,
                payload.source_id,
                payload.field_id,
                payload.season_id,
                payload.recommendation_id,
                payload.decision_id,
                payload.evidence_snapshot_id,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="LEARNING_UPDATE_RECORDED",
                aggregate_type="online_learning_updates",
                aggregate_id=update_id,
                payload={"model_id": payload.model_id, "traceability_status": traceability_status},
            )
        return {"update_id": update_id}
    finally:
        await conn.close()


async def emit_outbox_event(
    conn: Any,
    *,
    tenant_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO decision_outbox_events
          (event_id, tenant_id, event_type, aggregate_type, aggregate_id, payload, status)
        VALUES ('evt_' || replace(gen_random_uuid()::text, '-', ''), $1::uuid, $2, $3, $4, $5::jsonb, 'pending')
        """,
        tenant_id,
        event_type,
        aggregate_type,
        aggregate_id,
        _json(payload),
    )


def _authoritative_review(row: Any, *, replay: bool) -> dict[str, Any]:
    """Build the authoritative review result from a SAVED decision_reviews row (never from the
    request payload)."""
    reviewed_at = row["reviewed_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "decision_id": row["decision_id"],
        "previous_state": row["previous_state"],
        "state": row["new_state"],
        "review_id": row["review_id"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": reviewed_at.isoformat()
        if hasattr(reviewed_at, "isoformat")
        else reviewed_at,
        "candidate_lineage_id": row["candidate_lineage_id"],
    }


def _request_hash(
    *, decision_id: str, action: str, new_state: str, reason: str | None, candidate_lineage_id: str
) -> str:
    """Stable hash of the semantic review request — drives idempotency replay vs conflict."""
    blob = json.dumps(
        {
            "decision_id": decision_id,
            "action": action,
            "new_state": new_state,
            "reason": reason or "",
            "candidate_lineage_id": candidate_lineage_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()


async def review_decision(
    *,
    tenant_id: str,
    decision_id: str,
    action: str,
    new_state: str,
    reason: str | None,
    reviewed_by: str,
    candidate_lineage_id: str,
    idempotency_key: str,
    policy_version: str | None,
) -> dict[str, Any]:
    """WX-10.7 — atomic ``pending_approval -> approved|rejected`` transition owned by
    decision-service, in ONE transaction: conditional UPDATE of the dedicated ``review_state``
    column + append-only audit row + outbox event. The evidence in ``decision_value`` is NEVER an
    operational state source and is NEVER mutated; only ``review_state`` transitions.

    Returns a classification dict: ``{status: "ok", authoritative, persisted, ...}`` on success
    (built from the saved audit row), or ``{status: "not_found"}`` / ``{status: "conflict",
    reason: ...}`` for fail-closed mapping. 0-row classification is tenant-scoped — it never
    reveals a decision that belongs to another tenant (no cross-tenant existence oracle).
    """
    try:
        import asyncpg  # type: ignore

        unique_violation = asyncpg.exceptions.UniqueViolationError
    except ImportError as exc:  # pragma: no cover - deploy/runtime only
        raise RuntimeError("asyncpg is required when DECISION_SERVICE_SOR_ENABLED=true") from exc

    request_hash = _request_hash(
        decision_id=decision_id,
        action=action,
        new_state=new_state,
        reason=reason,
        candidate_lineage_id=candidate_lineage_id,
    )
    policy_version = policy_version or "unspecified"

    conn = await _connect()
    try:
        async with conn.transaction():
            # (1) Idempotency by (tenant, key) via request_hash: same key + same request ⇒ replay
            # the original authoritative result; same key + different request ⇒ conflict.
            existing = await conn.fetchrow(
                """
                SELECT review_id, decision_id, previous_state, new_state, reviewed_by,
                       reviewed_at, candidate_lineage_id, request_hash
                  FROM decision_reviews
                 WHERE tenant_id = $1::uuid AND idempotency_key = $2
                """,
                tenant_id,
                idempotency_key,
            )
            if existing is not None:
                if existing["request_hash"] == request_hash:
                    return _authoritative_review(existing, replay=True)
                return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}

            # (2) Atomic conditional transition on the dedicated review_state column. Evidence
            # (decision_value) untouched.
            updated = await conn.fetchrow(
                """
                UPDATE decision_record
                   SET review_state = $3, updated_at = now()
                 WHERE decision_id = $1
                   AND tenant_id = $2::uuid
                   AND stage = 'candidate'
                   AND review_state = 'pending_approval'
                   AND candidate_lineage_id = $4
                RETURNING decision_id
                """,
                decision_id,
                tenant_id,
                new_state,
                candidate_lineage_id,
            )
            if updated is None:
                # Tenant-scoped classification (no cross-tenant oracle). Only candidates are
                # reviewable, so probe is scoped to stage='candidate' + tenant.
                probe = await conn.fetchrow(
                    """
                    SELECT review_state, candidate_lineage_id
                      FROM decision_record
                     WHERE decision_id = $1 AND tenant_id = $2::uuid AND stage = 'candidate'
                    """,
                    decision_id,
                    tenant_id,
                )
                if probe is None:
                    return {"status": "not_found"}
                if probe["review_state"] != "pending_approval":
                    return {"status": "conflict", "reason": "not_pending_approval"}
                return {"status": "conflict", "reason": "candidate_lineage_mismatch"}

            # (3) Append-only audit row. UNIQUE(tenant_id, decision_id) is the concurrency backstop.
            try:
                review_row = await conn.fetchrow(
                    """
                    INSERT INTO decision_reviews
                      (review_id, decision_id, tenant_id, action, previous_state, new_state,
                       reason, reviewed_by, candidate_lineage_id, idempotency_key, request_hash,
                       policy_version)
                    VALUES ('rev_' || replace(gen_random_uuid()::text, '-', ''),
                            $1, $2::uuid, $3, 'pending_approval', $4, $5, $6, $7, $8, $9, $10)
                    RETURNING review_id, decision_id, previous_state, new_state, reviewed_by,
                              reviewed_at, candidate_lineage_id
                    """,
                    decision_id,
                    tenant_id,
                    action,
                    new_state,
                    reason,
                    reviewed_by,
                    candidate_lineage_id,
                    idempotency_key,
                    request_hash,
                    policy_version,
                )
            except unique_violation:
                # A concurrent reviewer already recorded the terminal review for this decision.
                return {"status": "conflict", "reason": "already_reviewed"}

            # (4) Outbox event in the SAME transaction. No consumer is required for success.
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="DECISION_REVIEWED",
                aggregate_type="decision_record",
                aggregate_id=decision_id,
                payload={
                    "action": action,
                    "new_state": new_state,
                    "review_id": review_row["review_id"],
                },
            )
            return _authoritative_review(review_row, replay=False)
    finally:
        await conn.close()


async def list_review_queue(*, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return authoritative pending decision candidates for a tenant.

    The dedicated ``review_state`` column is the only operational state source. Candidate
    evidence remains immutable inside ``decision_value`` and is returned for reviewer display.
    """
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT decision_id, field_id, decision_type, region, stage, decision_value,
                   confidence, review_state, candidate_lineage_id, created_at, updated_at
              FROM decision_record
             WHERE tenant_id = $1::uuid
               AND stage = 'candidate'
               AND review_state = 'pending_approval'
             ORDER BY created_at ASC, decision_id ASC
             LIMIT $2
            """,
            tenant_id,
            max(1, min(int(limit), 200)),
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def list_decision_records(
    *, tenant_id: str, field_id: str | None, decision_type: str | None, limit: int
) -> dict[str, Any]:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT decision_id, field_id, decision_type, region, stage, decision_value,
                   confidence, created_by, created_at
              FROM decision_record
             WHERE tenant_id = $1::uuid
               AND ($2::text IS NULL OR field_id = $2)
               AND ($3::text IS NULL OR decision_type = $3)
             ORDER BY created_at DESC
             LIMIT $4
            """,
            tenant_id,
            field_id,
            decision_type,
            limit,
        )
        decisions = [dict(row) for row in rows]
        return {"decisions": decisions, "count": len(decisions)}
    finally:
        await conn.close()


def _execution_plan_request_hash(
    *, decision_id: str, review_id: str, candidate_lineage_id: str, payload: Any
) -> str:
    blob = json.dumps(
        {
            "decision_id": decision_id,
            "review_id": review_id,
            "candidate_lineage_id": candidate_lineage_id,
            "operation_type": payload.operation_type,
            "planned_start": str(payload.planned_start) if payload.planned_start else None,
            "planned_end": str(payload.planned_end) if payload.planned_end else None,
            "target_zone_ids": payload.target_zone_ids,
            "required_resources": payload.required_resources,
            "constraints": payload.constraints,
            "safety_conditions": payload.safety_conditions,
            "weather_window_reference": payload.weather_window_reference,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_execution_plan(row: Any, *, replay: bool) -> dict[str, Any]:
    created_at = row["created_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "execution_plan_id": row["execution_plan_id"],
        "decision_id": row["decision_id"],
        "review_id": row["review_id"],
        "candidate_lineage_id": row["candidate_lineage_id"],
        "plan_state": row["status"],
        "created_by": row["created_by"],
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }


async def create_execution_plan(
    *,
    tenant_id: str,
    decision_id: str,
    review_id: str,
    candidate_lineage_id: str,
    idempotency_key: str,
    created_by: str,
    payload: Any,
) -> dict[str, Any]:
    """WX-10.9: persist one planned execution plan for an approved decision.

    The decision and terminal review are checked in the same transaction. No decision evidence
    is mutated and no dispatch/task/equipment side effect is emitted. Same-key/same-payload is a
    deterministic replay; same-key/different-payload conflicts.
    """
    request_hash = _execution_plan_request_hash(
        decision_id=decision_id,
        review_id=review_id,
        candidate_lineage_id=candidate_lineage_id,
        payload=payload,
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                """
                SELECT * FROM decision_execution_plans
                 WHERE tenant_id=$1::uuid AND idempotency_key=$2
                """,
                tenant_id,
                idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_execution_plan(prior, replay=True)

            source = await conn.fetchrow(
                """
                SELECT d.decision_id, d.review_state, d.candidate_lineage_id,
                       r.review_id, r.new_state
                  FROM decision_record d
                  JOIN decision_reviews r
                    ON r.tenant_id=d.tenant_id AND r.decision_id=d.decision_id
                 WHERE d.tenant_id=$1::uuid AND d.decision_id=$2
                """,
                tenant_id,
                decision_id,
            )
            if not source:
                return {"status": "not_found"}
            if source["review_state"] != "approved" or source["new_state"] != "approved":
                return {"status": "conflict", "reason": "decision_not_approved"}
            if source["candidate_lineage_id"] != candidate_lineage_id:
                return {"status": "conflict", "reason": "candidate_lineage_mismatch"}
            if source["review_id"] != review_id:
                return {"status": "conflict", "reason": "review_id_mismatch"}

            plan_id = (
                "xplan_"
                + hashlib.sha256(
                    f"{tenant_id}:{decision_id}:{idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """
                INSERT INTO decision_execution_plans
                  (execution_plan_id, tenant_id, decision_id, review_id,
                   candidate_lineage_id, operation_type, planned_start, planned_end,
                   target_zone_ids, required_resources, constraints, safety_conditions,
                   weather_window_reference, status, idempotency_key, request_hash, created_by)
                VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11::jsonb,
                        $12::jsonb,$13::jsonb,'planned',$14,$15,$16)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                plan_id,
                tenant_id,
                decision_id,
                review_id,
                candidate_lineage_id,
                payload.operation_type,
                payload.planned_start,
                payload.planned_end,
                json.dumps(payload.target_zone_ids, ensure_ascii=False),
                json.dumps(payload.required_resources, ensure_ascii=False, default=str),
                json.dumps(payload.constraints, ensure_ascii=False, default=str),
                json.dumps(payload.safety_conditions, ensure_ascii=False, default=str),
                json.dumps(payload.weather_window_reference, ensure_ascii=False, default=str)
                if payload.weather_window_reference is not None
                else None,
                idempotency_key,
                request_hash,
                created_by,
            )
            if row is None:
                # A competing request won a unique constraint. Re-read deterministically; no
                # endpoint retry and no transaction-aborting exception path.
                concurrent = await conn.fetchrow(
                    """SELECT * FROM decision_execution_plans
                         WHERE tenant_id=$1::uuid AND (decision_id=$2 OR idempotency_key=$3)""",
                    tenant_id,
                    decision_id,
                    idempotency_key,
                )
                if (
                    concurrent
                    and concurrent["idempotency_key"] == idempotency_key
                    and concurrent["request_hash"] == request_hash
                ):
                    return _authoritative_execution_plan(concurrent, replay=True)
                return {"status": "conflict", "reason": "execution_plan_already_exists"}

            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="EXECUTION_PLAN_CREATED",
                aggregate_type="decision_execution_plans",
                aggregate_id=row["execution_plan_id"],
                payload={
                    "decision_id": decision_id,
                    "review_id": review_id,
                    "status": "planned",
                },
            )
            return _authoritative_execution_plan(row, replay=False)
    finally:
        await conn.close()


def _dispatch_authorization_request_hash(
    *,
    execution_plan_id: str,
    decision_id: str,
    review_id: str,
    candidate_lineage_id: str,
    payload: Any,
) -> str:
    blob = json.dumps(
        {
            "execution_plan_id": execution_plan_id,
            "decision_id": decision_id,
            "review_id": review_id,
            "candidate_lineage_id": candidate_lineage_id,
            "expected_plan_state": payload.expected_plan_state,
            "policy_version": payload.policy_version,
            "weather_snapshot_id": payload.weather_snapshot_id,
            "resource_snapshot_id": payload.resource_snapshot_id,
            "authorization_reason": payload.authorization_reason,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_dispatch_authorization(row: Any, *, replay: bool) -> dict[str, Any]:
    authorized_at = row["authorized_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "dispatch_authorization_id": row["dispatch_authorization_id"],
        "execution_plan_id": row["execution_plan_id"],
        "decision_id": row["decision_id"],
        "review_id": row["review_id"],
        "candidate_lineage_id": row["candidate_lineage_id"],
        "authorization_state": row["status"],
        "policy_version": row["policy_version"],
        "weather_snapshot_id": row["weather_snapshot_id"],
        "resource_snapshot_id": row["resource_snapshot_id"],
        "authorized_by": row["authorized_by"],
        "authorized_at": authorized_at.isoformat()
        if hasattr(authorized_at, "isoformat")
        else authorized_at,
    }


async def authorize_dispatch(
    *,
    tenant_id: str,
    execution_plan_id: str,
    decision_id: str,
    review_id: str,
    candidate_lineage_id: str,
    idempotency_key: str,
    authorized_by: str,
    payload: Any,
) -> dict[str, Any]:
    """WX-10.10: persist one authorization for a still-valid planned execution plan.

    The plan, terminal review, and decision approval are verified in one transaction. The
    function emits only an authorization-created outbox record; it never dispatches, creates a
    task, or issues an equipment command.
    """
    request_hash = _dispatch_authorization_request_hash(
        execution_plan_id=execution_plan_id,
        decision_id=decision_id,
        review_id=review_id,
        candidate_lineage_id=candidate_lineage_id,
        payload=payload,
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                """
                SELECT * FROM decision_dispatch_authorizations
                 WHERE tenant_id=$1::uuid AND idempotency_key=$2
                """,
                tenant_id,
                idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_dispatch_authorization(prior, replay=True)

            source = await conn.fetchrow(
                """
                SELECT p.execution_plan_id, p.decision_id, p.review_id,
                       p.candidate_lineage_id, p.status AS plan_state,
                       d.review_state, r.new_state
                  FROM decision_execution_plans p
                  JOIN decision_record d
                    ON d.tenant_id=p.tenant_id AND d.decision_id=p.decision_id
                  JOIN decision_reviews r
                    ON r.tenant_id=p.tenant_id AND r.decision_id=p.decision_id
                 WHERE p.tenant_id=$1::uuid AND p.execution_plan_id=$2
                 FOR UPDATE OF p
                """,
                tenant_id,
                execution_plan_id,
            )
            if not source:
                return {"status": "not_found"}
            if source["plan_state"] != "planned" or payload.expected_plan_state != "planned":
                return {"status": "conflict", "reason": "execution_plan_not_planned"}
            if source["review_state"] != "approved" or source["new_state"] != "approved":
                return {"status": "conflict", "reason": "decision_not_approved"}
            if source["decision_id"] != decision_id:
                return {"status": "conflict", "reason": "decision_id_mismatch"}
            if source["review_id"] != review_id:
                return {"status": "conflict", "reason": "review_id_mismatch"}
            if source["candidate_lineage_id"] != candidate_lineage_id:
                return {"status": "conflict", "reason": "candidate_lineage_mismatch"}

            authorization_id = (
                "dauth_"
                + hashlib.sha256(
                    f"{tenant_id}:{execution_plan_id}:{idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """
                INSERT INTO decision_dispatch_authorizations
                  (dispatch_authorization_id, tenant_id, execution_plan_id, decision_id,
                   review_id, candidate_lineage_id, expected_plan_state, policy_version,
                   weather_snapshot_id, resource_snapshot_id, authorization_reason, status,
                   idempotency_key, request_hash, authorized_by)
                VALUES ($1,$2::uuid,$3,$4,$5,$6,'planned',$7,$8,$9,$10,'authorized',$11,$12,$13)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                authorization_id,
                tenant_id,
                execution_plan_id,
                decision_id,
                review_id,
                candidate_lineage_id,
                payload.policy_version,
                payload.weather_snapshot_id,
                payload.resource_snapshot_id,
                payload.authorization_reason,
                idempotency_key,
                request_hash,
                authorized_by,
            )
            if row is None:
                concurrent = await conn.fetchrow(
                    """SELECT * FROM decision_dispatch_authorizations
                         WHERE tenant_id=$1::uuid
                           AND (execution_plan_id=$2 OR idempotency_key=$3)""",
                    tenant_id,
                    execution_plan_id,
                    idempotency_key,
                )
                if (
                    concurrent
                    and concurrent["idempotency_key"] == idempotency_key
                    and concurrent["request_hash"] == request_hash
                ):
                    return _authoritative_dispatch_authorization(concurrent, replay=True)
                return {"status": "conflict", "reason": "dispatch_authorization_already_exists"}

            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="DISPATCH_AUTHORIZATION_CREATED",
                aggregate_type="decision_dispatch_authorizations",
                aggregate_id=row["dispatch_authorization_id"],
                payload={
                    "execution_plan_id": execution_plan_id,
                    "decision_id": decision_id,
                    "status": "authorized",
                },
            )
            return _authoritative_dispatch_authorization(row, replay=False)
    finally:
        await conn.close()


def _execution_request_hash(*, dispatch_authorization_id: str, payload: Any) -> str:
    blob = json.dumps(
        {
            "dispatch_authorization_id": dispatch_authorization_id,
            "execution_plan_id": payload.execution_plan_id,
            "decision_id": payload.decision_id,
            "target_type": payload.target_type,
            "target_id": payload.target_id,
            "operation_type": payload.operation_type,
            "command_payload": payload.command_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_execution_request(row: Any, *, replay: bool) -> dict[str, Any]:
    requested_at = row["requested_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "execution_request_id": row["execution_request_id"],
        "dispatch_authorization_id": row["dispatch_authorization_id"],
        "execution_plan_id": row["execution_plan_id"],
        "decision_id": row["decision_id"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "operation_type": row["operation_type"],
        "execution_state": row["status"],
        "requested_by": row["requested_by"],
        "requested_at": requested_at.isoformat()
        if hasattr(requested_at, "isoformat")
        else requested_at,
    }


async def create_execution_request(
    *, tenant_id: str, dispatch_authorization_id: str, requested_by: str, payload: Any
) -> dict[str, Any]:
    request_hash = _execution_request_hash(
        dispatch_authorization_id=dispatch_authorization_id, payload=payload
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_execution_requests WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_execution_request(prior, replay=True)
            auth = await conn.fetchrow(
                """SELECT a.dispatch_authorization_id,a.execution_plan_id,a.decision_id,a.status,
                          p.status AS plan_state,d.review_state
                     FROM decision_dispatch_authorizations a
                     JOIN decision_execution_plans p ON p.tenant_id=a.tenant_id AND p.execution_plan_id=a.execution_plan_id
                     JOIN decision_record d ON d.tenant_id=a.tenant_id AND d.decision_id=a.decision_id
                    WHERE a.tenant_id=$1::uuid AND a.dispatch_authorization_id=$2
                    FOR UPDATE OF a""",
                tenant_id,
                dispatch_authorization_id,
            )
            if not auth:
                return {"status": "not_found"}
            if (
                auth["status"] != "authorized"
                or auth["plan_state"] != "planned"
                or auth["review_state"] != "approved"
            ):
                return {"status": "conflict", "reason": "authorization_not_executable"}
            if auth["execution_plan_id"] != payload.execution_plan_id:
                return {"status": "conflict", "reason": "execution_plan_id_mismatch"}
            if auth["decision_id"] != payload.decision_id:
                return {"status": "conflict", "reason": "decision_id_mismatch"}
            request_id = (
                "exec_"
                + hashlib.sha256(
                    f"{tenant_id}:{dispatch_authorization_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_execution_requests
                   (execution_request_id,tenant_id,dispatch_authorization_id,execution_plan_id,
                    decision_id,target_type,target_id,operation_type,command_payload,status,
                    idempotency_key,request_hash,requested_by)
                   VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9::jsonb,'queued',$10,$11,$12)
                   ON CONFLICT DO NOTHING RETURNING *""",
                request_id,
                tenant_id,
                dispatch_authorization_id,
                payload.execution_plan_id,
                payload.decision_id,
                payload.target_type,
                payload.target_id,
                payload.operation_type,
                _json(payload.command_payload),
                payload.idempotency_key,
                request_hash,
                requested_by,
            )
            if row is None:
                return {"status": "conflict", "reason": "execution_request_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="EXECUTION_REQUEST_CREATED",
                aggregate_type="decision_execution_requests",
                aggregate_id=request_id,
                payload={
                    "dispatch_authorization_id": dispatch_authorization_id,
                    "target_type": payload.target_type,
                    "target_id": payload.target_id,
                    "operation_type": payload.operation_type,
                    "status": "queued",
                },
            )
            return _authoritative_execution_request(row, replay=False)
    finally:
        await conn.close()


def _delivery_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _authoritative_delivery(row: Any, *, replay: bool) -> dict[str, Any]:
    claimed_at = row["claimed_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "delivery_attempt_id": row["delivery_attempt_id"],
        "execution_request_id": row["execution_request_id"],
        "adapter_id": row["adapter_id"],
        "adapter_kind": row["adapter_kind"],
        "delivery_state": "delivering",
        "claimed_at": claimed_at.isoformat() if hasattr(claimed_at, "isoformat") else claimed_at,
    }


async def claim_execution_request(
    *,
    tenant_id: str,
    execution_request_id: str,
    adapter_id: str,
    adapter_kind: str,
    delivery_token: str,
) -> dict[str, Any]:
    token_hash = _delivery_token_hash(delivery_token)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_execution_delivery_attempts WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                tenant_id,
                execution_request_id,
            )
            if prior:
                if (
                    prior["adapter_id"] != adapter_id
                    or prior["adapter_kind"] != adapter_kind
                    or prior["delivery_token_hash"] != token_hash
                ):
                    return {"status": "conflict", "reason": "execution_request_already_claimed"}
                return _authoritative_delivery(prior, replay=True)
            request = await conn.fetchrow(
                "SELECT * FROM decision_execution_requests WHERE tenant_id=$1::uuid AND execution_request_id=$2 FOR UPDATE",
                tenant_id,
                execution_request_id,
            )
            if not request:
                return {"status": "not_found"}
            if request["status"] != "queued":
                return {"status": "conflict", "reason": "execution_request_not_queued"}
            if request["target_type"] != adapter_kind:
                return {"status": "conflict", "reason": "adapter_kind_mismatch"}
            attempt_id = (
                "del_"
                + hashlib.sha256(f"{tenant_id}:{execution_request_id}".encode()).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_execution_delivery_attempts
                   (delivery_attempt_id,tenant_id,execution_request_id,adapter_id,adapter_kind,delivery_token_hash)
                   VALUES ($1,$2::uuid,$3,$4,$5,$6) RETURNING *""",
                attempt_id,
                tenant_id,
                execution_request_id,
                adapter_id,
                adapter_kind,
                token_hash,
            )
            await conn.execute(
                "UPDATE decision_execution_requests SET status='delivering' WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                tenant_id,
                execution_request_id,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="EXECUTION_REQUEST_CLAIMED",
                aggregate_type="decision_execution_requests",
                aggregate_id=execution_request_id,
                payload={
                    "delivery_attempt_id": attempt_id,
                    "adapter_id": adapter_id,
                    "adapter_kind": adapter_kind,
                },
            )
            return _authoritative_delivery(row, replay=False)
    finally:
        await conn.close()


async def record_execution_receipt(
    *,
    tenant_id: str,
    execution_request_id: str,
    adapter_id: str,
    delivery_token: str,
    receipt_id: str,
    receipt_status: str,
    receipt_payload: dict[str, Any],
) -> dict[str, Any]:
    token_hash = _delivery_token_hash(delivery_token)
    conn = await _connect()
    try:
        async with conn.transaction():
            attempt = await conn.fetchrow(
                "SELECT * FROM decision_execution_delivery_attempts WHERE tenant_id=$1::uuid AND execution_request_id=$2 FOR UPDATE",
                tenant_id,
                execution_request_id,
            )
            if not attempt:
                return {"status": "not_found"}
            if attempt["adapter_id"] != adapter_id or attempt["delivery_token_hash"] != token_hash:
                return {"status": "conflict", "reason": "delivery_claim_mismatch"}
            if attempt["receipt_id"] is not None:
                same = (
                    attempt["receipt_id"] == receipt_id
                    and attempt["receipt_status"] == receipt_status
                    and (
                        (
                            json.loads(attempt["receipt_payload"])
                            if isinstance(attempt["receipt_payload"], str)
                            else (attempt["receipt_payload"] or {})
                        )
                        == (receipt_payload or {})
                    )
                )
                if not same:
                    return {"status": "conflict", "reason": "receipt_already_recorded"}
                received_at = attempt["received_at"]
                return {
                    "status": "ok",
                    "replay": True,
                    "authoritative": True,
                    "persisted": True,
                    "execution_request_id": execution_request_id,
                    "receipt_id": receipt_id,
                    "execution_state": receipt_status,
                    "received_at": received_at.isoformat()
                    if hasattr(received_at, "isoformat")
                    else received_at,
                }
            request = await conn.fetchrow(
                "SELECT status FROM decision_execution_requests WHERE tenant_id=$1::uuid AND execution_request_id=$2 FOR UPDATE",
                tenant_id,
                execution_request_id,
            )
            if not request or request["status"] != "delivering":
                return {"status": "conflict", "reason": "execution_request_not_delivering"}
            row = await conn.fetchrow(
                """UPDATE decision_execution_delivery_attempts
                   SET receipt_id=$3,receipt_status=$4,receipt_payload=$5::jsonb,received_at=now()
                   WHERE tenant_id=$1::uuid AND execution_request_id=$2 RETURNING *""",
                tenant_id,
                execution_request_id,
                receipt_id,
                receipt_status,
                _json(receipt_payload),
            )
            await conn.execute(
                """UPDATE decision_execution_requests
                   SET status=$3,receipt_id=$4,receipt_status=$3,receipt_payload=$5::jsonb,received_at=now()
                   WHERE tenant_id=$1::uuid AND execution_request_id=$2""",
                tenant_id,
                execution_request_id,
                receipt_status,
                receipt_id,
                _json(receipt_payload),
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="EXECUTION_RECEIPT_RECORDED",
                aggregate_type="decision_execution_requests",
                aggregate_id=execution_request_id,
                payload={
                    "receipt_id": receipt_id,
                    "receipt_status": receipt_status,
                    "adapter_id": adapter_id,
                },
            )
            received_at = row["received_at"]
            return {
                "status": "ok",
                "replay": False,
                "authoritative": True,
                "persisted": True,
                "execution_request_id": execution_request_id,
                "receipt_id": receipt_id,
                "execution_state": receipt_status,
                "received_at": received_at.isoformat()
                if hasattr(received_at, "isoformat")
                else received_at,
            }
    finally:
        await conn.close()


def _execution_outcome_hash(*, execution_request_id: str, payload: Any) -> str:
    blob = json.dumps(
        {
            "execution_request_id": execution_request_id,
            "execution_plan_id": payload.execution_plan_id,
            "dispatch_authorization_id": payload.dispatch_authorization_id,
            "decision_id": payload.decision_id,
            "receipt_id": payload.receipt_id,
            "verification_state": payload.verification_state,
            "evidence_snapshot_id": payload.evidence_snapshot_id,
            "actual": payload.actual,
            "metrics": payload.metrics,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_execution_outcome(row: Any, *, replay: bool) -> dict[str, Any]:
    verified_at = row["verified_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "outcome_id": row["outcome_id"],
        "execution_request_id": row["execution_request_id"],
        "execution_plan_id": row["execution_plan_id"],
        "dispatch_authorization_id": row["dispatch_authorization_id"],
        "decision_id": row["decision_id"],
        "receipt_id": row["receipt_id"],
        "verification_state": row["verification_state"],
        "evidence_snapshot_id": row["evidence_snapshot_id"],
        "success": row["success"],
        "verified_by": row["verified_by"],
        "verified_at": verified_at.isoformat()
        if hasattr(verified_at, "isoformat")
        else verified_at,
    }


async def verify_execution_outcome(
    *, tenant_id: str, execution_request_id: str, verified_by: str, payload: Any
) -> dict[str, Any]:
    request_hash = _execution_outcome_hash(
        execution_request_id=execution_request_id, payload=payload
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM outcome_record WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_execution_outcome(prior, replay=True)
            source = await conn.fetchrow(
                """SELECT r.execution_request_id,r.execution_plan_id,r.dispatch_authorization_id,
                          r.decision_id,r.status,r.receipt_id,r.receipt_status,
                          a.receipt_id AS attempt_receipt_id
                     FROM decision_execution_requests r
                     JOIN decision_execution_delivery_attempts a
                       ON a.tenant_id=r.tenant_id AND a.execution_request_id=r.execution_request_id
                    WHERE r.tenant_id=$1::uuid AND r.execution_request_id=$2
                    FOR UPDATE OF r,a""",
                tenant_id,
                execution_request_id,
            )
            if not source:
                return {"status": "not_found"}
            if source["status"] not in {"accepted", "failed"} or not source["receipt_id"]:
                return {"status": "conflict", "reason": "execution_request_not_terminal"}
            checks = {
                "execution_plan_id_mismatch": source["execution_plan_id"]
                == payload.execution_plan_id,
                "dispatch_authorization_id_mismatch": source["dispatch_authorization_id"]
                == payload.dispatch_authorization_id,
                "decision_id_mismatch": source["decision_id"] == payload.decision_id,
                "receipt_id_mismatch": source["receipt_id"]
                == payload.receipt_id
                == source["attempt_receipt_id"],
            }
            for reason, ok in checks.items():
                if not ok:
                    return {"status": "conflict", "reason": reason}
            outcome_id = (
                "out_"
                + hashlib.sha256(
                    f"{tenant_id}:{execution_request_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            success = payload.verification_state == "verified_success"
            row = await conn.fetchrow(
                """INSERT INTO outcome_record
                   (outcome_id,tenant_id,decision_id,planned,actual,metrics,success,created_by,
                    idempotency_key,execution_request_id,dispatch_authorization_id,execution_plan_id,
                    receipt_id,verification_state,evidence_snapshot_id,verified_by,verified_at,request_hash)
                   VALUES($1,$2::uuid,$3,'{}'::jsonb,$4::jsonb,$5::jsonb,$6,$7,$8,$9,$10,$11,$12,$13,$14,$7,now(),$15)
                   ON CONFLICT DO NOTHING RETURNING *""",
                outcome_id,
                tenant_id,
                payload.decision_id,
                _json(payload.actual),
                _json(payload.metrics),
                success,
                verified_by,
                payload.idempotency_key,
                execution_request_id,
                payload.dispatch_authorization_id,
                payload.execution_plan_id,
                payload.receipt_id,
                payload.verification_state,
                payload.evidence_snapshot_id,
                request_hash,
            )
            if row is None:
                concurrent = await conn.fetchrow(
                    "SELECT * FROM outcome_record WHERE tenant_id=$1::uuid AND execution_request_id=$2",
                    tenant_id,
                    execution_request_id,
                )
                if concurrent and concurrent["request_hash"] == request_hash:
                    return _authoritative_execution_outcome(concurrent, replay=True)
                return {"status": "conflict", "reason": "execution_outcome_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="EXECUTION_OUTCOME_VERIFIED",
                aggregate_type="outcome_record",
                aggregate_id=outcome_id,
                payload={
                    "execution_request_id": execution_request_id,
                    "decision_id": payload.decision_id,
                    "verification_state": payload.verification_state,
                    "evidence_snapshot_id": payload.evidence_snapshot_id,
                },
            )
            return _authoritative_execution_outcome(row, replay=False)
    finally:
        await conn.close()


def _learning_attribution_hash(*, outcome_id: str, payload: Any) -> str:
    blob = json.dumps(
        {
            "outcome_id": outcome_id,
            "model_id": payload.model_id,
            "feature_set_id": payload.feature_set_id,
            "attribution_method": payload.attribution_method,
            "label": payload.label,
            "weight": payload.weight,
            "evidence_snapshot_id": payload.evidence_snapshot_id,
            "metadata": payload.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_learning_attribution(row: Any, *, replay: bool) -> dict[str, Any]:
    attributed_at = row["attributed_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "learning_attribution_id": row["learning_attribution_id"],
        "outcome_id": row["outcome_id"],
        "decision_id": row["decision_id"],
        "execution_request_id": row["execution_request_id"],
        "model_id": row["model_id"],
        "feature_set_id": row["feature_set_id"],
        "attribution_method": row["attribution_method"],
        "label": row["label"],
        "weight": float(row["weight"]),
        "evidence_snapshot_id": row["evidence_snapshot_id"],
        "learning_state": row["learning_state"],
        "attributed_by": row["attributed_by"],
        "attributed_at": attributed_at.isoformat()
        if hasattr(attributed_at, "isoformat")
        else attributed_at,
    }


async def create_learning_attribution(
    *, tenant_id: str, outcome_id: str, attributed_by: str, payload: Any
) -> dict[str, Any]:
    """WX-10.13: persist attribution lineage only; never fit or mutate a model."""
    request_hash = _learning_attribution_hash(outcome_id=outcome_id, payload=payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_learning_attributions WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_learning_attribution(prior, replay=True)
            source = await conn.fetchrow(
                """SELECT outcome_id,decision_id,execution_request_id,verification_state,
                          evidence_snapshot_id,success
                     FROM outcome_record
                    WHERE tenant_id=$1::uuid AND outcome_id=$2
                    FOR SHARE""",
                tenant_id,
                outcome_id,
            )
            if not source:
                return {"status": "not_found"}
            if source["verification_state"] not in {"verified_success", "verified_failure"}:
                return {"status": "conflict", "reason": "outcome_not_verified"}
            if source["evidence_snapshot_id"] != payload.evidence_snapshot_id:
                return {"status": "conflict", "reason": "evidence_snapshot_mismatch"}
            expected_label = "success" if source["success"] else "failure"
            if payload.label != expected_label:
                return {"status": "conflict", "reason": "label_outcome_mismatch"}
            attribution_id = (
                "lat_"
                + hashlib.sha256(
                    f"{tenant_id}:{outcome_id}:{payload.model_id}:{payload.feature_set_id or ''}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_learning_attributions
                   (learning_attribution_id,tenant_id,outcome_id,decision_id,execution_request_id,
                    model_id,feature_set_id,attribution_method,label,weight,evidence_snapshot_id,
                    metadata,learning_state,idempotency_key,request_hash,attributed_by)
                   VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,'attributed',$13,$14,$15)
                   ON CONFLICT DO NOTHING RETURNING *""",
                attribution_id,
                tenant_id,
                outcome_id,
                source["decision_id"],
                source["execution_request_id"],
                payload.model_id,
                payload.feature_set_id,
                payload.attribution_method,
                payload.label,
                payload.weight,
                payload.evidence_snapshot_id,
                _json(payload.metadata),
                payload.idempotency_key,
                request_hash,
                attributed_by,
            )
            if row is None:
                concurrent = await conn.fetchrow(
                    """SELECT * FROM decision_learning_attributions
                        WHERE tenant_id=$1::uuid AND outcome_id=$2 AND model_id=$3
                          AND feature_set_id IS NOT DISTINCT FROM $4""",
                    tenant_id,
                    outcome_id,
                    payload.model_id,
                    payload.feature_set_id,
                )
                if concurrent and concurrent["request_hash"] == request_hash:
                    return _authoritative_learning_attribution(concurrent, replay=True)
                return {"status": "conflict", "reason": "learning_attribution_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="LEARNING_ATTRIBUTION_CREATED",
                aggregate_type="decision_learning_attributions",
                aggregate_id=attribution_id,
                payload={
                    "outcome_id": outcome_id,
                    "decision_id": source["decision_id"],
                    "execution_request_id": source["execution_request_id"],
                    "model_id": payload.model_id,
                    "feature_set_id": payload.feature_set_id,
                    "label": payload.label,
                    "learning_state": "attributed",
                },
            )
            return _authoritative_learning_attribution(row, replay=False)
    finally:
        await conn.close()


def _calibration_fingerprint(items: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "learning_attribution_id": item["learning_attribution_id"],
            "outcome_id": item["outcome_id"],
            "decision_id": item["decision_id"],
            "execution_request_id": item["execution_request_id"],
            "label": item["label"],
            "weight": item["weight"],
            "evidence_snapshot_id": item["evidence_snapshot_id"],
            "verification_state": item["verification_state"],
            "success": item["success"],
        }
        for item in sorted(items, key=lambda x: x["learning_attribution_id"])
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def build_calibration_dataset(
    *, tenant_id: str, model_id: str, feature_set_id: str | None, limit: int
) -> dict[str, Any]:
    """WX-11.1: read immutable attribution/outcome lineage into a calibration dataset."""
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """SELECT la.learning_attribution_id,la.outcome_id,la.decision_id,
                      la.execution_request_id,la.model_id,la.feature_set_id,la.label,
                      la.weight,la.evidence_snapshot_id,la.attributed_at,
                      o.verification_state,o.success,o.metrics,o.actual,
                      d.decision_type,d.field_id,d.confidence,d.created_at AS decision_created_at
                 FROM decision_learning_attributions la
                 JOIN outcome_record o
                   ON o.tenant_id=la.tenant_id AND o.outcome_id=la.outcome_id
                 JOIN decision_record d
                   ON d.tenant_id=la.tenant_id AND d.decision_id=la.decision_id
                WHERE la.tenant_id=$1::uuid AND la.model_id=$2
                  AND la.feature_set_id IS NOT DISTINCT FROM $3
                  AND la.learning_state='attributed'
                  AND o.verification_state IN ('verified_success','verified_failure')
                ORDER BY la.attributed_at DESC,la.learning_attribution_id DESC
                LIMIT $4""",
            tenant_id,
            model_id,
            feature_set_id,
            limit,
        )
        items = []
        success_weight = 0.0
        total_weight = 0.0
        for row in rows:
            weight = float(row["weight"])
            total_weight += weight
            if row["success"]:
                success_weight += weight
            items.append(
                {
                    "learning_attribution_id": row["learning_attribution_id"],
                    "outcome_id": row["outcome_id"],
                    "decision_id": row["decision_id"],
                    "execution_request_id": row["execution_request_id"],
                    "model_id": row["model_id"],
                    "feature_set_id": row["feature_set_id"],
                    "label": row["label"],
                    "weight": weight,
                    "evidence_snapshot_id": row["evidence_snapshot_id"],
                    "verification_state": row["verification_state"],
                    "success": bool(row["success"]),
                    "metrics": row["metrics"] or {},
                    "actual": row["actual"] or {},
                    "decision_type": row["decision_type"],
                    "field_id": row["field_id"],
                    "confidence": float(row["confidence"])
                    if row["confidence"] is not None
                    else None,
                    "decision_created_at": row["decision_created_at"].isoformat()
                    if hasattr(row["decision_created_at"], "isoformat")
                    else row["decision_created_at"],
                    "attributed_at": row["attributed_at"].isoformat()
                    if hasattr(row["attributed_at"], "isoformat")
                    else row["attributed_at"],
                }
            )
        return {
            "authoritative": True,
            "persisted": True,
            "read_only": True,
            "model_id": model_id,
            "feature_set_id": feature_set_id,
            "count": len(items),
            "weighted_success_rate": (success_weight / total_weight) if total_weight else None,
            "dataset_fingerprint": _calibration_fingerprint(items),
            "items": items,
        }
    finally:
        await conn.close()


def _model_evaluation_hash(payload: Any) -> str:
    blob = json.dumps(
        {
            "model_id": payload.model_id,
            "feature_set_id": payload.feature_set_id,
            "dataset_fingerprint": payload.dataset_fingerprint,
            "dataset_count": payload.dataset_count,
            "evaluator_version": payload.evaluator_version,
            "baseline_metrics": payload.baseline_metrics,
            "candidate_metrics": payload.candidate_metrics,
            "candidate_artifact_uri": payload.candidate_artifact_uri,
            "candidate_artifact_digest": payload.candidate_artifact_digest.lower(),
            "artifact_format": payload.artifact_format,
            "metadata": payload.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_model_evaluation(row: Any, *, replay: bool) -> dict[str, Any]:
    ts = row["evaluated_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "evaluation_run_id": row["evaluation_run_id"],
        "model_id": row["model_id"],
        "feature_set_id": row["feature_set_id"],
        "dataset_fingerprint": row["dataset_fingerprint"],
        "dataset_count": row["dataset_count"],
        "evaluator_version": row["evaluator_version"],
        "baseline_metrics": row["baseline_metrics"],
        "candidate_metrics": row["candidate_metrics"],
        "candidate_artifact_uri": row["candidate_artifact_uri"],
        "candidate_artifact_digest": row["candidate_artifact_digest"],
        "artifact_format": row["artifact_format"],
        "evaluation_state": row["evaluation_state"],
        "evaluated_by": row["evaluated_by"],
        "evaluated_at": ts.isoformat() if hasattr(ts, "isoformat") else ts,
    }


async def create_model_evaluation_run(
    *, tenant_id: str, evaluated_by: str, payload: Any
) -> dict[str, Any]:
    """WX-11.2: persist evaluation evidence; never train or promote a model."""
    request_hash = _model_evaluation_hash(payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_evaluation_runs WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_model_evaluation(prior, replay=True)
            rows = await conn.fetch(
                """SELECT la.learning_attribution_id,la.outcome_id,la.decision_id,la.execution_request_id,la.label,la.weight,la.evidence_snapshot_id,o.verification_state,o.success FROM decision_learning_attributions la JOIN outcome_record o ON o.tenant_id=la.tenant_id AND o.outcome_id=la.outcome_id WHERE la.tenant_id=$1::uuid AND la.model_id=$2 AND la.feature_set_id IS NOT DISTINCT FROM $3 AND la.learning_state='attributed' AND o.verification_state IN ('verified_success','verified_failure')""",
                tenant_id,
                payload.model_id,
                payload.feature_set_id,
            )
            fingerprint_items = [
                {
                    "learning_attribution_id": r["learning_attribution_id"],
                    "outcome_id": r["outcome_id"],
                    "decision_id": r["decision_id"],
                    "execution_request_id": r["execution_request_id"],
                    "label": r["label"],
                    "weight": float(r["weight"]),
                    "evidence_snapshot_id": r["evidence_snapshot_id"],
                    "verification_state": r["verification_state"],
                    "success": bool(r["success"]),
                }
                for r in rows
            ]
            if len(fingerprint_items) != payload.dataset_count:
                return {"status": "conflict", "reason": "dataset_count_mismatch"}
            if _calibration_fingerprint(fingerprint_items) != payload.dataset_fingerprint:
                return {"status": "conflict", "reason": "dataset_fingerprint_mismatch"}
            run_id = (
                "eval_"
                + hashlib.sha256(
                    f"{tenant_id}:{payload.model_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_model_evaluation_runs (evaluation_run_id,tenant_id,model_id,feature_set_id,dataset_fingerprint,dataset_count,evaluator_version,baseline_metrics,candidate_metrics,candidate_artifact_uri,candidate_artifact_digest,artifact_format,evaluation_state,idempotency_key,request_hash,evaluated_by,metadata) VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,'evaluated',$13,$14,$15,$16::jsonb) ON CONFLICT DO NOTHING RETURNING *""",
                run_id,
                tenant_id,
                payload.model_id,
                payload.feature_set_id,
                payload.dataset_fingerprint,
                payload.dataset_count,
                payload.evaluator_version,
                _json(payload.baseline_metrics),
                _json(payload.candidate_metrics),
                payload.candidate_artifact_uri,
                payload.candidate_artifact_digest.lower(),
                payload.artifact_format,
                payload.idempotency_key,
                request_hash,
                evaluated_by,
                _json(payload.metadata),
            )
            if row is None:
                return {"status": "conflict", "reason": "evaluation_or_artifact_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_EVALUATION_RUN_CREATED",
                aggregate_type="decision_model_evaluation_runs",
                aggregate_id=run_id,
                payload={
                    "model_id": payload.model_id,
                    "feature_set_id": payload.feature_set_id,
                    "dataset_fingerprint": payload.dataset_fingerprint,
                    "candidate_artifact_digest": payload.candidate_artifact_digest.lower(),
                    "evaluation_state": "evaluated",
                },
            )
            return _authoritative_model_evaluation(row, replay=False)
    finally:
        await conn.close()


def _promotion_decision_hash(payload: Any) -> str:
    blob = json.dumps(
        {
            "evaluation_run_id": payload.evaluation_run_id,
            "policy_version": payload.policy_version,
            "primary_metric": payload.primary_metric,
            "min_improvement": payload.min_improvement,
            "lower_is_better": payload.lower_is_better,
            "max_regression": payload.max_regression,
            "guardrail_metrics": sorted(set(payload.guardrail_metrics)),
            "metadata": payload.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _metric_number(metrics: dict[str, Any], name: str) -> float | None:
    value = (metrics or {}).get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _authoritative_promotion_decision(row: Any, *, replay: bool) -> dict[str, Any]:
    ts = row["decided_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "promotion_decision_id": row["promotion_decision_id"],
        "evaluation_run_id": row["evaluation_run_id"],
        "model_id": row["model_id"],
        "feature_set_id": row["feature_set_id"],
        "policy_version": row["policy_version"],
        "policy_snapshot": row["policy_snapshot"],
        "metric_deltas": row["metric_deltas"],
        "decision_state": row["decision_state"],
        "decision_reason": row["decision_reason"],
        "candidate_artifact_uri": row["candidate_artifact_uri"],
        "candidate_artifact_digest": row["candidate_artifact_digest"],
        "decided_by": row["decided_by"],
        "decided_at": ts.isoformat() if hasattr(ts, "isoformat") else ts,
    }


async def create_model_promotion_decision(
    *, tenant_id: str, decided_by: str, payload: Any
) -> dict[str, Any]:
    """WX-11.3: deterministic policy evaluation; no active-model mutation."""
    request_hash = _promotion_decision_hash(payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_promotion_decisions WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_promotion_decision(prior, replay=True)
            evaluation = await conn.fetchrow(
                "SELECT * FROM decision_model_evaluation_runs WHERE tenant_id=$1::uuid AND evaluation_run_id=$2 AND evaluation_state='evaluated' FOR SHARE",
                tenant_id,
                payload.evaluation_run_id,
            )
            if not evaluation:
                return {"status": "not_found"}
            baseline = dict(evaluation["baseline_metrics"] or {})
            candidate = dict(evaluation["candidate_metrics"] or {})
            primary_base = _metric_number(baseline, payload.primary_metric)
            primary_candidate = _metric_number(candidate, payload.primary_metric)
            if primary_base is None or primary_candidate is None:
                return {"status": "conflict", "reason": "primary_metric_missing_or_non_numeric"}
            signed_delta = (
                (primary_base - primary_candidate)
                if payload.lower_is_better
                else (primary_candidate - primary_base)
            )
            deltas: dict[str, float] = {payload.primary_metric: signed_delta}
            failed_guardrails: list[str] = []
            for metric in sorted(set(payload.guardrail_metrics)):
                base = _metric_number(baseline, metric)
                cand = _metric_number(candidate, metric)
                if base is None or cand is None:
                    failed_guardrails.append(f"{metric}:missing")
                    continue
                delta = cand - base
                deltas[metric] = delta
                if delta < -payload.max_regression:
                    failed_guardrails.append(metric)
            eligible = signed_delta >= payload.min_improvement and not failed_guardrails
            state = "promotion_eligible" if eligible else "promotion_rejected"
            reason = (
                "policy_thresholds_satisfied"
                if eligible
                else (
                    "primary_metric_below_threshold"
                    if signed_delta < payload.min_improvement
                    else "guardrail_regression"
                )
            )
            policy_snapshot = {
                "primary_metric": payload.primary_metric,
                "min_improvement": payload.min_improvement,
                "lower_is_better": payload.lower_is_better,
                "max_regression": payload.max_regression,
                "guardrail_metrics": sorted(set(payload.guardrail_metrics)),
                "failed_guardrails": failed_guardrails,
            }
            decision_id = (
                "promo_"
                + hashlib.sha256(
                    f"{tenant_id}:{payload.evaluation_run_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_model_promotion_decisions
                (promotion_decision_id,tenant_id,evaluation_run_id,model_id,feature_set_id,policy_version,
                 policy_snapshot,metric_deltas,decision_state,decision_reason,candidate_artifact_uri,
                 candidate_artifact_digest,idempotency_key,request_hash,decided_by,metadata)
                VALUES($1,$2::uuid,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10,$11,$12,$13,$14,$15,$16::jsonb)
                ON CONFLICT DO NOTHING RETURNING *""",
                decision_id,
                tenant_id,
                payload.evaluation_run_id,
                evaluation["model_id"],
                evaluation["feature_set_id"],
                payload.policy_version,
                _json(policy_snapshot),
                _json(deltas),
                state,
                reason,
                evaluation["candidate_artifact_uri"],
                evaluation["candidate_artifact_digest"],
                payload.idempotency_key,
                request_hash,
                decided_by,
                _json(payload.metadata),
            )
            if row is None:
                return {"status": "conflict", "reason": "promotion_decision_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_PROMOTION_DECISION_CREATED",
                aggregate_type="decision_model_promotion_decisions",
                aggregate_id=decision_id,
                payload={
                    "evaluation_run_id": payload.evaluation_run_id,
                    "model_id": evaluation["model_id"],
                    "decision_state": state,
                    "policy_version": payload.policy_version,
                    "candidate_artifact_digest": evaluation["candidate_artifact_digest"],
                },
            )
            return _authoritative_promotion_decision(row, replay=False)
    finally:
        await conn.close()


def _model_activation_request_hash(payload: Any) -> str:
    blob = json.dumps(
        {
            "promotion_decision_id": payload.promotion_decision_id,
            "target_environment": payload.target_environment,
            "metadata": payload.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_activation_request(row: Any, *, replay: bool) -> dict[str, Any]:
    ts = row["requested_at"]
    return {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "activation_request_id": row["activation_request_id"],
        "promotion_decision_id": row["promotion_decision_id"],
        "evaluation_run_id": row["evaluation_run_id"],
        "model_id": row["model_id"],
        "feature_set_id": row["feature_set_id"],
        "candidate_artifact_uri": row["candidate_artifact_uri"],
        "candidate_artifact_digest": row["candidate_artifact_digest"],
        "target_environment": row["target_environment"],
        "requested_state": row["requested_state"],
        "requested_by": row["requested_by"],
        "requested_at": ts.isoformat() if hasattr(ts, "isoformat") else ts,
    }


async def create_model_activation_request(
    *, tenant_id: str, requested_by: str, payload: Any
) -> dict[str, Any]:
    """WX-11.4: create a reviewable activation request; never mutate registry state."""
    request_hash = _model_activation_request_hash(payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_activation_requests WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != request_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return _authoritative_activation_request(prior, replay=True)
            promotion = await conn.fetchrow(
                """SELECT * FROM decision_model_promotion_decisions
                   WHERE tenant_id=$1::uuid AND promotion_decision_id=$2 FOR SHARE""",
                tenant_id,
                payload.promotion_decision_id,
            )
            if not promotion:
                return {"status": "not_found"}
            if promotion["decision_state"] != "promotion_eligible":
                return {"status": "conflict", "reason": "promotion_decision_not_eligible"}
            activation_request_id = (
                "activate_"
                + hashlib.sha256(
                    f"{tenant_id}:{payload.promotion_decision_id}:{payload.target_environment}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_model_activation_requests
                (activation_request_id,tenant_id,promotion_decision_id,evaluation_run_id,model_id,feature_set_id,
                 candidate_artifact_uri,candidate_artifact_digest,target_environment,requested_state,
                 requested_by,idempotency_key,request_hash,metadata)
                VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,'pending_activation_approval',$10,$11,$12,$13::jsonb)
                ON CONFLICT DO NOTHING RETURNING *""",
                activation_request_id,
                tenant_id,
                payload.promotion_decision_id,
                promotion["evaluation_run_id"],
                promotion["model_id"],
                promotion["feature_set_id"],
                promotion["candidate_artifact_uri"],
                promotion["candidate_artifact_digest"],
                payload.target_environment,
                requested_by,
                payload.idempotency_key,
                request_hash,
                _json(payload.metadata),
            )
            if row is None:
                return {"status": "conflict", "reason": "activation_request_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_ACTIVATION_REQUEST_CREATED",
                aggregate_type="decision_model_activation_requests",
                aggregate_id=activation_request_id,
                payload={
                    "promotion_decision_id": payload.promotion_decision_id,
                    "model_id": promotion["model_id"],
                    "target_environment": payload.target_environment,
                    "requested_state": "pending_activation_approval",
                    "candidate_artifact_digest": promotion["candidate_artifact_digest"],
                },
            )
            return _authoritative_activation_request(row, replay=False)
    finally:
        await conn.close()


def _model_activation_review_hash(payload: Any) -> str:
    blob = json.dumps(
        {
            "review_decision": payload.review_decision,
            "review_reason": payload.review_reason,
            "registry_alias": payload.registry_alias,
            "previous_artifact_uri": payload.previous_artifact_uri,
            "previous_artifact_digest": payload.previous_artifact_digest.lower()
            if payload.previous_artifact_digest
            else None,
            "metadata": payload.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _authoritative_activation_review(
    review: Any, command: Any | None, *, replay: bool
) -> dict[str, Any]:
    reviewed_at = review["reviewed_at"]
    result = {
        "status": "ok",
        "replay": replay,
        "authoritative": True,
        "persisted": True,
        "activation_review_id": review["activation_review_id"],
        "activation_request_id": review["activation_request_id"],
        "review_decision": review["review_decision"],
        "review_reason": review["review_reason"],
        "registry_alias": review["registry_alias"],
        "previous_artifact_uri": review["previous_artifact_uri"],
        "previous_artifact_digest": review["previous_artifact_digest"],
        "reviewed_by": review["reviewed_by"],
        "reviewed_at": reviewed_at.isoformat()
        if hasattr(reviewed_at, "isoformat")
        else reviewed_at,
        "activation_command": None,
    }
    if command:
        created_at = command["created_at"]
        result["activation_command"] = {
            "activation_command_id": command["activation_command_id"],
            "command_state": command["command_state"],
            "model_id": command["model_id"],
            "feature_set_id": command["feature_set_id"],
            "target_environment": command["target_environment"],
            "registry_alias": command["registry_alias"],
            "candidate_artifact_uri": command["candidate_artifact_uri"],
            "candidate_artifact_digest": command["candidate_artifact_digest"],
            "previous_artifact_uri": command["previous_artifact_uri"],
            "previous_artifact_digest": command["previous_artifact_digest"],
            "created_at": created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else created_at,
        }
    return result


async def review_model_activation_request(
    *, tenant_id: str, activation_request_id: str, reviewed_by: str, payload: Any
) -> dict[str, Any]:
    """WX-11.5: immutable review; approval queues one registry command with rollback pointer."""
    request_hash = _model_activation_review_hash(payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_activation_reviews WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if (
                    prior["request_hash"] != request_hash
                    or prior["activation_request_id"] != activation_request_id
                ):
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                command = await conn.fetchrow(
                    "SELECT * FROM decision_model_registry_activation_commands WHERE tenant_id=$1::uuid AND activation_review_id=$2",
                    tenant_id,
                    prior["activation_review_id"],
                )
                return _authoritative_activation_review(prior, command, replay=True)
            request = await conn.fetchrow(
                "SELECT * FROM decision_model_activation_requests WHERE tenant_id=$1::uuid AND activation_request_id=$2 FOR SHARE",
                tenant_id,
                activation_request_id,
            )
            if not request:
                return {"status": "not_found"}
            existing = await conn.fetchrow(
                "SELECT * FROM decision_model_activation_reviews WHERE tenant_id=$1::uuid AND activation_request_id=$2",
                tenant_id,
                activation_request_id,
            )
            if existing:
                return {"status": "conflict", "reason": "activation_request_already_reviewed"}
            review_id = (
                "actreview_"
                + hashlib.sha256(
                    f"{tenant_id}:{activation_request_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            review = await conn.fetchrow(
                """INSERT INTO decision_model_activation_reviews
                (activation_review_id,tenant_id,activation_request_id,review_decision,review_reason,registry_alias,
                 previous_artifact_uri,previous_artifact_digest,reviewed_by,idempotency_key,request_hash,metadata)
                VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb) RETURNING *""",
                review_id,
                tenant_id,
                activation_request_id,
                payload.review_decision,
                payload.review_reason,
                payload.registry_alias,
                payload.previous_artifact_uri,
                payload.previous_artifact_digest.lower()
                if payload.previous_artifact_digest
                else None,
                reviewed_by,
                payload.idempotency_key,
                request_hash,
                _json(payload.metadata),
            )
            command = None
            if payload.review_decision == "approved":
                command_id = (
                    "actcmd_" + hashlib.sha256(f"{tenant_id}:{review_id}".encode()).hexdigest()[:20]
                )
                command = await conn.fetchrow(
                    """INSERT INTO decision_model_registry_activation_commands
                    (activation_command_id,tenant_id,activation_review_id,activation_request_id,model_id,feature_set_id,
                     target_environment,registry_alias,candidate_artifact_uri,candidate_artifact_digest,
                     previous_artifact_uri,previous_artifact_digest,created_by,metadata)
                    VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb) RETURNING *""",
                    command_id,
                    tenant_id,
                    review_id,
                    activation_request_id,
                    request["model_id"],
                    request["feature_set_id"],
                    request["target_environment"],
                    payload.registry_alias,
                    request["candidate_artifact_uri"],
                    request["candidate_artifact_digest"],
                    payload.previous_artifact_uri,
                    payload.previous_artifact_digest.lower(),
                    reviewed_by,
                    _json(payload.metadata),
                )
                await emit_outbox_event(
                    conn,
                    tenant_id=tenant_id,
                    event_type="MODEL_REGISTRY_ACTIVATION_COMMAND_CREATED",
                    aggregate_type="decision_model_registry_activation_commands",
                    aggregate_id=command_id,
                    payload={
                        "activation_request_id": activation_request_id,
                        "model_id": request["model_id"],
                        "target_environment": request["target_environment"],
                        "registry_alias": payload.registry_alias,
                        "candidate_artifact_digest": request["candidate_artifact_digest"],
                        "previous_artifact_digest": payload.previous_artifact_digest.lower(),
                    },
                )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_ACTIVATION_REQUEST_REVIEWED",
                aggregate_type="decision_model_activation_reviews",
                aggregate_id=review_id,
                payload={
                    "activation_request_id": activation_request_id,
                    "review_decision": payload.review_decision,
                    "activation_command_id": command["activation_command_id"] if command else None,
                },
            )
            return _authoritative_activation_review(review, command, replay=False)
    finally:
        await conn.close()


# WX-11.6 registry adapter boundary -------------------------------------------------
def _wx116_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def claim_model_registry_activation_command(
    *, tenant_id: str, command_id: str, adapter_id: str, delivery_token: str
) -> dict[str, Any]:
    conn = await _connect()
    token_hash = hashlib.sha256(delivery_token.encode()).hexdigest()
    try:
        async with conn.transaction():
            command = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_commands WHERE tenant_id=$1::uuid AND activation_command_id=$2 FOR SHARE",
                tenant_id,
                command_id,
            )
            if not command:
                return {"status": "not_found"}
            receipt = await conn.fetchrow(
                "SELECT activation_receipt_id FROM decision_model_registry_activation_receipts WHERE tenant_id=$1::uuid AND activation_command_id=$2",
                tenant_id,
                command_id,
            )
            if receipt:
                return {"status": "conflict", "reason": "activation_command_already_terminal"}
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_claims WHERE tenant_id=$1::uuid AND activation_command_id=$2",
                tenant_id,
                command_id,
            )
            if prior:
                if prior["adapter_id"] == adapter_id and prior["delivery_token_hash"] == token_hash:
                    return {
                        "status": "ok",
                        "replay": True,
                        "authoritative": True,
                        "persisted": True,
                        "activation_claim_id": prior["activation_claim_id"],
                        "activation_command_id": command_id,
                        "adapter_id": adapter_id,
                        "claim_state": "claimed",
                    }
                return {
                    "status": "conflict",
                    "reason": "activation_command_claimed_by_another_adapter",
                }
            claim_id = (
                "regclaim_"
                + hashlib.sha256(f"{tenant_id}:{command_id}:{adapter_id}".encode()).hexdigest()[:20]
            )
            await conn.fetchrow(
                "INSERT INTO decision_model_registry_activation_claims (activation_claim_id,tenant_id,activation_command_id,adapter_id,delivery_token_hash) VALUES($1,$2::uuid,$3,$4,$5) RETURNING *",
                claim_id,
                tenant_id,
                command_id,
                adapter_id,
                token_hash,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_REGISTRY_ACTIVATION_COMMAND_CLAIMED",
                aggregate_type="decision_model_registry_activation_claims",
                aggregate_id=claim_id,
                payload={"activation_command_id": command_id, "adapter_id": adapter_id},
            )
            return {
                "status": "ok",
                "replay": False,
                "authoritative": True,
                "persisted": True,
                "activation_claim_id": claim_id,
                "activation_command_id": command_id,
                "adapter_id": adapter_id,
                "claim_state": "claimed",
            }
    finally:
        await conn.close()


async def record_model_registry_activation_receipt(
    *, tenant_id: str, command_id: str, recorded_by: str, payload: Any
) -> dict[str, Any]:
    req_hash = _wx116_hash(payload.model_dump() if hasattr(payload, "model_dump") else payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_receipts WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != req_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return {
                    "status": "ok",
                    "replay": True,
                    "authoritative": True,
                    "persisted": True,
                    "activation_receipt_id": prior["activation_receipt_id"],
                    "activation_command_id": command_id,
                    "receipt_state": prior["receipt_state"],
                }
            command = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_commands WHERE tenant_id=$1::uuid AND activation_command_id=$2 FOR SHARE",
                tenant_id,
                command_id,
            )
            claim = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_claims WHERE tenant_id=$1::uuid AND activation_command_id=$2",
                tenant_id,
                command_id,
            )
            if not command or not claim:
                return {"status": "not_found"}
            if (
                claim["adapter_id"] != payload.adapter_id
                or claim["delivery_token_hash"]
                != hashlib.sha256(payload.delivery_token.encode()).hexdigest()
            ):
                return {"status": "conflict", "reason": "claim_proof_mismatch"}
            existing = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_activation_receipts WHERE tenant_id=$1::uuid AND activation_command_id=$2",
                tenant_id,
                command_id,
            )
            if existing:
                return {"status": "conflict", "reason": "activation_receipt_already_recorded"}
            if (
                payload.receipt_state == "activated"
                and payload.active_artifact_digest.lower()
                != command["candidate_artifact_digest"].lower()
            ):
                return {"status": "conflict", "reason": "active_artifact_digest_mismatch"}
            rid = (
                "regreceipt_"
                + hashlib.sha256(
                    f"{tenant_id}:{command_id}:{payload.idempotency_key}".encode()
                ).hexdigest()[:20]
            )
            await conn.fetchrow(
                """INSERT INTO decision_model_registry_activation_receipts
              (activation_receipt_id,tenant_id,activation_command_id,activation_claim_id,receipt_state,active_artifact_uri,active_artifact_digest,registry_version,failure_reason,receipt_payload,recorded_by,idempotency_key,request_hash)
              VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13) RETURNING *""",
                rid,
                tenant_id,
                command_id,
                claim["activation_claim_id"],
                payload.receipt_state,
                payload.active_artifact_uri,
                payload.active_artifact_digest.lower() if payload.active_artifact_digest else None,
                payload.registry_version,
                payload.failure_reason,
                _json(payload.receipt_payload),
                recorded_by,
                payload.idempotency_key,
                req_hash,
            )
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_REGISTRY_ACTIVATION_RECEIPT_RECORDED",
                aggregate_type="decision_model_registry_activation_receipts",
                aggregate_id=rid,
                payload={
                    "activation_command_id": command_id,
                    "receipt_state": payload.receipt_state,
                    "registry_alias": command["registry_alias"],
                },
            )
            return {
                "status": "ok",
                "replay": False,
                "authoritative": True,
                "persisted": True,
                "activation_receipt_id": rid,
                "activation_command_id": command_id,
                "receipt_state": payload.receipt_state,
                "registry_alias": command["registry_alias"],
                "active_artifact_digest": payload.active_artifact_digest.lower()
                if payload.active_artifact_digest
                else None,
            }
    finally:
        await conn.close()


async def create_model_registry_rollback_command(
    *, tenant_id: str, receipt_id: str, requested_by: str, payload: Any
) -> dict[str, Any]:
    req_hash = _wx116_hash(payload.model_dump() if hasattr(payload, "model_dump") else payload)
    conn = await _connect()
    try:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT * FROM decision_model_registry_rollback_commands WHERE tenant_id=$1::uuid AND idempotency_key=$2",
                tenant_id,
                payload.idempotency_key,
            )
            if prior:
                if prior["request_hash"] != req_hash:
                    return {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
                return {
                    "status": "ok",
                    "replay": True,
                    "authoritative": True,
                    "persisted": True,
                    "rollback_command_id": prior["rollback_command_id"],
                    "command_state": "queued",
                }
            receipt = await conn.fetchrow(
                """SELECT r.*, c.registry_alias,c.target_environment,c.previous_artifact_uri,c.previous_artifact_digest,c.candidate_artifact_uri,c.candidate_artifact_digest
              FROM decision_model_registry_activation_receipts r JOIN decision_model_registry_activation_commands c USING (activation_command_id)
              WHERE r.tenant_id=$1::uuid AND r.activation_receipt_id=$2 FOR SHARE""",
                tenant_id,
                receipt_id,
            )
            if not receipt:
                return {"status": "not_found"}
            if receipt["receipt_state"] != "activated":
                return {"status": "conflict", "reason": "only_activated_receipt_can_rollback"}
            rid = (
                "rollback_" + hashlib.sha256(f"{tenant_id}:{receipt_id}".encode()).hexdigest()[:20]
            )
            row = await conn.fetchrow(
                """INSERT INTO decision_model_registry_rollback_commands
              (rollback_command_id,tenant_id,activation_receipt_id,activation_command_id,registry_alias,target_environment,restore_artifact_uri,restore_artifact_digest,replace_artifact_uri,replace_artifact_digest,requested_by,reason,idempotency_key,request_hash)
              VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) ON CONFLICT DO NOTHING RETURNING *""",
                rid,
                tenant_id,
                receipt_id,
                receipt["activation_command_id"],
                receipt["registry_alias"],
                receipt["target_environment"],
                receipt["previous_artifact_uri"],
                receipt["previous_artifact_digest"],
                receipt["candidate_artifact_uri"],
                receipt["candidate_artifact_digest"],
                requested_by,
                payload.reason,
                payload.idempotency_key,
                req_hash,
            )
            if not row:
                return {"status": "conflict", "reason": "rollback_command_already_exists"}
            await emit_outbox_event(
                conn,
                tenant_id=tenant_id,
                event_type="MODEL_REGISTRY_ROLLBACK_COMMAND_CREATED",
                aggregate_type="decision_model_registry_rollback_commands",
                aggregate_id=rid,
                payload={
                    "activation_receipt_id": receipt_id,
                    "registry_alias": receipt["registry_alias"],
                    "restore_artifact_digest": receipt["previous_artifact_digest"],
                },
            )
            return {
                "status": "ok",
                "replay": False,
                "authoritative": True,
                "persisted": True,
                "rollback_command_id": rid,
                "activation_receipt_id": receipt_id,
                "command_state": "queued",
                "registry_alias": receipt["registry_alias"],
                "restore_artifact_digest": receipt["previous_artifact_digest"],
            }
    finally:
        await conn.close()
