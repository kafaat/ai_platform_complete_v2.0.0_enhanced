from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from operations import operation_suitability  # noqa: E402

pytestmark = pytest.mark.unit


def _complete(**over):
    base = {
        "temperature_c": 22.0,
        "humidity_pct": 55.0,
        "wind_speed_10m_kmh": 8.0,
        "wind_gusts_10m_kmh": 12.0,
        "precipitation_mm": 0.0,
    }
    base.update(over)
    return base


def test_missing_wind_makes_spraying_unsafe_not_falsely_safe():
    # المشهد الخطر: عيّنة بلا رياح إطلاقاً — سابقاً كانت رياح=0 ⇒ نافذة «آمنة» زوراً.
    sample = {"temperature_c": 22.0, "humidity_pct": 55.0, "precipitation_mm": 0.0}
    out = operation_suitability(sample, "spraying")
    assert out["status"] == "insufficient_data"
    assert out["safe"] is False
    assert out["suitability"] == "insufficient_data"
    assert "missing_wind" in out["limiting_factors"]


def test_missing_precip_fails_closed_for_spraying():
    sample = {"temperature_c": 22.0, "wind_speed_10m_kmh": 8.0}
    out = operation_suitability(sample, "spraying")
    assert out["status"] == "insufficient_data"
    assert out["safe"] is False
    assert "missing_precip" in out["limiting_factors"]


def test_wind_from_ms_field_is_accepted():
    # الرياح متاحة عبر m/s ⇒ ليست مفقودة (تحويل صحيح).
    sample = {"temperature_c": 22.0, "wind_speed_ms": 3.0, "precipitation_mm": 0.0}
    out = operation_suitability(sample, "spraying")
    assert out["status"] == "ok"  # 3 m/s = 10.8 km/h < 18 ⇒ لا عقوبة رياح


def test_high_wind_still_penalized_normally():
    # سلوك قائم غير مُتأثِّر بإصلاح الـfail-closed: رياح عالية تُعاقَب كالمعتاد.
    out = operation_suitability(
        _complete(wind_speed_10m_kmh=40.0, wind_gusts_10m_kmh=52.0), "spraying"
    )
    assert out["status"] == "ok"
    assert "wind_speed_high" in out["limiting_factors"]
    assert out["suitability"] == "poor"  # 1.0 - 0.45 - 0.25 = 0.30


def test_complete_calm_sample_is_safe_ok():
    out = operation_suitability(_complete(), "spraying")
    assert out["status"] == "ok"
    assert out["safe"] is True
    assert out["suitability"] in {"optimal", "acceptable"}


def test_irrigation_only_needs_precip_not_wind():
    # الريّ حرِجه المطر فقط — غياب الرياح لا يُفشِله.
    out = operation_suitability({"temperature_c": 20.0, "precipitation_mm": 0.0}, "irrigation")
    assert out["status"] == "ok"
