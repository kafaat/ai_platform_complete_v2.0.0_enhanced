"""Tenant-owner administration of scout photo field grants and governance (owner phases 7 and 11).

Owner decision (2026-11-13): scout-ingest-service owns the grant, grant-audit, specialist-
credential and retention tables and serves their admin API; the delivery's platform routers
(scout_photo_grants.py, scout_photo_governance.py) are re-homed here. Public paths are
``/api/v1/scouting-media/admin/...`` through the existing nginx scout-ingest location.

Admin gate (the strongest one scout-ingest can verify; no platform_admin identity exists):
  1. SCOUT_MEDIA_GRANTS_ADMIN_ENABLED (default 0; governance routes also need
     SCOUT_MEDIA_GOVERNANCE_ADMIN_ENABLED) and the dedicated nginx-injected service token;
  2. the trusted identity nginx takes from the verified JWT: tenant UUID, users.id, and a role
     that is one of the platform's tenant-OWNER aliases ('owner', 'admin');
  3. in the same database transaction as the write, that user is ACTIVE in this tenant and its
     CURRENT users.role equals the trusted role (a demoted owner's old token is refused);
  4. the database principal is sahool_scout_grant_admin (SCOUT_GRANT_ADMIN_DATABASE_URL, never
     the ingest, app or jobs role): NOSUPERUSER, NOBYPASSRLS, verified on every connection.
So issuance is tenant-owner scoped. The v265 trigger refuses at COMMIT any grant or revocation
without its matching audit event, and any new grant without a finite lease of at most 90 days.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

from credential_status import SPECIALIST_ROLES, TENANT_OWNER_ROLES
from evidence_chain import (
    ChainCodes,
    append_event,
    guard_refusal,
    positive_user_id,
    same_previous,
    single_head,
)
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from shared.security.trusted_tenant import service_token_ok

router = APIRouter()
ADMIN_DB_ROLE = "sahool_scout_grant_admin"
_ENABLED = frozenset(("1", "true", "on", "yes"))
SCOPES = (
    "photo.read",
    "photo.upload",
    "photo.context",
    "photo.season_link",
    "photo.detection_link",
    "photo.lab_link",
    "photo.diagnosis_review",
    "photo.tissue_sample",
    "photo.treatment_review",
)
Scope = Literal[
    "photo.read",
    "photo.upload",
    "photo.context",
    "photo.season_link",
    "photo.detection_link",
    "photo.lab_link",
    "photo.diagnosis_review",
    "photo.tissue_sample",
    "photo.treatment_review",
]
# Which users.role may receive which scope (as delivered). A grant never exceeds what the role's
# route gate accepts; diagnosis/treatment review stay with specialists.
SCOPE_TARGET_ROLES: dict[str, frozenset[str]] = {
    "photo.read": frozenset(
        {"owner", "manager", "agronomist", "expert", "farmer", "worker", "viewer", "admin"}
    ),
    "photo.upload": frozenset({"owner", "manager", "agronomist", "expert", "farmer", "worker"}),
    "photo.context": frozenset({"owner", "manager", "agronomist", "expert", "farmer", "admin"}),
    "photo.season_link": frozenset({"owner", "manager", "agronomist", "expert", "admin"}),
    "photo.detection_link": frozenset({"owner", "manager", "agronomist", "expert", "admin"}),
    "photo.lab_link": frozenset({"owner", "manager", "agronomist", "expert", "admin"}),
    "photo.diagnosis_review": SPECIALIST_ROLES,
    "photo.tissue_sample": frozenset({"agronomist", "expert", "manager", "worker"}),
    "photo.treatment_review": SPECIALIST_ROLES,
}
MAX_LEASE = timedelta(days=90)
MAX_CREDENTIAL = timedelta(days=1095)


class IssueGrant(BaseModel):
    event_id: UUID
    user_id: int = Field(gt=0)
    scope: Scope
    expires_at: datetime  # an explicit finite lease; no perpetual access
    reason: str = Field(min_length=10, max_length=1000)


class RevokeGrant(BaseModel):
    event_id: UUID
    reason: str = Field(min_length=10, max_length=1000)


class CredentialIn(BaseModel):
    event_id: UUID
    subject_user_id: int = Field(gt=0)
    discipline: Literal["plant_pathology", "crop_protection", "agronomy"]
    action: Literal["attest_registry_check", "revoke"]
    previous_event_id: UUID | None = None
    issuer_code: str | None = Field(None, min_length=2, max_length=100)
    jurisdiction: str | None = Field(None, min_length=2, max_length=100)
    license_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    registry_check_ref: str | None = Field(None, min_length=12, max_length=300)
    expires_at: datetime | None = None
    reason: str = Field(min_length=20, max_length=2000)


class RetentionPolicyIn(BaseModel):
    event_id: UUID
    previous_event_id: UUID | None = None
    min_retention_days: int = Field(ge=365, le=3650)
    reason: str = Field(min_length=20, max_length=2000)


class RetentionEventIn(BaseModel):
    event_id: UUID
    action: Literal["legal_hold", "release_hold", "request_disposition", "deny_disposition"]
    previous_event_id: UUID | None = None
    reason: str = Field(min_length=20, max_length=2000)


# ─── pure rules ─────────────────────────────────────────────────────────────


def admin_identity(
    token: str | None,
    tenant: str | None,
    uid: str | None,
    role: str | None,
    *,
    governance: bool = False,
) -> tuple[str, int, str]:
    """Flags, service token, trusted tenant/user, tenant-owner role. ``(tenant, actor, role)``."""
    if os.getenv("SCOUT_MEDIA_GRANTS_ADMIN_ENABLED", "0").strip().lower() not in _ENABLED:
        raise HTTPException(404, "scout_photo_grants_admin_disabled")
    if (
        governance
        and os.getenv("SCOUT_MEDIA_GOVERNANCE_ADMIN_ENABLED", "0").strip().lower() not in _ENABLED
    ):
        raise HTTPException(404, "scout_governance_admin_disabled")
    expected = os.getenv("SCOUT_MEDIA_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(503, "scout_media_token_unconfigured")
    if not service_token_ok(token, expected):
        raise HTTPException(401, "scout_media_token_required")
    try:
        tenant_id = str(UUID(str(tenant)))
    except (TypeError, ValueError):
        raise HTTPException(403, "invalid_trusted_tenant") from None
    actor = positive_user_id((uid or "").strip(), "scout_photo_grants_invalid_actor")
    claim = (role or "").strip().lower()
    if claim not in TENANT_OWNER_ROLES:
        raise HTTPException(403, "scout_photo_grants_owner_required")
    return tenant_id, actor, claim


def lease_expiry(value: datetime, now: datetime) -> str:
    """UTC ISO text of a timezone-aware expiry within (now, now + 90 days]."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(422, "scout_photo_grant_expiry_requires_timezone")
    utc = value.astimezone(UTC)
    if utc <= now or utc > now + MAX_LEASE:
        raise HTTPException(422, "scout_photo_grant_expiry_must_be_within_90_days")
    return utc.isoformat()


