"""Live, tenant-scoped status of an owner-attested specialist credential (owner phase 11, v270).

The attestation is the tenant owner's record of a MANUAL issuer-registry check; no issuer API is
called and none is claimed (``issuer_connection_verified`` is always False). Behind
SCOUT_MEDIA_CREDENTIAL_ENFORCEMENT_ENABLED (default 0).
"""

from __future__ import annotations

import os

from evidence_chain import ChainCodes, single_head

# The platform's OWNER aliases (services/sahool-platform/api/main.py:_ROLE_ALIASES).
TENANT_OWNER_ROLES = frozenset({"owner", "admin"})
SPECIALIST_ROLES = frozenset({"expert", "agronomist"})
REVIEW_DISCIPLINES = ("plant_pathology", "agronomy")
_TRUE = {"1", "true", "on", "yes"}
_CODES = ChainCodes(
    reused="scout_credentials_event_id_reused",
    predecessor="scout_credentials_predecessor_conflict",
    concurrent="scout_credentials_concurrent_conflict",
    unverified="scout_credentials_receipt_unverified",
    ambiguous="scout_credentials_chain_ambiguous",
)


def enabled() -> bool:
    return os.getenv("SCOUT_MEDIA_CREDENTIAL_ENFORCEMENT_ENABLED", "0").strip().lower() in _TRUE


def _disabled() -> dict:
    return {
        "state": "not_checked_feature_disabled",
        "owner_registry_check_recorded": False,
        "issuer_connection_verified": False,
    }


def credential_state(row, *, unexpired: bool) -> dict:
    """The status of a chain head (pure): current only while every party still qualifies."""
    if row is None:
        return {
            "state": "no_attestation",
            "owner_registry_check_recorded": False,
            "issuer_connection_verified": False,
        }
    valid = (
        row["action"] == "attest_registry_check"
        and unexpired
        and row["subject_active"] is True
        and row["attester_active"] is True
        and str(row["subject_role"]).lower() in SPECIALIST_ROLES
        and str(row["attester_role"]).lower() in TENANT_OWNER_ROLES
    )
    return {
        "state": "owner_attested_current" if valid else "not_current",
        "credential_event_id": str(row["event_id"]),
        "owner_registry_check_recorded": bool(valid),
        "issuer_connection_verified": False,
    }


async def current_credential(conn, tenant: str, subject_user_id: int, discipline: str) -> dict:
    if not enabled():
        return _disabled()
    rows = await conn.fetch(
        "SELECT e.event_id, e.action, e.expires_at > now() AS unexpired, "
        "u.active AS subject_active, u.role AS subject_role, "
        "a.active AS attester_active, a.role AS attester_role "
        "FROM scout_specialist_credential_events e "
        "JOIN users u ON u.tenant_id=e.tenant_id AND u.id=e.subject_user_id "
        "JOIN users a ON a.tenant_id=e.tenant_id AND a.id=e.actor_user_id "
        "WHERE e.tenant_id=$1::uuid AND e.subject_user_id=$2 AND e.discipline=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_specialist_credential_events n "
        "WHERE n.previous_event_id=e.event_id) LIMIT 2",
        tenant,
        subject_user_id,
        discipline,
    )
    row = single_head(rows, _CODES)
    # Expiry is judged in database time, never device time.
    return credential_state(row, unexpired=bool(row and row["unexpired"]))


async def current_review_credential(conn, tenant: str, reviewer_user_id: int) -> dict:
    """The disciplines the v270 SQL guard accepts for a photo review."""
    if not enabled():
        return _disabled()
    for discipline in REVIEW_DISCIPLINES:
        status = await current_credential(conn, tenant, reviewer_user_id, discipline)
        if status["state"] == "owner_attested_current":
            return {**status, "discipline": discipline}
    return {
        "state": "not_current",
        "owner_registry_check_recorded": False,
        "issuer_connection_verified": False,
    }
