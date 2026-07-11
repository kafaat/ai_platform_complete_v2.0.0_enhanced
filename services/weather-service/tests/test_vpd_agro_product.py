"""اختبارات منتج VPD كـView مُشتقّ من CanonicalWeatherState عبر HTTP (WX-10.3).

يتحقّق أنّ ``POST /v1/weather/agro/vpd`` يشتقّ VPD من الحالة الكنسيّة (لا حساب مباشر) ويعيد
كامل عقد VPD حرفيّاً + نَسَب الحالة (derived_from/canonical_state_id/canonical_state_version/
source_snapshot_id/weather_snapshot_id). نقيّ حتميّ ⇒ لا 5xx.
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

from vpd import compute_vpd  # noqa: E402

main = importlib.import_module("main")

pytestmark = pytest.mark.unit


def test_route_agro_vpd_returns_full_contract_and_lineage():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/vpd",
        json={
            "t_max_c": 34.0,
            "t_min_c": 18.0,
            "rh_mean_pct": 45.0,
            "valid_time": "2026-07-10T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # عقد VPD القديم محفوظ حرفيّاً (byte-compatible مع النواة).
    direct = compute_vpd(t_max_c=34.0, t_min_c=18.0, rh_mean_pct=45.0, dew_point_c=None)
    for k in (
        "product",
        "vpd_kpa",
        "raw_vpd_kpa",
        "es_kpa",
        "ea_kpa",
        "method",
        "input_completeness",
        "input_consistency",
        "quality_status",
        "quality_flags",
        "limitations",
        "cross_check",
        "formula_version",
    ):
        assert body[k] == direct[k], k
    # نَسَب الحالة مضاف عبر HTTP.
    assert body["derived_from"] == "canonical_weather_state"
    assert isinstance(body["canonical_state_id"], str) and body["canonical_state_id"]
    assert body["canonical_state_version"]
    # بلا override: نَسَب الحالة = weather_snapshot_id للـView.
    assert body["source_snapshot_id"] == body["weather_snapshot_id"]


def test_route_agro_vpd_snapshot_override_coherent_over_http():
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/vpd",
        json={
            "t_max_c": 34.0,
            "t_min_c": 18.0,
            "rh_mean_pct": 45.0,
            "weather_snapshot_id": "consumer-vpd-snap",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_snapshot_id"] == "consumer-vpd-snap"
    assert body["weather_snapshot_id"] == "consumer-vpd-snap"


def test_route_agro_vpd_insufficient_no_5xx():
    # نقص مصدر الرطوبة ⇒ insufficient صريح (200، vpd_kpa=None) لا 5xx.
    client = TestClient(main.app)
    resp = client.post("/v1/weather/agro/vpd", json={"t_max_c": 30.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["quality_status"] == "insufficient"
    assert body["vpd_kpa"] is None
    assert body["derived_from"] == "canonical_weather_state"
