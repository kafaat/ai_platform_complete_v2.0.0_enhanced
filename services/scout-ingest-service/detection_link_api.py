"""Explicit photo -> attested model provenance links (owner phase 8, v266); never a diagnosis.

A link proves: same tenant, same field, the *persisted* image bytes (detection_provenance.
input_sha256 = scout_photo_evidence.content_sha256), attested provenance, a granted human and an
unbroken event chain. The v266 trigger checks the same in SQL. Behind
SCOUT_MEDIA_DETECTION_LINK_ENABLED (default 0). Owner scout-ingest; edge_results and
detection_provenance stay the platform's (column SELECT only).
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
_ENABLED = {"1", "yes", "true", "on"}
LINK_ROLES = media_api.SEASON_LINK_ROLES
LINK_PROOF = "scout_photo_detection_link_events:v266"
CODES = ChainCodes(
    reused="scout_photo_detection_event_id_reused",
    predecessor="scout_photo_detection_predecessor_conflict",
    concurrent="scout_photo_detection_concurrent_conflict",
    unverified="scout_photo_detection_receipt_unverified",
    ambiguous="scout_photo_detection_link_ambiguous",
)
_PATH = "/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/detection-link-events"


def detection_bridge_enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_DETECTION_LINK_ENABLED", "0").strip().lower() in _ENABLED


class DetectionLinkEventIn(BaseModel):
    event_id: UUID
    action: Literal["link", "revoke"]
    detection_provenance_id: int | None = Field(default=None, gt=0)
    previous_event_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)


def detection_refusal(data: DetectionLinkEventIn) -> tuple[str | None, str | None]:
    """``(code, None)`` for a malformed request (422), else ``(None, trimmed reason)``."""
    if data.action == "link" and data.detection_provenance_id is None:
        return "scout_photo_detection_provenance_id_required", None
    if data.action == "revoke" and data.detection_provenance_id is not None:
        return "scout_photo_detection_revoke_must_not_name_result", None
    if data.previous_event_id is not None and data.previous_event_id == data.event_id:
        return "scout_photo_detection_link_self_reference", None
    reason = data.reason.strip() if data.reason is not None else None
    if (data.action == "revoke" or data.previous_event_id is not None) and not reason:
        return "scout_photo_detection_revision_reason_required", None
    return None, reason or None


def detection_matches(row, data: DetectionLinkEventIn, actor: str, reason: str | None) -> bool:
    return (
        row["action"] == data.action
        and row["actor_id"] == actor
        and row["reason"] == reason
        and same_previous(row["previous_event_id"], data.previous_event_id)
        and row["detection_provenance_id"] == data.detection_provenance_id
    )


def public_detection(row) -> dict:
    """The detection part of the context; a link whose proof no longer holds is a 503."""
    if row is None:
        return {"state": "explicit_link_required", "result_id": None}
    if row["action"] == "revoke":
        return {"state": "revoked", "result_id": None, "link_event_id": str(row["event_id"])}
    if (
        row["attestation"] != "attested"
        or not row["input_sha256"]
        or row["input_sha256"] != str(row["content_sha256"]).strip()
    ):
        raise HTTPException(503, "scout_photo_detection_link_proof_invalid")
    return {
        "state": "linked_model_provenance_unreviewed",
        "detection_provenance_id": row["detection_provenance_id"],
        "edge_result_id": row["edge_result_id"],
        "result_id": row["edge_result_id"],
        "link_event_id": str(row["event_id"]),
        "model_id": row["model_id"],
        "model_version": row["model_version"],
        "input_sha256": row["input_sha256"],
        "link_proof": LINK_PROOF,
        "human_diagnosis_approved": False,
    }


async def _head(conn, tenant: str, field_id: str, pin_id: str):
    rows = await conn.fetch(
        "SELECT e.event_id, e.action, e.detection_provenance_id, e.edge_result_id, "
        "d.attestation, d.model_id, d.model_version, d.input_sha256, p.content_sha256 "
        "FROM scout_photo_detection_link_events e "
        "LEFT JOIN detection_provenance d ON d.id=e.detection_provenance_id "
        "AND d.tenant_id=e.tenant_id "
        "JOIN scout_photo_evidence p ON p.tenant_id=e.tenant_id AND p.field_id=e.field_id "
        "AND p.pin_id=e.pin_id "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_photo_detection_link_events n "
        "WHERE n.previous_event_id=e.event_id) ORDER BY e.created_at DESC LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    return single_head(rows, CODES)


async def current_detection_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not detection_bridge_enabled():
        return {"state": "explicit_link_required", "result_id": None}
    return public_detection(await _head(conn, tenant, field_id, pin_id))


def _gate(token, tenant, uid, role) -> tuple[str, str]:
    tenant_id, actor = media_api.authorize(token, tenant, uid, role, write=False)
    if not detection_bridge_enabled():
        raise HTTPException(404, "scout_photo_detection_link_disabled")
    media_api.require_role(role, LINK_ROLES, "scout_photo_detection_link_role_denied")
    return tenant_id, actor


@router.post(_PATH)
async def post_detection_link(
    field_id: str,
    pin_id: str,
    data: DetectionLinkEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    code, reason = detection_refusal(data)
    if code:
        raise HTTPException(422, code)
    scope = "photo.detection_link"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    try:
        photo = await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            # The grant is checked again on the connection that writes (revoked meanwhile => 403).
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )

            async def insert():
                if data.action == "revoke":
                    return await conn.fetchval(
                        "INSERT INTO scout_photo_detection_link_events "
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
                    "INSERT INTO scout_photo_detection_link_events "
                    "(event_id,tenant_id,field_id,pin_id,action,detection_provenance_id,"
                    "edge_result_id,previous_event_id,actor_id,reason) "
                    "SELECT $1,$2::uuid,$3,$4,'link',d.id,d.edge_result_id,$6,$7,$8 "
                    "FROM detection_provenance d JOIN edge_results er "
                    "ON er.id=d.edge_result_id AND er.tenant_id=d.tenant_id "
                    "JOIN scout_photo_evidence p ON p.tenant_id=d.tenant_id "
                    "AND p.field_id=$3 AND p.pin_id=$4 "
                    "WHERE d.tenant_id=$2::uuid AND d.id=$5 AND d.attestation='attested' "
                    "AND er.field_id=$3 AND d.input_sha256=p.content_sha256 "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                    data.detection_provenance_id,
                    data.previous_event_id,
                    actor,
                    reason,
                )

            async def explain_refusal():
                if data.action == "link" and not await conn.fetchval(
                    "SELECT true FROM detection_provenance d JOIN edge_results er "
                    "ON er.id=d.edge_result_id AND er.tenant_id=d.tenant_id "
                    "WHERE d.tenant_id=$1::uuid AND d.id=$2 AND er.field_id=$3 "
                    "AND d.attestation='attested' AND d.input_sha256=$4",
                    tenant,
                    data.detection_provenance_id,
                    field_id,
                    str(photo["content_sha256"]).strip(),
                ):
                    raise HTTPException(422, "scout_photo_detection_image_proof_missing")

            idempotent, head = await append_event(
                event_id=data.event_id,
                previous_event_id=data.previous_event_id,
                load_existing=lambda: conn.fetchrow(
                    "SELECT event_id, action, detection_provenance_id, previous_event_id, "
                    "actor_id, reason FROM scout_photo_detection_link_events "
                    "WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                ),
                matches=lambda row: detection_matches(row, data, actor, reason),
                read_head=lambda: _head(conn, tenant, field_id, pin_id),
                insert=insert,
                codes=CODES,
                head_required=data.action == "revoke",
                explain_refusal=explain_refusal,
            )
            current = public_detection(head)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — FK/trigger refusals included: never a 500
        raise media_api._db_error() from exc
    return {
        "event_id": str(data.event_id),
        "idempotent": idempotent,
        "persisted": True,
        "current": current,
        "automatic_pesticide_action_authorized": False,
    }


@router.get(_PATH)
async def get_detection_links(
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
        tenant, field_id, actor, "photo.detection_link", x_user_role
    )
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                "SELECT event_id, action, detection_provenance_id, edge_result_id, "
                "previous_event_id, actor_id, reason, created_at "
                "FROM scout_photo_detection_link_events "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 "
                "ORDER BY created_at, event_id LIMIT 201",
                tenant,
                field_id,
                pin_id,
            )
            events = history_rows(rows, "scout_photo_detection_history_limit_exceeded")
            current = public_detection(await _head(conn, tenant, field_id, pin_id))
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
