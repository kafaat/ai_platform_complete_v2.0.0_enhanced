"""Second-person review of a proposed treatment plan digest (owner phase 11, v271); no spray permit.

No product or dose is produced, nothing is dispensed, no application can start from here. A
proposal rests on a live human 'suspected' / 'requires_lab' review of this exact photo; the
reviewer differs from the proposer; both hold a photo.treatment_review grant and a current
owner-attested crop_protection credential (credential enforcement must be on). Behind
SCOUT_MEDIA_TREATMENT_REVIEW_ENABLED (default 0).
"""

from __future__ import annotations

import os
from typing import Literal
from uuid import UUID

import credential_status
import media_api
from evidence_chain import (
    ChainCodes,
    append_event,
    guard_refusal,
    history_rows,
    positive_user_id,
    same_previous,
    single_head,
    text_or_none,
)
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter()
_TRUE = {"1", "true", "on", "yes"}
REVIEWER_ROLES = credential_status.SPECIALIST_ROLES
CODES = ChainCodes(
    reused="scout_treatment_event_id_reused",
    predecessor="scout_treatment_predecessor_conflict",
    concurrent="scout_treatment_concurrent_conflict",
    unverified="scout_treatment_receipt_unverified",
    ambiguous="scout_treatment_chain_ambiguous",
)
_STATES = {
    "propose": "proposed",
    "review": "reviewed_for_manual_consideration",
    "reject": "rejected",
    "withdraw": "withdrawn",
}
_PATH = "/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/treatment-review-events"


def enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_TREATMENT_REVIEW_ENABLED", "0").strip().lower() in _TRUE


class TreatmentEventIn(BaseModel):
    event_id: UUID
    action: Literal["propose", "review", "reject", "withdraw"]
    plan_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    source_review_event_id: UUID | None = None
    previous_event_id: UUID | None = None
    reason: str = Field(min_length=20, max_length=2000)


def treatment_refusal(req: TreatmentEventIn) -> tuple[str | None, str]:
    note = req.reason.strip()
    if len(note) < 20:
        return "scout_treatment_reason_required", ""
    if req.previous_event_id is not None and req.event_id == req.previous_event_id:
        return "scout_treatment_self_reference", ""
    if req.action == "propose":
        if (
            req.previous_event_id is not None
            or not req.plan_sha256
            or req.source_review_event_id is None
        ):
            return "scout_treatment_proposal_proof_required", ""
    elif (
        req.previous_event_id is None
        or req.plan_sha256 is not None
        or req.source_review_event_id is not None
    ):
        return "scout_treatment_review_shape_invalid", ""
    return None, note


def treatment_head_refusal(head, action: str, actor_id: int) -> str | None:
    """Only a proposal can be reviewed/rejected/withdrawn; never by its own proposer (review)."""
    if head is None:
        return None
    if head["action"] != "propose":
        return "scout_treatment_already_reviewed"
    if action == "review" and head["actor_user_id"] == actor_id:
        return "scout_treatment_two_person_rule"
    return None


def public_treatment(row) -> dict:
    return {
        "state": _STATES[row["action"]] if row else "no_proposal",
        "event_id": str(row["event_id"]) if row else None,
        "manual_plan_review_only": True,
        "pesticide_application_authorized": False,
        "automatic_pesticide_action_authorized": False,
    }


