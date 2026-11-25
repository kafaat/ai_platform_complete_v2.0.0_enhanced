"""Opt-in owner bridge: anomaly task A, reviewed pin task B, explicit assessment.

The public gateway already routes /api/v1/field-tasks/ to this owner. New paths
remain disabled until their schema, grants and both service identities are ready.
The durable outbox is drained explicitly by its reviewer in this first slice;
there is no hidden background job and no actuator command.
"""

from __future__ import annotations

import json
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fm_gateway import (
    INSPECTION_REVIEW,
    OBSERVATION_RECORD,
    Caller,
    caller_connection,
    caller_dependency,
)
from fm_verification_client import (
    VegetationVerificationClient,
    VerificationRemoteError,
    VerificationRemoteRefused,
    VerificationRemoteRejected,
)
from fm_verification_contracts import AssessmentRequest, LinkRequest, canonical, digest, wire
from fm_verification_store import (
    anomaly_task,
    assessment_replay,
    link_replay,
    load_delivery,
    load_link,
    require_actor,
    require_current_assignee,
    resolve_scope,
    revalidate_delivery,
    write_assessment,
    write_link,
)

from shared.contracts.remote_sensing.verification_delivery import flag_enabled

router = APIRouter(prefix="/internal/field-tasks")
remote_client = VegetationVerificationClient()
# Mirrors v289's scouting_verification_delivery_guard; the database refuses a claim beyond it.
MAX_DELIVERY_ATTEMPTS = 8
# `refused` (the receiver's configuration refused the request; nothing applied) is not terminal:
# the reviewer dispatches again once an operator fixed the configuration, and its attempt is
# refunded. `rejected` (the owner will never apply this request) is terminal and keeps the
# owner's reason. `delivery_exhausted` is terminal for sending; dispatching it only reconciles.
TERMINAL_DELIVERY_STATES = frozenset(
    {"delivered", "delivered_review_required", "blocked", "rejected", "delivery_exhausted"}
)


def enabled():
    if not flag_enabled(os.getenv("FM_SCOUTING_VERIFICATION_ENABLED", "0")):
        raise HTTPException(503, "scouting_verification_bridge_disabled")


def storage_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, VerificationRemoteError):
        return HTTPException(503, str(exc))
    if getattr(exc, "sqlstate", "") in {"23505", "23514", "23503", "40001", "40P01"}:
        return HTTPException(409, "verification_owner_state_conflict")
    return HTTPException(503, "verification_owner_storage_unavailable")


async def task_remote(caller, field_id, task_id, permission=INSPECTION_REVIEW):
    async with caller_connection(caller) as conn:
        await require_actor(conn, caller, field_id, permission)
        task = await anomaly_task(conn, caller, field_id, task_id)
    return await remote_client.context(caller.tenant_id, task["anomaly_ref"])


@router.get("/fields/{field_id}/tasks/{task_id}/verification-context")
async def verification_context(
    field_id: str,
    task_id: UUID,
    inspection_task_id: UUID,
    season_binding: Literal["canonical_season", "accepted_record"],
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    # A reviewer reads it to link; the inspection's assignee reads it to write the assessment
    # (owner decision 1), so a caller without inspection:review must be B's current assignee
    # and A must already be linked to that B; both are checked before the owner is called.
    enabled()
    permission = INSPECTION_REVIEW if caller.can(INSPECTION_REVIEW) else OBSERVATION_RECORD
    try:
        if permission == OBSERVATION_RECORD:
            async with caller_connection(caller) as conn:
                await require_current_assignee(conn, caller, field_id, task_id, inspection_task_id)
        remote = await task_remote(caller, field_id, task_id, permission)
        async with caller_connection(caller) as conn:
            context = await resolve_scope(
                conn,
                caller,
                field_id,
                task_id,
                inspection_task_id,
                season_binding,
                remote,
                permission=permission,
            )
            current = await conn.fetchrow(
                "SELECT link_id, revision FROM scouting_verification_links "
                "WHERE tenant_id=$1::uuid AND anomaly_task_id=$2",
                caller.tenant_id,
                task_id,
            )
        return {
            "persisted": True,
            "link_id": str(current["link_id"]) if current else None,
            "link_revision": current["revision"] if current else 0,
            **context,
        }
    except Exception as exc:
        raise storage_error(exc) from exc


@router.post("/fields/{field_id}/tasks/{task_id}/verification-links")
async def create_verification_link(
    field_id: str,
    task_id: UUID,
    req: LinkRequest,
    caller: Caller = Depends(caller_dependency(INSPECTION_REVIEW)),
):
    enabled()
    try:
        async with caller_connection(caller) as conn:
            replay = await link_replay(conn, caller, field_id, task_id, req)
        if replay:
            return replay
        remote = await task_remote(caller, field_id, task_id)
        async with caller_connection(caller) as conn:
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                f"verification-link:{caller.tenant_id}:{req.command_id}",
            )
            await anomaly_task(conn, caller, field_id, task_id, lock=True)
            context = await resolve_scope(
                conn, caller, field_id, task_id, req.inspection_task_id, req.season_binding, remote
            )
            return await write_link(conn, caller, field_id, task_id, req, context)
    except Exception as exc:
        raise storage_error(exc) from exc


