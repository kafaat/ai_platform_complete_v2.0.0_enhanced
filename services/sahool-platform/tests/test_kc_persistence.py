"""اختبارات الرابط النقيّ لتخزين Kc (kc_persistence) — بناء الصفّ + مقارنة المواسم.

المسار الحيّ للقاعدة (INSERT/SELECT عبر tenant_connection) مُغطّى بـIntegration Tests
(تطبّق هجرة v76 وتفرض RLS). هنا نختبر المنطق النقيّ فقط: بناء صفّ مطابق لمخطّط v76،
رفض السيناريو غير الصالح، ومقارنة موسمين None-آمنة.
"""

from __future__ import annotations

import pytest
from core.kc_extraction_engine import FaoStageKc
from core.kc_persistence import KC_SCENARIOS, build_kc_record, compare_kc_rows

pytestmark = pytest.mark.unit


def _stage(kc_ini=0.4, kc_mid=1.1, kc_end=0.5):
    return FaoStageKc(
        kc_ini=kc_ini, kc_mid=kc_mid, kc_end=kc_end, kcb_ini=0.15, kcb_mid=1.0, kcb_end=0.3
    )


def test_build_kc_record_matches_v76_columns():
    rec = build_kc_record(
        _stage(),
        field_id="fld_1",
        tenant_id="t-1",
        crop_id="wheat",
        season_id="2026",
        scenario_type="potential",
        cfet=1.15,
    )
    for col in (
        "tenant_id",
        "field_id",
        "crop_id",
        "season_id",
        "scenario_type",
        "kc_ini",
        "kc_mid",
        "kc_end",
        "kcb_ini",
        "kcb_mid",
        "kcb_end",
        "cfet",
        "source",
    ):
        assert col in rec
    assert rec["field_id"] == "fld_1" and rec["tenant_id"] == "t-1"
    assert rec["kc_mid"] == 1.1 and rec["cfet"] == 1.15
    assert rec["scenario_type"] == "potential"


def test_build_kc_record_missing_stage_stays_none():
    rec = build_kc_record(
        _stage(kc_end=None), field_id="f", tenant_id="t", crop_id="c", season_id="s"
    )
    assert rec["kc_end"] is None  # لا اختلاق


def test_build_kc_record_rejects_invalid_scenario():
    with pytest.raises(ValueError, match="scenario_type"):
        build_kc_record(
            _stage(),
            field_id="f",
            tenant_id="t",
            crop_id="c",
            season_id="s",
            scenario_type="bogus",
        )


def test_scenarios_constant_matches_check_values():
    assert KC_SCENARIOS == {"potential", "actual", "full_irrigation", "deficit"}


def test_compare_kc_rows_detects_rising_mid():
    cur = build_kc_record(
        _stage(kc_mid=1.2), field_id="f", tenant_id="t", crop_id="wheat", season_id="2026"
    )
    prev = build_kc_record(
        _stage(kc_mid=1.0), field_id="f", tenant_id="t", crop_id="wheat", season_id="2025"
    )
    out = compare_kc_rows(cur, prev)
    assert out["stages"]["kc_mid"]["direction"] == "up"
    assert out["stages"]["kc_mid"]["delta"] == pytest.approx(0.2)
    assert "أعلى" in out["verdict_ar"]
    assert out["current_season_id"] == "2026" and out["previous_season_id"] == "2025"


def test_compare_kc_rows_none_safe():
    cur = build_kc_record(
        _stage(kc_mid=None), field_id="f", tenant_id="t", crop_id="c", season_id="2026"
    )
    prev = build_kc_record(
        _stage(kc_mid=1.0), field_id="f", tenant_id="t", crop_id="c", season_id="2025"
    )
    out = compare_kc_rows(cur, prev)
    assert out["stages"]["kc_mid"]["delta"] is None
    assert out["stages"]["kc_mid"]["direction"] == "flat"
    assert "تعذّر" in out["verdict_ar"]
