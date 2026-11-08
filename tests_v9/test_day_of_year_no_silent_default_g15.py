"""G15 (follow-up): no silent ``day_of_year=100`` left in water-balance / what-if / etc-dual.

``WaterBalanceRequest`` and the what-if temperature/rainfall models still defaulted the day
of year to 100 (early April) for every request, so ET0's extraterrestrial radiation was
computed for a day that is not the request's. ``etc_dual`` had its own ``_today_doy``
instead of the shared helper. All now go through ``resolve_day_of_year`` (supplied value,
else the real server date) and declare ``day_of_year_source`` in their output.

The server date is pinned through the helper's own ``date`` seam (2026-07-15 = day 196),
so every expected number below is exact and differs from both 100 and the real today.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api import irrigation_models  # noqa: E402
from api.api_models import WhatIfRainRequest, WhatIfTempRequest  # noqa: E402
from api.water_balance_models import WaterBalanceRequest  # noqa: E402

_PINNED_TODAY = date(2026, 7, 15)
_PINNED_DOY = 196  # 31+28+31+30+31+30 + 15


class _PinnedDate(date):
    @classmethod
    def today(cls):  # type: ignore[override]
        return _PINNED_TODAY


@pytest.fixture
def pinned_today(monkeypatch):
    monkeypatch.setattr(irrigation_models, "date", _PinnedDate)
    assert irrigation_models.resolve_day_of_year(None) == (_PINNED_DOY, "server_date")


def _user():
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id="g15-doy", tenant_id="g15-tenant", role=UserRole.OWNER, name_ar="ا")


async def _post(app, path, body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://platform.test"
    ) as session:
        return await session.post(path, json=body)


# ── models: absence stays absent (no fixed 100) ─────────────────────────────


def test_request_models_have_no_fixed_day_100_default():
    assert WaterBalanceRequest(crop="wheat", t_min_c=15.0, t_max_c=30.0).day_of_year is None
    temp = WhatIfTempRequest(crop="wheat", t_min_c=15.0, t_max_c=30.0, temp_shift_c=2.0)
    assert temp.day_of_year is None
    rain = WhatIfRainRequest(
        crop="wheat", t_min_c=15.0, t_max_c=30.0, rain_baseline_mm=10.0, rain_scenario_mm=5.0
    )
    assert rain.day_of_year is None


# ── /api/v1/water-balance ───────────────────────────────────────────────────


@pytest.fixture
def water_balance_app(monkeypatch, pinned_today):
    from api.routers import water_balance as route
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user] = _user
    engine = AsyncMock(return_value={"et0_mm": 6.0, "method": "hargreaves_fallback"})
    monkeypatch.setattr(route, "get_et0_product", engine)
    return app, engine


_WB_BODY = {"crop": "wheat", "t_min_c": 15.0, "t_max_c": 30.0, "rain_mm": 0.0}


async def test_water_balance_absent_day_uses_server_date_and_declares_it(water_balance_app):
    app, engine = water_balance_app
    response = await _post(app, "/api/v1/water-balance", _WB_BODY)
    assert response.status_code == 200, response.text
    assert engine.await_args.kwargs["day_of_year"] == _PINNED_DOY
    assert response.json()["day_of_year"] == _PINNED_DOY
    assert response.json()["day_of_year_source"] == "server_date"


async def test_water_balance_supplied_day_is_passed_through(water_balance_app):
    app, engine = water_balance_app
    response = await _post(app, "/api/v1/water-balance", {**_WB_BODY, "day_of_year": 100})
    assert response.status_code == 200, response.text
    assert engine.await_args.kwargs["day_of_year"] == 100
    assert response.json()["day_of_year"] == 100
    assert response.json()["day_of_year_source"] == "supplied"


async def test_water_balance_salinity_branch_also_declares_the_day(water_balance_app):
    app, engine = water_balance_app
    body = {**_WB_BODY, "soil_ece": 1.0, "analysis_age_days": 30, "analysis_confidence": 0.9}
    response = await _post(app, "/api/v1/water-balance", body)
    assert response.status_code == 200, response.text
    assert "salinity_decision" in response.json()
    assert response.json()["day_of_year"] == _PINNED_DOY
    assert response.json()["day_of_year_source"] == "server_date"


# ── /api/v1/scenario/temperature · /api/v1/scenario/rainfall ────────────────


@pytest.fixture
def scenario_app(monkeypatch, pinned_today):
    from api.routers import scenario as route
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user] = _user
    engine = AsyncMock(return_value=(6.0, "hargreaves_fallback"))
    monkeypatch.setattr(route, "_engine_et0", engine)
    return app, engine


async def test_scenario_temperature_absent_day_uses_server_date(scenario_app):
    app, engine = scenario_app
    body = {"crop": "wheat", "t_min_c": 15.0, "t_max_c": 30.0, "temp_shift_c": 2.0}
    response = await _post(app, "/api/v1/scenario/temperature", body)
    assert response.status_code == 200, response.text
    assert engine.await_count == 2  # baseline + shifted
    assert [c.kwargs["day_of_year"] for c in engine.await_args_list] == [_PINNED_DOY] * 2
    assert response.json()["day_of_year"] == _PINNED_DOY
    assert response.json()["day_of_year_source"] == "server_date"


async def test_scenario_rainfall_supplied_and_absent_day(scenario_app):
    app, engine = scenario_app
    body = {
        "crop": "wheat",
        "t_min_c": 15.0,
        "t_max_c": 30.0,
        "rain_baseline_mm": 10.0,
        "rain_scenario_mm": 5.0,
    }
    absent = await _post(app, "/api/v1/scenario/rainfall", body)
    assert absent.status_code == 200, absent.text
    assert engine.await_args.kwargs["day_of_year"] == _PINNED_DOY
    assert absent.json()["day_of_year_source"] == "server_date"
    supplied = await _post(app, "/api/v1/scenario/rainfall", {**body, "day_of_year": 300})
    assert supplied.status_code == 200, supplied.text
    assert engine.await_args.kwargs["day_of_year"] == 300
    assert (supplied.json()["day_of_year"], supplied.json()["day_of_year_source"]) == (
        300,
        "supplied",
    )


# ── etc-dual: shared helper, not a private ``or _today_doy()`` ──────────────


async def test_etc_dual_request_weather_derives_day_from_the_shared_helper(pinned_today):
    from api.routers.etc_dual import EtcDualRequest, _resolve_weather

    req = EtcDualRequest(
        temp_max_c=34.0,
        temp_min_c=18.0,
        humidity_pct=45.0,
        wind_speed_m_s=2.0,
        solar_radiation_mj_m2=24.0,
        latitude_deg=15.5,
    )
    weather, source = await _resolve_weather(req, field_lat=None, field_lon=None)
    assert source == "request"
    assert weather.day_of_year == _PINNED_DOY
