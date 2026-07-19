"""حارس تصديق الحافّة (SEASON-RECORD-ENTRY-01 §4-①) — نواة HMAC نقيّة + براهين سلبيّة.

الفجوة الجوهريّة (تعديل المالك ①): التجريد عند nginx لا يحمي من POST مباشر داخل شبكة docker
بترويسة X-User-Id ملفّقة. الحلّ: توقيع HMAC مشترك بين nginx والخدمة فقط — الهويّة بلا توقيع صالح = 401.
لا يعتمد على بقاء منفذ الخدمة nginx-only (drift-proof).

فحص وحدة صرف — ``pytest -m unit`` (نقيّ، لا FastAPI/شبكة).
"""

from __future__ import annotations

import pytest

from shared.security.trusted_tenant import (
    ERROR_EDGE_STALE,
    ERROR_EDGE_UNATTESTED,
    TrustedTenantError,
    compute_edge_attestation,
    has_reviewer_role,
    verify_edge_attestation,
)

pytestmark = pytest.mark.unit

_SECRET = "edge-shared-secret-nginx-and-service-only"
_NOW = 1_800_000_000.0


def _sign(uid, roles, ts, secret=_SECRET):
    return compute_edge_attestation(uid, roles, ts, secret)


def test_valid_attestation_returns_user():
    ts = str(_NOW)
    att = _sign("user-ali", "season-reviewer", ts)
    got = verify_edge_attestation(
        user_id="user-ali",
        roles="season-reviewer",
        timestamp=ts,
        attestation=att,
        secret=_SECRET,
        now_epoch=_NOW,
    )
    assert got == "user-ali"


def test_forged_identity_without_signature_rejected():
    """① الفجوة الجوهريّة: X-User-Id ملفّقة بلا توقيع ⇒ edge_unattested (401)."""
    with pytest.raises(TrustedTenantError) as e:
        verify_edge_attestation(
            user_id="attacker",
            roles="season-reviewer",
            timestamp=str(_NOW),
            attestation=None,
            secret=_SECRET,
            now_epoch=_NOW,
        )
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_wrong_signature_rejected():
    """توقيع بمفتاح مختلف (لا يملكه المهاجم) ⇒ رفض."""
    att = _sign("user-ali", "season-reviewer", str(_NOW), secret="attacker-guessed-key")
    with pytest.raises(TrustedTenantError) as e:
        verify_edge_attestation(
            user_id="user-ali",
            roles="season-reviewer",
            timestamp=str(_NOW),
            attestation=att,
            secret=_SECRET,
            now_epoch=_NOW,
        )
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_tampered_user_after_signing_rejected():
    """توقيع صالح لـuser-ali ثمّ استبدال user_id ⇒ عدم تطابق التوقيع (لا يُقبل انتحال)."""
    att = _sign("user-ali", "season-reviewer", str(_NOW))
    with pytest.raises(TrustedTenantError) as e:
        verify_edge_attestation(
            user_id="user-mallory",
            roles="season-reviewer",
            timestamp=str(_NOW),
            attestation=att,
            secret=_SECRET,
            now_epoch=_NOW,
        )
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_stale_timestamp_rejected_both_directions():
    """خارج نافذة إعادة اللعب (±120ث) ⇒ edge_attestation_stale (يمنع إعادة توقيع قديم)."""
    old_ts = str(_NOW - 300)
    att = _sign("user-ali", "season-reviewer", old_ts)
    with pytest.raises(TrustedTenantError) as e:
        verify_edge_attestation(
            user_id="user-ali",
            roles="season-reviewer",
            timestamp=old_ts,
            attestation=att,
            secret=_SECRET,
            now_epoch=_NOW,
        )
    assert e.value.code == ERROR_EDGE_STALE


def test_missing_secret_fail_closed():
    """مفتاح غير مُهيّأ ⇒ رفض (لا يقبل بصمت — نفس درس service_token_ok)."""
    ts = str(_NOW)
    with pytest.raises(TrustedTenantError) as e:
        verify_edge_attestation(
            user_id="user-ali",
            roles="season-reviewer",
            timestamp=ts,
            attestation="anything",
            secret="",
            now_epoch=_NOW,
        )
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_reviewer_role_check():
    """②: دور season-reviewer مطلوب للقبول (attested لكن بلا الدور ⇒ لاحقاً 403)."""
    assert has_reviewer_role("season-reviewer") is True
    assert has_reviewer_role("farmer,season-reviewer,viewer") is True
    assert has_reviewer_role("farmer,viewer") is False
    assert has_reviewer_role(None) is False
    assert has_reviewer_role("") is False
