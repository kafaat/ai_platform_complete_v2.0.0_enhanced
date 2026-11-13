"""Explicit photo -> soil/water sample context (owner phase 9, v267).

Proves only that a granted user linked a sample of the same tenant and field, past 'requested'
and not rejected/cancelled, to persisted camera evidence. Not a plant tissue specimen and not a
diagnosis; the sample stays in the platform's lab workflow (lab_samples, column SELECT only).
Behind SCOUT_MEDIA_LAB_LINK_ENABLED (default 0).
"""

from __future__ import annotations

import os
from typing import Literal
from uuid import UUID

import media_api
from evidence_chain import ChainCodes, append_event, history_rows, same_previous, single_head
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter()
_TRUE = {"1", "true", "yes", "on"}
LINK_ROLES = media_api.SEASON_LINK_ROLES
ELIGIBLE_STATUSES = ("sampled", "in_lab", "result_received", "approved", "published")
LINK_PROOF = "scout_photo_lab_link_events:v267"
CODES = ChainCodes(
    reused="scout_photo_lab_event_id_reused",
    predecessor="scout_photo_lab_predecessor_conflict",
    concurrent="scout_photo_lab_concurrent_conflict",
    unverified="scout_photo_lab_receipt_unverified",
    ambiguous="scout_photo_lab_chain_ambiguous",
)
_PATH = "/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/lab-link-events"
_ELIGIBLE_SQL = "s.kind IN ('soil','water') AND s.status IN ({})".format(
    ",".join(f"'{status}'" for status in ELIGIBLE_STATUSES)
)


def lab_bridge_enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_LAB_LINK_ENABLED", "0").strip().lower() in _TRUE


class LabLinkEventIn(BaseModel):
    event_id: UUID
    action: Literal["link", "revoke"]
    sample_id: str | None = Field(None, max_length=64)
    previous_event_id: UUID | None = None
    reason: str | None = Field(None, max_length=2000)


def lab_refusal(data: LabLinkEventIn) -> tuple[str | None, str | None]:
    if data.action == "link" and (
        not data.sample_id or not data.sample_id.strip() or data.sample_id != data.sample_id.strip()
    ):
        return "scout_photo_lab_sample_id_required", None
    if data.action == "revoke" and data.sample_id is not None:
        return "scout_photo_lab_revoke_has_sample", None
    if data.previous_event_id is not None and data.previous_event_id == data.event_id:
        return "scout_photo_lab_self_reference", None
    reason = data.reason.strip() if data.reason else None
    # v267 CHECK: a revision or revocation carries a reason of 10-2000 characters.
    if (data.action == "revoke" or data.previous_event_id is not None) and (
        reason is None or len(reason) < 10
    ):
        return "scout_photo_lab_revision_reason_required", None
    return None, reason or None


def lab_matches(row, data: LabLinkEventIn, actor: str, reason: str | None) -> bool:
    return (
        row["action"] == data.action
        and row["sample_id"] == data.sample_id
        and row["actor_id"] == actor
        and row["reason"] == reason
        and same_previous(row["previous_event_id"], data.previous_event_id)
    )


def public_lab(row) -> dict:
    if row is None:
        return {"state": "explicit_link_required", "sample_id": None}
    if row["action"] == "revoke":
        return {"state": "revoked", "sample_id": None, "link_event_id": str(row["event_id"])}
    kind, status = row["sample_kind"], row["sample_status"]
    if kind not in ("soil", "water") or status is None:
        raise HTTPException(503, "scout_photo_lab_sample_proof_missing")
    return {
        "state": "linked_contextual_soil_water"
        if status in ELIGIBLE_STATUSES
        else "sample_inactive",
        "sample_id": row["sample_id"],
        "sample_kind": kind,
        "sample_status": status,
        "link_event_id": str(row["event_id"]),
        "link_proof": LINK_PROOF,
        "plant_tissue_sample": False,
        "disease_diagnosis_approved": False,
    }


