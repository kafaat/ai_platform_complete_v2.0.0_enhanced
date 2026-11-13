"""Tenant-authenticated, S3-only shared camera evidence for persisted scouting pins.

This belongs to scout-ingest and its own append-only table, not platform's
``scouting_pins`` writer. The Nginx boundary verifies JWT, strips caller-supplied
identity headers, and injects a *separate* service token + trusted tenant/user/role.
Direct external HTTP to this internal endpoint is not supported.
"""
from __future__ import annotations

import os
from uuid import UUID

from pydantic import BaseModel

from fastapi import APIRouter, Header, HTTPException, Request, Response

from shared.security.scout_photo import (
    MAX_PHOTO_BYTES, PhotoValidationError, inspect_photo, media_key,
)
from shared.security.trusted_tenant import service_token_ok
from shared.storage import blob_store

router = APIRouter()
_ENABLED = {"1", "true", "yes", "on"}
_WRITE_ROLES = {"owner", "manager", "expert", "agronomist", "farmer", "worker"}
_READ_ROLES = _WRITE_ROLES | {"admin", "viewer"}
# Task linkage reveals internal workflow state; unlike the photo thumbnail, it
# is not available to generic viewers/workers without a field-task assignment proof.
_CONTEXT_ROLES = {"owner", "manager", "expert", "agronomist", "farmer", "admin"}
_SEASON_LINK_ROLES = {"owner", "manager", "expert", "agronomist", "admin"}
_DETECTION_LINK_ROLES = _SEASON_LINK_ROLES


def _season_bridge_enabled() -> bool:
    # Separate rollout fence: existing media-context consumers work without v257.
    # Once switched on, missing schema/DB is a 503, not a fabricated empty link.
    return os.getenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "0").strip().lower() in _ENABLED


class PhotoSeasonLinkEventIn(BaseModel):
    # Client-generated UUID makes offline/mobile retries idempotent, even after
    # the first successful insert was followed by a network timeout.
    event_id: UUID
    action: str
    season_id: UUID | None = None
    previous_event_id: UUID | None = None
    reason: str | None = None


def _authorize(token: str | None, tenant: str | None, uid: str | None,
               role: str | None, *, write: bool) -> tuple[str, str]:
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
    if (role or "").strip().lower() not in (_WRITE_ROLES if write else _READ_ROLES):
        raise HTTPException(403, "scout_media_role_denied")
    # Shared photos must NOT be silently stored as file:// in one container.
    # blob_store's dev fallback is intentionally disallowed for this API.
    if not blob_store.s3_enabled():
        raise HTTPException(503, "shared_photo_storage_not_configured")
    return tenant_id, uid.strip()


async def _tenant_connection(tenant: str):
    import season_api
    return await season_api._tenant_conn(tenant)


async def _require_pin(conn, tenant: str, field_id: str, pin_id: str) -> None:
    exists = await conn.fetchval(
        "SELECT true FROM scouting_pins WHERE tenant_id=$1::uuid "
        "AND field_id=$2 AND pin_id=$3", tenant, field_id, pin_id
    )
    if not exists:
        raise HTTPException(404, "scouting_pin_not_found")


def _public_row(row) -> dict:
    return {
        "evidence_id": str(row["evidence_id"]),
        "field_id": row["field_id"],
        "pin_id": row["pin_id"],
        "sha256": str(row["content_sha256"]).strip(),
        "content_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "width": row["image_width"],
        "height": row["image_height"],
        "persisted": True,
        "verification_state": "bytes_verified",
        "review_state": "unreviewed",
    }


async def _read_row(tenant: str, field_id: str, pin_id: str):
    conn = await _tenant_connection(tenant)
    try:
        await _require_pin(conn, tenant, field_id, pin_id)
        return await conn.fetchrow(
            "SELECT evidence_id, field_id, pin_id, object_ref, content_sha256, "
            "mime_type, size_bytes, image_width, image_height "
            "FROM scout_photo_evidence WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
            tenant, field_id, pin_id,
        )
    finally:
        await conn.close()


def _db_error(exc: Exception) -> HTTPException:
    # Never leak connection strings, SQL/schema, object store credentials to clients.
    return HTTPException(503, "scout_media_database_unavailable")


