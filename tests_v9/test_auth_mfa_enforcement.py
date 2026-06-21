"""اختبارات وحدة لفرض MFA على الأدوار الحسّاسة (governance #411).

تُغطّي المنطق النقيّ دون قاعدة بيانات/Redis/شبكة:
  • تحليل قائمة الأدوار من ENV (تطبيع، فواصل، فراغات).
  • قرار الفرض كدالّة نقيّة _mfa_required_but_missing.

الافتراضيّ (لا بيئة) ⇒ الفرض مُعطَّل ⇒ لا تغيير في السلوك (يبقى CI أخضر).

يُحمَّل services/auth/main.py عبر importlib؛ يُتخطّى الاختبار بأمان إذا غابت
تبعيّات الخدمة (fastapi/asyncpg…) في بيئة الوحدات بـCI.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTH_DIR = os.path.join(ROOT, "services/auth")


def _load_auth_main():
    """يُحمّل main.py الخاصّ بخدمة auth، ويتخطّى الاختبار إن غابت تبعيّاتها."""
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    try:
        return importlib.import_module("main")
    except ImportError as e:  # تبعيّات الخدمة (fastapi…) غير مثبّتة في بيئة الوحدات
        # allow_module_level: التخطّي يحدث عند الاستيراد على مستوى الوحدة (لا داخل
        # اختبار)، فبدونه يرفع pytest خطأ تجميع يُفشِل التشغيل كلّه في CI.
        pytest.skip(f"auth main.py غير قابل للاستيراد (تبعيّة ناقصة): {e}", allow_module_level=True)


main = _load_auth_main()


class TestParseRequiredMfaRoles:
    @pytest.mark.unit
    def test_default_is_admin(self):
        assert main._parse_required_mfa_roles(None) == frozenset({"admin"})

    @pytest.mark.unit
    def test_empty_string_defaults_to_admin(self):
        assert main._parse_required_mfa_roles("") == frozenset({"admin"})

    @pytest.mark.unit
    def test_comma_separated_normalized(self):
        assert main._parse_required_mfa_roles(" Admin, Owner ,") == frozenset({"admin", "owner"})

    @pytest.mark.unit
    def test_lowercased_and_trimmed(self):
        assert main._parse_required_mfa_roles("EXPERT") == frozenset({"expert"})


class TestMfaRequiredButMissing:
    @pytest.mark.unit
    def test_disabled_enforcement_never_requires(self):
        # السلوك الافتراضيّ (CI): الفرض مُعطَّل ⇒ False دائماً، حتى لدور حسّاس بلا MFA.
        assert main._mfa_required_but_missing("admin", False, enforcement_enabled=False) is False

    @pytest.mark.unit
    def test_sensitive_role_without_mfa_is_rejected_when_enabled(self):
        assert (
            main._mfa_required_but_missing(
                "admin", False, enforcement_enabled=True, required_roles=frozenset({"admin"})
            )
            is True
        )

    @pytest.mark.unit
    def test_sensitive_role_with_mfa_passes(self):
        assert (
            main._mfa_required_but_missing(
                "admin", True, enforcement_enabled=True, required_roles=frozenset({"admin"})
            )
            is False
        )

    @pytest.mark.unit
    def test_non_sensitive_role_passes(self):
        assert (
            main._mfa_required_but_missing(
                "farmer", False, enforcement_enabled=True, required_roles=frozenset({"admin"})
            )
            is False
        )

    @pytest.mark.unit
    def test_role_is_case_insensitive(self):
        assert (
            main._mfa_required_but_missing(
                "ADMIN", False, enforcement_enabled=True, required_roles=frozenset({"admin"})
            )
            is True
        )

    @pytest.mark.unit
    def test_none_role_is_safe(self):
        assert (
            main._mfa_required_but_missing(
                None, False, enforcement_enabled=True, required_roles=frozenset({"admin"})
            )
            is False
        )

    @pytest.mark.unit
    def test_module_default_enforcement_is_off(self):
        # ضمان عدم كسر CI: المفتاح الرئيسيّ مُعطَّل ما لم تُضبط البيئة.
        assert main.MFA_ENFORCEMENT_ENABLED is False
