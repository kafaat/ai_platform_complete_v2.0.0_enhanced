"""اختبارات نواة GDD الموحَّدة + العقد + الطريقتان (WS-C.1c) — لا خلط صامت.

يُثبِت أنّ **المحرّك** يملك نواة GDD اليوميّة، وأنّ العقد يُصرّح بالعتبات المُستخدَمة
وفترة الصلاحيّة والإصدار، وأنّ السياسة (base) من المُستهلِك لا تُختلق.
"""

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

from gdd import METHODS, accumulate_gdd, gdd_agro_product, gdd_daily  # noqa: E402

main = importlib.import_module("main")

pytestmark = pytest.mark.unit


def test_daily_modified_clamps_tmin_to_base():
    # tmin=5 < base=10 ⇒ يُقصّ لـ10؛ tmax=30 ⇒ mean=(30+10)/2=20 ⇒ 20-10=10.
    assert gdd_daily(t_max_c=30.0, t_min_c=5.0, base_c=10.0, method="modified") == 10.0


def test_daily_simple_does_not_clamp_tmin():
    # simple: mean=(30+5)/2=17.5 ⇒ 17.5-10=7.5 (لا قصّ لـtmin).
    assert gdd_daily(t_max_c=30.0, t_min_c=5.0, base_c=10.0, method="simple") == 7.5


def test_daily_upper_cutoff_caps_tmax():
    # سقف 28 ⇒ tmax يُقصّ لـ28؛ modified: mean=(28+18)/2=23 ⇒ 23-10=13.
    assert gdd_daily(t_max_c=35.0, t_min_c=18.0, base_c=10.0, upper_cutoff_c=28.0) == 13.0


def test_daily_all_below_base_is_zero():
    assert gdd_daily(t_max_c=8.0, t_min_c=2.0, base_c=10.0, method="modified") == 0.0


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        gdd_daily(t_max_c=30.0, t_min_c=18.0, base_c=10.0, method="bogus")
    assert "modified" in METHODS and "simple" in METHODS


def test_accumulate_skips_non_finite_not_fabricated():
    daily, total, counted = accumulate_gdd(
        daily_t_min=[18.0, float("nan"), 20.0],
        daily_t_max=[30.0, 32.0, 34.0],
        base_c=10.0,
    )
    assert daily[1] is None  # مفقود ≠ صفر
    assert counted == 2
    assert total == round(daily[0] + daily[2], 3)


def test_product_contract_full():
    out = gdd_agro_product(
        daily_t_min=[18.0, 19.0, 20.0],
        daily_t_max=[30.0, 31.0, 32.0],
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
        start_date="2026-03-01",
        end_date="2026-03-03",
    )
    assert out["product"] == "gdd"
    assert out["calculation_version"] == "gdd/daily/1.0.0"
    assert out["unit"] == "degC-day"
    assert len(out["daily_gdd"]) == 3
    assert out["accumulated_gdd"] == round(sum(out["daily_gdd"]), 3)
    assert out["thresholds_used"] == {"base_c": 10.0, "upper_cutoff_c": 30.0, "method": "modified"}
    assert out["valid_period"] == {"start_date": "2026-03-01", "end_date": "2026-03-03", "days": 3}
    assert out["quality_status"] == "validated"


def test_product_missing_base_is_insufficient_not_assumed():
    out = gdd_agro_product(daily_t_min=[18.0], daily_t_max=[30.0], base_c=None)
    assert out["quality_status"] == "insufficient"
    assert out["accumulated_gdd"] is None
    assert any("base_c" in lim for lim in out["limitations"])


def test_product_degraded_when_some_days_missing():
    out = gdd_agro_product(
        daily_t_min=[18.0, None, 20.0],
        daily_t_max=[30.0, 32.0, 34.0],
        base_c=10.0,
    )
    assert out["quality_status"] == "degraded"
    assert out["input_completeness"] == round(2 / 3, 3)


def test_route_agro_gdd_returns_contract():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/gdd",
        json={
            "daily_t_min": [18.0, 19.0],
            "daily_t_max": [30.0, 31.0],
            "base_c": 10.0,
            "upper_cutoff_c": 30.0,
            "method": "modified",
            "start_date": "2026-03-01",
            "end_date": "2026-03-02",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == "gdd"
    assert body["accumulated_gdd"] is not None
    assert body["thresholds_used"]["method"] == "modified"


def test_route_missing_base_no_5xx():
    client = TestClient(main.app)
    resp = client.post("/v1/weather/agro/gdd", json={"daily_t_min": [18.0], "daily_t_max": [30.0]})
    assert resp.status_code == 200
    assert resp.json()["quality_status"] == "insufficient"