def _check_owned_object_ref(row, tenant: str, pin_id: str) -> None:
    """Never HEAD/presign an arbitrary S3 URI taken from a stored row.

    A poisoned row or historical bug must not let the media service sign objects
    outside this tenant+pin+digest namespace (nor another configured bucket).
    """
    try:
        digest = str(row["content_sha256"]).strip()
        key = media_key(tenant, pin_id, digest)
        expected = f"s3://{blob_store.S3_BUCKET}/{key}"
    except (KeyError, ValueError, PhotoValidationError, TypeError):
        raise HTTPException(503, "scout_photo_reference_invalid") from None
    if not blob_store.S3_BUCKET or row["object_ref"] != expected:
        raise HTTPException(503, "scout_photo_reference_invalid")


def _require_object_present(row, tenant: str, pin_id: str) -> None:
    _check_owned_object_ref(row, tenant, pin_id)
    try:
        if not blob_store.object_exists(row["object_ref"]):
            raise HTTPException(503, "scout_photo_object_not_verified")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "scout_photo_store_unavailable") from exc


async def _require_media_field_scope(tenant: str, field_id: str, actor: str, scope: str, live_role_claim: str) -> None:
    """P0 field-level authorization, independent of RBAC and tenant authentication.

    The *platform-owned* grants table is the only source of field access.
    Neither creating a pin, holding an OWNER role, nor possessing a service
    token implicitly grants a media scope. Role changes invalidate older edge
    tokens: the trusted role must match the current user role in PostgreSQL.
    Historical indefinite grants are NEVER runtime authorization. Missing
    schema/DB => 503, missing or revoked/expired grant => 403.
    """
    conn = None
    try:
        conn = await _tenant_connection(tenant)
        permitted = await conn.fetchval(
            "SELECT true FROM scout_photo_field_access_grants AS g "
            "JOIN users AS u ON u.id=g.user_id AND u.tenant_id=g.tenant_id AND u.active IS TRUE "
            "JOIN fields AS f ON f.tenant_id=g.tenant_id AND f.field_id=g.field_id "
            "WHERE g.tenant_id=$1::uuid AND g.field_id=$2 AND u.id::text=$3 "
            "AND g.scope=$4 AND lower(u.role::text)=$5 "
            "AND g.revoked_at IS NULL AND g.expires_at IS NOT NULL "
            "AND g.granted_at <= now() AND g.expires_at > now() "
            "AND g.expires_at <= g.granted_at + interval '90 days' LIMIT 1",
            tenant, field_id, actor, scope, live_role_claim.strip().lower(),
        )
    except Exception as exc:
        raise _db_error(exc) from exc
    finally:
        if conn is not None:
            await conn.close()
    if not permitted:
        raise HTTPException(403, "scout_media_field_scope_denied")


