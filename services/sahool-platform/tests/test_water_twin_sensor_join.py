"""وصلةُ الحسّاس في راوتر توأم المياه — `SOIL-MOISTURE-UNIT-IDENTITY-01`.

المنطقُ الصرف مقيسٌ في `tests_v9/test_soil_moisture_unit_identity.py`؛ هنا يُقاس
التركيبُ داخل الراوتر (`_join_sensor`): θFC من قوام الطلب، Zr من اشتقاق TAW، العمرُ
من `recorded_at`، والسقفُ من سجلّ الأجهزة — بلا قاعدة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from api.routers.water_twin import FieldWaterTwinRequest, _join_sensor
from api.soil_telemetry import SoilMoistureReading

pytestmark = pytest.mark.unit


def _reading(unit: str, kind: str, *, age: timedelta = timedelta(minutes=10), pct: float = 25.0):
    return SoilMoistureReading(
        value_pct=pct,
        recorded_at=datetime.now(UTC) - age,
        device_id="dev_1",
        unit=unit,
        unit_kind=kind,
    )


def test_a_fresh_vwc_reading_is_converted_through_the_request_texture_and_derived_zr():
    out = _join_sensor(
        _reading("vwc_pct", "vwc_pct"),
        40.0,
        "ledger.depletion_mm",
        100.0,
        {"taw_source": "dynamic_zr", "root_depth_m": 0.6},
        FieldWaterTwinRequest(texture="clay loam"),  # θFC = 0.32
    )
    assert out["source"] == "ledger.depletion_mm" and out["depletion_mm"] == 40.0
    assert out["sensor"]["depletion_mm"] == pytest.approx(42.0)
    assert out["sensor"]["stale"] is False and out["sensor"]["age_s"] < 4 * 3600
    assert out["delta_mm"] == pytest.approx(2.0)
    assert out["limitations"] == []


def test_an_explicit_taw_request_has_no_zr_so_vwc_cannot_be_converted():
    out = _join_sensor(
        _reading("vwc_pct", "vwc_pct"),
        None,
        "unavailable",
        100.0,
        {"taw_source": "request", "root_depth_m": None},
        FieldWaterTwinRequest(taw_mm=100.0),
    )
    assert out["depletion_mm"] is None and out["source"] == "unavailable"
    assert "soil_moisture_sensor_conversion_inputs_missing" in out["limitations"]


def test_a_stale_reading_uses_the_registry_bound_not_a_router_constant():
    out = _join_sensor(
        _reading("vwc_pct", "vwc_pct", age=timedelta(hours=5)),
        None,
        "unavailable",
        100.0,
        {"taw_source": "dynamic_zr", "root_depth_m": 0.6},
        FieldWaterTwinRequest(texture="clay loam"),
    )
    assert out["sensor"]["stale"] is True
    assert out["depletion_mm"] is None
    assert "soil_moisture_sensor_reading_stale" in out["limitations"]


def test_a_bare_percent_reading_is_published_but_never_converted():
    out = _join_sensor(
        _reading("%", "undeclared"),
        40.0,
        "ledger.depletion_mm",
        100.0,
        {"taw_source": "dynamic_zr", "root_depth_m": 0.6},
        FieldWaterTwinRequest(),
    )
    assert out["sensor"]["unit_kind"] == "undeclared"
    assert out["sensor"]["depletion_mm"] is None and out["delta_mm"] is None
    assert out["limitations"] == ["soil_moisture_sensor_unit_undeclared"]


def test_no_reading_is_an_honest_absence():
    out = _join_sensor(None, 40.0, "ledger.depletion_mm", 100.0, {}, FieldWaterTwinRequest())
    assert out["sensor"] is None and out["limitations"] == ["soil_moisture_sensor_unavailable"]
