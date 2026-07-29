"""حارس ساكن — ERP-BRIDGE-FIX-01: رفع عزل RLS على جداول odoo إلى معيار v204.

قبل الإصلاح: الحلقة العامّة في v9_odoo_bridge.sql كانت ENABLE فقط + USING بلا WITH CHECK —
مالك الجدول (owner) يتجاوز RLS، وإدراج صفّ موسوم بمستأجر آخر لا يُفحَص.
بعده: FORCE ROW LEVEL SECURITY + WITH CHECK مطابق لـUSING على كلّ جدول في الحلقة.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "v9_odoo_bridge.sql").read_text(encoding="utf-8")


def test_force_row_level_security_in_loop() -> None:
    assert "FORCE ROW LEVEL SECURITY" in SQL
    assert SQL.count("FORCE ROW LEVEL SECURITY") >= 1


def test_policy_has_with_check() -> None:
    assert ") WITH CHECK (" in SQL
    using = SQL.index("CREATE POLICY tenant_isolation")
    segment = SQL[using : using + 600]
    assert "WITH CHECK" in segment
    assert segment.count("current_setting('app.current_tenant', true)") >= 2  # USING + WITH CHECK


def test_enable_still_present_before_force() -> None:
    enable = SQL.index("ENABLE ROW LEVEL SECURITY")
    force = SQL.index("FORCE ROW LEVEL SECURITY")
    assert enable < force  # الترتيب الصحيح داخل الحلقة
