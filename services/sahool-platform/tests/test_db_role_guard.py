"""اختبارات حارس دور قاعدة البيانات (core.db_role_guard) — لينشين عزل المستأجرين.

تدقيق موجَّه للعزل: التطبيق إن اتّصل بدور يتجاوز RLS (superuser/BYPASSRLS) ينهار العزل
صامتاً. هذا الحارس يرفض الإقلاع (fail-closed) عند الفرض. اختبارات نقيّة + حارس وصل.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

from core.db_role_guard import (  # noqa: E402
    enforcement_enabled,
    role_can_bypass_rls,
    role_guard_message,
    should_refuse_startup,
)


# ── كشف الدور غير الآمن ──
def test_superuser_bypasses_rls():
    assert role_can_bypass_rls(True, False) is True


def test_bypassrls_bypasses_rls():
    assert role_can_bypass_rls(False, True) is True


def test_restricted_role_is_safe():
    # sahool_app: NOSUPERUSER NOBYPASSRLS ⇒ آمن (يخضع لـRLS)
    assert role_can_bypass_rls(False, False) is False


def test_handles_none_flags():
    assert role_can_bypass_rls(None, None) is False


# ── الفرض ──
def test_enforcement_flag_parsing():
    for v in ("1", "true", "TRUE", "yes", "on"):
        assert enforcement_enabled(v) is True
    for v in ("0", "false", "", None, "off"):
        assert enforcement_enabled(v) is False


# ── قرار الرفض (fail-closed عند الفرض فقط) ──
def test_refuse_only_when_unsafe_and_enforced():
    assert should_refuse_startup(True, True) is True  # دور غير آمن + فرض ⇒ رفض
    assert should_refuse_startup(True, False) is False  # غير آمن لكن بلا فرض ⇒ تحذير فقط
    assert should_refuse_startup(False, True) is False  # آمن ⇒ لا رفض
    assert should_refuse_startup(False, False) is False


def test_message_explains_risk_and_fix():
    msg = role_guard_message(True, False, refused=True)
    assert "superuser" in msg
    assert "sahool_app" in msg  # يذكر الإصلاح (الدور المقيّد)
    assert "رُفِض" in msg
    msg2 = role_guard_message(False, True, refused=False)
    assert "BYPASSRLS" in msg2
    assert "تحذير" in msg2


# ── حارس الوصل في الإقلاع ──
def test_startup_wires_role_guard():
    import os

    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "api", "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert "_assert_db_role_rls_safe(_DB_POOL)" in src, "الإقلاع لا يفحص دور RLS"
    # رفض الإقلاع المتعمَّد لا يُبتلَع (RuntimeError يُعاد رفعه)
    assert "except RuntimeError:" in src and "raise" in src, "رفض الإقلاع يُبتلَع بدل إعادة رفعه"
