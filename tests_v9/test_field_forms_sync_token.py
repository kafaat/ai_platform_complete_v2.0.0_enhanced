"""اختبارات definition_sync_token (GAP-FIELD-FORMS-01 §9.2) — HMAC ذاتيّ التحقّق بلا جدول خامس."""

from __future__ import annotations

import pytest

from shared.contracts.forms.sync_token import SyncTokenError, issue_token, verify_token

NOW = 1_800_000_000.0


def _claims() -> dict:
    return {
        "token_version": 1,
        "key_id": "k1",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "actor_id": "scout-7",
        "device_id": "device-3",
        "assignment_id": "22222222-2222-2222-2222-222222222222",
        "revision": 4,
        "form_version_id": "33333333-3333-3333-3333-333333333333",
        "schema_hash": "a" * 64,
        "issued_at": NOW - 3600,
    }


def test_roundtrip_current_key() -> None:
    token = issue_token(_claims(), secret="s3cret", key_id="k1")
    out = verify_token(
        token, current_secret="s3cret", current_key_id="k1", now_epoch=NOW
    )
    assert out["tenant_id"] == _claims()["tenant_id"]
    assert out["revision"] == 4


def test_tampered_payload_rejected() -> None:
    token = issue_token(_claims(), secret="s3cret", key_id="k1")
    payload_b64, _sig = token.split(".", 1)
    import base64
    import json as _json

    claims = _json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    claims["form_version_id"] = "99999999-9999-9999-9999-999999999999"  # انتحال وجهة
    forged = (
        base64.urlsafe_b64encode(_json.dumps(claims, sort_keys=True).encode()).rstrip(b"=").decode()
        + "."
        + token.split(".", 1)[1]
    )
    with pytest.raises(SyncTokenError):
        verify_token(forged, current_secret="s3cret", current_key_id="k1", now_epoch=NOW)


def test_wrong_secret_rejected() -> None:
    token = issue_token(_claims(), secret="s3cret", key_id="k1")
    with pytest.raises(SyncTokenError):
        verify_token(token, current_secret="WRONG", current_key_id="k1", now_epoch=NOW)


def test_previous_key_accepted_within_window() -> None:
    token = issue_token(_claims(), secret="old-secret", key_id="k0")
    out = verify_token(
        token,
        current_secret="s3cret",
        current_key_id="k1",
        previous_secret="old-secret",
        previous_key_id="k0",
        previous_until_epoch=NOW + 100,
        now_epoch=NOW,
    )
    assert out["key_id"] == "k0"


def test_previous_key_rejected_after_window() -> None:
    token = issue_token(_claims(), secret="old-secret", key_id="k0")
    with pytest.raises(SyncTokenError):
        verify_token(
            token,
            current_secret="s3cret",
            current_key_id="k1",
            previous_secret="old-secret",
            previous_key_id="k0",
            previous_until_epoch=NOW - 1,  # انتهى الحدّ الزمنيّ — لا سرّ قديم بلا انتهاء
            now_epoch=NOW,
        )


def test_missing_claim_rejected() -> None:
    claims = _claims()
    del claims["schema_hash"]
    with pytest.raises(SyncTokenError):
        issue_token(claims, secret="s3cret", key_id="k1")