def valid_field_id(field_id: str) -> str:
    if not field_id or len(field_id) > 50 or field_id.strip() != field_id:
        raise HTTPException(422, "scout_photo_grants_invalid_field")
    return field_id


def request_hash(action: str, tenant: str, field_id: str, actor: int, **payload) -> str:
    data = {"action": action, "tenant": tenant, "field": field_id, "actor": actor, **payload}
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


def reason_text(value: str, minimum: int, code: str) -> str:
    text = value.strip()
    if not (minimum <= len(text) <= 2000):
        raise HTTPException(422, code)
    return text


def credential_refusal(data: CredentialIn, now: datetime) -> tuple[str | None, str | None]:
    """``(code, expiry_iso)``; code set for a malformed attestation or revocation (422)."""
    if data.previous_event_id is not None and data.previous_event_id == data.event_id:
        return "scout_governance_self_reference", None
    if data.action == "revoke":
        proof = (
            data.issuer_code,
            data.jurisdiction,
            data.license_sha256,
            data.registry_check_ref,
            data.expires_at,
        )
        if data.previous_event_id is None or any(x is not None for x in proof):
            return "scout_credentials_invalid_revoke", None
        return None, None
    texts = (data.issuer_code, data.jurisdiction, data.registry_check_ref)
    if any(not x or x != x.strip() for x in texts):
        return "scout_credentials_manual_check_proof_required", None
    if not data.license_sha256:
        return "scout_credentials_license_digest_required", None
    expiry = data.expires_at
    if expiry is None or expiry.tzinfo is None or expiry.utcoffset() is None:
        return "scout_credentials_expiry_timezone_required", None
    utc = expiry.astimezone(UTC)
    if not now < utc <= now + MAX_CREDENTIAL:
        return "scout_credentials_expiry_out_of_range", None
    return None, utc.isoformat()