async def _head(conn, tenant: str, field_id: str, pin_id: str):
    rows = await conn.fetch(
        "SELECT event_id, action, actor_user_id, previous_event_id "
        "FROM scout_treatment_review_events e "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_treatment_review_events n "
        "WHERE n.previous_event_id=e.event_id) LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    return single_head(rows, CODES)


async def current_treatment_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not enabled():
        return {"state": "disabled", "pesticide_application_authorized": False}
    head = await _head(conn, tenant, field_id, pin_id)
    result = public_treatment(head)
    if head and head["action"] in ("propose", "review"):
        # A plan is current only while its source assessment is still the photo's live review:
        # an old plan must not look active after the specialist retracts the finding.
        proposal_id = head["event_id"] if head["action"] == "propose" else head["previous_event_id"]
        proposal = await conn.fetchrow(
            "SELECT source_review_event_id, actor_user_id FROM scout_treatment_review_events "
            "WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4 "
            "AND action='propose'",
            proposal_id,
            tenant,
            field_id,
            pin_id,
        )
        if proposal is None:
            raise HTTPException(503, "scout_treatment_source_proposal_missing")
        from human_review_api import current_human_review_context

        origin = await current_human_review_context(conn, tenant, field_id, pin_id)
        if origin.get("state") != "human_assessment_recorded" or origin.get(
            "review_event_id"
        ) != text_or_none(proposal["source_review_event_id"]):
            result["state"] = "historical_source_assessment_not_current"
        if credential_status.enabled():
            signers = list(dict.fromkeys([head["actor_user_id"], proposal["actor_user_id"]]))
            states = [
                (await credential_status.current_credential(conn, tenant, s, "crop_protection"))[
                    "state"
                ]
                for s in signers
            ]
            result["all_signers_credential_current"] = all(
                state == "owner_attested_current" for state in states
            )
            if not result["all_signers_credential_current"]:
                result["state"] = "historical_signer_credential_not_current"
        else:
            result["state"] = "historical_credential_enforcement_disabled"
    return result


def _gate(token, tenant, uid, role) -> tuple[str, str, int]:
    tenant_id, actor = media_api.authorize(token, tenant, uid, role, write=False)
    if not enabled():
        raise HTTPException(404, "scout_treatment_review_disabled")
    media_api.require_role(role, REVIEWER_ROLES, "scout_treatment_reviewer_role_required")
    return tenant_id, actor, positive_user_id(actor, "scout_treatment_actor_invalid")


@router.post(_PATH)
async def post_treatment_event(
    field_id: str,
    pin_id: str,
    req: TreatmentEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor, actor_id = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    if not credential_status.enabled():
        raise HTTPException(503, "scout_treatment_credentials_enforcement_required")
    media_api._require_valid_pin(pin_id)
    code, reason = treatment_refusal(req)
    if code:
        raise HTTPException(422, code)
    scope = "photo.treatment_review"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )
            credential = await credential_status.current_credential(
                conn, tenant, actor_id, "crop_protection"
            )
            if credential["state"] != "owner_attested_current":
                raise HTTPException(403, "scout_treatment_current_credential_required")

            def head_allows(head) -> None:
                refusal = treatment_head_refusal(head, req.action, actor_id)
                if refusal == "scout_treatment_two_person_rule":
                    raise HTTPException(403, refusal)
                if refusal:
                    raise HTTPException(409, refusal)

            idempotent, head = await append_event(
                event_id=req.event_id,
                previous_event_id=req.previous_event_id,
                load_existing=lambda: conn.fetchrow(
                    "SELECT action, plan_sha256, source_review_event_id, previous_event_id, "
                    "actor_user_id, reason FROM scout_treatment_review_events "
                    "WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                    req.event_id,
                    tenant,
                    field_id,
                    pin_id,
                ),
                matches=lambda row: (
                    row["action"] == req.action
                    and row["actor_user_id"] == actor_id
                    and row["reason"] == reason
                    and same_previous(row["previous_event_id"], req.previous_event_id)
                    and same_previous(row["source_review_event_id"], req.source_review_event_id)
                    and (str(row["plan_sha256"]).strip() if row["plan_sha256"] else None)
                    == req.plan_sha256
                ),
                read_head=lambda: _head(conn, tenant, field_id, pin_id),
                insert=lambda: conn.fetchval(
                    "INSERT INTO scout_treatment_review_events "
                    "(event_id,tenant_id,field_id,pin_id,action,plan_sha256,"
                    "source_review_event_id,previous_event_id,actor_user_id,reason) "
                    "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10) "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    req.event_id,
                    tenant,
                    field_id,
                    pin_id,
                    req.action,
                    req.plan_sha256,
                    req.source_review_event_id,
                    req.previous_event_id,
                    actor_id,
                    reason,
                ),
                codes=CODES,
                head_required=req.action != "propose",
                head_allows=head_allows,
            )
            current = public_treatment(head)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if guard_refusal(exc):
            raise HTTPException(403, "scout_treatment_actor_unauthorized") from None
        if getattr(exc, "sqlstate", None) == "23514" and str(exc).startswith("scout_treatment"):
            raise HTTPException(422, str(exc).split()[0]) from None
        raise media_api._db_error() from exc
    return {
        "event_id": str(req.event_id),
        "persisted": True,
        "idempotent": idempotent,
        "current": current,
        "pesticide_application_authorized": False,
        "manual_review_only": True,
    }


@router.get(_PATH)
async def get_treatment_events(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor, _ = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    await media_api.require_media_field_scope(
        tenant, field_id, actor, "photo.treatment_review", x_user_role
    )
    try:
        conn = await media_api._tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                "SELECT event_id, action, actor_user_id, previous_event_id, recorded_at "
                "FROM scout_treatment_review_events WHERE tenant_id=$1::uuid AND field_id=$2 "
                "AND pin_id=$3 ORDER BY recorded_at, event_id LIMIT 201",
                tenant,
                field_id,
                pin_id,
            )
            events = history_rows(rows, "scout_treatment_history_limit_exceeded")
            current = await current_treatment_context(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise media_api._db_error() from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {"events": events, "current": current, "pesticide_application_authorized": False}
