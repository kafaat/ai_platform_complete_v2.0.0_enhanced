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
