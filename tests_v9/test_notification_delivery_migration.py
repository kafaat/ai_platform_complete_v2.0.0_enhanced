"""حارس ثابت (static) لهجرة إيصالات تسليم الإشعار v83 — يمنع انحدار البُنى الحرجة:
RLS الإلزاميّ الصريح (ENABLE+FORCE)، قيد CHECK على status (المجموعة المغلقة)،
UNIQUE(tenant,alert_key,channel) للـupsert، وإدراج الهجرة في MANIFEST. فحص مصدر/هجرة
يُنفَّذ في CI بلا قاعدة.
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


def test_v83_notification_delivery_table_and_rls():
    """v83: جدول notification_delivery بـtenant UUID NOT NULL + RLS إلزاميّ معزول."""
    sql = _read("migrations/v83_notification_delivery.sql")
    assert "CREATE TABLE IF NOT EXISTS notification_delivery" in sql
    assert "tenant_id    UUID         NOT NULL" in sql
    assert "alert_key    TEXT         NOT NULL" in sql
    assert "channel      TEXT         NOT NULL" in sql
    _assert_explicit_rls(sql, "notification_delivery")


def test_v83_status_is_closed_set():
    """قيد CHECK يحصر status في المجموعة المغلقة الأربع (لا حالة مُلفّقة)."""
    sql = _read("migrations/v83_notification_delivery.sql")
    assert "CHECK (status IN ('queued', 'sent', 'failed', 'delivered'))" in sql


def test_v83_unique_upsert_and_index():
    """جوهر الإيصال: UNIQUE(tenant,alert_key,channel) للـupsert + فهرس الجلب."""
    sql = _read("migrations/v83_notification_delivery.sql")
    assert "UNIQUE (tenant_id, alert_key, channel)" in sql
    assert "idx_notification_delivery_alert" in sql
    assert "ON notification_delivery (tenant_id, alert_key)" in sql


def test_v83_timestamps_present():
    """created_at + updated_at لتتبّع دورة حياة الإيصال."""
    sql = _read("migrations/v83_notification_delivery.sql")
    assert "created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()" in sql
    assert "updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()" in sql


def test_v83_in_manifest():
    """الهجرة مُدرَجة في MANIFEST (لا هجرة يتيمة)."""
    manifest = _read("migrations/MANIFEST.txt")
    assert "v83_notification_delivery.sql" in manifest
