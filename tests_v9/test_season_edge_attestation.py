"""حارس تصديق الحافّة (SEASON-RECORD-ENTRY-01 §4-①) — نواة HMAC نقيّة **مقيَّدة بالوجهة** + براهين سلبيّة.

الفجوة الجوهريّة (تعديل المالك ①، الشريحة 1): التجريد عند البوّابة لا يحمي من POST مباشر داخل شبكة docker
بترويسة X-User-Id ملفّقة. الحلّ: توقيع HMAC مشترك بين auth والخدمة — الهويّة بلا توقيع صالح = 401.

**تقييد الوجهة (تعديل المالك ①، الشريحة 3):** التوقيع يغطّي (الهويّة + method + path + body_hash + الوقت)
فتصديقٌ صُكّ لمسار بريء (GET مثلاً) لا يُعاد لعبه على .../accept — النافذة ±120ث تحمي الزمن، وتقييد
method/path/body يحمي المكان والحمولة. لا يعتمد على بقاء منفذ الخدمة nginx-only (drift-proof).

فحص وحدة صرف — ``pytest -m unit`` (نقيّ، لا FastAPI/شبكة).
"""

from __future__ import annotations

import pytest

from shared.security.trusted_tenant import (
    ERROR_EDGE_STALE,
    ERROR_EDGE_UNATTESTED,
    TrustedTenantError,
    compute_edge_attestation,
    edge_body_sha256,
    has_reviewer_role,
    verify_edge_attestation,
)

pytestmark = pytest.mark.unit

_SECRET = "edge-shared-secret-auth-and-service-only"
_NOW = 1_800_000_000.0
_METHOD = "POST"
_PATH = "/internal/seasons/abc/accept"
_BODY = edge_body_sha256(b"")  # القبول بلا جسم


def _sign(uid, roles, ts, *, method=_METHOD, path=_PATH, body=_BODY, secret=_SECRET):
    return compute_edge_attestation(uid, roles, method, path, body, ts, secret)


def _verify(att, uid="user-ali", roles="season-reviewer", ts=str(_NOW), **kw):
    kwargs = dict(
        user_id=uid,
        roles=roles,
        method=_METHOD,
        path=_PATH,
        body_sha256=_BODY,
        timestamp=ts,
        attestation=att,
        secret=_SECRET,
        now_epoch=_NOW,
    )
    kwargs.update(kw)
    return verify_edge_attestation(**kwargs)


def test_valid_attestation_returns_user():
    att = _sign("user-ali", "season-reviewer", str(_NOW))
    assert _verify(att) == "user-ali"


def test_forged_identity_without_signature_rejected():
    """① الفجوة الجوهريّة: X-User-Id ملفّقة بلا توقيع ⇒ edge_unattested (401)."""
    with pytest.raises(TrustedTenantError) as e:
        _verify(None, uid="attacker")
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_wrong_signature_rejected():
    att = _sign("user-ali", "season-reviewer", str(_NOW), secret="attacker-guessed-key")
    with pytest.raises(TrustedTenantError) as e:
        _verify(att)
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_tampered_user_after_signing_rejected():
    att = _sign("user-ali", "season-reviewer", str(_NOW))
    with pytest.raises(TrustedTenantError) as e:
        _verify(att, uid="user-mallory")
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_stale_timestamp_rejected_both_directions():
    old_ts = str(_NOW - 300)
    att = _sign("user-ali", "season-reviewer", old_ts)
    with pytest.raises(TrustedTenantError) as e:
        _verify(att, ts=old_ts)
    assert e.value.code == ERROR_EDGE_STALE


def test_missing_secret_fail_closed():
    with pytest.raises(TrustedTenantError) as e:
        _verify("anything", secret="")
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_reviewer_role_check():
    assert has_reviewer_role("season-reviewer") is True
    assert has_reviewer_role("farmer,season-reviewer,viewer") is True
    assert has_reviewer_role("farmer,viewer") is False
    assert has_reviewer_role(None) is False
    assert has_reviewer_role("") is False


# ── ① تقييد الوجهة — براهين إعادة اللعب عبر المسارات/الطرائق/الحمولة ─────────────
def test_cross_path_replay_rejected():
    """تصديق صُكّ لمسار GET بريء ⇒ لا يُقبَل على .../accept (المكان مُوقَّع)."""
    att_benign = _sign("user-ali", "season-reviewer", str(_NOW), path="/internal/seasons/abc")
    with pytest.raises(TrustedTenantError) as e:
        _verify(att_benign, path=_PATH)  # نفس التوقيع، مسار مختلف ⇒ رفض
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_cross_method_replay_rejected():
    att_get = _sign("user-ali", "season-reviewer", str(_NOW), method="GET")
    with pytest.raises(TrustedTenantError) as e:
        _verify(att_get, method="POST")
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_body_tamper_rejected():
    """تصديق صُكّ لجسم فارغ ⇒ لا يُقبَل مع جسم مختلف (الحمولة مُوقَّعة)."""
    att_empty = _sign("user-ali", "season-reviewer", str(_NOW), body=edge_body_sha256(b""))
    with pytest.raises(TrustedTenantError) as e:
        _verify(att_empty, body_sha256=edge_body_sha256(b'{"tampered":true}'))
    assert e.value.code == ERROR_EDGE_UNATTESTED


def test_missing_destination_parts_fail_closed():
    """method/path/body مفقودة ⇒ edge_unattested (fail-closed، لا توقيع بلا وجهة)."""
    att = _sign("user-ali", "season-reviewer", str(_NOW))
    for missing in ("method", "path", "body_sha256"):
        with pytest.raises(TrustedTenantError) as e:
            _verify(att, **{missing: None})
        assert e.value.code == ERROR_EDGE_UNATTESTED
