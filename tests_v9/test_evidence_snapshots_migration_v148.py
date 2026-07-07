"""حارس ساكن — ترحيل v148 (field_evidence_snapshots): RLS + فهارس + تسجيل بالمُشغّلَين.

لا يمكن اختبار العزل بالمستأجِر تكامليّاً هنا (يحتاج Postgres)، فنُثبّت ساكناً أنّ:
- الجدول يُنشأ بـFORCE RLS + سياسة tenant_isolation عبر current_setting (نمط v140/v144).
- فهرسا (tenant/field/زمن) و(GIN على الرسم) موجودان.
- الترحيل مُسجَّل في MANIFEST **و** run_migrations.sql (يمنع فشل بوّابة الإنتاج).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MIG = REPO / "migrations" / "v148_field_evidence_snapshots.sql"


def _sql() -> str:
    return MIG.read_text(encoding="utf-8")


def test_table_has_force_rls_and_tenant_policy():
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS field_evidence_snapshots" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON field_evidence_snapshots" in sql
    # العزل عبر app.current_tenant (نمط v140/v144 الحرفيّ) — USING + WITH CHECK.
    assert "current_setting('app.current_tenant', true)" in sql
    assert "WITH CHECK" in sql


def test_required_indexes_present():
    sql = _sql()
    assert "idx_field_evidence_snapshots_tenant_field_time" in sql
    assert "USING GIN (evidence_graph)" in sql


def test_no_secret_columns_stored():
    # أمن: لا أعمدة أسرار/توكنات في مخطّط اللقطة (التنقية في الكاتب أيضاً).
    sql = _sql().lower()
    for bad in ("password", "token", "secret", "credential"):
        assert bad not in sql


def test_registered_in_both_migration_runners():
    manifest = (REPO / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    run = (REPO / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v148_field_evidence_snapshots.sql" in manifest
    assert "v148_field_evidence_snapshots.sql" in run
