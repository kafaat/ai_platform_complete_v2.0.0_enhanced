"""Read-only retention projection for a scouting photo (owner phase 11, v272).

Policy and legal holds are append-only and written by the tenant owner through the admin API
(grants_admin_api.py). Nothing here deletes object-store bytes or immutable metadata, and a missing
policy is never a licence to purge. Behind SCOUT_MEDIA_RETENTION_ENABLED (default 0).
"""

from __future__ import annotations

import os
from datetime import UTC, timedelta

import media_api
from evidence_chain import ChainCodes, single_head
from fastapi import APIRouter, Header, HTTPException, Response

router = APIRouter()
_TRUE = {"1", "true", "on", "yes"}
RETENTION_ROLES = frozenset({"owner", "admin", "manager", "expert", "agronomist"})
_CODES = ChainCodes(
    reused="scout_retention_event_id_reused",
    predecessor="scout_retention_predecessor_conflict",
    concurrent="scout_retention_concurrent_conflict",
    unverified="scout_retention_receipt_unverified",
    ambiguous="scout_retention_chain_ambiguous",
)


def enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_RETENTION_ENABLED", "0").strip().lower() in _TRUE


def retention_view(policy, head, uploaded_at) -> dict:
    """The retention part of the context (pure)."""
    earliest = None
    if policy is not None and uploaded_at is not None:
        earliest = (
            uploaded_at.astimezone(UTC) + timedelta(days=policy["min_retention_days"])
        ).isoformat()
    return {
        "state": "policy_configured" if policy else "policy_missing_fail_closed",
        "policy_event_id": str(policy["event_id"]) if policy else None,
        "min_retention_days": policy["min_retention_days"] if policy else None,
        "earliest_disposition_review_at": earliest,
        "legal_hold": bool(head and head["action"] == "legal_hold"),
        "latest_event": head["action"] if head else None,
        "delete_authorized": False,
        "purge_job_scheduled": False,
        "physical_deletion_supported": False,
    }


async def current_retention_context(conn, tenant: str, field_id: str, pin_id: str) -> dict:
    if not enabled():
        return {"state": "disabled", "delete_authorized": False, "purge_job_scheduled": False}
    policy = single_head(
        await conn.fetch(
            "SELECT event_id, min_retention_days FROM scout_photo_retention_policy_events p "
            "WHERE p.tenant_id=$1::uuid AND NOT EXISTS (SELECT 1 FROM "
            "scout_photo_retention_policy_events n WHERE n.previous_event_id=p.event_id) LIMIT 2",
            tenant,
        ),
        _CODES,
    )
    head = single_head(
        await conn.fetch(
            "SELECT event_id, action FROM scout_photo_retention_events e "
            "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
            "AND NOT EXISTS (SELECT 1 FROM scout_photo_retention_events n "
            "WHERE n.previous_event_id=e.event_id) LIMIT 2",
            tenant,
            field_id,
            pin_id,
        ),
        _CODES,
    )
    uploaded = await conn.fetchval(
        "SELECT uploaded_at FROM scout_photo_evidence "
        "WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
        tenant,
        field_id,
        pin_id,
    )
    if uploaded is None:
        raise HTTPException(404, "scout_photo_not_found")
    return retention_view(policy, head, uploaded)


@router.get("/internal/scouting-media/fields/{field_id}/pins/{pin_id}/photo/retention")
async def get_evidence_retention(
    field_id: str,
    pin_id: str,
    response: Response,
    x_scout_media_token: str | None = Header(None, alias="X-Scout-Media-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
):
    tenant, actor = media_api.authorize(
        x_scout_media_token, x_tenant_id, x_user_id, x_user_role, write=False
    )
    if not enabled():
        raise HTTPException(404, "scout_retention_disabled")
    media_api.require_role(x_user_role, RETENTION_ROLES, "scout_retention_role_denied")
    media_api._require_valid_pin(pin_id)
    await media_api.require_media_field_scope(tenant, field_id, actor, "photo.context", x_user_role)
    try:
        await media_api._verified_photo(tenant, field_id, pin_id)
        conn = await media_api._tenant_connection(tenant)
        try:
            result = await current_retention_context(conn, tenant, field_id, pin_id)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise media_api._db_error() from exc
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return result