@router.post("/fields/{field_id}/verification-links/{link_id}/assessments")
async def approve_verification_assessment(
    field_id: str,
    link_id: UUID,
    req: AssessmentRequest,
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    enabled()
    try:
        async with caller_connection(caller) as conn:
            replay = await assessment_replay(conn, caller, field_id, link_id, req)
            if replay:
                return replay
            link = await load_link(conn, caller, field_id, link_id)
        remote = await task_remote(caller, field_id, link["anomaly_task_id"], OBSERVATION_RECORD)
        async with caller_connection(caller) as conn:
            return await write_assessment(conn, caller, field_id, link_id, req, remote)
    except Exception as exc:
        raise storage_error(exc) from exc


def delivery_view(row):
    return wire(
        {
            k: row[k]
            for k in (
                "delivery_id",
                "assessment_id",
                "state",
                "attempts",
                "last_error",
                "body_digest",
            )
        }
    )


@router.get("/fields/{field_id}/verification-deliveries/{delivery_id}")
async def verification_delivery(
    field_id: str,
    delivery_id: UUID,
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    # A reviewer reads any delivery in scope; the assessment's writer reads their own.
    enabled()
    try:
        async with caller_connection(caller) as conn:
            reviewer = caller.can(INSPECTION_REVIEW)
            await require_actor(
                conn, caller, field_id, INSPECTION_REVIEW if reviewer else OBSERVATION_RECORD
            )
            row = await load_delivery(conn, caller, field_id, delivery_id)
            if not reviewer and row["reviewer"] != caller.user_id:
                raise HTTPException(404, "verification_delivery_not_found")
            return delivery_view(row)
    except Exception as exc:
        raise storage_error(exc) from exc


@router.get("/fields/{field_id}/verification-assessments/{assessment_id}")
async def verification_assessment(
    field_id: str,
    assessment_id: UUID,
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    # A reviewer reads any assessment in scope; the writer reads their own.
    enabled()
    try:
        async with caller_connection(caller) as conn:
            reviewer = caller.can(INSPECTION_REVIEW)
            await require_actor(
                conn, caller, field_id, INSPECTION_REVIEW if reviewer else OBSERVATION_RECORD
            )
            row = await conn.fetchrow(
                "SELECT assessment_text,assessment_digest,reviewer "
                "FROM scouting_verification_assessments "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND assessment_id=$3",
                caller.tenant_id,
                field_id,
                assessment_id,
            )
            if not row or (not reviewer and row["reviewer"] != caller.user_id):
                raise HTTPException(404, "verification_assessment_not_found")
            return {
                "persisted": True,
                "evidence_ref": f"urn:sahool:evidence:scout-{assessment_id.hex}",
                "content_hash": row["assessment_digest"].strip(),
                "assessment": json.loads(row["assessment_text"]),
            }
    except Exception as exc:
        raise storage_error(exc) from exc


def receipt_matches(remote, delivery, link):
    record = remote.get("anomaly") or {}
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        return False
    payload = record["payload"]
    receipt = remote.get("verification_delivery") or payload.get("verification_delivery")
    body = json.loads(delivery["body_text"])
    accepted_version = body["expected_version"] + 1
    current_version = record.get("aggregate_version")
    if type(current_version) is not int or current_version < accepted_version:
        return False
    # A later legitimate owner disposition may change its live reason codes.
    # At the acceptance version itself, the live completion must match as well.
    if current_version == accepted_version and (
        payload.get("verification_result") != body["verification_result"]
        or payload.get("verification_completed_at") != body["completed_at"]
        or payload.get("verification_evidence_refs") != body["evidence_refs"]
        or payload.get("verification_evidence") != body["evidence"]
        or payload.get("disposition_reason_codes") != body["reason_codes"]
    ):
        return False
    return bool(
        isinstance(receipt, dict)
        and record.get("tenant_id") == str(delivery["tenant_id"])
        and record.get("field_id") == delivery["field_id"]
        and record.get("anomaly_ref") == link["scope_snapshot"]["anomaly_ref"]
        and record.get("task_ref") == body["task_ref"]
        and receipt.get("idempotency_key") == delivery["idempotency_key"]
        and receipt.get("request_digest") == delivery["body_digest"].strip()
        and receipt.get("expected_version") == body["expected_version"]
        and receipt.get("accepted_version") == accepted_version
        and receipt.get("request_snapshot_digest") == link["anomaly_snapshot_digest"].strip()
        and receipt.get("original_completion") == body
    )


async def finish_delivery(caller, field_id, delivery, lease, state, *, error=None, receipt=None):
    async with caller_connection(caller) as conn:
        if state == "delivered":
            try:
                await revalidate_delivery(conn, caller, field_id, delivery)
            except HTTPException as exc:
                # Acceptance at another owner cannot be rolled back by changing
                # the local label. Keep that fact and require a new human review.
                state, error = "delivered_review_required", str(exc.detail)
        # v289 lets a row leave `sending` only for the transaction that names its lease. The
        # explicit block keeps the transaction-local setting and the UPDATE in one visible scope
        # (inside caller_connection's transaction it is a savepoint; the setting survives its
        # release), so tenant_guc_scope_guard sees it is never set outside a transaction.
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.verification_lease', $1, true)", str(lease))
            # A configuration refusal applied nothing at the owner, so its attempt is refunded.
            await conn.execute(
                "UPDATE scouting_verification_outbox SET state=$4,last_error=$5,receipt=$6::jsonb,"
                "attempts=attempts-CASE WHEN $4='refused' THEN 1 ELSE 0 END,"
                "lease_token=NULL,lease_until=NULL,updated_at=clock_timestamp() "
                "WHERE tenant_id=$1::uuid AND delivery_id=$2 AND lease_token=$3",
                caller.tenant_id,
                delivery["delivery_id"],
                lease,
                state,
                error,
                canonical(receipt) if receipt is not None else None,
            )
        row = await load_delivery(conn, caller, field_id, delivery["delivery_id"])
        return delivery_view(row)


async def reconcile_exhausted(caller, field_id, delivery):
    """Read-only check of an exhausted delivery against the owner; never sends the result again.

    The owner's receipt settles it as delivered; an anomaly that moved on without our receipt
    settles it as blocked (the owner's compare-and-set refuses our stale version, so no late
    retry can apply it). Otherwise the outcome is still unknown and the row stays exhausted.
    """
    require_original_assessor(caller, delivery)
    async with caller_connection(caller) as conn:
        link = await load_link(conn, caller, field_id, delivery["link_id"])
    anomaly_ref = link["scope_snapshot"]["anomaly_ref"]
    try:
        remote = await remote_client.context(caller.tenant_id, anomaly_ref)
    except VerificationRemoteError as exc:
        raise HTTPException(503, f"verification_reconcile_unavailable:{exc}") from exc
    state, error, receipt = None, None, None
    if receipt_matches(remote, delivery, link):
        state, receipt = "delivered", remote
    elif remote.get("snapshot_digest") != link["anomaly_snapshot_digest"].strip() or digest(
        remote.get("anomaly")
    ) != remote.get("snapshot_digest"):
        state, error = "blocked", "anomaly_changed_without_matching_receipt"
    async with caller_connection(caller) as conn:
        if state == "delivered":
            try:
                await revalidate_delivery(conn, caller, field_id, delivery)
            except HTTPException as exc:
                state, error = "delivered_review_required", str(exc.detail)
        if state is not None:
            await conn.execute(
                "UPDATE scouting_verification_outbox SET state=$3,last_error=$4,receipt=$5::jsonb,"
                "updated_at=clock_timestamp() WHERE tenant_id=$1::uuid AND delivery_id=$2 "
                "AND state='delivery_exhausted'",
                caller.tenant_id,
                delivery["delivery_id"],
                state,
                error,
                canonical(receipt) if receipt is not None else None,
            )
        return delivery_view(await load_delivery(conn, caller, field_id, delivery["delivery_id"]))


async def dispatch_delivery(caller, field_id, delivery_id):
    enabled()
    lease = uuid4()
    async with caller_connection(caller) as conn:
        await require_actor(conn, caller, field_id, OBSERVATION_RECORD)
        delivery = await load_delivery(conn, caller, field_id, delivery_id, lock=True)
        # Only the assessment's writer dispatches, reconciles or sees the row through this route,
        # whatever its state: GET hides another user's delivery, so dispatch must not reveal it.
        require_original_assessor(caller, delivery)
        if delivery["state"] == "delivery_exhausted":
            if not remote_client.configured():
                raise HTTPException(503, "verification_transport_unconfigured")
            reconcile = True
        elif delivery["state"] in TERMINAL_DELIVERY_STATES:
            return delivery_view(delivery)
        else:
            reconcile = False
            # An unconfigured transport (no URL, token, key or key id) is refused before any
            # read or claim, so the row is not left in `sending` and no attempt is counted.
            if not remote_client.configured():
                raise HTTPException(503, "verification_transport_unconfigured")
            if await delivery_busy(conn, delivery_id):
                raise HTTPException(409, "verification_delivery_already_claimed")
            link = await load_link(conn, caller, field_id, delivery["link_id"])
            prior_state = delivery["state"]
    if reconcile:
        return await reconcile_exhausted(caller, field_id, delivery)
    # The owner's current state is read BEFORE the claim. This read sends nothing, so a failed
    # read must not use up the delivery's budget: eight timeouts here used to exhaust a row that
    # was never sent, leaving it stuck (reconcile never sends, relinking refuses it).
    anomaly_ref = link["scope_snapshot"]["anomaly_ref"]
    remote, pre_read = None, None
    try:
        remote = await remote_client.context(caller.tenant_id, anomaly_ref)
    except VerificationRemoteRejected as exc:
        # Definitive: the owner will never accept this request. Recorded as terminal below.
        pre_read = ("rejected", {"error": str(exc)})
    except VerificationRemoteRefused as exc:
        if prior_state not in {"pending", "refused"}:
            # An earlier POST of this delivery may have been applied; recording a refusal
            # would hide that uncertainty (and let relinking block it). Nothing changes.
            raise HTTPException(503, f"verification_context_unavailable:{exc}") from exc
        # Nothing was ever sent: record the receiver's refusal visibly, with the attempt
        # refunded (the only refund v289 allows is sending -> refused).
        pre_read = ("refused", {"error": str(exc)})
    except VerificationRemoteError as exc:
        raise HTTPException(503, f"verification_context_unavailable:{exc}") from exc
    except Exception as exc:
        raise HTTPException(503, f"verification_context_unavailable:{type(exc).__name__}") from exc
    async with caller_connection(caller) as conn:
        delivery = await load_delivery(conn, caller, field_id, delivery_id, lock=True)
        require_original_assessor(caller, delivery)
        if (
            delivery["state"] in TERMINAL_DELIVERY_STATES
            or delivery["state"] == "delivery_exhausted"
        ):
            return delivery_view(delivery)
        if delivery["state"] != prior_state or await delivery_busy(conn, delivery_id):
            raise HTTPException(409, "verification_delivery_already_claimed")
        if delivery["attempts"] >= MAX_DELIVERY_ATTEMPTS:
            # Whether the owner accepted an earlier attempt is unknown; stop retrying and
            # hand the row to a person. v289 refuses any further claim at this count.
            await conn.execute(
                "UPDATE scouting_verification_outbox SET state='delivery_exhausted',"
                "lease_token=NULL,lease_until=NULL,"
                "last_error='verification_delivery_attempts_exhausted',"
                "updated_at=clock_timestamp() WHERE delivery_id=$1",
                delivery_id,
            )
            return delivery_view(await load_delivery(conn, caller, field_id, delivery_id))
        await conn.execute(
            "UPDATE scouting_verification_outbox SET state='sending',lease_token=$2,"
            "lease_until=clock_timestamp()+interval '120 seconds',attempts=attempts+1,"
            "updated_at=clock_timestamp() WHERE delivery_id=$1",
            delivery_id,
            lease,
        )
    if pre_read is not None:
        return await settle(caller, field_id, delivery, lease, *pre_read)
    # The try block only decides the outcome; settle() records it once, outside, so a storage
    # failure while recording can never be mistaken for the owner's verdict.
    try:
        if receipt_matches(remote, delivery, link):
            outcome = ("delivered", {"receipt": remote})
        elif remote.get("snapshot_digest") != link["anomaly_snapshot_digest"].strip() or digest(
            remote.get("anomaly")
        ) != remote.get("snapshot_digest"):
            outcome = ("blocked", {"error": "anomaly_changed_without_matching_receipt"})
        else:
            async with caller_connection(caller) as conn:
                await revalidate_delivery(conn, caller, field_id, delivery)
                held = await conn.fetchval(
                    "SELECT true FROM scouting_verification_outbox WHERE delivery_id=$1 "
                    "AND lease_token=$2 AND lease_until>clock_timestamp()",
                    delivery_id,
                    lease,
                )
                if not held:
                    raise HTTPException(409, "verification_delivery_lease_lost")
            response = await remote_client.complete(
                caller.tenant_id,
                anomaly_ref,
                json.loads(delivery["body_text"]),
                delivery["idempotency_key"],
            )
            if receipt_matches(response, delivery, link):
                outcome = ("delivered", {"receipt": response})
            else:
                outcome = ("delivery_unknown", {"error": "verification_receipt_not_bound"})
    except VerificationRemoteRefused as exc:
        outcome = ("refused", {"error": str(exc)})
    except VerificationRemoteRejected as exc:
        outcome = ("rejected", {"error": str(exc)})
    except VerificationRemoteError as exc:
        outcome = ("delivery_unknown", {"error": str(exc)})
    except HTTPException as exc:
        # A 4xx here is a local revalidation verdict (scope, grant, evidence, lease lost): the
        # delivery must not be sent, so it is blocked. A 5xx is local storage being unavailable,
        # which says nothing about the delivery: its outcome is unknown, not blocked.
        if exc.status_code < 500:
            outcome = ("blocked", {"error": str(exc.detail)})
        else:
            outcome = ("delivery_unknown", {"error": f"verification_local_storage:{exc.detail}"})
    except Exception as exc:
        # A bug or a malformed reply: a request may already have reached the owner.
        outcome = (
            "delivery_unknown",
            {"error": f"verification_dispatch_failed:{type(exc).__name__}"},
        )
    return await settle(caller, field_id, delivery, lease, *outcome)


def require_original_assessor(caller, delivery):
    if delivery["reviewer"] != caller.user_id or delivery["reviewer_role"] != caller.role:
        raise HTTPException(403, "delivery_requires_the_original_assessor")


async def delivery_busy(conn, delivery_id):
    return await conn.fetchval(
        "SELECT lease_until > clock_timestamp() FROM scouting_verification_outbox WHERE delivery_id=$1",
        delivery_id,
    )


async def settle(caller, field_id, delivery, lease, state, fields):
    """Record the outcome; if that fails, record `delivery_unknown` instead of stranding the row.

    A failure while recording `delivered` (a connection blip) must never become `blocked`:
    the owner accepted the result. If even the fallback cannot be written, the error
    propagates and the 120-second lease plus the next dispatch's reconcile recover the row.
    """
    try:
        return await finish_delivery(caller, field_id, delivery, lease, state, **fields)
    except Exception as exc:
        if state == "delivery_unknown":
            raise
        return await finish_delivery(
            caller,
            field_id,
            delivery,
            lease,
            "delivery_unknown",
            error=f"verification_settle_failed:{state}:{type(exc).__name__}",
        )


@router.post("/fields/{field_id}/verification-deliveries/{delivery_id}/deliver")
async def deliver_verification(
    field_id: str,
    delivery_id: UUID,
    caller: Caller = Depends(caller_dependency(OBSERVATION_RECORD)),
):
    try:
        return await dispatch_delivery(caller, field_id, delivery_id)
    except Exception as exc:
        raise storage_error(exc) from exc
