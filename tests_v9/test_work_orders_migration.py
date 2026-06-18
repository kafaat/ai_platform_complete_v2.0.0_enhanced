"""tests_v9/test_work_orders_migration.py — حارس ساكن لمهاجرة v75_work_orders.sql.

يتحقّق (دون قاعدة بيانات) من ثوابت الأمن والمخطّط الحرجة: field_id نصّ (لا UUID)،
RLS+FORCE مفعّل، سياسة العزل تستعمل current_setting، وقيود CHECK على status/wo_type.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "v75_work_orders.sql"
_SQL = _MIGRATION.read_text(encoding="utf-8")
_SQL_LOWER = _SQL.lower()


def test_field_id_is_text_not_uuid():
    """field_id يجب أن يكون TEXT (يطابق fields.field_id) لا UUID."""
    assert re.search(r"field_id\s+text\s+not\s+null", _SQL_LOWER), (
        "field_id يجب أن يُعرَّف TEXT NOT NULL"
    )
    assert not re.search(r"field_id\s+uuid", _SQL_LOWER), "field_id يجب ألّا يكون UUID"


def test_enable_and_force_rls_present():
    """يجب تفعيل ENABLE وFORCE ROW LEVEL SECURITY على work_orders."""
    assert "enable row level security" in _SQL_LOWER
    assert "force row level security" in _SQL_LOWER
    assert "alter table work_orders enable row level security" in _SQL_LOWER
    assert "alter table work_orders force row level security" in _SQL_LOWER


def test_policy_uses_current_setting():
    """سياسة العزل tenant_isolation تستعمل current_setting('app.current_tenant', ...)."""
    assert "drop policy if exists tenant_isolation on work_orders" in _SQL_LOWER
    assert "create policy tenant_isolation on work_orders" in _SQL_LOWER
    assert "current_setting('app.current_tenant', true)" in _SQL_LOWER
    assert "nullif(current_setting('app.current_tenant', true), '')" in _SQL_LOWER
    # USING وWITH CHECK كلاهما موجود
    assert "using (" in _SQL_LOWER
    assert "with check (" in _SQL_LOWER


def test_status_and_wo_type_check_constraints_present():
    """قيود CHECK على status وwo_type تمنع القيم خارج آلة الحالات."""
    for status in ("planned", "assigned", "in_progress", "done", "verified", "cancelled"):
        assert f"'{status}'" in _SQL_LOWER, f"الحالة {status} مفقودة من قيد CHECK"
    for wo_type in ("irrigation", "fertilization", "spraying", "scouting", "harvest"):
        assert f"'{wo_type}'" in _SQL_LOWER, f"النوع {wo_type} مفقود من قيد CHECK"
    assert re.search(r"status\s+text\s+not\s+null\s+default\s+'planned'\s+check", _SQL_LOWER)
    assert re.search(r"wo_type\s+text\s+not\s+null\s+check", _SQL_LOWER)