@router.post("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo")
async def post_pin_photo(
    field_id: str, pin_id: str, request: Request,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    x_content_sha256: str | None = Header(None, alias="X-Content-SHA256"),
):
    tenant, uid = _authorize(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=True
    )
    await _require_media_field_scope(tenant, field_id, uid, "photo.upload", x_user_role or "")
    try:
        # Validate server-key syntax BEFORE reading data or contacting object storage.
        media_key(tenant, pin_id, "0" * 64)
    except (ValueError, PhotoValidationError):
        raise HTTPException(422, "invalid_pin_id") from None
    try:
        existing = await _read_row(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc

    # Read bounded chunks, never a multi-MB unlimited await request.body().
    parts: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo_too_large")
        parts.append(chunk)
    data = b"".join(parts)
    try:
        image = inspect_photo(
            data, request.headers.get("content-type", "").split(";", 1)[0].lower(),
            x_content_sha256 or "",
        )
    except PhotoValidationError as exc:
        raise HTTPException(415 if exc.code in {"unsupported_photo_type", "photo_type_mismatch", "photo_decode_failed"} else 422,
                            exc.code) from exc

    if existing:
        if str(existing["content_sha256"]).strip() != image.sha256:
            raise HTTPException(409, "photo_already_saved_with_other_bytes")
        # A DB row alone is NOT a durable object receipt. Check both its
        # deterministic tenant namespace and the currently present S3 object.
        _require_object_present(existing, tenant, pin_id)
        return {**_public_row(existing), "idempotent": True}

    object_key = media_key(tenant, pin_id, image.sha256)
    try:
        ref = blob_store.upload_bytes(object_key, data, image.content_type)
        # A storage adapter returning some other bucket/key must never poison
        # the immutable SQL receipt (and thereby block all future retries).
        expected_ref = f"s3://{blob_store.S3_BUCKET}/{object_key}"
        if ref != expected_ref:
            raise blob_store.BlobStoreError("S3 upload reference disagrees with server-derived key")
    except Exception as exc:
        raise HTTPException(503, "scout_media_store_unavailable") from exc

    await _require_media_field_scope(tenant, field_id, uid, "photo.upload", x_user_role or "")
    try:
        conn = await _tenant_connection(tenant)
        try:
            # Foreign key plus unique constraint fence competing uploads even
            # when the observation is deleted/replaced between the two calls.
            inserted_id = await conn.fetchval(
                "INSERT INTO scout_photo_evidence "
                "(tenant_id, field_id, pin_id, object_ref, content_sha256, mime_type, "
                "size_bytes, image_width, image_height, uploaded_by) "
                "VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10) "
                "ON CONFLICT (tenant_id,field_id,pin_id) DO NOTHING RETURNING evidence_id",
                tenant, field_id, pin_id, ref, image.sha256, image.content_type,
                image.size_bytes, image.width, image.height, uid,
            )
        finally:
            await conn.close()
        saved = await _read_row(tenant, field_id, pin_id)
        if saved is None:
            raise RuntimeError("missing persisted photo receipt")
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    if str(saved["content_sha256"]).strip() != image.sha256:
        raise HTTPException(409, "photo_already_saved_with_other_bytes")
    # Even for the first POST, a committed SQL record is not proof that S3
    # retained the bytes. Return 503 when HEAD cannot verify the object.
    _require_object_present(saved, tenant, pin_id)
    return {**_public_row(saved), "idempotent": inserted_id is None}


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo")
async def get_pin_photo(
    field_id: str, pin_id: str, response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = _authorize(x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False)
    await _require_media_field_scope(tenant, field_id, actor, "photo.read", x_user_role or "")
    try:
        row = await _read_row(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise HTTPException(404, "scout_photo_not_found")
    _require_object_present(row, tenant, pin_id)
    try:
        url = blob_store.presigned_get_url(row["object_ref"], ttl_s=120)
        if not url.startswith("https://"):
            raise blob_store.BlobStoreError("refused non-HTTPS photo URL")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "scout_photo_presign_unavailable") from exc
    # A presigned link is a bearer capability. Never allow a shared cache to
    # retain it across tenant sessions, even during the 120s validity window.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {**_public_row(row), "url": url, "expires_in_seconds": 120}


async def _linked_inspection(tenant: str, field_id: str, pin_id: str) -> dict | None:
    """Read ONLY the authoritative v246 FK link, never infer a task by proximity.

    field_tasks belongs to field-management-service. This consumer has narrow SELECT
    rights only; no task mutation, assignment inference, or direct DB ownership.
    """
    conn = await _tenant_connection(tenant)
    try:
        matches = await conn.fetch(
            "SELECT task_id, status FROM field_tasks "
            "WHERE tenant_id=$1::uuid AND field_id=$2 AND source_scouting_pin_id=$3 "
            "ORDER BY task_id LIMIT 2", tenant, field_id, pin_id,
        )
    finally:
        await conn.close()
    # Defensive: no arbitrary winner if schema drift ever permits >1 source link.
    if len(matches) > 1:
        raise HTTPException(503, "scout_photo_inspection_link_ambiguous")
    if not matches:
        return None
    return {
        "task_id": str(matches[0]["task_id"]),
        "status": str(matches[0]["status"]),
        "link_proof": "field_tasks.source_scouting_pin_id:v246",
    }


async def _current_season_link_event(tenant: str, field_id: str, pin_id: str, *, conn=None):
    """Read chain HEAD, not a date-sorted winner or a heuristic season match.

    The table's unique root + unique successor constraints admit exactly one
    linear chain. Detect a second head anyway rather than returning random truth.
    """
    close_after = conn is None
    if conn is None:
        conn = await _tenant_connection(tenant)
    try:
        rows = await conn.fetch(
            "SELECT e.event_id, e.action, e.season_id, e.previous_event_id, "
            "s.trust_status, s.accepted_by, s.accepted_at "
            "FROM scout_photo_season_link_events e "
            "LEFT JOIN season_records s ON s.id=e.season_id AND s.tenant_id=e.tenant_id "
            "AND s.field_id=e.field_id "
            "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
            "AND NOT EXISTS (SELECT 1 FROM scout_photo_season_link_events successor "
            "WHERE successor.previous_event_id=e.event_id) "
            "ORDER BY e.created_at DESC LIMIT 2", tenant, field_id, pin_id,
        )
    finally:
        if close_after:
            await conn.close()
    if len(rows) > 1:
        raise HTTPException(503, "scout_photo_season_link_chain_ambiguous")
    return rows[0] if rows else None


def _season_context(head) -> dict:
    if head is None:
        return {"state": "explicit_link_required", "season_id": None}
    if head["action"] == "revoke":
        return {
            "state": "revoked", "season_id": None,
            "link_event_id": str(head["event_id"]),
        }
    if (head["trust_status"] != "accepted" or not head["accepted_by"]
            or head["accepted_at"] is None):
        return {
            "state": "linked_not_accepted", "season_id": str(head["season_id"]),
            "link_event_id": str(head["event_id"]),
        }
    return {
        "state": "linked_accepted", "season_id": str(head["season_id"]),
        "link_event_id": str(head["event_id"]),
        "link_proof": "scout_photo_season_link_events:v257",
    }


def _event_matches(row, data: PhotoSeasonLinkEventIn, reason: str | None, actor: str) -> bool:
    return (
        row["action"] == data.action
        and row["actor_id"] == actor
        and (str(row["season_id"]) if row["season_id"] is not None else None)
        == (str(data.season_id) if data.season_id is not None else None)
        and (str(row["previous_event_id"]) if row["previous_event_id"] is not None else None)
        == (str(data.previous_event_id) if data.previous_event_id is not None else None)
        and row["reason"] == reason
    )


@router.post("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/season-link-events")
async def post_pin_photo_season_link_event(
    field_id: str, pin_id: str, data: PhotoSeasonLinkEventIn,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """Append an explicit accepted-season link, correction, or revocation.

    This is NOT a season acceptance, diagnostic review, or pesticide approval.
    Off by default. Does not bypass field-assignment authorization still needed
    for a general-audience production rollout.
    """
    # Read-level base gate includes admin, while the dedicated link-role fence
    # below is stricter than ordinary photo upload permissions.
    tenant, actor = _authorize(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False
    )
    if not _season_bridge_enabled():
        raise HTTPException(404, "scout_photo_season_link_disabled")
    if (x_user_role or "").strip().lower() not in _SEASON_LINK_ROLES:
        raise HTTPException(403, "scout_photo_season_link_role_denied")
    await _require_media_field_scope(tenant, field_id, actor, "photo.season_link", x_user_role or "")
    reason = data.reason.strip() if data.reason is not None else None
    if data.action not in {"link", "revoke"}:
        raise HTTPException(422, "scout_photo_link_action_invalid")
    if data.action == "link" and data.season_id is None:
        raise HTTPException(422, "scout_photo_season_id_required")
    if data.action == "revoke" and data.season_id is not None:
        raise HTTPException(422, "scout_photo_revoke_must_not_name_season")
    if (data.action == "revoke" or data.previous_event_id is not None) and not reason:
        raise HTTPException(422, "scout_photo_link_revision_reason_required")
    if reason is not None and len(reason) > 2000:
        raise HTTPException(422, "scout_photo_link_reason_too_long")
    if data.previous_event_id == data.event_id:
        raise HTTPException(422, "scout_photo_link_self_reference")
    try:
        photo = await _read_row(tenant, field_id, pin_id)
        if photo is None:
            raise HTTPException(404, "scout_photo_not_found")
        _require_object_present(photo, tenant, pin_id)
        conn = await _tenant_connection(tenant)
        try:
            existing = await conn.fetchrow(
                "SELECT event_id, action, season_id, previous_event_id, actor_id, reason "
                "FROM scout_photo_season_link_events "
                "WHERE event_id=$1::uuid AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                str(data.event_id), tenant, field_id, pin_id,
            )
            if existing is not None:
                if not _event_matches(existing, data, reason, actor):
                    raise HTTPException(409, "scout_photo_link_idempotency_conflict")
                head = await _current_season_link_event(tenant, field_id, pin_id, conn=conn)
                return {
                    "event_id": str(data.event_id), "persisted": True,
                    "idempotent": True,
                    "is_current": head is not None and str(head["event_id"]) == str(data.event_id),
                    "season": _season_context(head),
                    "automatic_pesticide_action_authorized": False,
                }
            head = await _current_season_link_event(tenant, field_id, pin_id, conn=conn)
            predecessor = str(head["event_id"]) if head is not None else None
            requested_predecessor = str(data.previous_event_id) if data.previous_event_id is not None else None
            if predecessor != requested_predecessor or (data.action == "revoke" and head is None):
                raise HTTPException(409, "scout_photo_link_predecessor_conflict")
            if data.action == "link":
                # Same SQL statement proves that a HUMAN-accepted season belongs
                # to the exact tenant+field. UUID+FK and unique successor fence races.
                inserted = await conn.fetchval(
                    "INSERT INTO scout_photo_season_link_events "
                    "(event_id,tenant_id,field_id,pin_id,season_id,action,previous_event_id,actor_id,reason) "
                    "SELECT $1::uuid,$2::uuid,$3,$4,s.id,'link',$6::uuid,$7,$8 "
                    "FROM season_records s WHERE s.id=$5::uuid AND s.tenant_id=$2::uuid "
                    "AND s.field_id=$3 AND s.trust_status='accepted' "
                    "AND s.accepted_by IS NOT NULL AND s.accepted_at IS NOT NULL "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    str(data.event_id), tenant, field_id, pin_id, str(data.season_id),
                    requested_predecessor, actor, reason,
                )
                if inserted is None:
                    # Distinguish an invalid season from a valid concurrent
                    # successor (which the event-id idempotency path below resolves).
                    season_exists = await conn.fetchval(
                        "SELECT true FROM season_records WHERE id=$1::uuid AND tenant_id=$2::uuid "
                        "AND field_id=$3 AND trust_status='accepted' AND accepted_by IS NOT NULL "
                        "AND accepted_at IS NOT NULL",
                        str(data.season_id), tenant, field_id,
                    )
                    if not season_exists:
                        concurrent = await conn.fetchrow(
                            "SELECT event_id, action, season_id, previous_event_id, actor_id, reason "
                            "FROM scout_photo_season_link_events "
                            "WHERE event_id=$1::uuid AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                            str(data.event_id), tenant, field_id, pin_id,
                        )
                        if concurrent is None or not _event_matches(concurrent, data, reason, actor):
                            raise HTTPException(422, "scout_photo_accepted_season_not_found")
            else:
                inserted = await conn.fetchval(
                    "INSERT INTO scout_photo_season_link_events "
                    "(event_id,tenant_id,field_id,pin_id,season_id,action,previous_event_id,actor_id,reason) "
                    "VALUES ($1::uuid,$2::uuid,$3,$4,NULL,'revoke',$5::uuid,$6,$7) "
                    "ON CONFLICT DO NOTHING RETURNING event_id",
                    str(data.event_id), tenant, field_id, pin_id, requested_predecessor,
                    actor, reason,
                )
            if inserted is None:
                # A concurrent identical attempt may have won the unique event_id
                # race. Acknowledge it ONLY if every immutable payload field
                # agrees; never treat a conflicting id/season as idempotent.
                winner = await conn.fetchrow(
                    "SELECT event_id, action, season_id, previous_event_id, actor_id, reason "
                    "FROM scout_photo_season_link_events "
                    "WHERE event_id=$1::uuid AND tenant_id=$2::uuid AND field_id=$3 AND pin_id=$4",
                    str(data.event_id), tenant, field_id, pin_id,
                )
                if winner is not None and _event_matches(winner, data, reason, actor):
                    latest = await _current_season_link_event(tenant, field_id, pin_id, conn=conn)
                    return {
                        "event_id": str(data.event_id), "persisted": True,
                        "idempotent": True,
                        "is_current": latest is not None and str(latest["event_id"]) == str(data.event_id),
                        "season": _season_context(latest),
                        "automatic_pesticide_action_authorized": False,
                    }
                raise HTTPException(409, "scout_photo_link_concurrent_conflict")
            new_head = await _current_season_link_event(tenant, field_id, pin_id, conn=conn)
            if new_head is None or str(new_head["event_id"]) != str(data.event_id):
                raise HTTPException(503, "scout_photo_link_commit_unverified")
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    return {
        "event_id": str(data.event_id), "persisted": True,
        "idempotent": False, "is_current": True,
        "season": _season_context(new_head),
        "automatic_pesticide_action_authorized": False,
    }


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/season-link-events")
async def list_pin_photo_season_link_events(
    field_id: str, pin_id: str, response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """Human-auditable complete event chain. Do not leak S3 object refs."""
    tenant, actor = _authorize(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False
    )
    if not _season_bridge_enabled():
        raise HTTPException(404, "scout_photo_season_link_disabled")
    if (x_user_role or "").strip().lower() not in _SEASON_LINK_ROLES:
        raise HTTPException(403, "scout_photo_season_link_role_denied")
    await _require_media_field_scope(tenant, field_id, actor, "photo.season_link", x_user_role or "")
    try:
        photo = await _read_row(tenant, field_id, pin_id)
        if photo is None:
            raise HTTPException(404, "scout_photo_not_found")
        _require_object_present(photo, tenant, pin_id)
        conn = await _tenant_connection(tenant)
        try:
            rows = await conn.fetch(
                "SELECT event_id, action, season_id, previous_event_id, actor_id, reason, created_at "
                "FROM scout_photo_season_link_events "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3 "
                "ORDER BY created_at, event_id LIMIT 201", tenant, field_id, pin_id,
            )
            # Refuse a partial audit trail. A separate cursor-based audit API
            # is required before a single image accumulates over 200 events.
            if len(rows) > 200:
                raise HTTPException(503, "scout_photo_link_history_limit_exceeded")
            head = await _current_season_link_event(tenant, field_id, pin_id, conn=conn)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "field_id": field_id, "pin_id": pin_id,
        "history_complete": True,
        "events": [
            {
                "event_id": str(row["event_id"]),
                "action": row["action"],
                "season_id": str(row["season_id"]) if row["season_id"] is not None else None,
                "previous_event_id": str(row["previous_event_id"]) if row["previous_event_id"] is not None else None,
                "actor_id": row["actor_id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
        "current": _season_context(head),
        "automatic_pesticide_action_authorized": False,
    }


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/context")
async def get_pin_photo_context(
    field_id: str, pin_id: str, response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    """B1.4 read-model: photo -> pin -> proven inspection, NOT an AI decision.

    An observation photo is not automatically bound to a season, laboratory
    sample, detection result, or pesticide authorization. A missing link is
    represented as unresolved, never filled by crop/time/nearby coordinates.
    """
    tenant, actor = _authorize(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False
    )
    if (x_user_role or "").strip().lower() not in _CONTEXT_ROLES:
        raise HTTPException(403, "scout_media_context_role_denied")
    await _require_media_field_scope(tenant, field_id, actor, "photo.context", x_user_role or "")
    try:
        row = await _read_row(tenant, field_id, pin_id)
        if row is None:
            raise HTTPException(404, "scout_photo_not_found")
        _require_object_present(row, tenant, pin_id)
        inspection = await _linked_inspection(tenant, field_id, pin_id)
        season = (
            _season_context(await _current_season_link_event(tenant, field_id, pin_id))
            if _season_bridge_enabled()
            else {"state": "explicit_link_required", "season_id": None}
        )
        # Only a signed, auditable event can link a model result to this image.
        # Lazy import avoids circular dependency between the two owner routers.
        from detection_link_api import current_detection_context
        detection = await current_detection_context(tenant, field_id, pin_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc) from exc

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "schema": "sahool.scout-photo-evidence-context/v1",
        "source": {"kind": "scouting_pin", "field_id": field_id, "pin_id": pin_id},
        "evidence": _public_row(row),
        "object_state": "present_at_check",  # HEAD existence only, not remote re-hash
        "inspection": {"state": "linked", **inspection} if inspection else {"state": "not_linked"},
        # Only an explicit, tenant+field fenced, accepted-season event links a
        # season. No heuristic image-to-sample/model/decision link exists.
        "season": season,
        "lab_sample": {"state": "explicit_link_required", "sample_id": None},
        "detection": detection,
        "decision": {"state": "not_authorized", "decision_id": None},
        "automatic_pesticide_action_authorized": False,
    }
