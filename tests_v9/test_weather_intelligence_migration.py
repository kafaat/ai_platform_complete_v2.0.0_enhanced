"""حارس هجرة طبقة ذكاء الطقس (v74) — يثبت التكيّف مع مخطّط/أمن SAHOOL.

البرومبت المرجعيّ افترض field_id UUID واتّصال postgres superuser — كلاهما يكسر SAHOOL
(field_id نصّ؛ superuser يتجاوز RLS = FINDING-001). هذا الحارس يُجمّد التصحيحات.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))
_V74 = os.path.join(BASE, "migrations", "v74_weather_intelligence.sql")


def _sql():
    with open(_V74, encoding="utf-8") as f:
        return f.read()


def test_in_manifest():
    with open(os.path.join(BASE, "migrations", "MANIFEST.txt"), encoding="utf-8") as f:
        assert "v74_weather_intelligence.sql" in f.read()


def test_field_id_is_text_not_uuid():
    """field_id نصّ (يطابق fields.field_id VARCHAR) — لا UUID (يكسر الربط)."""
    sql = _sql()
    # في الجداول المستأجَرة: field_id TEXT.
    assert re.search(r"field_id\s+TEXT\s+NOT NULL", sql)
    # لا يُعرَّف field_id كـUUID في أيّ مكان.
    assert not re.search(r"field_id\s+UUID", sql)
    # مصفوفة التنبيهات نصّيّة أيضاً.
    assert "field_ids" in sql and "TEXT[]" in sql


def test_tenant_tables_have_force_rls_and_current_setting():
    """الجداول المستأجَرة الثلاثة: ENABLE+FORCE RLS وسياسة تستند إلى current_setting."""
    sql = _sql()
    for tbl in ("field_weather_overlay", "weather_signals", "weather_alerts"):
        assert tbl in sql
    # تُطبَّق عبر حلقة FOREACH على الجداول الثلاثة.
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation" in sql
    assert "current_setting('app.current_tenant', true)" in sql


def test_overlay_pk_includes_tenant():
    """PK لـfield_weather_overlay يضمّ tenant_id (field_id ليس عالميّاً)."""
    sql = _sql()
    assert re.search(r"PRIMARY KEY \(tenant_id, field_id, time\)", sql)


def test_confidence_and_score_checks():
    """قيود [0,1]/[0,100] على الدرجات + confidence_score (تصحيحات المراجعة)."""
    sql = _sql()
    assert re.search(r"confidence_score\s+DOUBLE PRECISION\s+CHECK", sql)
    assert "spray_suitability_score" in sql and "BETWEEN 0 AND 1" in sql
    assert "trafficability_score" in sql and "BETWEEN 0 AND 100" in sql


def test_no_superuser_dsn_in_migration():
    """لا اتّصال postgres superuser في الهجرة (الكتابة عبر sahool_app)."""
    assert "postgres:password" not in _sql()
