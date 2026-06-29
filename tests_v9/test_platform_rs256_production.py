"""حارس تحصين: RS256 إلزاميّ في الإنتاج لـsahool-platform (تماثُل مع auth).

المنصّة تقبل توكنات من ``sahool-auth`` (عابر-خدمات). حين تُصدِر auth بـRS256 يجب أن
تتحقّق المنصّة بـRS256 (المفتاح العامّ) وإلّا تعذّر التحقّق ⇒ كسر المصادقة في الإنتاج.
``_refuse_hs256_in_production`` دالّة نقيّة (مطابِقة لنظيرتها في auth) تقرّر رفض الإقلاع:
إنتاج + بلا RS256 + بلا مهرب صريح ⇒ رفض. تُحمَّل من ``services/sahool-platform/api/main.py``
عبر importlib (تُتخطّى إن غابت تبعيّاتها محلّيّاً).
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")


def _load_main():
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    try:
        return importlib.import_module("api.main")
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محلّيّاً (asyncpg…)
        pytest.skip(f"platform deps missing: {e}")


def test_production_without_rs256_refuses_boot():
    """إنتاج + بلا RS256 + بلا مهرب ⇒ رفض (fail-closed)."""
    m = _load_main()
    assert m._refuse_hs256_in_production(has_rs256=False, is_production=True, allow_hs256_env=None)


def test_production_with_rs256_allowed():
    """إنتاج + RS256 (JWT_PUBLIC_KEY) ⇒ يُقبَل (الوضع الموصى به)."""
    m = _load_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=True, is_production=True, allow_hs256_env=None
    )


def test_development_hs256_allowed():
    """تطوير + HS256 ⇒ يُقبَل (لا يكسر CI/التطوير)."""
    m = _load_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=False, is_production=False, allow_hs256_env=None
    )


@pytest.mark.parametrize("flag", ["1", "true", "YES", "on"])
def test_production_hs256_escape_hatch(flag):
    """إنتاج + HS256 + مهرب صريح ⇒ يُقبَل (ترحيل مؤقّت موثَّق)."""
    m = _load_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=False, is_production=True, allow_hs256_env=flag
    )


def test_escape_hatch_only_truthy():
    """قيمة غير صريحة للمهرب لا تُعطّل الفرض (fail-closed)."""
    m = _load_main()
    assert m._refuse_hs256_in_production(
        has_rs256=False, is_production=True, allow_hs256_env="maybe"
    )


def test_default_mode_is_hs256_without_public_key():
    """بلا JWT_PUBLIC_KEY: التحقّق HS256 بالسرّ المتماثل (سلوك التطوير الحاليّ)."""
    m = _load_main()
    if m.JWT_PUBLIC_KEY:  # بيئة CI ضبطت مفتاحاً عامّاً — لا ينطبق
        pytest.skip("JWT_PUBLIC_KEY set in environment")
    assert m.JWT_VERIFY_ALGORITHM == "HS256"
    assert m.JWT_VERIFY_KEY == m.JWT_SECRET


def test_rs256_cross_service_roundtrip():
    """توكن auth موقَّع RS256 (مفتاح خاصّ) يتحقّق بالمفتاح العامّ للمنصّة؛ وHS256 يُرفَض."""
    pytest.importorskip("jwt")
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    from cryptography.hazmat.primitives import serialization

    key = crypto.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )

    import jwt

    # توكن auth (RS256) يتحقّق بالمفتاح العامّ.
    tok = jwt.encode({"sub": "u", "aud": "sahool", "iss": "sahool-auth"}, priv, algorithm="RS256")
    payload = jwt.decode(tok, pub, algorithms=["RS256"], audience="sahool")
    assert payload["iss"] == "sahool-auth"

    # في وضع RS256، توكن HS256 يُرفَض (لا خلط خوارزميّات).
    hs = jwt.encode({"aud": "sahool"}, "x" * 40, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(hs, pub, algorithms=["RS256"], audience="sahool")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
