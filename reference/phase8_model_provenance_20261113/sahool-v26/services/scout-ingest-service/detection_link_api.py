"""Explicit photo -> model-provenance links, never plant diagnosis or actuation.

Each link must prove: same tenant, same field, same *persisted* input bytes,
attested model provenance, authorized human and uninterrupted event lineage.
The owner is scout-ingest, not edge inference or platform decision services.
"""
from __future__ import annotations

import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

import media_api
from media_api import (
    _authorize, _db_error, _DETECTION_LINK_ROLES, _read_row,
    _require_media_field_scope, _require_object_present,
)

router = APIRouter()
_ENABLED = {"1", "yes", "true", "on"}


def detection_bridge_enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_DETECTION_LINK_ENABLED", "0").strip().lower() in _ENABLED


class DetectionLinkEventIn(BaseModel):
    event_id: UUID
    action: Literal["link", "revoke"]
    detection_provenance_id: int | None = Field(default=None, gt=0)
    previous_event_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)


def _require_request(tenant: str, role: str | None) -> None:
    if not detection_bridge_enabled():
        raise HTTPException(404, "scout_photo_detection_link_disabled")
    if (role or "").strip().lower() not in _DETECTION_LINK_ROLES:
        raise HTTPException(403, "scout_photo_detection_link_role_denied")


def _validate_event(data: DetectionLinkEventIn) -> str | None:
    if data.action == "link" and data.detection_provenance_id is None:
        raise HTTPException(422, "scout_photo_detection_provenance_id_required")
    if data.action == "revoke" and data.detection_provenance_id is not None:
        raise HTTPException(422, "scout_photo_detection_revoke_must_not_name_result")
    if data.previous_event_id == data.event_id:
        raise HTTPException(422, "scout_photo_detection_link_self_reference")
    reason = data.reason.strip() if data.reason is not None else None
    if (data.action == "revoke" or data.previous_event_id is not None) and not reason:
        raise HTTPException(422, "scout_photo_detection_revision_reason_required")
    return reason


async def _head(conn, tenant: str, field_id: str, pin_id: str):
    heads = await conn.fetch(
        "SELECT e.event_id,e.action,e.detection_provenance_id,e.edge_result_id, "
        "d.attestation,d.model_id,d.model_version,d.input_sha256,p.content_sha256 "
        "FROM scout_photo_detection_link_events e "
        "LEFT JOIN detection_provenance d ON d.id=e.detection_provenance_id "
        "AND d.tenant_id=e.tenant_id "
        "JOIN scout_photo_evidence p ON p.tenant_id=e.tenant_id AND p.field_id=e.field_id "
        "AND p.pin_id=e.pin_id "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_photo_detection_link_events n "
        "WHERE n.previous_event_id=e.event_id) "
        "ORDER BY e.created_at DESC LIMIT 2", tenant, field_id, pin_id,
    )
    if len(heads) > 1:
        raise HTTPException(503, "scout_photo_detection_link_ambiguous")
    return heads[0] if heads else None


def _public_head(row) -> dict:
    if row is None:
        return {"state": "explicit_link_required", "result_id": None}
    if row["action"] == "revoke":
        return {"state": "revoked", "result_id": None,
                "link_event_id": str(row["event_id"])}
    # Even if the referenced model provenance was corrupted/deleted/changed,
    # never report an unverified image-model bond as truth.
    if (row["attestation"] != "attested" or not row["input_sha256"]
            or row["input_sha256"] != row["content_sha256"]):
        raise HTTPException(503, "scout_photo_detection_link_proof_invalid")
    return {
        "state": "linked_model_provenance_unreviewed",
        "detection_provenance_id": row["detection_provenance_id"],
        "edge_result_id": row["edge_result_id"],
        "result_id": row["edge_result_id"],
        "link_event_id": str(row["event_id"]),
        "model_id": row["model_id"], "model_version": row["model_version"],
        "input_sha256": row["input_sha256"],
        "link_proof": "scout_photo_detection_link_events:v261",
        "human_diagnosis_approved": False,
    }


async def current_detection_context(tenant: str, field_id: str, pin_id: str) -> dict:
    if not detection_bridge_enabled():
        return {"state": "explicit_link_required", "result_id": None}
    conn = await media_api._tenant_connection(tenant)
    try:
        return _public_head(await _head(conn, tenant, field_id, pin_id))
    finally:
        await conn.close()


def _is_replay(row, data: DetectionLinkEventIn, actor: str, reason: str | None):
    return (row["action"] == data.action and row["actor_id"] == actor
            and row["reason"] == reason
            and (str(row["previous_event_id"]) if row["previous_event_id"] else None)
            == (str(data.previous_event_id) if data.previous_event_id else None)
            and row["detection_provenance_id"] == data.detection_provenance_id)


