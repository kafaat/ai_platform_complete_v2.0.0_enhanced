"""حارس شريحة الطقس (HIGH-002، إغلاق): RLS على جداول الطقس + المجدوِل على دور المهامّ.

نفس نمط event_outbox (#332): الجداول العابرة للمستأجرين تُعزَل بـRLS (فيُحمى التطبيق)،
والمجدوِل وحده يتجاوز عبر sahool_jobs (مسبح المهامّ).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))


def _read(p):
    with open(os.path.join(BASE, p), encoding="utf-8") as f:
        return f.read()


def test_v73_in_manifest():
    assert "v73_weather_automation_rls.sql" in _read("migrations/MANIFEST.txt")


def test_weather_locations_force_rls_via_field():
    """weather_automation_locations: RLS+FORCE معزولة عبر field_id→fields (NULL=عالميّ)."""
    sql = _read("migrations/v73_weather_automation_rls.sql")
    assert "ALTER TABLE weather_automation_locations ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE weather_automation_locations FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON weather_automation_locations" in sql
    assert "field_id IS NULL" in sql  # المواقع العالميّة مرئيّة
    assert "FROM fields f" in sql


def test_weather_cache_force_rls_inherits_location():
    """weather_automation_cache: RLS+FORCE يرث رؤية موقعه (location_key ضمن المرئيّة)."""
    sql = _read("migrations/v73_weather_automation_rls.sql")
    assert "ALTER TABLE weather_automation_cache ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE weather_automation_cache FORCE ROW LEVEL SECURITY" in sql
    assert "location_key IN (SELECT location_key FROM weather_automation_locations)" in sql


def test_weather_scheduler_uses_jobs_pool():
    """مجدوِل الطقس على مسبح المهامّ (sahool_jobs) — وإلّا تكسره RLS الجديدة."""
    src = _read("services/sahool-platform/api/main.py")
    assert "weather_automation.set_pool(_JOBS_POOL or _DB_POOL)" in src, (
        "مجدوِل الطقس لا يستعمل مسبح المهامّ ⇒ يقرأ عابراً بدور معزول فيفشل تحت RLS v73"
    )