async def _head(conn, tenant: str, field_id: str, pin_id: str):
    rows = await conn.fetch(
        "SELECT e.event_id, e.action, e.sample_id, s.kind AS sample_kind, "
        "s.status AS sample_status FROM scout_photo_lab_link_events e "
        "LEFT JOIN lab_samples s ON s.tenant_id=e.tenant_id AND s.field_id=e.field_id "
        "AND s.sample_id=e.sample_id WHERE e.tenant_id=$1::uuid AND e.field_id=$2 "
        "AND e.pin_id=$3 AND NOT EXISTS (SELECT 1 FROM scout_photo_lab_link_events n "
        "WHERE n.previous_event_id=e.event_id) ORDER BY e.created_at DESC LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    return single_head(rows, CODES)


async def current_lab_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not lab_bridge_enabled():
        return {"state": "explicit_link_required", "sample_id": None}
    return public_lab(await _head(conn, tenant, field_id, pin_id))


def _gate(token, tenant, uid, role) -> tuple[str, str]:
    tenant_id, actor = media_api.authorize(token, tenant, uid, role, write=False)
    if not lab_bridge_enabled():
        raise HTTPException(404, "scout_photo_lab_link_disabled")
    media_api.require_role(role, LINK_ROLES, "scout_photo_lab_link_role_denied")
    return tenant_id, actor


@router.post(_PATH)
async def post_lab_link(
    field_id: str,
    pin_id: str,
    data: LabLinkEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    code, reason = lab_refusal(data)
    if code:
        raise HTTPException(422, code)
    scope = "photo.lab_link"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )

            async def insert():
                if data.action == "revoke":
                    return await conn.fetchval(
                        "INSERT INTO scout_photo_lab_link_events "
                        "(event_id,tenant_id,field_id,pin_id,action,previous_event_id,actor_id,"
                        "reason) VALUES ($1,$2::uuid,$3,$4,'revoke',$5,$6,$7) "
                        "ON CONFLICT DO NOTHING RETURNING event_id",
                        data.event_id,
                        tenant,
                        field_id,
                        pin_id,
                        data.previous_event_id,
                        actor,
                        reason,
                    )
                return await conn.fetchval(
                    "INSERT INTO scout_photo_lab_link_events "
                    "(event_id,tenant_id,field_id,pin_id,action,sample_id,previous_event_id,"
                    "actor_id,reason) SELECT $1,$2::uuid,$3,$4,'link',s.sample_id,$6,$7,$8 "
                    "FROM lab_samples s WHERE s.tenant_id=$2::uuid AND s.field_id=$3 "
                    f"AND s.sample_id=$5 AND {_ELIGIBLE_SQL} "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                    data.sample_id,
                    data.previous_event_id,
                    actor,
                    reason,
                )

            async def explain_refusal():
                if data.action == "link" and not await conn.fetchval(
                    f"SELECT true FROM lab_samples s WHERE s.tenant_id=$1::uuid "
                    f"AND s.field_id=$2 AND s.sample_id=$3 AND {_ELIGIBLE_SQL}",
                    tenant,
                    field_id,
                    data.sample_id,
                ):
                    raise HTTPException(422, "scout_photo_lab_sample_not_eligible")

            idempotent, head = await append_event(
                event_id=data.event_id,
                previous_event_id=data.previous_event_id,
                load_existing=lambda: conn.fetchrow(
                    "SELECT event_id, action, sample_id, previous_event_id, actor_id, reason "
                    "FROM scout_photo_lab_link_events WHERE event_id=$1 "
                    "AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                ),
                matches=lambda row: lab_matches(row, data, actor, reason),
                read_head=lambda: _head(conn, tenant, field_id, pin_id),
                insert=insert,
                codes=CODES,
                head_required=data.action == "revoke",
                explain_refusal=explain_refusal,
            )
            current = public_lab(head)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise media_api._db_error() from exc
    return {
        "event_id": str(data.event_id),
        "idempotent": idempotent,
        "persisted": True,
        "current": current,
        "automatic_pesticide_action_authorized": False,
    }


@router.get(_PATH)
async def get_lab_links(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    await media_api.require_media_field_scope(
        tenant, field_id, actor, "photo.lab_link", x_user_role
    )
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                "SELECT event_id, action, sample_id, previous_event_id, actor_id, reason, "
                "created_at FROM scout_photo_lab_link_events "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 "
                "ORDER BY created_at, event_id LIMIT 201",
                tenant,
                field_id,
                pin_id,
            )
            events = history_rows(rows, "scout_photo_lab_history_limit_exceeded")
            current = public_lab(await _head(conn, tenant, field_id, pin_id))
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
