"""ربط إبطال JWT (denylist) بالمنصّة — get_current_user يستشيره + logout يُفعّله.

الفجوة (P1): النواة core/jwt_denylist موجودة لكن غير مربوطة ⇒ التوكن بعد تسجيل
الخروج يبقى صالحاً حتى انتهائه. هذه الاختبارات تثبّت أنّ: التوكن يحمل jti، وأنّ
logout يُبطِله فعليّاً، فيُرفَض في الطلبات اللاحقة (401)، مع fail-open عند تعذّر الفحص.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def m():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as main_mod

    # المعالِج auth_logout انتقل إلى api/routers/auth.py بعد تفكيك monolith؛
    # نوفّره على نسق الوصول القديم m.auth_logout (نفس الدالّة، موقعها فقط تغيّر).
    if not hasattr(main_mod, "auth_logout"):
        from api.routers import auth as _auth

        main_mod.auth_logout = _auth.auth_logout

    return main_mod


@pytest.fixture
def fresh_denylist(m, monkeypatch):
    """قائمة إبطال ذاكرة نظيفة لكلّ اختبار (عزل) — بلا Redis."""
    from core.jwt_denylist import InMemoryDenylist

    dl = InMemoryDenylist()
    monkeypatch.setattr(m, "_DENYLIST", dl)
    return dl


def _user(m):
    return m.UserSchema(user_id="u1", tenant_id="t1", role=m._normalize_role("farmer"), name_ar="م")


def test_token_carries_jti(m):
    import jwt as _jwt

    tok = m.create_token(_user(m))
    payload = _jwt.decode(tok, m.JWT_SECRET, algorithms=[m.JWT_ALGORITHM], audience="sahool")
    assert payload.get("jti"), "التوكن بلا jti — لا يمكن إبطاله"


def test_valid_token_authenticates(m, fresh_denylist):
    tok = m.create_token(_user(m))
    who = m.get_current_user("Bearer " + tok)
    assert who.user_id == "u1"


def test_logout_revokes_then_token_rejected(m, fresh_denylist):
    from fastapi import HTTPException

    tok = m.create_token(_user(m))
    who = m.get_current_user("Bearer " + tok)  # صالح قبل الخروج
    m.auth_logout(authorization="Bearer " + tok, user=who)  # يُبطِل jti
    with pytest.raises(HTTPException) as e:
        m.get_current_user("Bearer " + tok)  # بعد الخروج ⇒ مرفوض
    assert e.value.status_code == 401
    assert "مُبطَل" in e.value.detail


def test_other_token_unaffected_by_revocation(m, fresh_denylist):
    """إبطال توكن لا يؤثّر على توكن آخر (jti مختلف)."""
    tok1 = m.create_token(_user(m))
    tok2 = m.create_token(_user(m))
    m.auth_logout(authorization="Bearer " + tok1, user=m.get_current_user("Bearer " + tok1))
    # tok2 ما زال صالحاً
    assert m.get_current_user("Bearer " + tok2).user_id == "u1"


def test_is_token_revoked_fail_open_on_backend_error(m):
    """تعذّر فحص القائمة (backend يرمي) ⇒ يُسمَح (fail-open) لا يقفل المستخدمين."""
    from core.jwt_denylist import is_token_revoked

    class _Broken:
        def is_revoked(self, jti):
            raise RuntimeError("redis down")

    assert is_token_revoked(_Broken(), "any-jti") is False  # fail-open
    assert is_token_revoked(None, "any-jti") is False  # ميزة غير مُفعَّلة
    assert is_token_revoked(_Broken(), None) is False  # توكن بلا jti
