"""Owner-governed, audit-atomic field-scoped scouting photo grant administration.

Separate database credential: the normal platform app role and the ingest role
cannot write either grants or audit. JWT permission is necessary but not enough:
the issuer is re-checked against *live* active users in this tenant on each call.
The feature is disabled by default; nothing in this module grants by role alone.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission

router = APIRouter()
_SCOPES = Literal["photo.read", "photo.upload", "photo.context", "photo.season_link", "photo.detection_link"]
_ADMIN_ROLE = "sahool_scout_grant_admin"
_ENABLED = frozenset(("1", "true", "on", "yes"))


class IssueGrant(BaseModel):
    event_id: UUID
    user_id: int = Field(gt=0)
    scope: _SCOPES
    expires_at: datetime  # Explicit finite lease; no perpetual admin-issued access.
    reason: str = Field(min_length=10, max_length=1000)


class RevokeGrant(BaseModel):
    event_id: UUID
    reason: str = Field(min_length=10, max_length=1000)


def _ensure_enabled(user: UserSchema) -> tuple[str, int]:
    if os.getenv("SCOUT_MEDIA_GRANTS_ADMIN_ENABLED", "0").strip().lower() not in _ENABLED:
        raise HTTPException(404, "scout_photo_grants_admin_disabled")
    # Extra restriction: only this tenant's actual owner, never a generic
    # platform_admin, manager or background service, may administer the grants.
    role = getattr(user.role, "value", user.role)
    if role != "owner":
        raise HTTPException(403, "scout_photo_grants_owner_required")
    try:
        tenant = str(UUID(str(user.tenant_id)))
        actor_id = int(user.user_id)
        if actor_id <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(403, "scout_photo_grants_invalid_actor") from None
    return tenant, actor_id


@asynccontextmanager
async def _admin_transaction(tenant: str, actor: int):
    dsn = os.getenv("SCOUT_GRANT_ADMIN_DATABASE_URL", "")
    if not dsn:
        raise HTTPException(503, "scout_photo_grants_admin_db_unconfigured")
    conn = None
    try:
        import asyncpg

        # Dedicated connection, never the application pool, jobs pool, or the
        # migrator's superuser. Do not log connection strings or errors.
        conn = await asyncpg.connect(dsn, statement_cache_size=0, timeout=5)
        role = await conn.fetchrow(
            "SELECT current_user AS role_name, rolsuper, rolbypassrls, rolcanlogin "
            "FROM pg_roles WHERE rolname=current_user"
        )
        if (not role or role["role_name"] != _ADMIN_ROLE or
                role["rolsuper"] or role["rolbypassrls"] or not role["rolcanlogin"]):
            raise HTTPException(503, "scout_photo_grants_unsafe_db_role")
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant',$1,true), "
                "set_config('app.current_user_id',$2,true), "
                "set_config('app.current_role','owner',true)",
                tenant, str(actor),
            )
            owner_active = await conn.fetchval(
                "SELECT true FROM users WHERE tenant_id=$1::uuid AND id=$2 "
                "AND active IS TRUE AND lower(role)='owner'", tenant, actor,
            )
            if not owner_active:
                raise HTTPException(403, "scout_photo_grants_owner_inactive_or_changed")
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        # SQLSTATE 23505 = duplicated active grant; authorization failures or
        # missing schema must NOT become false successes.
        if getattr(exc, "sqlstate", None) in ("23505", "23503", "23514"):
            raise HTTPException(409, "scout_photo_grant_conflict") from None
        raise HTTPException(503, "scout_photo_grants_database_unavailable") from None
    finally:
        if conn is not None:
            await conn.close()


def _request_hash(action: str, tenant: str, field_id: str, actor: int, **payload) -> str:
    data = {"action": action, "tenant": tenant, "field": field_id, "actor": actor, **payload}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


async def _record_event(conn, *, event_id: UUID, tenant: str, field_id: str,
                        grant_id: UUID, actor: int, target: int, scope: str,
                        action: str, digest: str, reason: str) -> bool:
    """Atomic audit-first idempotency fence: one event ID = one immutable command.

    Concurrent identical requests block on the unique event_id key. Their
    replay reads the committed audit row; altered payload or another tenant
    is never allowed to borrow the same event ID.
    """
    inserted = await conn.fetchval(
        "INSERT INTO scout_photo_grant_audit_events "
        "(event_id,tenant_id,field_id,grant_id,actor_user_id,target_user_id,scope,action,request_sha256,reason) "
        "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10) "
        "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
        event_id, tenant, field_id, grant_id, actor, target, scope, action, digest, reason,
    )
    if inserted:
        return False
    existing = await conn.fetchrow(
        "SELECT grant_id, actor_user_id, target_user_id, scope, action, request_sha256 "
        "FROM scout_photo_grant_audit_events "
        "WHERE event_id=$1 AND tenant_id=$2::uuid AND field_id=$3",
        event_id, tenant, field_id,
    )
    if (existing is None or existing["actor_user_id"] != actor or
            existing["target_user_id"] != target or existing["scope"] != scope or
            existing["action"] != action or existing["request_sha256"] != digest):
        raise HTTPException(409, "scout_photo_grant_event_id_reused")
    return True


def _expiry_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(422, "scout_photo_grant_expiry_requires_timezone")
    utc = value.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if utc <= now or utc > now + timedelta(days=90):
        raise HTTPException(422, "scout_photo_grant_expiry_must_be_within_90_days")
    return utc.isoformat()


@router.post("/api/v1/admin/fields/{field_id}/scouting-media-grants", status_code=201)
async def issue_scout_photo_grant(
    field_id: str, req: IssueGrant,
    user: UserSchema = Depends(require_permission(Permission.USER_CHANGE_ROLE)),
):
    tenant, actor = _ensure_enabled(user)
    if req.user_id == actor:
        raise HTTPException(403, "scout_photo_grants_self_issue_forbidden")
    if not field_id or len(field_id) > 50 or field_id.strip() != field_id:
        raise HTTPException(422, "scout_photo_grants_invalid_field")
    expiry = _expiry_text(req.expires_at)
    reason = req.reason.strip()
    if len(reason) < 10:
        raise HTTPException(422, "scout_photo_grants_reason_required")
    digest = _request_hash(
        "issue", tenant, field_id, actor, target=req.user_id,
        scope=req.scope, expires_at=expiry, reason=reason,
    )
    new_grant = uuid4()
    async with _admin_transaction(tenant, actor) as conn:
        # The target must still be active; field + user are both in the owner's
        # tenant. A request cannot bootstrap a grant to a missing field/user.
        target = await conn.fetchrow(
            "SELECT u.id,u.role FROM users u WHERE u.id=$1 AND u.tenant_id=$2::uuid "
            "AND u.active IS TRUE", req.user_id, tenant,
        )
        field_exists = await conn.fetchval(
            "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2", tenant, field_id,
        )
        if not target or not field_exists:
            raise HTTPException(404, "scout_photo_grants_field_or_user_not_found")
        role = str(target["role"]).lower()
        permitted_roles = {
            "photo.read": {"owner", "manager", "agronomist", "expert", "farmer", "worker", "viewer", "admin"},
            "photo.upload": {"owner", "manager", "agronomist", "expert", "farmer", "worker"},
            "photo.context": {"owner", "manager", "agronomist", "expert", "farmer", "admin"},
            "photo.season_link": {"owner", "manager", "agronomist", "expert", "admin"},
            "photo.detection_link": {"owner", "manager", "agronomist", "expert", "admin"},
        }
        if role not in permitted_roles[req.scope]:
            raise HTTPException(403, "scout_photo_grants_target_role_incompatible")
        replay = await _record_event(
            conn, event_id=req.event_id, tenant=tenant, field_id=field_id,
            grant_id=new_grant, actor=actor, target=req.user_id, scope=req.scope,
            action="issue", digest=digest, reason=reason,
        )
        if replay:
            previous = await conn.fetchrow(
                "SELECT grant_id,expires_at FROM scout_photo_field_access_grants "
                "WHERE tenant_id=$1::uuid AND field_id=$2 AND user_id=$3 AND scope=$4 "
                "AND grant_id=(SELECT grant_id FROM scout_photo_grant_audit_events WHERE event_id=$5)",
                tenant, field_id, req.user_id, req.scope, req.event_id,
            )
            if previous is None:
                raise HTTPException(503, "scout_photo_grant_receipt_missing")
            return {"grant_id": str(previous["grant_id"]), "event_id": str(req.event_id),
                    "scope": req.scope, "idempotent": True, "status": "recorded"}
        await conn.execute(
            "INSERT INTO scout_photo_field_access_grants "
            "(grant_id,tenant_id,field_id,user_id,scope,granted_by,expires_at) "
            "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7::timestamptz)",
            new_grant, tenant, field_id, req.user_id, req.scope, actor, expiry,
        )
    return {"grant_id": str(new_grant), "event_id": str(req.event_id),
            "scope": req.scope, "idempotent": False, "status": "recorded"}


@router.post("/api/v1/admin/fields/{field_id}/scouting-media-grants/{grant_id}/revoke")
async def revoke_scout_photo_grant(
    field_id: str, grant_id: UUID, req: RevokeGrant,
    user: UserSchema = Depends(require_permission(Permission.USER_CHANGE_ROLE)),
):
    tenant, actor = _ensure_enabled(user)
    reason = req.reason.strip()
    if len(reason) < 10:
        raise HTTPException(422, "scout_photo_grants_reason_required")
    async with _admin_transaction(tenant, actor) as conn:
        grant = await conn.fetchrow(
            "SELECT grant_id,user_id,scope,revoked_at FROM scout_photo_field_access_grants "
            "WHERE tenant_id=$1::uuid AND field_id=$2 AND grant_id=$3 FOR UPDATE",
            tenant, field_id, grant_id,
        )
        if grant is None:
            raise HTTPException(404, "scout_photo_grant_not_found")
        digest = _request_hash(
            "revoke", tenant, field_id, actor, grant_id=str(grant_id),
            target=grant["user_id"], scope=grant["scope"], reason=reason,
        )
        replay = await _record_event(
            conn, event_id=req.event_id, tenant=tenant, field_id=field_id,
            grant_id=grant_id, actor=actor, target=grant["user_id"], scope=grant["scope"],
            action="revoke", digest=digest, reason=reason,
        )
        if replay:
            if grant["revoked_at"] is None:
                raise HTTPException(503, "scout_photo_grant_revocation_receipt_missing")
            return {"grant_id": str(grant_id), "event_id": str(req.event_id),
                    "status": "revoked", "idempotent": True}
        if grant["revoked_at"] is not None:
            raise HTTPException(409, "scout_photo_grant_already_revoked")
        changed = await conn.fetchval(
            "UPDATE scout_photo_field_access_grants SET revoked_at=now(), "
            "revoked_by=$4, revocation_reason=$5 WHERE tenant_id=$1::uuid "
            "AND field_id=$2 AND grant_id=$3 AND revoked_at IS NULL RETURNING grant_id",
            tenant, field_id, grant_id, actor, reason,
        )
        if not changed:
            raise HTTPException(409, "scout_photo_grant_already_revoked")
    return {"grant_id": str(grant_id), "event_id": str(req.event_id),
            "status": "revoked", "idempotent": False}


@router.get("/api/v1/admin/fields/{field_id}/scouting-media-grants")
async def list_scout_photo_grants(
    field_id: str, limit: int = Query(default=50, ge=1, le=100),
    user: UserSchema = Depends(require_permission(Permission.USER_CHANGE_ROLE)),
):
    tenant, actor = _ensure_enabled(user)
    async with _admin_transaction(tenant, actor) as conn:
        field_exists = await conn.fetchval(
            "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2", tenant, field_id,
        )
        if not field_exists:
            raise HTTPException(404, "scout_photo_grants_field_not_found")
        grants = await conn.fetch(
            "SELECT grant_id,user_id,scope,granted_by,granted_at,expires_at,revoked_at,revoked_by "
            "FROM scout_photo_field_access_grants WHERE tenant_id=$1::uuid AND field_id=$2 "
            "ORDER BY granted_at DESC,grant_id LIMIT $3", tenant, field_id, limit,
        )
        events = await conn.fetch(
            "SELECT event_id,grant_id,actor_user_id,target_user_id,scope,action,recorded_at,reason "
            "FROM scout_photo_grant_audit_events WHERE tenant_id=$1::uuid AND field_id=$2 "
            "ORDER BY recorded_at DESC,event_id LIMIT $3", tenant, field_id, limit,
        )
    def _json_row(row):
        return {k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if isinstance(v, UUID) else v)
                for k,v in dict(row).items()}
    return {"field_id": field_id, "grants": [_json_row(r) for r in grants],
            "events": [_json_row(r) for r in events], "limit": limit}
