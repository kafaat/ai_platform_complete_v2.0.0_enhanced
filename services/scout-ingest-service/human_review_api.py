"""A specialist's assessment history for an immutable scouting photo (owner phase 9, v268).

suspected / ruled_out / requires_lab / inconclusive only: no 'confirmed', no prescription, no
actuation. The reviewer is an active expert/agronomist with a live photo.diagnosis_review grant
(and, from v270, a current owner-attested credential; the SQL guards enforce both). A review stays
in the history after the reviewer loses the grant and is shown as no longer authorised. Behind
SCOUT_MEDIA_HUMAN_REVIEW_ENABLED (default 0).
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
)
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter()
_TRUE = {"1", "yes", "true", "on"}
REVIEWER_ROLES = credential_status.SPECIALIST_ROLES
LINK_PROOF = "scout_photo_human_review_events:v268"
CODES = ChainCodes(
    reused="scout_photo_human_event_id_reused",
    predecessor="scout_photo_human_predecessor_conflict",
    concurrent="scout_photo_human_concurrent_conflict",
    unverified="scout_photo_human_receipt_unverified",
    ambiguous="scout_photo_human_review_chain_ambiguous",
)


def human_review_enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_HUMAN_REVIEW_ENABLED", "0").strip().lower() in _TRUE


class HumanReviewEventIn(BaseModel):
    event_id: UUID
    action: Literal["review", "retract"]
    assessment: Literal["suspected", "ruled_out", "requires_lab", "inconclusive"] | None = None
    diagnosis_code: str | None = Field(None, max_length=100, pattern=r"^[a-z][a-z0-9_.-]{1,99}$")
    review_method: Literal["photo_review", "field_exam"] | None = None
    previous_event_id: UUID | None = None
    reason: str = Field(min_length=20, max_length=2000)


def review_refusal(data: HumanReviewEventIn) -> tuple[str | None, str | None]:
    reason = data.reason.strip()
    if len(reason) < 20:
        return "scout_photo_human_reason_required", None
    if data.previous_event_id is not None and data.previous_event_id == data.event_id:
        return "scout_photo_human_self_reference", None
    if data.action == "review":
        if data.assessment is None or data.review_method is None:
            return "scout_photo_human_assessment_required", None
        if (data.assessment == "suspected") != (data.diagnosis_code is not None):
            return "scout_photo_human_suspicion_code_mismatch", None
    elif (
        data.assessment is not None
        or data.diagnosis_code is not None
        or data.review_method is not None
        or data.previous_event_id is None
    ):
        return "scout_photo_human_retraction_invalid", None
    return None, reason


def review_matches(row, data: HumanReviewEventIn, reviewer: int, reason: str) -> bool:
    return (
        row["action"] == data.action
        and row["assessment"] == data.assessment
        and row["diagnosis_code"] == data.diagnosis_code
        and row["review_method"] == data.review_method
        and row["reason"] == reason
        and row["reviewer_user_id"] == reviewer
        and same_previous(row["previous_event_id"], data.previous_event_id)
    )


def public_review(row) -> dict:
    if row is None:
        return {"state": "human_review_not_recorded", "human_diagnosis_approved": False}
    if row["action"] == "retract":
        return {
            "state": "retracted",
            "link_event_id": str(row["event_id"]),
            "human_diagnosis_approved": False,
        }
    if not row["image_sha256"] or (
        str(row["image_sha256"]).strip() != str(row["content_sha256"]).strip()
    ):
        raise HTTPException(503, "scout_photo_human_review_image_proof_invalid")
    active = (
        row["reviewer_active"] is True
        and str(row["reviewer_role"]).lower() in REVIEWER_ROLES
        and row["reviewer_grant_active"] is True
    )
    return {
        "state": "human_assessment_recorded" if active else "reviewer_no_longer_authorized",
        "review_event_id": str(row["event_id"]),
        "reviewer_user_id": row["reviewer_user_id"],
        "assessment": row["assessment"],
        "diagnosis_code": row["diagnosis_code"],
        "review_method": row["review_method"],
        "image_sha256": str(row["image_sha256"]).strip(),
        "link_proof": LINK_PROOF,
        "professional_license_verified": False,
        "human_diagnosis_approved": False,
    }


async def _head(conn, tenant: str, field_id: str, pin_id: str):
    rows = await conn.fetch(
        "SELECT e.event_id, e.action, e.assessment, e.diagnosis_code, e.review_method, "
        "e.image_sha256, p.content_sha256, e.reviewer_user_id, u.active AS reviewer_active, "
        "u.role AS reviewer_role, EXISTS (SELECT 1 FROM scout_photo_field_access_grants g "
        "WHERE g.tenant_id=e.tenant_id AND g.field_id=e.field_id "
        "AND g.user_id=e.reviewer_user_id AND g.scope='photo.diagnosis_review' "
        "AND g.revoked_at IS NULL AND g.granted_at <= now() "
        "AND g.expires_at > now() AND g.expires_at <= g.granted_at + interval '90 days') "
        "AS reviewer_grant_active FROM scout_photo_human_review_events e "
        "JOIN scout_photo_evidence p ON p.tenant_id=e.tenant_id "
        "AND p.field_id=e.field_id AND p.pin_id=e.pin_id "
        "LEFT JOIN users u ON u.id=e.reviewer_user_id AND u.tenant_id=e.tenant_id "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_photo_human_review_events n "
        "WHERE n.previous_event_id=e.event_id) ORDER BY e.created_at DESC LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    return single_head(rows, CODES)


async def current_human_review_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not human_review_enabled():
        return {"state": "human_review_not_recorded", "human_diagnosis_approved": False}
    row = await _head(conn, tenant, field_id, pin_id)
    result = public_review(row)
    if row is not None and row["action"] == "review":
        credential = await credential_status.current_review_credential(
            conn, tenant, row["reviewer_user_id"]
        )
        result["credential"] = credential
        if credential["state"] not in ("owner_attested_current", "not_checked_feature_disabled"):
            result["state"] = "reviewer_credential_not_current"
    return result


def _gate(token, tenant, uid, role) -> tuple[str, str, int]:
    tenant_id, actor = media_api.authorize(token, tenant, uid, role, write=False)
    if not human_review_enabled():
        raise HTTPException(404, "scout_photo_human_review_disabled")
    media_api.require_role(role, REVIEWER_ROLES, "scout_photo_human_reviewer_role_required")
    return tenant_id, actor, positive_user_id(actor, "scout_photo_human_reviewer_id_invalid")


@router.post("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/human-review-events")
async def post_human_review(
    field_id: str,
    pin_id: str,
    data: HumanReviewEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor, reviewer = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    code, reason = review_refusal(data)
    if code:
        raise HTTPException(422, code)
    scope = "photo.diagnosis_review"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )
            if data.action == "review" and credential_status.enabled():
                status = await credential_status.current_review_credential(conn, tenant, reviewer)
                if status["state"] != "owner_attested_current":
                    raise HTTPException(403, "scout_human_review_current_credential_required")

            async def insert():
                if data.action == "retract":
                    return await conn.fetchval(
                        "INSERT INTO scout_photo_human_review_events "
                        "(event_id,tenant_id,field_id,pin_id,action,previous_event_id,"
                        "reviewer_user_id,reason) VALUES ($1,$2::uuid,$3,$4,'retract',$5,$6,$7) "
                        "ON CONFLICT DO NOTHING RETURNING event_id",
                        data.event_id,
                        tenant,
                        field_id,
                        pin_id,
                        data.previous_event_id,
                        reviewer,
                        reason,
                    )
                # The image digest comes from the stored evidence row, never from the client.
                return await conn.fetchval(
                    "INSERT INTO scout_photo_human_review_events "
                    "(event_id,tenant_id,field_id,pin_id,action,assessment,diagnosis_code,"
                    "review_method,image_sha256,previous_event_id,reviewer_user_id,reason) "
                    "SELECT $1,$2::uuid,$3,$4,'review',$5,$6,$7,p.content_sha256,$8,$9,$10 "
                    "FROM scout_photo_evidence p WHERE p.tenant_id=$2::uuid AND p.field_id=$3 "
                    "AND p.pin_id=$4 ON CONFLICT DO NOTHING RETURNING event_id",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                    data.assessment,
                    data.diagnosis_code,
                    data.review_method,
                    data.previous_event_id,
                    reviewer,
                    reason,
                )

            idempotent, head = await append_event(
                event_id=data.event_id,
                previous_event_id=data.previous_event_id,
                load_existing=lambda: conn.fetchrow(
                    "SELECT event_id, action, assessment, diagnosis_code, review_method, "
                    "previous_event_id, reviewer_user_id, reason "
                    "FROM scout_photo_human_review_events "
                    "WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                ),
                matches=lambda row: review_matches(row, data, reviewer, reason),
                read_head=lambda: _head(conn, tenant, field_id, pin_id),
                insert=insert,
                codes=CODES,
                head_required=data.action == "retract",
            )
            current = public_review(head)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if guard_refusal(exc):  # the v268/v270 guards: reviewer not (or no longer) qualified
            raise HTTPException(403, "scout_photo_reviewer_not_authorized") from None
        raise media_api._db_error() from exc
    return {
        "event_id": str(data.event_id),
        "idempotent": idempotent,
        "persisted": True,
        "current": current,
        "automatic_pesticide_action_authorized": False,
    }


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/human-review-events")
async def get_human_reviews(
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
        tenant, field_id, actor, "photo.diagnosis_review", x_user_role
    )
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                "SELECT event_id, action, assessment, diagnosis_code, review_method, "
                "previous_event_id, reviewer_user_id, reason, created_at "
                "FROM scout_photo_human_review_events "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 "
                "ORDER BY created_at, event_id LIMIT 201",
                tenant,
                field_id,
                pin_id,
            )
            events = history_rows(rows, "scout_photo_human_history_limit_exceeded")
            current = await current_human_review_context(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise media_api._db_error() from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "field_id": field_id,
        "pin_id": pin_id,
        "history_complete": True,
        "events": events,
        "current": current,
        "automatic_pesticide_action_authorized": False,
    }
