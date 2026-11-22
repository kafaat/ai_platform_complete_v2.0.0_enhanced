"""G1 — a weather window the plan does not recommend, or that is not safe, is never saved.

The two save paths (`POST /api/v1/weather/tasks/from-operation-plan` and
`POST /api/v1/weather/recommendations/from-operation-plan`) used to build a draft from the
plan's `top_recommendation` and insert it with no condition on the plan's own `recommended`
flag or the window's `safe` flag. The refusal must name its reason and must come before any
database work, so these tests call the handlers with no database at all: a refusal answers
422 with its reason code; a handler that reaches the database instead answers 503.

Only the weather-service client is replaced (a fixed plan); no connection or pool is.
The flags are the weather engine's own: these tests add no threshold.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


def _item(operation="spraying", *, recommended, safe, suitability, score):
    return {
        "operation": operation,
        "best": {
            "hour_offset": 3,
            "time": "+3h",
            "operation": {
                "operation": operation,
                "score": score,
                "suitability": suitability,
                "safe": safe,
                "limiting_factors": [],
            },
        },
        "frames": [],
        "recommended": recommended,
        "priority": score,
        "advice_ar": "—",
    }


def _plan_with(top, items=None):
    items = items if items is not None else ([top] if top else [])

    async def fake_plan(lat, lon, *, operations, hours, model="best_match"):
        return {
            "location": {"lat": lat, "lon": lon},
            "model": model,
            "operations": items,
            "recommended_now": [i for i in items if i.get("recommended")],
            "top_recommendation": top,
            "source": "open-meteo+sahool-operation-plan",
            "partial": False,
            "upstream_errors": [],
        }

    return fake_plan


def _user():
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id="1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.MANAGER,
        name_ar="u",
    )


NOT_RECOMMENDED = _item(recommended=False, safe=True, suitability="poor", score=0.4)
NOT_SAFE = _item(recommended=True, safe=False, suitability="acceptable", score=0.6)


# ── the pure gate ──────────────────────────────────────────────────────────────


def test_gate_refuses_a_window_the_plan_does_not_recommend():
    from api.routers.weather import _operation_plan_save_refusal

    refusal = _operation_plan_save_refusal(NOT_RECOMMENDED)
    assert refusal["reason_code"] == "weather_window_not_recommended"
    assert refusal["message_ar"]
    assert refusal["recommended"] is False


def test_gate_refuses_a_window_that_is_not_safe():
    from api.routers.weather import _operation_plan_save_refusal

    refusal = _operation_plan_save_refusal(NOT_SAFE)
    assert refusal["reason_code"] == "weather_window_not_safe"
    assert refusal["safe"] is False


def test_gate_refuses_a_window_whose_safety_is_not_stated():
    # A missing `safe` flag is not taken as safe.
    from api.routers.weather import _operation_plan_save_refusal

    item = _item(recommended=True, safe=True, suitability="optimal", score=0.9)
    del item["best"]["operation"]["safe"]
    assert _operation_plan_save_refusal(item)["reason_code"] == "weather_window_not_safe"


def test_gate_refuses_when_the_plan_offers_no_window():
    from api.routers.weather import _operation_plan_save_refusal

    for top in (None, {}):
        assert _operation_plan_save_refusal(top)["reason_code"] == "no_recommended_weather_window"


def test_gate_passes_a_recommended_safe_window():
    from api.routers.weather import _operation_plan_save_refusal

    item = _item(recommended=True, safe=True, suitability="optimal", score=0.9)
    assert _operation_plan_save_refusal(item) is None


# ── the save handlers refuse before any database work ──────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("top", "reason"),
    [
        (NOT_RECOMMENDED, "weather_window_not_recommended"),
        (NOT_SAFE, "weather_window_not_safe"),
        (None, "no_recommended_weather_window"),
    ],
)
async def test_task_save_refuses_a_window_that_is_not_recommended_or_not_safe(
    monkeypatch, top, reason
):
    from api.routers import weather

    monkeypatch.setattr(weather, "get_operation_plan", _plan_with(top, [NOT_RECOMMENDED]))
    req = weather.WeatherTaskFromPlanRequest(
        field_id="field-1", lat=15.3, lon=44.2, operation="spraying", dry_run=False
    )
    with pytest.raises(HTTPException) as exc:
        await weather.weather_create_task_from_operation_plan(req, user=_user())
    assert exc.value.status_code == 422, exc.value.detail
    assert exc.value.detail["reason_code"] == reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("top", "reason"),
    [
        (NOT_RECOMMENDED, "weather_window_not_recommended"),
        (NOT_SAFE, "weather_window_not_safe"),
        (None, "no_recommended_weather_window"),
    ],
)
async def test_recommendation_save_refuses_a_window_that_is_not_recommended_or_not_safe(
    monkeypatch, top, reason
):
    from api.routers import weather

    monkeypatch.setattr(weather, "get_operation_plan", _plan_with(top, [NOT_RECOMMENDED]))
    req = weather.WeatherRecommendationFromPlanRequest(
        field_id="field-1", lat=15.3, lon=44.2, dry_run=False
    )
    with pytest.raises(HTTPException) as exc:
        await weather.weather_recommendation_from_operation_plan(req, user=_user())
    assert exc.value.status_code == 422, exc.value.detail
    assert exc.value.detail["reason_code"] == reason


@pytest.mark.asyncio
async def test_dry_run_reports_the_refusal_and_offers_no_draft(monkeypatch):
    from api.routers import weather

    monkeypatch.setattr(weather, "get_operation_plan", _plan_with(NOT_RECOMMENDED))
    task = await weather.weather_create_task_from_operation_plan(
        weather.WeatherTaskFromPlanRequest(
            field_id="field-1", lat=15.3, lon=44.2, operation="spraying", dry_run=True
        ),
        user=_user(),
    )
    assert task["created"] is False
    assert task["task"] is None
    assert task["save_gate"]["allowed"] is False
    assert task["save_gate"]["reason_code"] == "weather_window_not_recommended"

    rec = await weather.weather_recommendation_from_operation_plan(
        weather.WeatherRecommendationFromPlanRequest(
            field_id="field-1", lat=15.3, lon=44.2, dry_run=True
        ),
        user=_user(),
    )
    assert rec["saved"] is False
    assert rec["recommendation"] is None
    assert rec["save_gate"]["reason_code"] == "weather_window_not_recommended"


def test_both_save_paths_gate_and_check_the_point_before_inserting():
    """Order in the handler source: gate → tenant connection → point-in-field → INSERT."""
    import ast
    import inspect

    from api.routers import weather

    for handler in (
        weather.weather_create_task_from_operation_plan,
        weather.weather_recommendation_from_operation_plan,
    ):
        src = inspect.getsource(handler)
        tree = ast.parse(src.lstrip())
        calls = [
            (node.lineno, node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
        ]
        names = [name for _, name in sorted(calls)]
        assert "_operation_plan_save_refusal" in names, handler.__name__
        assert "_refuse_point_outside_field" in names, handler.__name__
        gate = names.index("_operation_plan_save_refusal")
        conn = names.index("tenant_connection")
        point = names.index("_refuse_point_outside_field")
        insert = min(i for i, n in enumerate(names) if n in {"fetchrow", "execute"})
        assert gate < conn < point < insert, (handler.__name__, names)
