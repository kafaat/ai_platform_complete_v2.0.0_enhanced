"""Static regression guards for newly opened tenant-sensitive boundaries."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    compile(text, path, "exec")
    return text


def test_yield_interval_checks_field_owner_and_marks_client_calibration_unverified():
    src = _source("services/sahool-platform/api/routers/yield_interval.py")
    assert "await _assert_field_in_tenant(conn, field_id)" in src
    assert '"decision_usable": False' in src
    assert '"calibration_owner_verified": False' in src
    assert '"evidence_source": "client_supplied_unverified"' in src


def test_sharing_key_revocation_requires_owner_permission_and_rls_scope():
    src = _source("services/sahool-platform/api/routers/sharing.py")
    segment = src.split('"/api/v1/sharing/keys/{key_id}/revoke"', 1)[1]
    assert "require_permission(Permission.USER_INVITE)" in segment
    assert "async with tenant_connection(user)" in segment
    assert "svc.revoke_key(key_id, str(user.tenant_id))" in segment


def test_market_reservations_remain_issued_by_the_authoritative_market_owner():
    market = _source("services/mcp_servers/market_server.py")
    assert "async def _reserve_from_harvest_lot(" in market
    assert "FOR UPDATE" in market
    assert "status = 'active'" in market
    custody = _source("services/sahool-platform/api/routers/harvest_traceability.py")
    assert "async def _listing_reservation(" in custody
    assert "reserved_kg=reserved_kg" in custody


def test_revoke_capability_handshake_is_fail_closed_for_legacy_backend():
    """The old /sharing/keys response has keys but no revoke route; don't show its button."""
    backend = _source("services/sahool-platform/api/routers/sharing.py")
    assert '"capabilities": {"revoke_keys": True}' in backend
    panel = (ROOT / "frontend/src/components/sharing/SharingPanel.tsx").read_text(encoding="utf-8")
    assert "supportsSharingKeyRevocation(data)" in panel
    assert "manageable && revokeSupported && k.revoked_at == null" in panel
    assert "() => refetch({ throwOnError: true })" in panel
    helper = (ROOT / "frontend/src/lib/sharingRevocation.ts").read_text(encoding="utf-8")
    assert "revoke_keys === true" in helper
    assert "SHARING_REVOKE_UNAVAILABLE_AR" in helper
