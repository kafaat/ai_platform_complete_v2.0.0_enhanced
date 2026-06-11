"""اختبارات اختيار/تشكيل أحدث قراءة رطوبة تربة (api.soil_telemetry) — offline.

يغطّي: اختيار الأحدث بـrecorded_at بصرف النظر عن ترتيب الإدخال، تجاهل القيم خارج
النطاق المعقول (٪) و NaN و recorded_at المفقود، إرجاع None على دفعة فارغة/بلا قراءة
صالحة، وتشكيل JSON (as_dict). لا قاعدة/لا شبكة.
"""

from datetime import UTC, datetime

from api.soil_telemetry import (
    SOIL_MOISTURE_MAX_PCT,
    SoilMoistureReading,
    pick_latest_soil_moisture,
)


def _row(value, when, device_id="dev_x", unit="%"):
    return {"value": value, "recorded_at": when, "device_id": device_id, "unit": unit}


def _t(year, month, day, hour=0):
    return datetime(year, month, day, hour, tzinfo=UTC)


class TestPickLatest:
    def test_empty_returns_none(self):
        assert pick_latest_soil_moisture([]) is None

    def test_single_reading(self):
        r = pick_latest_soil_moisture([_row(42.5, _t(2026, 6, 1))])
        assert r is not None
        assert r.value_pct == 42.5
        assert r.recorded_at == _t(2026, 6, 1)

    def test_picks_most_recent_regardless_of_order(self):
        rows = [
            _row(20.0, _t(2026, 6, 1)),
            _row(55.0, _t(2026, 6, 5)),  # الأحدث
            _row(33.0, _t(2026, 6, 3)),
        ]
        r = pick_latest_soil_moisture(rows)
        assert r is not None
        assert r.value_pct == 55.0
        assert r.recorded_at == _t(2026, 6, 5)

    def test_ignores_out_of_range_values(self):
        # 150٪ و -5٪ خاطئتان؛ تُتجاهَلان فتبقى 30٪ رغم أنّها أقدم.
        rows = [
            _row(30.0, _t(2026, 6, 1)),
            _row(150.0, _t(2026, 6, 9)),
            _row(-5.0, _t(2026, 6, 8)),
        ]
        r = pick_latest_soil_moisture(rows)
        assert r is not None
        assert r.value_pct == 30.0

    def test_boundary_values_are_valid(self):
        r0 = pick_latest_soil_moisture([_row(0.0, _t(2026, 6, 1))])
        r100 = pick_latest_soil_moisture([_row(SOIL_MOISTURE_MAX_PCT, _t(2026, 6, 2))])
        assert r0 is not None and r0.value_pct == 0.0
        assert r100 is not None and r100.value_pct == 100.0

    def test_ignores_missing_recorded_at(self):
        rows = [_row(40.0, None), _row(35.0, _t(2026, 6, 1))]
        r = pick_latest_soil_moisture(rows)
        assert r is not None
        assert r.value_pct == 35.0

    def test_ignores_non_numeric_and_nan(self):
        rows = [
            _row("not-a-number", _t(2026, 6, 9)),
            _row(float("nan"), _t(2026, 6, 8)),
            _row(48.0, _t(2026, 6, 1)),
        ]
        r = pick_latest_soil_moisture(rows)
        assert r is not None
        assert r.value_pct == 48.0

    def test_all_invalid_returns_none(self):
        rows = [_row(200.0, _t(2026, 6, 1)), _row(None, _t(2026, 6, 2))]
        assert pick_latest_soil_moisture(rows) is None


class TestShaping:
    def test_as_dict_iso_timestamp(self):
        reading = SoilMoistureReading(
            value_pct=44.0, recorded_at=_t(2026, 6, 11, 9), device_id="dev_42", unit="%"
        )
        d = reading.as_dict()
        assert d["soil_moisture_pct"] == 44.0
        assert d["device_id"] == "dev_42"
        assert d["unit"] == "%"
        assert d["recorded_at"] == "2026-06-11T09:00:00+00:00"
