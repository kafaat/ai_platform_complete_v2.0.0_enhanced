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


def test_market_origins_are_read_only_not_uuid_coercion():
    src = _source("services/sahool-platform/api/routers/harvest_traceability.py")
    assert 'result["market_origin_preview"] = assess_market_origin_preview(lot, chain)' in src
    core = _source("services/sahool-platform/core/engines/harvest_traceability.py")
    assert '"decision_usable": False' in core
    assert "uuid.UUID" not in core

