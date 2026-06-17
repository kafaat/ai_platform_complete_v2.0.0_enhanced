"""حارس RLS للجداول المعزولة بمفتاح أجنبيّ (MEDIUM-009 من التدقيق الخارجيّ).

حارس test_rls_tenant_coverage يفحص الجداول ذات عمود tenant_id فقط. لكنّ بعض الجداول
تحمل بيانات لكلّ مستأجِر بلا عمود tenant_id (تُعزَل عبر مفتاح أجنبيّ للأب) — فتفوته.
استعلام مباشر عليها يُسرِّب صفوف مستأجِرين آخرين ما لم تُحمَ بـRLS مبنيّة على الأب.

هذا الحارس (ثابت، بلا قاعدة) يُلزم v71 بتفعيل RLS+FORCE+سياسة tenant_isolation على
field_lifecycle_transitions، ويوثّق أنّ weather_automation_locations عالميّ عمداً.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))
_V71 = os.path.join(BASE, "migrations", "v71_rls_missing_tables.sql")


def _v71() -> str:
    with open(_V71, encoding="utf-8") as f:
        return f.read()


def test_v71_exists_in_manifest():
    with open(os.path.join(BASE, "migrations", "MANIFEST.txt"), encoding="utf-8") as f:
        assert "v71_rls_missing_tables.sql" in f.read(), "v71 غير مُدرَج في MANIFEST"


def test_field_lifecycle_transitions_rls_enabled():
    sql = _v71()
    assert "ALTER TABLE field_lifecycle_transitions ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE field_lifecycle_transitions FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON field_lifecycle_transitions" in sql


def test_field_lifecycle_transitions_isolates_via_parent_tenant():
    """العزل عبر الأب field_lifecycle.tenant_id بالمفتاح الأجنبيّ lifecycle_id."""
    sql = _v71()
    # USING يربط lifecycle_id بـfield_lifecycle.tenant_id تحت سياق المستأجِر.
    assert "FROM field_lifecycle fl" in sql
    assert "fl.lifecycle_id = field_lifecycle_transitions.lifecycle_id" in sql
    assert "current_setting('app.current_tenant', true)" in sql


def test_with_check_allows_system_writes_no_context():
    """WITH CHECK يسمح كتابة النظام/الهجرات بلا سياق (لا يكسر) — كنمط الحارس الموحّد."""
    sql = _v71()
    assert "NULLIF(current_setting('app.current_tenant', true), '') IS NULL" in sql


def test_weather_locations_documented_global_not_rls():
    """weather_automation_locations عابر للمستأجرين بالتصميم (مجدوِل) ⇒ لا RLS عليه،
    موثّق صراحةً (لئلّا يُضاف لاحقاً فيكسر المجدوِل)."""
    sql = _v71()
    assert "weather_automation_locations" in sql  # مذكور
    # لا تُفعَّل RLS عليه في هذا الملفّ.
    assert "ALTER TABLE weather_automation_locations ENABLE ROW LEVEL SECURITY" not in sql
