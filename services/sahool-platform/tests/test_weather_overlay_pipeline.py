"""اختبارات قلب weather-polygon-worker (core/weather_overlay_pipeline) — نقيّ.

يثبت أنّ تنبّؤ خلايا الحقل يتحوّل إلى سجلّ تراكب (مخطّط v74) + سجلّات إشارات صحيحة.
"""

from __future__ import annotations

import pytest
from core.weather_overlay_pipeline import build_overlay_record, build_signal_records

pytestmark = pytest.mark.unit


def _rows():
    # خليّتان (cell A/B) عبر 3 ساعات، رشّ ملائم (Δ-T/ريح ضمن النطاق، بلا مطر).
    rows = []
    for hour in range(3):
        for cell in ("A", "B"):
            rows.append(
                {
                    "hour": hour,
                    "cell_key": cell,
                    "temp_avg": 22,
                    "temp_min": 18,
                    "temp_max": 28,
                    "humidity": 60,
                    "wind_speed": 2.0,
                    "wind_gust": 5.0,
                    "precip_sum": 0.0,
                    "precip_prob": 5.0,
                    "et0": 0.3,
                    "delta_t": 4.0,
                }
            )
    return rows


def test_overlay_record_matches_v74_columns():
    rec = build_overlay_record("fld_1", "tenant-x", _rows())
    # أعمدة مخطّط v74 الأساسيّة موجودة.
    for col in (
        "field_id",
        "tenant_id",
        "temperature_max_c",
        "temperature_min_c",
        "spray_suitability_score",
        "disease_risk_score",
        "trafficability_score",
        "heat_stress_hours",
        "frost_risk_hours",
        "grid_cells_count",
        "spatial_coverage",
    ):
        assert col in rec
    assert rec["field_id"] == "fld_1" and rec["tenant_id"] == "tenant-x"
    assert rec["grid_cells_count"] == 2  # خليّتان مميّزتان
    assert rec["temperature_max_c"] == 28 and rec["temperature_min_c"] == 18
    assert rec["spray_suitability_score"] == 1.0  # كلّ الساعات صالحة للرشّ
    assert rec["precipitation_sum_mm"] == 0.0


def test_empty_rows_returns_none():
    assert build_overlay_record("f", "t", []) is None


def test_signals_built_from_overlay():
    rec = build_overlay_record("fld_1", "tenant-x", _rows())
    sigs = build_signal_records("fld_1", "tenant-x", rec)
    # رشّ ملائم ⇒ إشارة نافذة رشّ مفتوحة على الأقلّ.
    assert any(s["signal_type"] == "spray_window_open" for s in sigs)
    assert all(s["field_id"] == "fld_1" and s["tenant_id"] == "tenant-x" for s in sigs)
    assert all(0.0 <= s["confidence_score"] <= 1.0 for s in sigs)


def test_frost_overlay_yields_frost_signal():
    rows = [
        {"hour": h, "cell_key": "A", "temp_min": 0, "temp_max": 10, "precip_sum": 0.0}
        for h in range(4)
    ]
    rec = build_overlay_record("fld_2", "t", rows)
    assert rec["frost_risk_hours"] == 4
    sigs = build_signal_records("fld_2", "t", rec)
    assert any(s["signal_type"] == "frost_imminent" for s in sigs)
