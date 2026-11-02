"""G5 — طقسٌ ناقص لا يُملأ بثوابت ولا يُسمّى «حقيقيّاً».

قبل الإصلاح كان ``fetch_weather_real`` يملأ كلّ قيمة null بثابت (Tmax 30 · Tmin 15 ·
إشعاع 15 · ET0 4 · مطر 0) والمحاكاة تقول ``data_source: "Open-Meteo (حقيقي ...)"``.
هنا: الفجوة الصغيرة تُستوفى خطّيّاً وتُوسَم يوماً بيوم، والكبيرة رفضٌ مُنمَّط، والذيل
الناقص (تأخّر ERA5) يُقَصّ، والنَّسَب يصل استجابة ``/simulate/what-if``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
_PLANTING = date(2024, 1, 1)


def _weather(days: int = 200, *, gaps: tuple[int, ...] = (), field: str = "tmax") -> list[dict]:
    out = []
    for i in range(days):
        day = {
            "date": (_PLANTING + timedelta(days=i)).isoformat(),
            "tmax": 30.0 + (i % 4),
            "tmin": 15.0,
            "rain_mm": 0.0,
            "rad_mj": 18.0,
            "et0_mm": 5.0,
        }
        if i in gaps:
            day[field] = None
        out.append(day)
    return out


@pytest.fixture
def engine(monkeypatch):
    from shared.wofost import engine as eng

    state = {"weather": _weather()}

    async def _fake_fetch(lat, lon, start, end):
        return state["weather"]

    monkeypatch.setattr(eng, "fetch_weather_real", _fake_fetch)
    eng._state = state
    return eng


def _simulate(eng, weather):
    eng._state["weather"] = weather
    return asyncio.run(
        eng.simulate_wofost("F1", "قمح صلب", "loam", 15.0, 44.0, _PLANTING, irrigation=True)
    )


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_client(payload):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            return _FakeResponse(payload)

    return _Client


def test_fetch_never_fills_a_missing_day_with_constants(monkeypatch):
    """Open-Meteo null داخل السلسلة: استيفاء بين الجارين، لا 30/15/15/4."""
    from shared.wofost import engine as eng

    payload = {
        "daily": {
            "time": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            "temperature_2m_max": [20.0, None, 24.0, 22.0],
            "temperature_2m_min": [8.0, None, 10.0, 9.0],
            "precipitation_sum": [0.0, None, 2.0, 0.0],
            "shortwave_radiation_sum": [20.0, None, 22.0, 21.0],
            "et0_fao_evapotranspiration": [3.0, None, 3.4, 3.2],
        }
    }
    monkeypatch.setattr(eng.httpx, "AsyncClient", _fake_client(payload))
    out = asyncio.run(eng.fetch_weather_real(15.0, 44.0, date(2024, 1, 1), date(2024, 1, 4)))

    gap = out[1]
    assert gap["tmax"] == 22.0 and gap["tmin"] == 9.0, "ثابت مُختلَق بدل الاستيفاء"
    assert gap["rad_mj"] == 21.0 and gap["et0_mm"] == 3.2 and gap["rain_mm"] == 1.0
    assert gap["weather_source"] == "gap_filled"
    assert set(gap["filled_fields"]) == {"tmax", "tmin", "rain_mm", "rad_mj", "et0_mm"}
    assert [d["weather_source"] for d in out] == [
        "observed",
        "gap_filled",
        "observed",
        "observed",
    ]


def test_trailing_archive_lag_is_truncated_not_invented(monkeypatch):
    """الأيّام الأخيرة null (تأخّر ERA5 ~5 أيّام) لم تصدر بعد: تُقَصّ، لا تُملأ ولا تُرفض."""
    from shared.wofost import engine as eng

    n = 20
    vals = [25.0] * 15 + [None] * 5
    payload = {
        "daily": {
            "time": [(_PLANTING + timedelta(days=i)).isoformat() for i in range(n)],
            "temperature_2m_max": vals,
            "temperature_2m_min": [12.0 if v else None for v in vals],
            "precipitation_sum": [0.0 if v else None for v in vals],
            "shortwave_radiation_sum": [20.0 if v else None for v in vals],
            "et0_fao_evapotranspiration": [4.5 if v else None for v in vals],
        }
    }
    monkeypatch.setattr(eng.httpx, "AsyncClient", _fake_client(payload))
    out = asyncio.run(eng.fetch_weather_real(15.0, 44.0, _PLANTING, _PLANTING))
    assert len(out) == 15
    assert all(d["weather_source"] == "observed" for d in out)


def test_small_gap_is_labelled_not_called_real(engine):
    r = _simulate(engine, _weather(gaps=(40, 41)))

    prov = r["weather_provenance"]
    assert prov["source"] == "observed+gap_filled"
    assert prov["gap_filled_days"] == 2
    assert prov["gap_filled_dates"] == ["2024-02-10", "2024-02-11"]
    assert prov["fill_method"] == "linear_interpolation"
    assert "حقيقي —" not in r["data_source"], "بيانات مُستكمَلة ما تزال تُسمّى «حقيقيّة»"
    assert "مُستكمَل" in r["data_source"]
    by_date = {d["date"]: d for d in r["daily_series"]}
    assert by_date["2024-02-10"]["weather_source"] == "gap_filled"
    assert by_date["2024-02-09"]["weather_source"] == "observed"
    # 2024-02-09 → i=39 (tmax 33)، 2024-02-12 → i=42 (tmax 32): استيفاء لا 30.
    assert by_date["2024-02-10"]["tmax"] == pytest.approx(32.67, abs=0.01)


def test_a_long_gap_is_refused_with_a_typed_error(engine):
    r = _simulate(engine, _weather(gaps=(50, 51, 52, 53)))
    assert r["error_code"] == "WEATHER_GAPS_EXCEEDED"
    assert r["error"]
    assert r["weather_provenance"]["max_consecutive_gap_days"] == 4
    assert "simulation" not in r


def test_too_many_scattered_gaps_are_refused(engine):
    r = _simulate(engine, _weather(gaps=tuple(range(10, 200, 8))))
    assert r["error_code"] == "WEATHER_GAPS_EXCEEDED"


def test_fully_observed_weather_keeps_the_real_label(engine):
    r = _simulate(engine, _weather())
    assert r["weather_provenance"]["source"] == "observed"
    assert r["weather_provenance"]["gap_filled_days"] == 0
    assert r["data_source"].startswith("Open-Meteo (حقيقي")


@pytest.fixture
def route():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.routers.simulate as mod

    return mod


def _request(**kw):
    from api.api_models import WhatIfRequest

    args = {"field_id": "F1", "lat": 15.0, "lon": 44.0, "planting_date": _PLANTING.isoformat()}
    args.update(kw)
    return WhatIfRequest(**args)


def test_route_exposes_gap_filled_provenance(route, engine, monkeypatch):
    import shared.wofost as pkg

    monkeypatch.setattr(pkg, "simulate_wofost", engine.simulate_wofost)
    engine._state["weather"] = _weather(gaps=(40,))
    out = asyncio.run(route.simulate_what_if(_request(), user=None))

    assert out["available"] is True
    assert out["weather_gap_filled"] is True
    assert out["weather_provenance"]["source"] == "observed+gap_filled"
    assert "الاستيفاء" in out["note_ar"]


def test_route_returns_the_typed_refusal_code(route, engine, monkeypatch):
    import shared.wofost as pkg

    monkeypatch.setattr(pkg, "simulate_wofost", engine.simulate_wofost)
    engine._state["weather"] = _weather(gaps=(60, 61, 62, 63, 64))
    out = asyncio.run(route.simulate_what_if(_request(), user=None))

    assert out["available"] is False
    assert out["error_code"] == "WEATHER_GAPS_EXCEEDED"
    assert out["weather_provenance"]["source"] == "insufficient"
