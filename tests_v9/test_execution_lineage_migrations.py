"""حارس ثابت (static) لهجرة جسر النَّسَب الموحّد v82 — يمنع انحدار البُنى الحرجة:
RLS الإلزاميّ الصريح، قيد CHECK على ref_type (المجموعة المغلقة)، UNIQUE للربط مرّةً،
وفهرس (tenant,lineage_id) لجلب السلسلة. فحص مصدر/هجرة يُنفَّذ في CI بلا قاعدة.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _assert_explicit_rls(sql: str, table: str) -> None:
    """عزل المستأجِر الصريح (يطابق sahool_inspector/test_rls_*): ENABLE+FORCE + سياسة
    tenant_isolation بـcurrent_setting('app.current_tenant') — لجدول مُضاف بعد propagate."""
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    assert f"CREATE POLICY tenant_isolation ON {table}" in sql
    assert "current_setting('app.current_tenant', true)" in sql


def test_v82_lineage_link_table_and_rls():
    """v82: جدول lineage_link بمعرّف عالميّ + tenant + RLS إلزاميّ معزول."""
    sql = _read("migrations/v82_lineage_link.sql")
    assert "CREATE TABLE IF NOT EXISTS lineage_link" in sql
    assert "lineage_id  TEXT         NOT NULL" in sql
    assert "tenant_id   UUID         NOT NULL" in sql
    assert "ref_id      TEXT         NOT NULL" in sql
    _assert_explicit_rls(sql, "lineage_link")


def test_v82_ref_type_is_closed_set():
    """قيد CHECK يحصر ref_type في المجموعة المغلقة الخمس (لا ربط لنوع مجهول)."""
    sql = _read("migrations/v82_lineage_link.sql")
    assert "CHECK (ref_type IN ('decision', 'dispatch', 'command', 'execution', 'outcome'))" in sql


def test_v82_unique_link_once_and_chain_index():
    """جوهر الجسر: UNIQUE(tenant,ref_type,ref_id) للربط مرّةً + فهرس (tenant,lineage_id)."""
    sql = _read("migrations/v82_lineage_link.sql")
    assert "UNIQUE (tenant_id, ref_type, ref_id)" in sql
    assert "idx_lineage_link_chain" in sql
    assert "ON lineage_link (tenant_id, lineage_id)" in sql


def test_v82_in_manifest():
    """الهجرة مُدرَجة في MANIFEST (لا هجرة يتيمة)."""
    manifest = _read("migrations/MANIFEST.txt")
    assert "v82_lineage_link.sql" in manifest
