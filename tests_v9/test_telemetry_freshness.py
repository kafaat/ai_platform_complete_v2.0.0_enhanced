"""عمر قراءة الحسّاس وقِدمها — تُحسَب في الخادم ولا تُعرَض قراءةٌ قديمة كأنّها حيّة.

العطلُ الذي وُجد هذا لأجله (2026-11-02): ``GET /api/v1/devices/{id}/telemetry`` كان يعيد القيمة
ووقتها فقط، وشاشة المراقبة الهجينة تسمّيها «القراءات الحيّة». فقراءةٌ عمرها يومان كانت تُقرأ
كأنّها الآن. صار كلّ صفٍّ يحمل ``age_sec`` و``stale`` بنافذة «online» نفسها (15 دقيقة).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _fresh(recorded_at, window_min=15):
    from api.device_models import telemetry_freshness

    return telemetry_freshness(recorded_at, NOW, window_min)


def test_a_reading_inside_the_online_window_is_not_stale():
    out = _fresh(NOW - timedelta(minutes=5))
    assert out == {"age_sec": 300, "stale": False, "stale_after_sec": 900}


def test_a_two_day_old_reading_is_stale():
    out = _fresh(NOW - timedelta(days=2))
    assert out["stale"] is True and out["age_sec"] == 2 * 86400


def test_the_boundary_is_inclusive_of_the_window():
    assert _fresh(NOW - timedelta(minutes=15))["stale"] is False
    assert _fresh(NOW - timedelta(minutes=15, seconds=1))["stale"] is True


def test_a_reading_without_a_time_is_stale_not_assumed_fresh():
    assert _fresh(None) == {"age_sec": None, "stale": True, "stale_after_sec": 900}


def test_a_future_reading_from_a_skewed_device_clock_has_zero_age():
    out = _fresh(NOW + timedelta(minutes=3))
    assert out["age_sec"] == 0 and out["stale"] is False


def test_the_route_attaches_freshness_from_the_online_window():
    src = open(os.path.join(CORE, "api/routers/devices.py"), encoding="utf-8").read()
    body = src[src.index('@router.get("/api/v1/devices/{device_id}/telemetry")') :]
    assert '**telemetry_freshness(r["recorded_at"], now, _DEVICE_ONLINE_WINDOW_MIN)' in body
