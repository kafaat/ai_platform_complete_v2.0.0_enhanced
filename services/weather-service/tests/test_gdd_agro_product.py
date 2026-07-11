"""WX-10.4 — GDD View عبر HTTP (POST /v1/weather/agro/gdd): parity + نَسَب + تغطية.

يتحقّق أنّ العقد القديم byte-compatible عبر HTTP، مع حقول النَّسَب التراكميّة والتغطية
المُضافة، وأنّ الطلب القديم (بلا daily_dates) يبقى محفوظ السلوك.
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

from gdd import gdd_agro_product  # noqa: E402

main = importlib.import_module("main")

pytestmark = pytest.mark.unit


def test_route_agro_gdd_legacy_request_is_byte_compatible():
    # طلب قديم (بلا daily_dates) ⇒ عقد GDD القديم محفوظ حرفيّاً + نَسَب/تغطية مُضافة.
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "")
    client = TestClient(main.app)
    payload = {
        "daily_t_min": [12.0, 14.0, 16.0],
        "daily_t_max": [26.0, 28.0, 30.0],
        "base_c": 10.0,
        "upper_cutoff_c": 30.0,
        "method": "modified",
        "start_date": "2026-04-01",
        "end_date": "2026-04-03",
    }
    resp = client.post("/v1/weather/agro/gdd", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    direct = gdd_agro_product(
        daily_t_min=payload["daily_t_min"],
        daily_t_max=payload["daily_t_max"],
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
        start_date="2026-04-01",
        end_date="2026-04-03",
    )
    for k in ("daily_gdd", "accumulated_gdd", "thresholds_used", "valid_period", "quality_status"):
        assert body[k] == direct[k], k
    # نَسَب تراكميّ + تغطية عبر HTTP.
    assert body["derived_from"] == "canonical_daily_weather_series"
    assert body["gdd_lineage_id"].startswith("gddseq/")
    assert len(body["contributing_state_ids"]) == 3
    assert body["coverage"]["observed_days"] == 3


def test_route_agro_gdd_dated_gap_reflected_in_coverage():
    # daily_dates بفجوة (يومان من 3) ⇒ coverage يُظهر النقص + series_quality لا validated.
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/gdd",
        json={
            "daily_t_min": [12.0, 16.0],
            "daily_t_max": [26.0, 28.0],
            "daily_dates": ["2026-04-01", "2026-04-03"],
            "base_c": 10.0,
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["coverage"]["expected_days"] == 3
    assert body["coverage"]["observed_days"] == 2
    assert body["coverage"]["missing_days"] == 1
    assert body["series_quality_status"] == "degraded_incomplete_coverage"


def test_route_agro_gdd_per_day_snapshot_ids_in_lineage():
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/gdd",
        json={
            "daily_t_min": [12.0, 14.0],
            "daily_t_max": [26.0, 28.0],
            "daily_dates": ["2026-04-01", "2026-04-02"],
            "daily_snapshot_ids": ["snap-d1", "snap-d2"],
            "base_c": 10.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contributing_state_ids"] == ["snap-d1", "snap-d2"]


def test_route_agro_gdd_missing_base_c_insufficient_no_5xx():
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/gdd",
        json={"daily_t_min": [12.0], "daily_t_max": [26.0], "start_date": "2026-04-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["quality_status"] == "insufficient"


def test_route_agro_gdd_length_mismatch_is_byte_compatible():
    # فجوة مراجعة المستخدم: طلب قديم بطولين مختلفين ⇒ العقد == النواة القديمة تماماً،
    # incl. limitations + valid_period.days.
    client = TestClient(main.app)
    payload = {
        "daily_t_min": [10.0, 11.0, 12.0],
        "daily_t_max": [20.0, 21.0],
        "base_c": 5.0,
        "start_date": "2026-04-01",
        "end_date": "2026-04-03",
    }
    resp = client.post("/v1/weather/agro/gdd", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    direct = gdd_agro_product(
        daily_t_min=payload["daily_t_min"],
        daily_t_max=payload["daily_t_max"],
        base_c=5.0,
        start_date="2026-04-01",
        end_date="2026-04-03",
    )
    for k in ("daily_gdd", "accumulated_gdd", "limitations", "valid_period", "quality_status"):
        assert body[k] == direct[k], k
    assert any("length mismatch" in lim for lim in body["limitations"])
    # التشخيصات تُفصح عن الأطوال الأصليّة (3 مقابل 2).
    assert body["diagnostics"]["input_t_min_count"] == 3
    assert body["diagnostics"]["input_t_max_count"] == 2


def test_route_agro_gdd_invalid_dates_surface_in_diagnostics():
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/gdd",
        json={
            "daily_t_min": [10.0, 11.0],
            "daily_t_max": [20.0, 21.0],
            "daily_dates": ["2026-04-01", "not-a-date"],
            "base_c": 5.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # يوم بتاريخ فاسد أُسقِط ⇒ يظهر في invalid_records (لا إخفاء صامت).
    assert body["diagnostics"]["invalid_records"] == 1
    assert body["coverage"]["observed_days"] == 1
