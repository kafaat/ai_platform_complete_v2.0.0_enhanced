"""حُرّاس ثابتة (static) لهجرتَي إدامة سلسلة النَّسَب v78/v79 — تمنع انحدار البُنى
الحرجة فيهما (RLS الإلزاميّ، المفتاح الأساسيّ، فهرس decision_id الذي يصل القرار بنتيجته).

نفس فلسفة test_event_bus_invariants: فحص مصدر/هجرة يُنفَّذ في CI بلا قاعدة. مسار الكتابة
الفعليّ يطبّقه CI Integration (يتطلّب Postgres+RLS).
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


def test_v78_decision_record_table_and_rls():
    """v78: جدول decision_record بمفتاح أساسيّ decision_id + RLS إلزاميّ معزول."""
    sql = _read("migrations/v78_decision_record.sql")
    assert "CREATE TABLE IF NOT EXISTS decision_record" in sql
    assert "decision_id     VARCHAR(40)  PRIMARY KEY" in sql
    assert "decision_value  JSONB        NOT NULL" in sql
    assert "tenant_id       UUID         NOT NULL" in sql
    _assert_explicit_rls(sql, "decision_record")


def test_v79_outcome_record_links_decision_and_rls():
    """v79: جدول outcome_record يربط القياس بـdecision_id (فهرس) + RLS إلزاميّ."""
    sql = _read("migrations/v79_outcome_record.sql")
    assert "CREATE TABLE IF NOT EXISTS outcome_record" in sql
    assert "outcome_id      VARCHAR(40)  PRIMARY KEY" in sql
    assert "decision_id     VARCHAR(40)  NOT NULL" in sql
    # جوهر النَّسَب: فهرس decision_id (الانضمام Decision→Outcome) لا يُسقَط.
    assert "idx_outcome_record_decision ON outcome_record (decision_id)" in sql
    # لاتكرار قاعديّ: فهرس فريد جزئيّ على (tenant, idempotency_key) يحمي sample_count.
    assert "ux_outcome_record_idem" in sql
    assert "WHERE idempotency_key IS NOT NULL" in sql
    _assert_explicit_rls(sql, "outcome_record")


def test_no_hard_fk_bypassing_rls():
    """قرار تصميميّ صريح: لا قيد FK صلب من outcome_record إلى decision_record —
    قيد FK يتحقّق بصلاحيّة المالك متجاوزاً RLS؛ الربط ليّن عبر decision_id المفهرس."""
    sql = _read("migrations/v79_outcome_record.sql")
    assert "REFERENCES decision_record" not in sql