# ─── the admin transaction ──────────────────────────────────────────────────


@asynccontextmanager
async def admin_transaction(tenant: str, actor: int, claim: str):
    """A transaction on the dedicated admin principal, after the live tenant-owner check."""
    dsn = os.getenv("SCOUT_GRANT_ADMIN_DATABASE_URL", "")
    if not dsn:
        raise HTTPException(503, "scout_photo_grants_admin_db_unconfigured")
    conn = None
    try:
        import asyncpg

        conn = await asyncpg.connect(dsn, statement_cache_size=0, timeout=5)
        role = await conn.fetchrow(
            "SELECT current_user AS role_name, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        )
        if (
            not role
            or role["role_name"] != ADMIN_DB_ROLE
            or role["rolsuper"]
            or role["rolbypassrls"]
        ):
            raise HTTPException(503, "scout_photo_grants_unsafe_db_role")
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant',$1,true), "
                "set_config('app.current_user_id',$2,true)",
                tenant,
                str(actor),
            )
            owner_active = await conn.fetchval(
                "SELECT true FROM users WHERE tenant_id=$1::uuid AND id=$2 AND active IS TRUE "
                "AND lower(role::text)=$3",
                tenant,
                actor,
                claim,
            )
            if not owner_active:
                raise HTTPException(403, "scout_photo_grants_owner_inactive_or_changed")
            yield conn
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — never a false success, never a leaked DSN
        if guard_refusal(exc):
            raise HTTPException(403, str(exc).split()[0]) from None
        if getattr(exc, "sqlstate", None) == "23514" and str(exc).startswith("scout_"):
            raise HTTPException(409, str(exc).split()[0]) from None  # a v265/v270/v272 rule
        if getattr(exc, "sqlstate", None) in ("23505", "23503", "23514"):
            raise HTTPException(409, "scout_photo_grant_conflict") from None
        raise HTTPException(503, "scout_photo_grants_database_unavailable") from None
    finally:
        if conn is not None:
            await conn.close()


async def _record_audit(
    conn, *, event_id, tenant, field_id, grant_id, actor, target, scope, action, digest, reason
) -> bool:
    """Audit first, as the idempotency fence: ``True`` when this event id was already recorded.

    Concurrent identical requests block on the event_id key; a replay with another payload, or
    another field, never borrows the id.
    """
    inserted = await conn.fetchval(
        "INSERT INTO scout_photo_grant_audit_events "
        "(event_id,tenant_id,field_id,grant_id,actor_user_id,target_user_id,scope,action,"
        "request_sha256,reason) VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10) "
        "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
        event_id,
        tenant,
        field_id,
        grant_id,
        actor,
        target,
        scope,
        action,
        digest,
        reason,
    )
    if inserted:
        return False
    existing = await conn.fetchrow(
        "SELECT actor_user_id, target_user_id, scope, action, request_sha256 "
        "FROM scout_photo_grant_audit_events WHERE event_id=$1 AND tenant_id=$2::uuid "
        "AND field_id=$3",
        event_id,
        tenant,
        field_id,
    )
    if (
        existing is None
        or existing["actor_user_id"] != actor
        or existing["target_user_id"] != target
        or existing["scope"] != scope
        or existing["action"] != action
        or existing["request_sha256"] != digest
    ):
        raise HTTPException(409, "scout_photo_grant_event_id_reused")
    return True


def _json_row(row) -> dict:
    out = {}
    for key, value in dict(row).items():
        if isinstance(value, UUID):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        out[key] = value
    return out


_IDENTITY = {
    "token": Header(None, alias="X-Scout-Media-Token"),
    "tenant": Header(None, alias="X-Tenant-Id"),
    "uid": Header(None, alias="X-User-Id"),
    "role": Header(None, alias="X-User-Role"),
}


