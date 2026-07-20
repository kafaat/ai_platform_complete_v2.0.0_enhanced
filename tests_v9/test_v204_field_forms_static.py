"""حارس v204 الساكن (GAP-FIELD-FORMS-01) — يتحقّق من نصّ الهجرة قبل أيّ تشغيل حيّ.

درس «الحارس الساكن يفحص النصّ، والحيّ يفحص التنفيذ»: هذا يضمن بنية العقد حرفيًّا؛
براهين PG الحيّة (§14) تعمل على CI/staging بدور sahool_ingest الفعليّ.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "v204_field_forms.sql").read_text(encoding="utf-8")

TABLES = (
    "field_form_definitions",
    "field_form_versions",
    "field_form_assignments",
    "field_submissions",
)


def test_all_four_tables_created() -> None:
    for table in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in SQL, table


def test_rls_explicit_enable_force_policy_per_table() -> None:
    """RLS صريح (ENABLE+FORCE+DROP+CREATE) على كلّ جدول — لا يُكتفى بحلقة عامّة (درس v9)."""
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in SQL, table
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in SQL, table
        assert f"DROP POLICY IF EXISTS tenant_isolation ON {table}" in SQL, table
        assert f"CREATE POLICY tenant_isolation ON {table}" in SQL, table
    assert SQL.count("app.current_tenant") >= 8  # USING + WITH CHECK ×4


def test_no_hard_delete_revoked_and_triggered() -> None:
    """§6: حظر DELETE على الجدولين صلاحيّةً + بنيويًّا (دفاع عمق)، والتقاعد آلية الإزالة الوحيدة."""
    assert "REVOKE DELETE ON field_form_definitions FROM sahool_ingest" in SQL
    assert "REVOKE DELETE ON field_form_versions FROM sahool_ingest" in SQL
    assert "trg_field_form_definitions_no_delete" in SQL
    assert "trg_field_form_versions_no_delete" in SQL


def test_versions_state_machine_and_column_precise_immutability() -> None:
    body = SQL[SQL.index("field_form_versions_guard") :]
    # immutability بدقّة الأعمدة (لا منع UPDATE شامل — كان سيمنع التقاعد نفسه)
    for col in ("schema_json", "logic_json", "schema_hash", "validation_rules",
                "localization", "form_definition_id", "version_number"):
        assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in body, col
    # state machine: draft→published→retired فقط
    assert "draft' AND NEW.status = 'published" in body
    assert "published' AND NEW.status = 'retired" in body
    # write-once
    for col in ("retired_at", "retired_by", "retirement_reason", "retirement_mode"):
        assert f"{col} is write-once" in body, col
    # نشر ثانٍ مستحيل بنيويًّا
    assert "WHERE status = 'published'" in SQL
    assert "ux_field_form_versions_one_published" in SQL


def test_retirement_mode_check_consistency() -> None:
    assert "retirement_mode" in SQL
    assert re.search(r"status <> 'retired' AND retirement_mode IS NULL", SQL)
    assert re.search(r"status = 'retired' AND retirement_mode IS NOT NULL", SQL)


def test_composite_tenant_fks_and_unique_tenant_id() -> None:
    """نمط v201: UNIQUE(tenant_id,id) على كلّ جدول + FKs مركّبة عند كلّ مرجع."""
    for table in TABLES:
        assert f"ux_{table}_tenant_id" in SQL, table
    assert "REFERENCES field_form_definitions (tenant_id, id)" in SQL
    assert "REFERENCES field_form_versions (tenant_id, id)" in SQL
    assert "REFERENCES external_submissions (tenant_id, id)" in SQL
    assert "REFERENCES field_form_assignments (tenant_id, id)" in SQL
    assert "ux_external_submissions_tenant_id" in SQL


def test_envelope_unique_simple_no_idempotency_column() -> None:
    """UNIQUE(envelope_id) بسيط (one-to-one) + لا عمود idempotency_key (ديدوب B1 حصرًا)."""
    assert re.search(r"CREATE UNIQUE INDEX.*ux_field_submissions_envelope\s+ON field_submissions \(envelope_id\)", SQL)
    block = SQL[SQL.index("CREATE TABLE IF NOT EXISTS field_submissions") :]
    block = block[: block.index(");")]
    assert "idempotency_key" not in block
    assert "unknown_quarantined" not in block  # الإصدار المجهول لا صفّ له (§12.1)
    assert "form_version_id" in block and "NOT NULL" in block


def test_grants_target_runtime_role_sahool_ingest() -> None:
    assert "rolname = 'sahool_ingest'" in SQL
    assert "GRANT SELECT, INSERT ON field_submissions TO sahool_ingest" in SQL


def test_manifest_and_ownership_registered() -> None:
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "v204_field_forms.sql" in manifest
    ownership = (ROOT / "docs" / "architecture" / "db_ownership.yml").read_text(encoding="utf-8")
    for table in TABLES:
        assert table in ownership, table


def test_assignments_revision_guard() -> None:
    assert "field_form_assignments_revision_guard" in SQL
    assert "revision may not decrease" in SQL
