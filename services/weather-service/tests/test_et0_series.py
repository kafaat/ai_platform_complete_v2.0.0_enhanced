"""اختبارات سلسلة ET0 الدفعيّة (WS-C.1b) — أساس ترحيل المحاكاة عن نواة ET0 المحلّيّة."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from et0 import compute_et0, et0_series_product  # noqa: E402

main = importlib.import_module("main")

pytestmark = pytest.mark.unit


def test_series_matches_per_day_compute():
    tmins = [16.0, 17.0, 18.0]
    tmaxs = [30.0, 31.0, 32.0]
    out = et0_series_product(
        daily_t_min=tmins, daily_t_max=tmaxs, lat_deg=15.5, day_of_year_start=100
    )
    # كلّ يوم يطابق compute_et0 المفرد (لا مسار حساب ثانٍ).
    for i in range(3):
        one = compute_et0(t_max_c=tmaxs[i], t_min_c=tmins[i], lat_deg=15.5, day_of_year=100 + i)
        assert out["daily_et0_mm"][i] == one["et0_mm"]
    assert out["accumulated_et0_mm"] == round(sum(out["daily_et0_mm"]), 3)
    assert out["days"] == 3 and out["days_computed"] == 3


def test_series_missing_day_is_none_not_fabricated():
    out = et0_series_product(
        daily_t_min=[16.0, None, 18.0],
        daily_t_max=[30.0, 31.0, 32.0],
        lat_deg=15.5,
        day_of_year_start=100,
    )
    assert out["daily_et0_mm"][1] is None  # حرارة ناقصة ⇒ None لا صفر
    assert out["days_computed"] == 2


def test_series_insufficient_without_geography():
    out = et0_series_product(daily_t_min=[16.0], daily_t_max=[30.0], lat_deg=None)
    assert out["daily_et0_mm"][0] is None  # لا lat/doy ⇒ insufficient
    assert out["days_computed"] == 0


def test_route_et0_series_contract():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/et0/series",
        json={
            "daily_t_min": [16.0, 17.0],
            "daily_t_max": [30.0, 31.0],
            "lat_deg": 15.5,
            "day_of_year_start": 100,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == "et0_series"
    assert len(body["daily_et0_mm"]) == 2
    assert body["accumulated_et0_mm"] is not None
