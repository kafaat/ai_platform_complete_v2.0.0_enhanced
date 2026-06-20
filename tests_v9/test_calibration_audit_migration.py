"""حارس ثابت (static) لهجرة سجلّ تدقيق المعايرة v84 — يمنع انحدار البُنى الحرجة:
RLS الإلزاميّ الصريح (ENABLE+FORCE)، قيد CHECK على action (المجموعة المغلقة)،
الطبيعة append-only (لا UPDATE/DELETE، ولا عمود updated_at)، فهرس الجلب
(tenant,region,created_at DESC)، وإدراج الهجرة في MANIFEST. فحص مصدر/هجرة يُنفَّذ في
CI بلا قاعدة.
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
    tenant_isolation بـcurrent_setting('app.current_tenant')."""
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    assert f"CREATE POLICY tenant_isolation ON {table}" in sql
    assert "current_setting('app.current_tenant', true)" in sql


def test_v84_table_and_rls():
    """v84: جدول calibration_audit بـtenant UUID NOT NULL + RLS إلزاميّ معزول."""
    sql = _read("migrations/v84_calibration_audit.sql")
    assert "CREATE TABLE IF NOT EXISTS calibration_audit" in sql
    assert "audit_id    UUID PRIMARY KEY" in sql
    assert "tenant_id   UUID         NOT NULL" in sql
    assert "region      VARCHAR(40)" in sql
    assert "old_values  JSONB" in sql
    assert "new_values  JSONB" in sql
    _assert_explicit_rls(sql, "calibration_audit")


def test_v84_action_is_closed_set():
    """قيد CHECK يحصر action في المجموعة المغلقة الثلاث (لا فعل مُلفّق)."""
    sql = _read("migrations/v84_calibration_audit.sql")
    assert "CHECK (action IN ('override_set', 'reverted', 'adaptation_applied'))" in sql


def test_v84_append_only():
    """سجلّ التدقيق append-only: لا عمود updated_at، ولا UPDATE/DELETE على الجدول."""
    sql = _read("migrations/v84_calibration_audit.sql")
    # لا عمود updated_at (سجلّ لا يُعدَّل) — نتجاهل التعليقات لتفادي ذِكره وصفيّاً.
    code = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    assert "updated_at" not in code
    # لا عبارات UPDATE/DELETE تستهدف الجدول داخل الهجرة (سطر الـCHECK يحوي كلمات الأفعال
    # كقيم نصّيّة لا كأوامر SQL — نتحقّق من غياب الأمر الفعليّ).
    upper = code.upper()
    assert "UPDATE CALIBRATION_AUDIT" not in upper
    assert "DELETE FROM CALIBRATION_AUDIT" not in upper


def test_v84_index_for_region_history():
    """فهرس جلب سجلّ المنطقة بالأحدث أوّلاً (tenant,region,created_at DESC)."""
    sql = _read("migrations/v84_calibration_audit.sql")
    assert "idx_calibration_audit_tenant_region" in sql
    assert "ON calibration_audit (tenant_id, region, created_at DESC)" in sql


def test_v84_timestamps_present():
    """created_at لتسجيل زمن القيد (append-only: created_at فقط، لا updated_at)."""
    sql = _read("migrations/v84_calibration_audit.sql")
    assert "created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()" in sql


def test_v84_in_manifest():
    """الهجرة مُدرَجة في MANIFEST (لا هجرة يتيمة)."""
    manifest = _read("migrations/MANIFEST.txt")
    assert "v84_calibration_audit.sql" in manifest
