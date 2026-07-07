"""حارس تحصين: RS256 إلزاميّ في الإنتاج (auth) — قرار نقيّ.

HS256 (سرّ متماثل مشترَك) لا يُنهي shared trust domain؛ RS256 (مفتاح خاصّ لـauth) يُنهيه.
``_refuse_hs256_in_production`` دالّة نقيّة تقرّر رفض الإقلاع: إنتاج + بلا RS256 + بلا مهرب
صريح ⇒ رفض. تُحمَّل من ``services/auth/main.py`` عبر importlib (تُتخطّى إن غابت تبعيّاتها).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

_AUTH_DIR = os.path.join(os.path.dirname(__file__), "..", "services", "auth")


def _load_auth_main():
    """Load services/auth/main.py without colliding with any already-imported module named `main`."""
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    try:
        spec = importlib.util.spec_from_file_location(
            "sahool_auth_main_for_rs256_test", os.path.join(_AUTH_DIR, "main.py")
        )
        if spec is None or spec.loader is None:
            pytest.skip("auth main.py could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except ModuleNotFoundError as e:  # تبعيّات auth غائبة محليّاً (jose/asyncpg…)
        pytest.skip(f"auth deps missing: {e}")


def test_production_without_rs256_refuses_boot():
    """إنتاج + بلا RS256 + بلا مهرب ⇒ رفض (fail-closed)."""
    m = _load_auth_main()
    assert m._refuse_hs256_in_production(has_rs256=False, is_production=True, allow_hs256_env=None)


def test_production_with_rs256_allowed():
    """إنتاج + RS256 ⇒ يُقبَل (الوضع الموصى به)."""
    m = _load_auth_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=True, is_production=True, allow_hs256_env=None
    )


def test_development_hs256_allowed():
    """تطوير + HS256 ⇒ يُقبَل (لا يكسر CI/التطوير)."""
    m = _load_auth_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=False, is_production=False, allow_hs256_env=None
    )


@pytest.mark.parametrize("flag", ["1", "true", "YES", "on"])
def test_production_hs256_escape_hatch(flag):
    """إنتاج + HS256 + مهرب صريح ⇒ يُقبَل (ترحيل مؤقّت موثَّق)."""
    m = _load_auth_main()
    assert not m._refuse_hs256_in_production(
        has_rs256=False, is_production=True, allow_hs256_env=flag
    )


def test_escape_hatch_only_truthy():
    """قيمة غير صريحة للمهرب لا تُعطّل الفرض (fail-closed)."""
    m = _load_auth_main()
    assert m._refuse_hs256_in_production(
        has_rs256=False, is_production=True, allow_hs256_env="maybe"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
