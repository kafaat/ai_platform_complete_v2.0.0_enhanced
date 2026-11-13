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
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response

from shared.security.scout_photo import (
    MAX_PHOTO_BYTES,
    PhotoValidationError,
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
PRESIGN_TTL_S = 120

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


async def _read_row(tenant: str, field_id: str, pin_id: str):
    """The pin must be visible under the tenant's RLS; then its photo row, or None."""
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
    if not ref.startswith("s3://"):  # S3_ALLOW_FILE_FALLBACK degraded to file:// — not shared
        raise HTTPException(503, "scout_media_store_unavailable")

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
    tenant, _ = authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    _require_valid_pin(pin_id)
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
