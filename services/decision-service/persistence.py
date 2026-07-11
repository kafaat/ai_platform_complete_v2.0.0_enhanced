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
