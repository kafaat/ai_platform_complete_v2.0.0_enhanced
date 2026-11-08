"""G15: كفاءة الريّ كسرٌ في (0, 1] (لا نسبة مئويّة صامتة) ويوم السنة بلا ثابت 100.

كان ``irrigation_efficiency=85`` (بدل 0.85) يقسم الاحتياج على 85 ⇒ ≈1% منه، و``0`` يسقط
صامتاً إلى 0.85. وكان ``day_of_year`` الغائب = 100 (أوائل أبريل) لكلّ طلب، فيُحسَب الإشعاع
خارج الغلاف الجوّيّ لـET0 ليومٍ غير يوم الطلب.
"""

from __future__ import annotations

import json
import math
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

from api.irrigation_models import (  # noqa: E402
    IrrigationRecommendationRequest,
    resolve_day_of_year,
)
from api.irrigation_recommendation_policy import (  # noqa: E402
    recommend_irrigation,
    validate_irrigation_efficiency,
)
from pydantic import ValidationError  # noqa: E402

_BASE = dict(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0, forecast_rain_mm=0.0)
_LEACH = dict(
    soil_ece=6.0,
    crop_salt_tolerance_ece=4.0,
    water_ec=2.0,
    drainage="medium",
)


# ── كفاءة الريّ ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [0.85, 1, 1.0, 0.01])
def test_efficiency_fraction_is_accepted_as_is(value):
    assert validate_irrigation_efficiency(value) == float(value)


def test_efficiency_absent_stays_absent():
    assert validate_irrigation_efficiency(None) is None


@pytest.mark.parametrize("value", [85, 85.0, 100])
def test_percentage_efficiency_is_rejected_with_a_named_hint(value):
    with pytest.raises(ValueError, match="looks like a percentage") as exc:
        validate_irrigation_efficiency(value)
    assert f"send {value / 100:g}" in str(exc.value)


@pytest.mark.parametrize(
    "value", [0, 0.0, -0.1, 1.0001, 250.0, float("nan"), float("inf"), True, "0.85"]
)
def test_out_of_range_or_non_numeric_efficiency_is_rejected(value):
    with pytest.raises(ValueError, match="irrigation_efficiency"):
        validate_irrigation_efficiency(value)


def test_policy_core_rejects_percentage_instead_of_dividing_by_85():
    with pytest.raises(ValueError, match="fraction in \\(0, 1\\]"):
        recommend_irrigation(**_BASE, **_LEACH, irrigation_efficiency=85)


def test_policy_core_rejects_zero_instead_of_silently_using_default():
    with pytest.raises(ValueError, match="fraction in \\(0, 1\\]"):
        recommend_irrigation(**_BASE, **_LEACH, irrigation_efficiency=0.0)


def test_policy_core_gross_uses_the_given_fraction_exactly():
    half = recommend_irrigation(**_BASE, **_LEACH, irrigation_efficiency=0.5)
    full = recommend_irrigation(**_BASE, **_LEACH, irrigation_efficiency=1.0)
    assert half["policy"] == full["policy"] == "salinity_with_leaching"
    water = half["net_irrigation_mm"] + half["salinity_leaching_mm"]
    assert water > 0.0
    assert half["gross_irrigation_mm"] == round(water / 0.5, 1)
    assert full["gross_irrigation_mm"] == round(water / 1.0, 1)
    assert math.isclose(half["gross_irrigation_mm"], 2 * full["gross_irrigation_mm"], abs_tol=0.11)


def test_request_model_rejects_percentage_efficiency():
    with pytest.raises(ValidationError) as exc:
        IrrigationRecommendationRequest(t_min_c=15.0, t_max_c=30.0, irrigation_efficiency=85)
    errors = exc.value.errors()
    assert [e["loc"] for e in errors] == [("irrigation_efficiency",)]
    assert "looks like a percentage" in errors[0]["msg"]


def test_request_model_keeps_fraction_and_absence():
    assert (
        IrrigationRecommendationRequest(
            t_min_c=15.0, t_max_c=30.0, irrigation_efficiency=0.85
        ).irrigation_efficiency
        == 0.85
    )
    assert IrrigationRecommendationRequest(t_min_c=15.0, t_max_c=30.0).irrigation_efficiency is None


# ── يوم السنة ───────────────────────────────────────────────────────────────


def test_request_model_has_no_fixed_day_of_year_default():
    assert IrrigationRecommendationRequest(t_min_c=15.0, t_max_c=30.0).day_of_year is None


@pytest.mark.parametrize(
    "doy,today,expected",
    [
        (None, date(2026, 11, 1), (305, "server_date")),
        (None, date(2024, 12, 31), (366, "server_date")),
        (None, date(2026, 1, 1), (1, "server_date")),
        (191, date(2026, 11, 1), (191, "supplied")),
    ],
)
def test_resolve_day_of_year_uses_the_actual_date(doy, today, expected):
    assert resolve_day_of_year(doy, today) == expected


# ── المسار عبر HTTP (الموجِّه الحقيقيّ، المحرّك مُستبدَل) ─────────────────────


@pytest.fixture
def irrigation_app(monkeypatch):
    from api.routers import irrigation_recommendation as route
    from core.canonical_schemas import UserRole, UserSchema
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(route.router)
    user = UserSchema(user_id="g15-user", tenant_id="g15-tenant", role=UserRole.OWNER, name_ar="ا")
    app.dependency_overrides[route.get_current_user] = lambda: user
    engine = AsyncMock(
        return_value={"et0_mm": 6.0, "method": "hargreaves_fallback", "unit": "mm/day"}
    )
    monkeypatch.setattr(route, "_engine_et0", engine)
    return app, engine


async def _post(app, body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://platform.test"
    ) as session:
        return await session.post("/api/v1/irrigation-recommendation", json=body)


_BODY = {
    "crop": "wheat",
    "t_min_c": 15.0,
    "t_max_c": 30.0,
    "rain_recent_mm": 0.0,
    "forecast_rain_mm": 0.0,
}


async def test_http_percentage_efficiency_is_422_before_engine(irrigation_app):
    app, engine = irrigation_app
    response = await _post(app, {**_BODY, "irrigation_efficiency": 85})
    assert response.status_code == 422
    json.dumps(response.json(), allow_nan=False)
    assert "looks like a percentage" in json.dumps(response.json(), ensure_ascii=False)
    engine.assert_not_awaited()


async def test_http_absent_day_of_year_uses_server_date_and_declares_it(irrigation_app):
    app, engine = irrigation_app
    response = await _post(app, _BODY)
    assert response.status_code == 200
    today_doy = date.today().timetuple().tm_yday
    assert engine.await_args.kwargs["day_of_year"] == today_doy
    assert response.json()["et0"]["day_of_year"] == today_doy
    assert response.json()["et0"]["day_of_year_source"] == "server_date"


async def test_http_supplied_day_of_year_is_passed_through(irrigation_app):
    app, engine = irrigation_app
    response = await _post(app, {**_BODY, "day_of_year": 191})
    assert response.status_code == 200
    assert engine.await_args.kwargs["day_of_year"] == 191
    assert response.json()["et0"]["day_of_year_source"] == "supplied"
