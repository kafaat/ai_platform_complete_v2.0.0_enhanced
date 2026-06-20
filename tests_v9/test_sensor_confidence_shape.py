"""اختبارات نقيّة لطبقة ثقة الحسّاس + التوأم الرقميّ (api.sensor_confidence).

درجة صحّة شفّافة على الإشارات المتوفّرة فقط: الغائبة تُعلَن لا تُفترَض، جهاز بلا إشارة
unknown (needs_data)، والانقطاع/البَيات من العمر — لا تلفيق.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.sensor_confidence import score_device_health, shape_device_twin  # noqa: E402

_HOUR = 3600


def test_fresh_full_signals_is_healthy():
    out = score_device_health(
        {
            "device_id": "d1",
            "status": "online",
            "age_sec": 600,  # 10 دقائق
            "battery_pct": 90,
            "calibration_age_days": 30,
            "signal_quality": 0.95,
        }
    )
    assert out["level"] == "healthy"
    assert out["health_score"] >= 0.8
    assert out["missing_signals"] == []
    assert out["note_ar"] is None


def test_missing_signals_declared_not_assumed():
    # فقط النضارة متوفّرة ⇒ تُحسب عليها وحدها، والبقيّة تُعلَن غائبة (لا افتراض).
    out = score_device_health({"device_id": "d1", "status": "online", "age_sec": 300})
    assert out["health_score"] is not None
    assert set(out["missing_signals"]) == {"battery", "calibration", "signal"}
    assert "battery" in out["note_ar"]


def test_never_seen_is_unknown_needs_data():
    # لا age_sec ولا أيّ إشارة ⇒ unknown (الثقة غير محسوبة، لا صحّة افتراضيّة).
    out = score_device_health({"device_id": "d1", "status": "unknown"})
    assert out["level"] == "unknown"
    assert out["health_score"] is None
    assert "لا إشارة" in out["note_ar"]


def test_offline_status_overrides_score():
    out = score_device_health(
        {"device_id": "d1", "status": "offline", "age_sec": 300, "battery_pct": 100}
    )
    assert out["level"] == "offline"


def test_old_last_seen_is_stale_then_offline():
    stale = score_device_health({"device_id": "d1", "status": "online", "age_sec": 30 * _HOUR})
    assert stale["level"] == "stale"
    offline = score_device_health({"device_id": "d2", "status": "online", "age_sec": 96 * _HOUR})
    assert offline["level"] == "offline"


def test_low_battery_lowers_score():
    high = score_device_health(
        {"device_id": "d1", "status": "online", "age_sec": 300, "battery_pct": 95}
    )
    low = score_device_health(
        {"device_id": "d2", "status": "online", "age_sec": 300, "battery_pct": 8}
    )
    assert low["health_score"] < high["health_score"]


def test_signal_quality_accepts_0_100_scale():
    out = score_device_health(
        {"device_id": "d1", "status": "online", "age_sec": 300, "signal_quality": 80}
    )
    assert out["factors"]["signal"] == 0.8


def test_twin_summary_fleet_confidence_excludes_unknown():
    out = shape_device_twin(
        [
            {"device_id": "d1", "status": "online", "age_sec": 300, "battery_pct": 90},
            {"device_id": "d2", "status": "unknown"},  # بلا إشارة ⇒ unknown، لا يُحتسب
        ],
        generated_at="2026-06-20T12:00:00+00:00",
    )
    assert out["generated_at"] == "2026-06-20T12:00:00+00:00"
    assert out["device_count"] == 2
    assert out["scored_count"] == 1  # d2 unknown مُستبعَد من المتوسّط
    assert out["by_level"]["unknown"] == 1
    assert out["fleet_confidence"] is not None


def test_twin_empty_is_safe():
    out = shape_device_twin([])
    assert out["device_count"] == 0
    assert out["fleet_confidence"] is None
    assert out["provenance"]["calibrated"] == "not_applicable"
