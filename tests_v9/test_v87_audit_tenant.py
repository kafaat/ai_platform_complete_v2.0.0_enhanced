"""حارس مُركَّز لهجرة v87 — audit_log: tenant_id + RLS مُنطّق بالمستأجِر (الحوكمة #407).

يتأكّد أنّ الهجرة تُضيف عمود tenant_id، وتطبّق FORCE ROW LEVEL SECURITY (دفاع عمق
يُخضِع مالك الجدول)، وأنّ سياسة USING مُنطّقة بالمستأجِر فعلاً (لا «المدير يرى الكلّ»
المطلق القديم). انحدار أيّ منها يكشف سجلّ التدقيق عبر المستأجرين ⇒ يُرصَد هنا.
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "migrations" / "v87_audit_log_tenant.sql"


@pytest.mark.unit
@pytest.mark.security
def test_v87_migration_exists_and_in_manifest():
    assert MIGRATION.exists(), "هجرة v87_audit_log_tenant.sql مفقودة"
    manifest = (REPO_ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "v87_audit_log_tenant.sql" in manifest, "v87 غير مُدرَجة في MANIFEST.txt"


@pytest.mark.unit
@pytest.mark.security
def test_v87_adds_tenant_id_and_forces_rls():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+tenant_id\s+UUID", sql, re.I), (
        "v87 لا تضيف عمود tenant_id UUID"
    )
    assert re.search(r"ALTER TABLE\s+audit_log\s+FORCE ROW LEVEL SECURITY", sql, re.I), (
        "v87 لا تطبّق FORCE ROW LEVEL SECURITY (دفاع عمق مفقود)"
    )
    assert re.search(r"ALTER TABLE\s+audit_log\s+ENABLE ROW LEVEL SECURITY", sql, re.I), (
        "v87 لا تُفعّل RLS"
    )


@pytest.mark.unit
@pytest.mark.security
def test_v87_policy_is_tenant_scoped():
    sql = MIGRATION.read_text(encoding="utf-8")
    # سياسة جديدة على audit_log
    assert re.search(r"CREATE POLICY\s+\w+\s+ON\s+audit_log", sql, re.I), (
        "v87 لا تُنشئ سياسة على audit_log"
    )
    # شرط المستأجِر صريح في الـUSING (المستأجِر يرى صفوفه فقط)
    assert re.search(
        r"tenant_id::TEXT\s*=\s*current_setting\(\s*'app\.current_tenant'", sql, re.I
    ), "سياسة v87 ليست مُنطّقة بالمستأجِر (شرط tenant_id مفقود)"
    # WITH CHECK لعزل الكتابة
    assert re.search(r"WITH CHECK", sql, re.I), "v87 بلا WITH CHECK لعزل الكتابة"
