"""Scout photo evidence (v260 ``scout_photo_evidence``): tenant-bound, S3-only, immutable.

Owner decision (2026-11-13): this table is the photo's single source of truth. It belongs to
scout-ingest, not to the platform's ``scouting_pins`` writer; ``scouting_pins`` carries no photo
link. A row is bound to an existing pin by FK on (tenant_id, field_id, pin_id).

Trust boundary: nginx (``location ^~ /api/v1/scouting-media/``) verifies the JWT, clears
caller-supplied identity headers, and injects the verified tenant/user/role plus a *dedicated*
service token (``SCOUT_MEDIA_SERVICE_TOKEN``). Direct external HTTP to this internal path is not
supported. Behind ``SCOUT_MEDIA_ENABLED`` (default 0 ⇒ 404).

Order of a POST: gates ⇒ key syntax ⇒ bounded body read and full decode (no DB, no store) ⇒
pin exists under RLS ⇒ object upload ⇒ INSERT … ON CONFLICT DO NOTHING ⇒ re-read ⇒ HEAD. Success
is reported only when the row matches these bytes **and** the object exists in the bucket.

Pure decisions live in ``shared.security.scout_photo``; this module only wires them to I/O.

Owner phases 4-5 add, on the same gates: ``GET …/photo/context`` (photo → pin → the v246
inspection task, never inferred) and, behind ``SCOUT_MEDIA_SEASON_LINK_ENABLED`` (default 0),
``POST``/``GET …/photo/season-link-events`` (v262: explicit, append-only links to a human-accepted
season of the same tenant and field). None of these authorises a diagnosis or a pesticide action.
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from shared.security.scout_photo import (
    MAX_PHOTO_BYTES,
    PhotoValidationError,
    expected_object_ref,
    http_status_for,
    inspect_photo,
    media_key,
    owned_object_ref,
    public_receipt,
    stored_sha,
    valid_pin_id,
)
from shared.security.trusted_tenant import service_token_ok
from shared.storage import blob_store

router = APIRouter()
_ENABLED = {"1", "true", "yes", "on"}
# The JWT roles the auth service issues (admin/expert/farmer) and the platform's five-role
# model, as normalised by services/sahool-platform/api/main.py:_ROLE_ALIASES. Writing a photo
# needs the same right as writing the pin (Permission.OBSERVATION_RECORD); reading it the same
# as reading the pin (OBSERVATION_VIEW). platform_admin has neither.
WRITE_ROLES = frozenset({"owner", "admin", "manager", "agronomist", "expert", "worker", "farmer"})
READ_ROLES = WRITE_ROLES | {"viewer"}
# The photo's evidence context names an inspection task (internal workflow state): not for a
# viewer or a worker, unlike the photo itself (owner phase 4).
CONTEXT_ROLES = WRITE_ROLES - {"worker"}
# Linking a photo to an accepted season is stricter than uploading it (owner phase 5, v262).
SEASON_LINK_ROLES = frozenset({"owner", "admin", "manager", "agronomist", "expert"})
PRESIGN_TTL_S = 120
SEASON_LINK_HISTORY_LIMIT = 200
SEASON_LINK_PROOF = "scout_photo_season_link_events:v262"

_SELECT_ROW = (
    "SELECT evidence_id, field_id, pin_id, object_ref, content_sha256, "
    "mime_type, size_bytes, image_width, image_height "
    "FROM scout_photo_evidence WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3"
)
_INSERT_ROW = (
    "INSERT INTO scout_photo_evidence "
    "(tenant_id, field_id, pin_id, object_ref, content_sha256, mime_type, "
    "size_bytes, image_width, image_height, uploaded_by) "
    "VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10) "
    "ON CONFLICT (tenant_id, field_id, pin_id) DO NOTHING RETURNING evidence_id"
)


def authorize(
    token: str | None, tenant: str | None, uid: str | None, role: str | None, *, write: bool
) -> tuple[str, str]:
    """Feature flag, service token, trusted identity, role, shared store. Pure apart from env."""
    if os.getenv("SCOUT_MEDIA_ENABLED", "0").strip().lower() not in _ENABLED:
        raise HTTPException(404, "scout_media_disabled")
    expected = os.getenv("SCOUT_MEDIA_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(503, "scout_media_token_unconfigured")
    if not service_token_ok(token, expected):
        raise HTTPException(401, "scout_media_token_required")
    if not tenant or not uid or not uid.strip():
        raise HTTPException(403, "trusted_tenant_and_user_required")
    try:
        tenant_id = str(UUID(tenant))
    except (TypeError, ValueError):
        raise HTTPException(403, "invalid_trusted_tenant") from None
    if (role or "").strip().lower() not in (WRITE_ROLES if write else READ_ROLES):
        raise HTTPException(403, "scout_media_role_denied")
    # Shared photos must NOT be silently stored as file:// in one container.
    if not blob_store.s3_enabled():
        raise HTTPException(503, "shared_photo_storage_not_configured")
    return tenant_id, uid.strip()


def _require_valid_pin(pin_id: str) -> None:
    if not valid_pin_id(pin_id):
        raise HTTPException(422, "invalid_pin_id")


async def _tenant_connection(tenant: str):
    """Short connection with ``app.current_tenant`` set (RLS on), as season_api does."""
    import season_api

    try:
        return await season_api._tenant_conn(tenant)
    except HTTPException:  # DATABASE_URL unset ⇒ the same opaque 503 as any DB failure
        raise _db_error() from None


async def _read_row(tenant: str, field_id: str, pin_id: str, *, conn=None):
    """The pin must be visible under the tenant's RLS; then its photo row, or None.

    The context passes its snapshot connection so every part reads the same PostgreSQL instant.
    """
    owns = conn is None
    if owns:
        conn = await _tenant_connection(tenant)
    try:
        exists = await conn.fetchval(
            "SELECT true FROM scouting_pins WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
            tenant,
            field_id,
            pin_id,
        )
        if not exists:
            raise HTTPException(404, "scouting_pin_not_found")
        return await conn.fetchrow(_SELECT_ROW, tenant, field_id, pin_id)
    finally:
        if owns:
            await conn.close()


async def _insert_row(tenant: str, field_id: str, pin_id: str, ref: str, image, uid: str):
    conn = await _tenant_connection(tenant)
    try:
        return await conn.fetchval(
            _INSERT_ROW,
            tenant,
            field_id,
            pin_id,
            ref,
            image.sha256,
            image.content_type,
            image.size_bytes,
            image.width,
            image.height,
            uid,
        )
    finally:
        await conn.close()


def _db_error() -> HTTPException:
    # Never leak connection strings, SQL/schema, object store credentials to clients.
    return HTTPException(503, "scout_media_database_unavailable")


# Owner phases 6 and 8 (v263): the field grant is the only source of field access. A tenant
# role, creating the pin or holding the service token grants nothing by itself. The trusted role
# claim must equal the caller's CURRENT users.role (a role change invalidates older tokens), the
# user must be active, and the grant must be unrevoked, started, unexpired and at most 90 days long
# (an indefinite pre-v265 grant never authorises). No grant => 403; DB or schema missing => 503.
_FIELD_SCOPE_SQL = (
    "SELECT true FROM scout_photo_field_access_grants AS g "
    "JOIN users AS u ON u.id=g.user_id AND u.tenant_id=g.tenant_id AND u.active IS TRUE "
    "JOIN fields AS f ON f.tenant_id=g.tenant_id AND f.field_id=g.field_id "
    "WHERE g.tenant_id=$1::uuid AND g.field_id=$2 AND u.id::text=$3 "
    "AND g.scope=$4 AND lower(u.role::text)=$5 "
    "AND g.revoked_at IS NULL AND g.expires_at IS NOT NULL "
    "AND g.granted_at <= now() AND g.expires_at > now() "
    "AND g.expires_at <= g.granted_at + interval '90 days' LIMIT 1"
)


async def require_media_field_scope(
    tenant: str, field_id: str, actor: str, scope: str, role_claim: str | None, *, conn=None
) -> None:
    """403 unless the caller holds a live grant for this field and scope (owner phase 6)."""
    owns = conn is None
    try:
        if owns:
            conn = await _tenant_connection(tenant)
        permitted = await conn.fetchval(
            _FIELD_SCOPE_SQL, tenant, field_id, actor, scope, (role_claim or "").strip().lower()
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a missing table or DB is a 503, never a pass
        raise _db_error() from exc
    finally:
        if owns and conn is not None:
            await conn.close()
    if not permitted:
        raise HTTPException(403, "scout_media_field_scope_denied")


def _owned_ref(row, tenant: str, pin_id: str) -> str:
    try:
        return owned_object_ref(row, blob_store.S3_BUCKET, tenant, pin_id)
    except PhotoValidationError as exc:
        raise HTTPException(503, exc.code) from None


async def _require_object_present(row, tenant: str, pin_id: str) -> str:
    """A DB row alone is not a durable receipt: HEAD the server-derived object."""
    ref = _owned_ref(row, tenant, pin_id)
    try:
        present = await asyncio.to_thread(blob_store.object_exists, ref)
    except Exception as exc:  # noqa: BLE001 — any store error ⇒ cannot prove the object
        raise HTTPException(503, "scout_photo_store_unavailable") from exc
    if not present:
        raise HTTPException(503, "scout_photo_object_not_verified")
    return ref


async def _read_bounded(request: Request) -> bytes:
    """Read bounded chunks, never an unlimited ``await request.body()``."""
    parts: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo_too_large")
        parts.append(chunk)
    return b"".join(parts)


@router.post("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo")
async def post_pin_photo(
    field_id: str,
    pin_id: str,
    request: Request,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    x_content_sha256: str | None = Header(None, alias="X-Content-SHA256"),
):
    tenant, uid = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=True)
    _require_valid_pin(pin_id)
    data = await _read_bounded(request)
    claimed_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        image = inspect_photo(data, claimed_type, x_content_sha256 or "")
    except PhotoValidationError as exc:
        raise HTTPException(http_status_for(exc.code), exc.code) from exc

    await require_media_field_scope(tenant, field_id, uid, "photo.upload", x_user_role)
    try:
        existing = await _read_row(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error() from exc
    if existing is not None:
        if stored_sha(existing) != image.sha256:
            raise HTTPException(409, "photo_already_saved_with_other_bytes")
        await _require_object_present(existing, tenant, pin_id)
        return {**public_receipt(existing), "idempotent": True}

    object_key = media_key(tenant, pin_id, image.sha256)
    try:
        ref = await asyncio.to_thread(blob_store.upload_bytes, object_key, data, image.content_type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "scout_media_store_unavailable") from exc
    # S3_ALLOW_FILE_FALLBACK degrades to file:// (not shared), and a store adapter answering with
    # another bucket/key must never reach the immutable row (it would block every retry).
    if ref != expected_object_ref(blob_store.S3_BUCKET, tenant, pin_id, image.sha256):
        raise HTTPException(503, "scout_media_store_unavailable")

    # A grant revoked while the bytes were uploading must not reach the immutable row.
    await require_media_field_scope(tenant, field_id, uid, "photo.upload", x_user_role)
    try:
        inserted_id = await _insert_row(tenant, field_id, pin_id, ref, image, uid)
        # The FK and the unique key fence a concurrent upload; re-read whichever row won.
        saved = await _read_row(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — FK violation (pin deleted meanwhile) included
        raise _db_error() from exc
    if saved is None:
        raise _db_error()
    if stored_sha(saved) != image.sha256:
        raise HTTPException(409, "photo_already_saved_with_other_bytes")
    # Even for the first POST, a committed row is not proof that S3 kept the bytes.
    await _require_object_present(saved, tenant, pin_id)
    return {**public_receipt(saved), "idempotent": inserted_id is None}


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo")
async def get_pin_photo(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    _require_valid_pin(pin_id)
    await require_media_field_scope(tenant, field_id, actor, "photo.read", x_user_role)
    try:
        row = await _read_row(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error() from exc
    if row is None:
        raise HTTPException(404, "scout_photo_not_found")
    ref = await _require_object_present(row, tenant, pin_id)
    try:
        url = await asyncio.to_thread(blob_store.presigned_get_url, ref, PRESIGN_TTL_S)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "scout_photo_presign_unavailable") from exc
    if not url.startswith("https://"):
        raise HTTPException(503, "scout_photo_presign_unavailable")
    # A presigned link is a bearer capability: no shared cache may keep it.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {**public_receipt(row), "url": url, "expires_in_seconds": PRESIGN_TTL_S}


# ─── Evidence context and explicit season links (owner phases 4-5; v262) ─────────────────────
#
# A photo is evidence, not a decision. The context names only links that a key proves: the
# v246 inspection task (field_tasks.source_scouting_pin_id) and, behind its own flag, an explicit
# human link event to an ACCEPTED season (v262 scout_photo_season_link_events). Nothing is
# inferred from crop, date, coordinates or model output, and nothing here authorises a
# pesticide action.


def season_bridge_enabled() -> bool:
    """Separate rollout fence (default off). Once on, a missing table or DB is a 503."""
    return os.getenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "0").strip().lower() in _ENABLED


class PhotoSeasonLinkEventIn(BaseModel):
    # A client-generated UUID makes a retry idempotent, also after a timeout on the first insert.
    event_id: UUID
    action: str
    season_id: UUID | None = None
    previous_event_id: UUID | None = None
    reason: str | None = None


def season_link_refusal(data: PhotoSeasonLinkEventIn) -> tuple[str | None, str | None]:
    """``(code, None)`` when the request is malformed (422), else ``(None, normalised reason)``."""
    reason = data.reason.strip() if data.reason is not None else None
    if data.action not in {"link", "revoke"}:
        return "scout_photo_link_action_invalid", None
    if data.action == "link" and data.season_id is None:
        return "scout_photo_season_id_required", None
    if data.action == "revoke" and data.season_id is not None:
        return "scout_photo_revoke_must_not_name_season", None
    if (data.action == "revoke" or data.previous_event_id is not None) and not reason:
        return "scout_photo_link_revision_reason_required", None
    if reason is not None and len(reason) > 2000:
        return "scout_photo_link_reason_too_long", None
    if data.previous_event_id is not None and data.previous_event_id == data.event_id:
        return "scout_photo_link_self_reference", None
    return None, reason or None


def _text_or_none(value) -> str | None:
    return str(value) if value is not None else None


def season_event_matches(row, data: PhotoSeasonLinkEventIn, reason: str | None, actor: str) -> bool:
    """A stored event acknowledges a retry only when every immutable field agrees."""
    return (
        row["action"] == data.action
        and row["actor_id"] == actor
        and _text_or_none(row["season_id"]) == _text_or_none(data.season_id)
        and _text_or_none(row["previous_event_id"]) == _text_or_none(data.previous_event_id)
        and row["reason"] == reason
    )


def season_context(head) -> dict:
    """The season part of the context, from the chain head (or its absence)."""
    if head is None:
        return {"state": "explicit_link_required", "season_id": None}
    event_id = str(head["event_id"])
    if head["action"] == "revoke":
        return {"state": "revoked", "season_id": None, "link_event_id": event_id}
    if head["trust_status"] != "accepted" or not head["accepted_by"] or head["accepted_at"] is None:
        # The season left (or never had) human acceptance: the link carries no authority now.
        return {
            "state": "linked_not_accepted",
            "season_id": str(head["season_id"]),
            "link_event_id": event_id,
        }
    return {
        "state": "linked_accepted",
        "season_id": str(head["season_id"]),
        "link_event_id": event_id,
        "link_proof": SEASON_LINK_PROOF,
    }


def require_role(role: str | None, allowed: frozenset, code: str) -> None:
    if (role or "").strip().lower() not in allowed:
        raise HTTPException(403, code)


async def _linked_inspection(conn, tenant: str, field_id: str, pin_id: str) -> dict | None:
    """Only the v246 FK pointer (field_tasks.source_scouting_pin_id); never a nearby task.

    field_tasks belongs to field-management-service; sahool_ingest has column SELECT on it.
    """
    matches = await conn.fetch(
        "SELECT task_id, status FROM field_tasks "
        "WHERE tenant_id=$1::uuid AND field_id=$2 AND source_scouting_pin_id=$3 "
        "ORDER BY task_id LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    if len(matches) > 1:  # never an arbitrary winner if the schema ever admits two
        raise HTTPException(503, "scout_photo_inspection_link_ambiguous")
    if not matches:
        return None
    return {
        "task_id": str(matches[0]["task_id"]),
        "status": str(matches[0]["status"]),
        "link_proof": "field_tasks.source_scouting_pin_id:v246",
    }


_SEASON_EVENT_COLS = "event_id, action, season_id, previous_event_id, actor_id, reason"
_SELECT_SEASON_EVENT = (
    f"SELECT {_SEASON_EVENT_COLS} FROM scout_photo_season_link_events "
    "WHERE event_id=$1::uuid AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4"
)


async def _season_head(conn, tenant: str, field_id: str, pin_id: str):
    """The chain head (the event nothing succeeds), not a date-sorted winner.

    v262's unique root and unique successor admit one linear chain; a second head is refused.
    """
    rows = await conn.fetch(
        "SELECT e.event_id, e.action, e.season_id, e.previous_event_id, "
        "s.trust_status, s.accepted_by, s.accepted_at "
        "FROM scout_photo_season_link_events e "
        "LEFT JOIN season_records s ON s.id=e.season_id AND s.tenant_id=e.tenant_id "
        "AND s.field_id=e.field_id "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_photo_season_link_events successor "
        "WHERE successor.previous_event_id=e.event_id) "
        "ORDER BY e.created_at DESC LIMIT 2",
        tenant,
        field_id,
        pin_id,
    )
    if len(rows) > 1:
        raise HTTPException(503, "scout_photo_season_link_chain_ambiguous")
    return rows[0] if rows else None


async def _verified_photo(tenant: str, field_id: str, pin_id: str):
    """The photo row, only when its object is present (404 without a row)."""
    row = await _read_row(tenant, field_id, pin_id)
    if row is None:
        raise HTTPException(404, "scout_photo_not_found")
    await _require_object_present(row, tenant, pin_id)
    return row


def _season_receipt(event_id: UUID, head, *, idempotent: bool) -> dict:
    return {
        "event_id": str(event_id),
        "persisted": True,
        "idempotent": idempotent,
        "is_current": head is not None and str(head["event_id"]) == str(event_id),
        "season": season_context(head),
        "automatic_pesticide_action_authorized": False,
    }


async def _insert_season_event(conn, tenant, field_id, pin_id, data, reason, actor):
    """INSERT the event; ``None`` when nothing was inserted (conflict or no accepted season)."""
    previous = _text_or_none(data.previous_event_id)
    if data.action == "revoke":
        return await conn.fetchval(
            "INSERT INTO scout_photo_season_link_events "
            "(event_id,tenant_id,field_id,pin_id,season_id,action,previous_event_id,actor_id,reason) "
            "VALUES ($1::uuid,$2::uuid,$3,$4,NULL,'revoke',$5::uuid,$6,$7) "
            "ON CONFLICT DO NOTHING RETURNING event_id",
            str(data.event_id),
            tenant,
            field_id,
            pin_id,
            previous,
            actor,
            reason,
        )
    # One statement proves the season is this tenant+field's and human-accepted; the UUID, the
    # FK and the unique successor fence concurrent writers.
    return await conn.fetchval(
        "INSERT INTO scout_photo_season_link_events "
        "(event_id,tenant_id,field_id,pin_id,season_id,action,previous_event_id,actor_id,reason) "
        "SELECT $1::uuid,$2::uuid,$3,$4,s.id,'link',$6::uuid,$7,$8 "
        "FROM season_records s WHERE s.id=$5::uuid AND s.tenant_id=$2::uuid "
        "AND s.field_id=$3 AND s.trust_status='accepted' "
        "AND s.accepted_by IS NOT NULL AND s.accepted_at IS NOT NULL "
        "ON CONFLICT DO NOTHING RETURNING event_id",
        str(data.event_id),
        tenant,
        field_id,
        pin_id,
        str(data.season_id),
        previous,
        actor,
        reason,
    )


@router.post("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/season-link-events")
async def post_pin_photo_season_link_event(
    field_id: str,
    pin_id: str,
    data: PhotoSeasonLinkEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """Append an explicit accepted-season link, a correction, or a revocation.

    Not a season acceptance, a diagnostic review or a pesticide approval. Off by default.
    """
    tenant, actor = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    if not season_bridge_enabled():
        raise HTTPException(404, "scout_photo_season_link_disabled")
    require_role(x_user_role, SEASON_LINK_ROLES, "scout_photo_season_link_role_denied")
    _require_valid_pin(pin_id)
    code, reason = season_link_refusal(data)
    if code:
        raise HTTPException(422, code)
    await require_media_field_scope(tenant, field_id, actor, "photo.season_link", x_user_role)
    try:
        await _verified_photo(tenant, field_id, pin_id)
        conn = await _tenant_connection(tenant)
        try:
            args = (str(data.event_id), tenant, field_id, pin_id)

            async def replay():
                """The stored event under this id, when it is this very request (else None)."""
                stored = await conn.fetchrow(_SELECT_SEASON_EVENT, *args)
                if stored is None:
                    return None
                if not season_event_matches(stored, data, reason, actor):
                    raise HTTPException(409, "scout_photo_link_idempotency_conflict")
                head = await _season_head(conn, tenant, field_id, pin_id)
                return _season_receipt(data.event_id, head, idempotent=True)

            if (receipt := await replay()) is not None:
                return receipt
            head = await _season_head(conn, tenant, field_id, pin_id)
            predecessor = str(head["event_id"]) if head is not None else None
            if predecessor != _text_or_none(data.previous_event_id) or (
                data.action == "revoke" and head is None
            ):
                # An identical concurrent request may have become the head since the read
                # above: that is this request's own event, not a conflict.
                if (receipt := await replay()) is not None:
                    return receipt
                raise HTTPException(409, "scout_photo_link_predecessor_conflict")
            inserted = await _insert_season_event(
                conn, tenant, field_id, pin_id, data, reason, actor
            )
            if inserted is None:
                # A concurrent identical request may have won the event_id; acknowledge it only
                # when every immutable field agrees. Otherwise: no accepted season (422) or a
                # different concurrent successor (409).
                if (receipt := await replay()) is not None:
                    return receipt
                if data.action == "link" and not await conn.fetchval(
                    "SELECT true FROM season_records WHERE id=$1::uuid AND tenant_id=$2::uuid "
                    "AND field_id=$3 AND trust_status='accepted' AND accepted_by IS NOT NULL "
                    "AND accepted_at IS NOT NULL",
                    str(data.season_id),
                    tenant,
                    field_id,
                ):
                    raise HTTPException(422, "scout_photo_accepted_season_not_found")
                raise HTTPException(409, "scout_photo_link_concurrent_conflict")
            new_head = await _season_head(conn, tenant, field_id, pin_id)
            if new_head is None or str(new_head["event_id"]) != str(data.event_id):
                raise HTTPException(503, "scout_photo_link_commit_unverified")
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — FK/unique violations included: never a 500
        raise _db_error() from exc
    return _season_receipt(data.event_id, new_head, idempotent=False)


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/season-link-events")
async def list_pin_photo_season_link_events(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """The whole actor-attributed chain, or a 503: never a partial audit trail."""
    tenant, actor = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    if not season_bridge_enabled():
        raise HTTPException(404, "scout_photo_season_link_disabled")
    require_role(x_user_role, SEASON_LINK_ROLES, "scout_photo_season_link_role_denied")
    _require_valid_pin(pin_id)
    await require_media_field_scope(tenant, field_id, actor, "photo.season_link", x_user_role)
    try:
        await _verified_photo(tenant, field_id, pin_id)
        conn = await _tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                f"SELECT {_SEASON_EVENT_COLS}, created_at FROM scout_photo_season_link_events "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 "
                "ORDER BY created_at, event_id LIMIT $4",
                tenant,
                field_id,
                pin_id,
                SEASON_LINK_HISTORY_LIMIT + 1,
            )
            if len(rows) > SEASON_LINK_HISTORY_LIMIT:
                raise HTTPException(503, "scout_photo_link_history_limit_exceeded")
            head = await _season_head(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_error() from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "field_id": field_id,
        "pin_id": pin_id,
        "history_complete": True,
        "events": [
            {
                "event_id": str(row["event_id"]),
                "action": row["action"],
                "season_id": _text_or_none(row["season_id"]),
                "previous_event_id": _text_or_none(row["previous_event_id"]),
                "actor_id": row["actor_id"],
                "reason": row["reason"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ],
        "current": season_context(head),
        "automatic_pesticide_action_authorized": False,
    }


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/context")
async def get_pin_photo_context(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """photo → pin → proven links, each by its own key and flag; not an AI decision.

    Every relational part is read in one REPEATABLE READ READ ONLY transaction (owner phase 10), so
    the context never mixes PostgreSQL instants. The object HEAD runs after that snapshot and is
    named as such: it cannot be transactionally consistent with PostgreSQL.
    """
    tenant, actor = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    require_role(x_user_role, CONTEXT_ROLES, "scout_media_context_role_denied")
    _require_valid_pin(pin_id)
    await require_media_field_scope(tenant, field_id, actor, "photo.context", x_user_role)
    from detection_link_api import current_detection_context
    from evidence_retention_api import current_retention_context
    from human_review_api import current_human_review_context
    from lab_link_api import current_lab_context
    from tissue_samples_api import current_tissue_context
    from treatment_review_api import current_treatment_context

    try:
        conn = await _tenant_connection(tenant)
        try:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                row = await _read_row(tenant, field_id, pin_id, conn=conn)
                if row is None:
                    raise HTTPException(404, "scout_photo_not_found")
                parts = {
                    "inspection": await _linked_inspection(conn, tenant, field_id, pin_id),
                    "season": (
                        season_context(await _season_head(conn, tenant, field_id, pin_id))
                        if season_bridge_enabled()
                        else {"state": "explicit_link_required", "season_id": None}
                    ),
                    "detection": await current_detection_context(conn, tenant, field_id, pin_id),
                    "lab_sample": await current_lab_context(conn, tenant, field_id, pin_id),
                    "human_review": await current_human_review_context(
                        conn, tenant, field_id, pin_id
                    ),
                    "plant_tissue_samples": await current_tissue_context(
                        conn, tenant, field_id, pin_id
                    ),
                    "treatment_review": await current_treatment_context(
                        conn, tenant, field_id, pin_id
                    ),
                    "retention": await current_retention_context(conn, tenant, field_id, pin_id),
                }
        finally:
            await conn.close()
        await _require_object_present(row, tenant, pin_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a DB failure is a 503, never "not linked"
        raise _db_error() from exc
    inspection = parts.pop("inspection")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "schema": "sahool.scout-photo-evidence-context/v1",
        "source": {"kind": "scouting_pin", "field_id": field_id, "pin_id": pin_id},
        "evidence": public_receipt(row),
        "object_state": "present_at_check",  # HEAD existence only, not a remote re-hash
        "consistency": {
            "relational_snapshot": "repeatable_read",
            "object_presence": "checked_after_relational_snapshot",
        },
        "inspection": {"state": "linked", **inspection} if inspection else {"state": "not_linked"},
        **parts,
        "decision": {"state": "not_authorized", "decision_id": None},
        "automatic_pesticide_action_authorized": False,
    }
