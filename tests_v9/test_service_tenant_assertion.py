from __future__ import annotations

import pytest

from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    create_tenant_assertion,
    verify_tenant_assertion,
)

pytestmark = pytest.mark.unit
KEYS = {"2026-07": "k" * 32, "2026-06": "p" * 32}


def _token(**overrides):
    values = dict(
        key_id="2026-07",
        method="GET",
        path="/internal/fields/f-1",
        request_id="req-1",
        nonce="nonce-1",
        issued_at=100,
    )
    values.update(overrides)
    return create_tenant_assertion(KEYS[values["key_id"]], "vegetation", "tenant-a", **values)


def _verify(token, **overrides):
    values = dict(
        expected_method="GET",
        expected_path="/internal/fields/f-1",
        expected_request_id="req-1",
        now=120,
    )
    values.update(overrides)
    return verify_tenant_assertion(token, KEYS, "vegetation", "tenant-a", **values)


def test_assertion_binds_entire_request_and_exposes_replay_key() -> None:
    claims = _verify(_token())
    assert claims.nonce == "nonce-1"
    assert claims.replay_key.startswith("sahool:tenant-assertion:")
    for changed in (
        {"expected_method": "POST"},
        {"expected_path": "/internal/fields"},
        {"expected_request_id": "req-2"},
    ):
        with pytest.raises(TenantAssertionError, match="scope"):
            _verify(_token(), **changed)


def test_rotation_accepts_previous_key_but_unknown_kid_fails() -> None:
    assert _verify(_token(key_id="2026-06")).key_id == "2026-06"
    forged = _token().replace("v2:2026-07:", "v2:unknown:", 1)
    with pytest.raises(TenantAssertionError, match="unknown assertion key"):
        _verify(forged)


def test_assertion_rejects_tamper_expiry_and_future() -> None:
    token = _token()
    with pytest.raises(TenantAssertionError):
        _verify(token + "0")
    with pytest.raises(TenantAssertionError, match="expired"):
        _verify(token, now=161)
    with pytest.raises(TenantAssertionError, match="future"):
        _verify(token, now=90)
