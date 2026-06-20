"""اختبار المعايرة الإقليميّة المُدارة DB-backed (البند 3) — الجزء النقيّ + حارس الهجرة.

apply_region_override يطبّق تجاوزات مُتحقَّقة فوق القاعدة (get_calibration) نقيّاً؛ ومسار
الإدامة (calibration_override، RLS) تكامليّ يتطلّب Postgres. هنا نتحقّق من المنطق الحتميّ
وبنية الهجرة بلا قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.calibration import apply_region_override  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_no_override_is_inherited():
    """تجاوزات فارغة ⇒ القاعدة الموروثة كما هي (validated=false، لا تطبيق)."""
    out = apply_region_override("ibb", {})
    assert out["override_source"] == "inherited"
    assert out["override_applied"] == []
    assert out["validated"] is False


def test_override_applies_only_passed_fields():
    """يطبّق الحقول المُمرَّرة فقط ويضبط validated + evidence_level + المصدر (لا تلفيق)."""
    out = apply_region_override(
        "jawf",
        {"raw_fraction": 0.55, "root_depth_m": 1.2},
        source_ar="قياس حقول الجوف 2026",
    )
    assert out["raw_fraction"] == 0.55
    assert out["root_depth_m"] == 1.2
    assert out["validated"] is True
    assert out["override_source"] == "db_override"
    assert set(out["override_applied"]) == {"raw_fraction", "root_depth_m"}
    assert out["evidence_level"] == "expert_opinion"  # كان none ⇒ يُرفَع برأي خبير
    assert out["source_ar"] == "قياس حقول الجوف 2026"


def test_override_ignores_none_values():
    """قيمة None لا تُطبَّق (صدق: لا تطغى على القاعدة بقيمة غائبة)."""
    out = apply_region_override("ibb", {"raw_fraction": None, "kc_dyn_max": 1.15})
    assert out["override_applied"] == ["kc_dyn_max"]
    assert out["kc_dyn_max"] == 1.15


def test_v80_migration_table_and_rls():
    """v80: جدول calibration_override بـUNIQUE(tenant,region) + RLS صريح معزول."""
    sql = _read("migrations/v80_calibration_override.sql")
    assert "CREATE TABLE IF NOT EXISTS calibration_override" in sql
    assert "UNIQUE (tenant_id, region)" in sql
    assert "override_values JSONB        NOT NULL" in sql
    # عزل المستأجِر الصريح (يطابق sahool_inspector/test_rls).
    assert "ALTER TABLE calibration_override ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE calibration_override FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON calibration_override" in sql
    assert "current_setting('app.current_tenant', true)" in sql
