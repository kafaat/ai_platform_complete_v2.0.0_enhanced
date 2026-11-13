"""Plant tissue samples with an append-only custody chain (owner phase 11, v269); not a lab result.

A sample is tied to a persisted photo and a collector with a live photo.tissue_sample grant; the
'collected' custody event is written in the same transaction (v269's deferred guard refuses an
orphan sample at COMMIT). Never soil/water lab_samples, never pathogen confirmation. Behind
SCOUT_MEDIA_TISSUE_SAMPLE_ENABLED (default 0).
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import media_api
from evidence_chain import (
    ChainCodes,
    append_event,
    guard_refusal,
    positive_user_id,
    single_head,
)
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter()
# As delivered (and as the v269 guard checks users.role): the platform's WORKER alias 'farmer' is
# not among them.
TISSUE_ROLES = frozenset({"worker", "manager", "expert", "agronomist"})
CUSTODY_STATES = ("collected", "handed_over", "received", "rejected", "disposed")
_TRUE = {"1", "true", "on", "yes"}
_RECIPIENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,119}")
CODES = ChainCodes(
    reused="scout_tissue_event_id_reused",
    predecessor="scout_tissue_custody_predecessor_conflict",
    concurrent="scout_tissue_custody_concurrent_conflict",
    unverified="scout_tissue_custody_receipt_unverified",
    ambiguous="scout_tissue_custody_chain_ambiguous",
)
_BASE = "/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/tissue-samples"


def enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_TISSUE_SAMPLE_ENABLED", "0").strip().lower() in _TRUE


class TissueSampleIn(BaseModel):
    sample_id: UUID
    collection_event_id: UUID
    barcode: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{5,63}$")
    specimen_type: Literal["leaf", "stem", "root", "fruit", "flower", "seed"]
    collected_at: datetime
    symptoms_note: str | None = Field(None, max_length=2000)
    collection_note: str = Field(min_length=10, max_length=2000)


class CustodyEventIn(BaseModel):
    event_id: UUID
    action: Literal["handed_over", "received", "rejected", "disposed"]
    previous_event_id: UUID
    recipient_ref: str | None = Field(None, min_length=3, max_length=120)
    note: str = Field(min_length=10, max_length=2000)


def collection_refusal(data: TissueSampleIn, now: datetime) -> tuple[str | None, str, str]:
    """``(code, collected_at_utc_iso, note)``; code is set for a malformed request (422)."""
    if data.sample_id == data.collection_event_id:
        return "scout_tissue_ids_must_differ", "", ""
    collected = data.collected_at
    if collected.tzinfo is None or collected.utcoffset() is None:
        return "scout_tissue_collection_timezone_required", "", ""
    collected = collected.astimezone(UTC)
    if not (now - timedelta(days=365) <= collected <= now + timedelta(hours=1)):
        return "scout_tissue_collection_time_out_of_range", "", ""
    note = data.collection_note.strip()
    if len(note) < 10:
        return "scout_tissue_note_invalid", "", ""
    return None, collected.isoformat(), note


def custody_refusal(data: CustodyEventIn) -> tuple[str | None, str]:
    if data.event_id == data.previous_event_id:
        return "scout_tissue_self_reference", ""
    if (data.action in ("received", "handed_over")) != (data.recipient_ref is not None):
        return "scout_tissue_recipient_mismatch", ""
    if data.recipient_ref and (
        data.recipient_ref.strip() != data.recipient_ref
        or not _RECIPIENT.fullmatch(data.recipient_ref)
    ):
        return "scout_tissue_recipient_invalid", ""
    note = data.note.strip()
    if len(note) < 10:
        return "scout_tissue_note_invalid", ""
    return None, note


def custody_transition_refusal(prior: str, action: str) -> str | None:
    """The v269 transition rule, checked before the insert for a clear 409."""
    if (
        prior in ("rejected", "disposed")
        or (action == "received" and prior != "handed_over")
        or (action == "handed_over" and prior not in ("collected", "received"))
    ):
        return "scout_tissue_illegal_custody_transition"
    return None


def public_sample(row) -> dict:
    return {
        "sample_id": str(row["sample_id"]),
        "barcode": row["barcode"],
        "specimen_type": row["specimen_type"],
        "collected_at": row["collected_at"].isoformat(),
        "collector_user_id": row["collected_by"],
        "custody_state": row["custody_state"],
        "context_only": True,
        "pathogen_identified": False,
        "laboratory_result_approved": False,
    }


async def current_tissue_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not enabled():
        return {"state": "disabled", "sample_count": 0, "laboratory_result_approved": False}
    samples = await conn.fetch(
        "SELECT s.sample_id, s.barcode, s.specimen_type, s.collected_at, s.collected_by, "
        "COALESCE((SELECT e.action FROM scout_tissue_custody_events e "
        "WHERE e.tenant_id=s.tenant_id AND e.sample_id=s.sample_id "
        "AND NOT EXISTS (SELECT 1 FROM scout_tissue_custody_events n "
        "WHERE n.previous_event_id=e.event_id) LIMIT 1), 'missing_chain') AS custody_state "
        "FROM scout_plant_tissue_samples s WHERE s.tenant_id=$1::uuid AND s.field_id=$2 "
        "AND s.pin_id=$3 ORDER BY s.created_at, s.sample_id LIMIT 101",
        tenant,
        field_id,
        pin_id,
    )
    if len(samples) > 100:
        raise HTTPException(503, "scout_tissue_sample_limit_exceeded")
    if any(row["custody_state"] not in CUSTODY_STATES for row in samples):
        raise HTTPException(
            503, "scout_tissue_custody_head_missing"
        )  # a broken chain is no receipt
    return {
        "state": "collected" if samples else "no_explicit_sample",
        "sample_count": len(samples),
        "samples": [public_sample(s) for s in samples],
        "laboratory_result_approved": False,
    }


def _gate(token, tenant, uid, role) -> tuple[str, str, int]:
    tenant_id, actor = media_api.authorize(token, tenant, uid, role, write=False)
    if not enabled():
        raise HTTPException(404, "scout_tissue_disabled")
    media_api.require_role(role, TISSUE_ROLES, "scout_tissue_role_denied")
    return tenant_id, actor, positive_user_id(actor, "scout_tissue_actor_invalid")


def _sample_matches(row, data: TissueSampleIn, actor_id: int, collected: str) -> bool:
    return (
        row["barcode"] == data.barcode
        and row["specimen_type"] == data.specimen_type
        and row["collected_by"] == actor_id
        and row["collected_at"].astimezone(UTC).isoformat() == collected
        and row["symptoms_note"] == data.symptoms_note
    )


def _collection_matches(row, actor_id: int, note: str) -> bool:
    return (
        row["action"] == "collected"
        and row["actor_user_id"] == actor_id
        and row["note"] == note
        and row["previous_event_id"] is None
    )


@router.post(_BASE, status_code=201)
async def create_tissue_sample(
    field_id: str,
    pin_id: str,
    data: TissueSampleIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor, actor_id = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    code, collected, note = collection_refusal(data, datetime.now(UTC))
    if code:
        raise HTTPException(422, code)
    scope = "photo.tissue_sample"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    select_sample = (
        "SELECT sample_id, barcode, specimen_type, collected_at, collected_by, symptoms_note "
        "FROM scout_plant_tissue_samples WHERE sample_id=$1 AND tenant_id=$2::uuid "
        "AND field_id=$3 AND pin_id=$4"
    )
    select_event = (
        "SELECT event_id, action, actor_user_id, note, previous_event_id "
        "FROM scout_tissue_custody_events WHERE event_id=$1 AND tenant_id=$2::uuid "
        "AND sample_id=$3"
    )
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )
            sample_args = (data.sample_id, tenant, field_id, pin_id)
            event_args = (data.collection_event_id, tenant, data.sample_id)
            existing = await conn.fetchrow(select_sample, *sample_args)
            if existing is None:
                async with conn.transaction():
                    inserted = await conn.fetchval(
                        "INSERT INTO scout_plant_tissue_samples "
                        "(sample_id,tenant_id,field_id,pin_id,barcode,specimen_type,collected_at,"
                        "collected_by,symptoms_note) "
                        "SELECT $1,$2::uuid,$3,$4,$5,$6,$7::timestamptz,$8,$9 "
                        "FROM scout_photo_evidence p WHERE p.tenant_id=$2::uuid "
                        "AND p.field_id=$3 AND p.pin_id=$4 "
                        "ON CONFLICT DO NOTHING RETURNING sample_id",
                        data.sample_id,
                        tenant,
                        field_id,
                        pin_id,
                        data.barcode,
                        data.specimen_type,
                        datetime.fromisoformat(collected),
                        actor_id,
                        data.symptoms_note,
                    )
                    if inserted is not None:
                        await conn.execute(
                            "INSERT INTO scout_tissue_custody_events "
                            "(event_id,tenant_id,field_id,pin_id,sample_id,action,actor_user_id,"
                            "note) VALUES ($1,$2::uuid,$3,$4,$5,'collected',$6,$7)",
                            data.collection_event_id,
                            tenant,
                            field_id,
                            pin_id,
                            data.sample_id,
                            actor_id,
                            note,
                        )
                if inserted is None:
                    # An identical concurrent request committed first, or the id/barcode is taken.
                    existing = await conn.fetchrow(select_sample, *sample_args)
                    if existing is None:
                        raise HTTPException(409, "scout_tissue_sample_conflict")
                else:
                    return _sample_receipt(data, idempotent=False)
            if not _sample_matches(existing, data, actor_id, collected):
                raise HTTPException(409, "scout_tissue_sample_id_reused")
            event = await conn.fetchrow(select_event, *event_args)
            if event is None or not _collection_matches(event, actor_id, note):
                raise HTTPException(409, "scout_tissue_collection_event_id_reused")
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if guard_refusal(exc):
            raise HTTPException(403, "scout_tissue_actor_not_authorized") from None
        raise media_api._db_error() from exc
    return _sample_receipt(data, idempotent=True)


def _sample_receipt(data: TissueSampleIn, *, idempotent: bool) -> dict:
    return {
        "sample_id": str(data.sample_id),
        "collection_event_id": str(data.collection_event_id),
        "persisted": True,
        "idempotent": idempotent,
        "laboratory_result_approved": False,
        "pesticide_application_authorized": False,
    }


@router.post(_BASE + "/{sample_id}/custody-events")
async def record_custody_event(
    field_id: str,
    pin_id: str,
    sample_id: UUID,
    data: CustodyEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor, actor_id = _gate(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    media_api._require_valid_pin(pin_id)
    code, note = custody_refusal(data)
    if code:
        raise HTTPException(422, code)
    scope = "photo.tissue_sample"
    await media_api.require_media_field_scope(tenant, field_id, actor, scope, x_user_role)
    try:
        conn = await media_api._tenant_connection(tenant)
        try:
            await media_api.require_media_field_scope(
                tenant, field_id, actor, scope, x_user_role, conn=conn
            )
            if not await conn.fetchval(
                "SELECT true FROM scout_plant_tissue_samples WHERE sample_id=$1 "
                "AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                sample_id,
                tenant,
                field_id,
                pin_id,
            ):
                raise HTTPException(404, "scout_tissue_sample_not_found")

            async def read_head():
                rows = await conn.fetch(
                    "SELECT event_id, action FROM scout_tissue_custody_events e "
                    "WHERE e.tenant_id=$1::uuid AND e.sample_id=$2 AND NOT EXISTS (SELECT 1 "
                    "FROM scout_tissue_custody_events n WHERE n.previous_event_id=e.event_id) "
                    "ORDER BY e.recorded_at DESC LIMIT 2",
                    tenant,
                    sample_id,
                )
                return single_head(rows, CODES)

            def head_allows(head) -> None:
                refusal = custody_transition_refusal(head["action"], data.action)
                if refusal:
                    raise HTTPException(409, refusal)

            idempotent, _ = await append_event(
                event_id=data.event_id,
                previous_event_id=data.previous_event_id,
                load_existing=lambda: conn.fetchrow(
                    "SELECT action, previous_event_id, actor_user_id, recipient_ref, note "
                    "FROM scout_tissue_custody_events WHERE event_id=$1 "
                    "AND tenant_id=$2::uuid AND sample_id=$3",
                    data.event_id,
                    tenant,
                    sample_id,
                ),
                matches=lambda row: (
                    row["action"] == data.action
                    and row["previous_event_id"] == data.previous_event_id
                    and row["actor_user_id"] == actor_id
                    and row["recipient_ref"] == data.recipient_ref
                    and row["note"] == note
                ),
                read_head=read_head,
                insert=lambda: conn.fetchval(
                    "INSERT INTO scout_tissue_custody_events "
                    "(event_id,tenant_id,field_id,pin_id,sample_id,action,previous_event_id,"
                    "actor_user_id,recipient_ref,note) "
                    "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10) "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    data.event_id,
                    tenant,
                    field_id,
                    pin_id,
                    sample_id,
                    data.action,
                    data.previous_event_id,
                    actor_id,
                    data.recipient_ref,
                    note,
                ),
                codes=CODES,
                head_required=True,
                head_allows=head_allows,
            )
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if guard_refusal(exc):
            raise HTTPException(403, "scout_tissue_actor_not_authorized") from None
        raise media_api._db_error() from exc
    return {
        "event_id": str(data.event_id),
        "sample_id": str(sample_id),
        "persisted": True,
        "idempotent": idempotent,
        "laboratory_result_approved": False,
    }


@router.get(_BASE)
async def list_tissue_samples(
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
        tenant, field_id, actor, "photo.tissue_sample", x_user_role
    )
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            result = await current_tissue_context(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise media_api._db_error() from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {**result, "pesticide_application_authorized": False}