@router.post('/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/detection-link-events')
async def post_detection_link(
    field_id: str, pin_id: str, data: DetectionLinkEventIn,
    x_scout_media_token: str | None = Header(None, alias='X-Scout-Media-Token'),
    x_tenant_id: str | None = Header(None, alias='X-Tenant-Id'),
    x_user_id: str | None = Header(None, alias='X-User-Id'),
    x_user_role: str | None = Header(None, alias='X-User-Role'),
):
    tenant, actor = _authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    _require_request(tenant, x_user_role)
    await _require_media_field_scope(tenant, field_id, actor, 'photo.detection_link', x_user_role or '')
    reason = _validate_event(data)
    try:
        photo = await _read_row(tenant, field_id, pin_id)
        if photo is None:
            raise HTTPException(404, 'scout_photo_not_found')
        _require_object_present(photo, tenant, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            existing = await conn.fetchrow(
                'SELECT event_id,action,detection_provenance_id,previous_event_id,actor_id,reason '
                'FROM scout_photo_detection_link_events '
                'WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4',
                data.event_id, tenant, field_id, pin_id,
            )
            if existing:
                if not _is_replay(existing, data, actor, reason):
                    raise HTTPException(409, 'scout_photo_detection_event_id_reused')
                current = await _head(conn, tenant, field_id, pin_id)
                return {"event_id": str(data.event_id), "idempotent": True,
                        "persisted": True, "current": _public_head(current),
                        "automatic_pesticide_action_authorized": False}
            head = await _head(conn, tenant, field_id, pin_id)
            expected_prev = str(head['event_id']) if head is not None else None
            provided_prev = str(data.previous_event_id) if data.previous_event_id else None
            if expected_prev != provided_prev or (data.action == 'revoke' and head is None):
                raise HTTPException(409, 'scout_photo_detection_predecessor_conflict')
            # Recheck grants near the write. Database FK/trigger independently
            # requires an attested provenance row, matching field and image hash.
            await _require_media_field_scope(tenant, field_id, actor, 'photo.detection_link', x_user_role or '')
            if data.action == 'link':
                inserted = await conn.fetchval(
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
                    data.event_id, tenant, field_id, pin_id, data.detection_provenance_id,
                    data.previous_event_id, actor, reason,
                )
                if not inserted:
                    # No DB receipt -> never claim a link on hash mismatch.
                    matching = await conn.fetchval(
                        "SELECT true FROM detection_provenance d JOIN edge_results er "
                        "ON er.id=d.edge_result_id AND er.tenant_id=d.tenant_id "
                        "WHERE d.tenant_id=$1::uuid AND d.id=$2 AND er.field_id=$3 "
                        "AND d.attestation='attested' AND d.input_sha256=$4",
                        tenant, data.detection_provenance_id, field_id,
                        str(photo['content_sha256']).strip(),
                    )
                    if not matching:
                        raise HTTPException(422, 'scout_photo_detection_image_proof_missing')
            else:
                inserted = await conn.fetchval(
                    "INSERT INTO scout_photo_detection_link_events "
                    "(event_id,tenant_id,field_id,pin_id,action,previous_event_id,actor_id,reason) "
                    "VALUES ($1,$2::uuid,$3,$4,'revoke',$5,$6,$7) "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    data.event_id, tenant, field_id, pin_id, data.previous_event_id, actor, reason,
                )
            if not inserted:
                raise HTTPException(409, 'scout_photo_detection_concurrent_conflict')
            current = await _head(conn, tenant, field_id, pin_id)
            if not current or str(current['event_id']) != str(data.event_id):
                raise HTTPException(503, 'scout_photo_detection_receipt_unverified')
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    return {"event_id": str(data.event_id), "idempotent": False,
            "persisted": True, "current": _public_head(current),
            "automatic_pesticide_action_authorized": False}


@router.get('/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/detection-link-events')
async def get_detection_links(
    field_id: str, pin_id: str, response: Response,
    x_scout_media_token: str | None = Header(None, alias='X-Scout-Media-Token'),
    x_tenant_id: str | None = Header(None, alias='X-Tenant-Id'),
    x_user_id: str | None = Header(None, alias='X-User-Id'),
    x_user_role: str | None = Header(None, alias='X-User-Role'),
):
    tenant, actor = _authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    _require_request(tenant, x_user_role)
    await _require_media_field_scope(tenant, field_id, actor, 'photo.detection_link', x_user_role or '')
    try:
        photo = await _read_row(tenant, field_id, pin_id)
        if photo is None:
            raise HTTPException(404, 'scout_photo_not_found')
        _require_object_present(photo, tenant, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                'SELECT event_id,action,detection_provenance_id,edge_result_id,previous_event_id,actor_id,reason,created_at '
                'FROM scout_photo_detection_link_events '
                'WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 '
                'ORDER BY created_at,event_id LIMIT 201', tenant, field_id, pin_id,
            )
            if len(rows) > 200:
                raise HTTPException(503, 'scout_photo_detection_history_limit_exceeded')
            current = await _head(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Pragma'] = 'no-cache'
    return {
        'field_id': field_id, 'pin_id': pin_id, 'history_complete': True,
        'events': [{k: (str(v) if isinstance(v, UUID) else v.isoformat() if hasattr(v, 'isoformat') else v)
                    for k, v in dict(row).items()} for row in rows],
        'current': _public_head(current),
        'automatic_pesticide_action_authorized': False,
    }