# ─── field grants (phase 7) ─────────────────────────────────────────────────


@router.post("/internal/scouting-media/admin/fields/{field_id}/grants", status_code=201)
async def issue_scout_photo_grant(
    field_id: str,
    req: IssueGrant,
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    tenant, actor, claim = admin_identity(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    if req.user_id == actor:
        raise HTTPException(403, "scout_photo_grants_self_issue_forbidden")
    valid_field_id(field_id)
    expiry = lease_expiry(req.expires_at, datetime.now(UTC))
    reason = reason_text(req.reason, 10, "scout_photo_grants_reason_required")
    digest = request_hash(
        "issue",
        tenant,
        field_id,
        actor,
        target=req.user_id,
        scope=req.scope,
        expires_at=expiry,
        reason=reason,
    )
    new_grant = uuid4()
    async with admin_transaction(tenant, actor, claim) as conn:
        target = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id=$1 AND tenant_id=$2::uuid AND active IS TRUE",
            req.user_id,
            tenant,
        )
        field_exists = await conn.fetchval(
            "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2", tenant, field_id
        )
        if not target or not field_exists:
            raise HTTPException(404, "scout_photo_grants_field_or_user_not_found")
        if str(target["role"]).lower() not in SCOPE_TARGET_ROLES[req.scope]:
            raise HTTPException(403, "scout_photo_grants_target_role_incompatible")
        replay = await _record_audit(
            conn,
            event_id=req.event_id,
            tenant=tenant,
            field_id=field_id,
            grant_id=new_grant,
            actor=actor,
            target=req.user_id,
            scope=req.scope,
            action="issue",
            digest=digest,
            reason=reason,
        )
        if replay:
            previous = await conn.fetchval(
                "SELECT g.grant_id FROM scout_photo_field_access_grants g "
                "JOIN scout_photo_grant_audit_events e ON e.grant_id=g.grant_id "
                "WHERE e.event_id=$1 AND g.tenant_id=$2::uuid AND g.field_id=$3",
                req.event_id,
                tenant,
                field_id,
            )
            if previous is None:
                raise HTTPException(503, "scout_photo_grant_receipt_missing")
            return {
                "grant_id": str(previous),
                "event_id": str(req.event_id),
                "scope": req.scope,
                "idempotent": True,
                "status": "recorded",
            }
        await conn.execute(
            "INSERT INTO scout_photo_field_access_grants "
            "(grant_id,tenant_id,field_id,user_id,scope,granted_by,expires_at) "
            "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7::timestamptz)",
            new_grant,
            tenant,
            field_id,
            req.user_id,
            req.scope,
            actor,
            datetime.fromisoformat(expiry),
        )
    return {
        "grant_id": str(new_grant),
        "event_id": str(req.event_id),
        "scope": req.scope,
        "idempotent": False,
        "status": "recorded",
    }


@router.post("/internal/scouting-media/admin/fields/{field_id}/grants/{grant_id}/revoke")
async def revoke_scout_photo_grant(
    field_id: str,
    grant_id: UUID,
    req: RevokeGrant,
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    tenant, actor, claim = admin_identity(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    valid_field_id(field_id)
    reason = reason_text(req.reason, 10, "scout_photo_grants_reason_required")
    async with admin_transaction(tenant, actor, claim) as conn:
        grant = await conn.fetchrow(
            "SELECT grant_id, user_id, scope, revoked_at FROM scout_photo_field_access_grants "
            "WHERE tenant_id=$1::uuid AND field_id=$2 AND grant_id=$3 FOR UPDATE",
            tenant,
            field_id,
            grant_id,
        )
        if grant is None:
            raise HTTPException(404, "scout_photo_grant_not_found")
        digest = request_hash(
            "revoke",
            tenant,
            field_id,
            actor,
            grant_id=str(grant_id),
            target=grant["user_id"],
            scope=grant["scope"],
            reason=reason,
        )
        replay = await _record_audit(
            conn,
            event_id=req.event_id,
            tenant=tenant,
            field_id=field_id,
            grant_id=grant_id,
            actor=actor,
            target=grant["user_id"],
            scope=grant["scope"],
            action="revoke",
            digest=digest,
            reason=reason,
        )
        if replay:
            if grant["revoked_at"] is None:
                raise HTTPException(503, "scout_photo_grant_revocation_receipt_missing")
            return {
                "grant_id": str(grant_id),
                "event_id": str(req.event_id),
                "status": "revoked",
                "idempotent": True,
            }
        if grant["revoked_at"] is not None:
            raise HTTPException(409, "scout_photo_grant_already_revoked")
        changed = await conn.fetchval(
            "UPDATE scout_photo_field_access_grants SET revoked_at=now(), revoked_by=$4, "
            "revocation_reason=$5 WHERE tenant_id=$1::uuid AND field_id=$2 AND grant_id=$3 "
            "AND revoked_at IS NULL RETURNING grant_id",
            tenant,
            field_id,
            grant_id,
            actor,
            reason,
        )
        if not changed:
            raise HTTPException(409, "scout_photo_grant_already_revoked")
    return {
        "grant_id": str(grant_id),
        "event_id": str(req.event_id),
        "status": "revoked",
        "idempotent": False,
    }


@router.get("/internal/scouting-media/admin/fields/{field_id}/grants")
async def list_scout_photo_grants(
    field_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    tenant, actor, claim = admin_identity(x_scout_media_token, x_tenant_id, x_user_id, x_user_role)
    valid_field_id(field_id)
    async with admin_transaction(tenant, actor, claim) as conn:
        if not await conn.fetchval(
            "SELECT true FROM fields WHERE tenant_id=$1::uuid AND field_id=$2", tenant, field_id
        ):
            raise HTTPException(404, "scout_photo_grants_field_not_found")
        grants = await conn.fetch(
            "SELECT grant_id, user_id, scope, granted_by, granted_at, expires_at, revoked_at, "
            "revoked_by FROM scout_photo_field_access_grants WHERE tenant_id=$1::uuid "
            "AND field_id=$2 ORDER BY granted_at DESC, grant_id LIMIT $3",
            tenant,
            field_id,
            limit,
        )
        events = await conn.fetch(
            "SELECT event_id, grant_id, actor_user_id, target_user_id, scope, action, "
            "recorded_at, reason FROM scout_photo_grant_audit_events WHERE tenant_id=$1::uuid "
            "AND field_id=$2 ORDER BY recorded_at DESC, event_id LIMIT $3",
            tenant,
            field_id,
            limit,
        )
    return {
        "field_id": field_id,
        "grants": [_json_row(r) for r in grants],
        "events": [_json_row(r) for r in events],
        "limit": limit,
    }


# ─── governance: specialist credentials and retention (phase 11) ────────────

_CREDENTIAL_CODES = ChainCodes(
    reused="scout_credentials_event_id_reused",
    predecessor="scout_credentials_predecessor_conflict",
    concurrent="scout_credentials_concurrent_conflict",
    unverified="scout_credentials_receipt_unverified",
    ambiguous="scout_credentials_chain_ambiguous",
)
_POLICY_CODES = ChainCodes(
    reused="scout_retention_policy_event_id_reused",
    predecessor="scout_retention_policy_predecessor_conflict",
    concurrent="scout_retention_policy_concurrent_conflict",
    unverified="scout_retention_policy_receipt_unverified",
    ambiguous="scout_retention_policy_chain_ambiguous",
)
_RETENTION_CODES = ChainCodes(
    reused="scout_retention_event_id_reused",
    predecessor="scout_retention_predecessor_conflict",
    concurrent="scout_retention_concurrent_conflict",
    unverified="scout_retention_receipt_unverified",
    ambiguous="scout_retention_chain_ambiguous",
)


def _iso(value) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


@router.post("/internal/scouting-media/admin/credential-events")
async def post_credential_event(
    data: CredentialIn,
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    """The owner records a MANUAL issuer-registry check (no issuer API); never self-attested."""
    tenant, actor, claim = admin_identity(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, governance=True
    )
    if data.subject_user_id == actor:
        raise HTTPException(403, "scout_credentials_self_attestation_denied")
    code, expiry = credential_refusal(data, datetime.now(UTC))
    if code:
        raise HTTPException(422, code)
    reason = reason_text(data.reason, 20, "scout_governance_reason_required")
    async with admin_transaction(tenant, actor, claim) as conn:
        if not await conn.fetchval(
            "SELECT true FROM users WHERE tenant_id=$1::uuid AND id=$2 AND active IS TRUE "
            "AND lower(role::text) IN ('expert','agronomist')",
            tenant,
            data.subject_user_id,
        ):
            raise HTTPException(404, "scout_credentials_subject_ineligible")

        async def read_head():
            rows = await conn.fetch(
                "SELECT event_id FROM scout_specialist_credential_events e "
                "WHERE e.tenant_id=$1::uuid AND e.subject_user_id=$2 AND e.discipline=$3 "
                "AND NOT EXISTS (SELECT 1 FROM scout_specialist_credential_events n "
                "WHERE n.previous_event_id=e.event_id) LIMIT 2",
                tenant,
                data.subject_user_id,
                data.discipline,
            )
            return single_head(rows, _CREDENTIAL_CODES)

        idempotent, _ = await append_event(
            event_id=data.event_id,
            previous_event_id=data.previous_event_id,
            load_existing=lambda: conn.fetchrow(
                "SELECT action, previous_event_id, actor_user_id, discipline, issuer_code, "
                "jurisdiction, license_sha256, registry_check_ref, expires_at, reason "
                "FROM scout_specialist_credential_events WHERE tenant_id=$1::uuid "
                "AND event_id=$2 AND subject_user_id=$3",
                tenant,
                data.event_id,
                data.subject_user_id,
            ),
            matches=lambda old: (
                old["action"] == data.action
                and old["actor_user_id"] == actor
                and old["discipline"] == data.discipline
                and old["reason"] == reason
                and same_previous(old["previous_event_id"], data.previous_event_id)
                and old["issuer_code"] == data.issuer_code
                and old["jurisdiction"] == data.jurisdiction
                and (str(old["license_sha256"]).strip() if old["license_sha256"] else None)
                == data.license_sha256
                and old["registry_check_ref"] == data.registry_check_ref
                and _iso(old["expires_at"]) == expiry
            ),
            read_head=read_head,
            insert=lambda: conn.fetchval(
                "INSERT INTO scout_specialist_credential_events "
                "(event_id,tenant_id,subject_user_id,actor_user_id,action,discipline,issuer_code,"
                "jurisdiction,license_sha256,registry_check_ref,expires_at,previous_event_id,"
                "reason) VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11::timestamptz,$12,$13) "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                data.event_id,
                tenant,
                data.subject_user_id,
                actor,
                data.action,
                data.discipline,
                data.issuer_code,
                data.jurisdiction,
                data.license_sha256,
                data.registry_check_ref,
                datetime.fromisoformat(expiry) if expiry else None,
                data.previous_event_id,
                reason,
            ),
            codes=_CREDENTIAL_CODES,
            head_required=data.action == "revoke",
        )
    return {
        "event_id": str(data.event_id),
        "persisted": True,
        "idempotent": idempotent,
        "proof_level": "owner_attested_manual_registry_check",
        "issuer_connection_verified": False,
        "pesticide_application_authorized": False,
    }


@router.post("/internal/scouting-media/admin/retention-policy-events")
async def post_retention_policy(
    data: RetentionPolicyIn,
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    """The tenant's minimum retention; it can be raised, never lowered (v272)."""
    tenant, actor, claim = admin_identity(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, governance=True
    )
    reason = reason_text(data.reason, 20, "scout_governance_reason_required")
    if data.previous_event_id is not None and data.event_id == data.previous_event_id:
        raise HTTPException(422, "scout_governance_self_reference")
    async with admin_transaction(tenant, actor, claim) as conn:

        async def read_head():
            rows = await conn.fetch(
                "SELECT event_id, min_retention_days FROM scout_photo_retention_policy_events p "
                "WHERE p.tenant_id=$1::uuid AND NOT EXISTS (SELECT 1 FROM "
                "scout_photo_retention_policy_events n WHERE n.previous_event_id=p.event_id) "
                "LIMIT 2",
                tenant,
            )
            return single_head(rows, _POLICY_CODES)

        def head_allows(head) -> None:
            if head is not None and data.min_retention_days < head["min_retention_days"]:
                raise HTTPException(422, "scout_retention_minimum_cannot_decrease")

        idempotent, _ = await append_event(
            event_id=data.event_id,
            previous_event_id=data.previous_event_id,
            load_existing=lambda: conn.fetchrow(
                "SELECT previous_event_id, actor_user_id, reason, min_retention_days "
                "FROM scout_photo_retention_policy_events WHERE tenant_id=$1::uuid "
                "AND event_id=$2",
                tenant,
                data.event_id,
            ),
            matches=lambda old: (
                old["actor_user_id"] == actor
                and old["reason"] == reason
                and old["min_retention_days"] == data.min_retention_days
                and same_previous(old["previous_event_id"], data.previous_event_id)
            ),
            read_head=read_head,
            insert=lambda: conn.fetchval(
                "INSERT INTO scout_photo_retention_policy_events "
                "(event_id,tenant_id,previous_event_id,min_retention_days,actor_user_id,reason) "
                "VALUES ($1,$2::uuid,$3,$4,$5,$6) ON CONFLICT DO NOTHING RETURNING event_id",
                data.event_id,
                tenant,
                data.previous_event_id,
                data.min_retention_days,
                actor,
                reason,
            ),
            codes=_POLICY_CODES,
            head_allows=head_allows,
        )
    return {
        "event_id": str(data.event_id),
        "persisted": True,
        "idempotent": idempotent,
        "min_retention_days": data.min_retention_days,
        "delete_authorized": False,
    }


@router.post("/internal/scouting-media/admin/fields/{field_id}/pins/{pin_id}/retention-events")
async def post_retention_event(
    field_id: str,
    pin_id: str,
    data: RetentionEventIn,
    x_scout_media_token: str | None = _IDENTITY["token"],
    x_tenant_id: str | None = _IDENTITY["tenant"],
    x_user_id: str | None = _IDENTITY["uid"],
    x_user_role: str | None = _IDENTITY["role"],
):
    """Legal hold / release / disposition request and denial; no physical deletion exists."""
    tenant, actor, claim = admin_identity(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, governance=True
    )
    valid_field_id(field_id)
    reason = reason_text(data.reason, 20, "scout_governance_reason_required")
    if data.previous_event_id is not None and data.event_id == data.previous_event_id:
        raise HTTPException(422, "scout_governance_self_reference")
    async with admin_transaction(tenant, actor, claim) as conn:
        if not await conn.fetchval(
            "SELECT true FROM scout_photo_evidence WHERE tenant_id=$1::uuid AND field_id=$2 "
            "AND pin_id=$3",
            tenant,
            field_id,
            pin_id,
        ):
            raise HTTPException(404, "scout_retention_photo_not_found")

        async def read_head():
            rows = await conn.fetch(
                "SELECT event_id, action FROM scout_photo_retention_events e "
                "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
                "AND NOT EXISTS (SELECT 1 FROM scout_photo_retention_events n "
                "WHERE n.previous_event_id=e.event_id) LIMIT 2",
                tenant,
                field_id,
                pin_id,
            )
            return single_head(rows, _RETENTION_CODES)

        idempotent, _ = await append_event(
            event_id=data.event_id,
            previous_event_id=data.previous_event_id,
            load_existing=lambda: conn.fetchrow(
                "SELECT action, previous_event_id, actor_user_id, reason "
                "FROM scout_photo_retention_events WHERE event_id=$1 AND tenant_id=$2::uuid "
                "AND field_id=$3 AND pin_id=$4",
                data.event_id,
                tenant,
                field_id,
                pin_id,
            ),
            matches=lambda old: (
                old["actor_user_id"] == actor
                and old["reason"] == reason
                and old["action"] == data.action
                and same_previous(old["previous_event_id"], data.previous_event_id)
            ),
            read_head=read_head,
            insert=lambda: conn.fetchval(
                "INSERT INTO scout_photo_retention_events "
                "(event_id,tenant_id,field_id,pin_id,action,previous_event_id,actor_user_id,"
                "reason) VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8) "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                data.event_id,
                tenant,
                field_id,
                pin_id,
                data.action,
                data.previous_event_id,
                actor,
                reason,
            ),
            codes=_RETENTION_CODES,
        )
    return {
        "event_id": str(data.event_id),
        "persisted": True,
        "idempotent": idempotent,
        "delete_authorized": False,
        "object_store_deleted": False,
    }
