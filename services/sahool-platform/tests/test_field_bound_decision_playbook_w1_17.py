"""W1-17 / weather-2: the field-bound decision playbook derives its weather from weather-service.

Before: ``POST /api/v1/agro/decision-playbook`` read every weather signal from the request
body. A client that sent no keys got a playbook with no weather at all, so a day of strong
wind never produced "do not spray". Now, with ``field_id``, the server derives the signals
from weather-service (operation plan, thermal stress, disease risk), stamps them with a
``weather_snapshot_id`` and refuses weather keys from the caller. Without ``field_id`` the
route is a labelled what-if tool.

The spraying frames are built with the weather-service's own ``operation_suitability``
(loaded by path), so the platform reads the owner's real output shape, not a copy of it.
Fetchers are replaced at the store-function level; no database connection is faked.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import api.main  # noqa: F401 — initialise api.main before importing routers (import cycle)
import pytest
from api.routers import field_workspace_weather as fdw
from api.routers.agro_intelligence import (
    DecisionPlaybookRequest,
    WeatherSignalRequest,
    decision_playbook_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema
from core.decision_playbook import PlaybookContext, build_playbook
from core.weather_signals import (
    SPRAY_UNSAFE,
    SPRAY_WINDOW_OPEN,
    decision_weather_snapshot_id,
    disease_signals,
    spray_signals_from_operation_plan,
    thermal_signals,
)
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_WEATHER_OPS = Path(__file__).resolve().parents[2] / "weather-service" / "operations.py"

_USER = UserSchema(
    user_id="u-w117",
    tenant_id="00000000-0000-0000-0000-000000000017",
    role=UserRole.OWNER,
    name_ar="مزارع",
)

_CALM = {
    "temperature_c": 22.0,
    "humidity_pct": 55.0,
    "wind_speed_10m_kmh": 6.0,
    "wind_gusts_10m_kmh": 10.0,
    "precipitation_mm": 0.0,
}
_STRONG_WIND = {**_CALM, "wind_speed_10m_kmh": 40.0, "wind_gusts_10m_kmh": 62.0}


def _ws_operations():
    spec = importlib.util.spec_from_file_location("_ws_operations_w117", _WEATHER_OPS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plan(samples_by_offset: dict[int, dict | None]) -> dict:
    """An operation-plan response in the weather-service shape (``operation_plan``)."""
    ops = _ws_operations()
    frames = []
    for offset, sample in samples_by_offset.items():
        frames.append(
            {
                "hour_offset": offset,
                "time": "now" if offset == 0 else f"+{offset}h",
                "weather_time": f"2026-11-16T{offset % 24:02d}:00",
                "sample": sample,
                "cache_state": "refreshed",
                "operation": ops.operation_suitability(sample, "spraying"),
            }
        )
    best = ops.best_operation_frame(frames)
    return {
        "operations": [
            {
                "operation": "spraying",
                "best": best,
                "frames": frames,
                "recommended": (best["operation"]["score"] >= 0.55),
            }
        ],
        "source": "open-meteo+sahool-operation-plan",
        "partial": False,
    }


def _types(signals) -> set[str]:
    return {s.signal_type for s in signals}


# ── pure derivation ────────────────────────────────────────────────────────


def test_strong_wind_forecast_is_unsafe_to_spray_even_where_the_service_score_is_not_unsafe():
    plan = _plan({0: _STRONG_WIND})
    decision = plan["operations"][0]["frames"][0]["operation"]
    # The owner's score alone would not say "unsafe" (it says "poor"); drift is the reason.
    assert decision["suitability"] != "unsafe", f"premise changed: {decision}"
    assert "wind_speed_high" in decision["limiting_factors"], f"premise changed: {decision}"
    signals = spray_signals_from_operation_plan(plan)
    assert _types(signals) == {SPRAY_UNSAFE}, f"strong wind must block spraying: {signals}"
    unsafe = signals[0]
    assert unsafe.payload["basis"] == "forecast", f"measured, not unconfirmed: {unsafe.payload}"
    assert "wind_speed_high" in unsafe.payload["reasons"], f"reason missing: {unsafe.payload}"
    assert unsafe.confidence_score == pytest.approx(1.0 - decision["score"]), (
        f"confidence must come from the service score: {unsafe}"
    )


def test_moderate_wind_that_scores_acceptable_still_blocks_spraying():
    plan = _plan({0: {**_CALM, "wind_speed_10m_kmh": 20.0, "wind_gusts_10m_kmh": 25.0}})
    decision = plan["operations"][0]["frames"][0]["operation"]
    assert decision["suitability"] == "acceptable", f"premise changed: {decision}"
    assert _types(spray_signals_from_operation_plan(plan)) == {SPRAY_UNSAFE}, (
        "wind above the drift threshold must not read as an open spray window"
    )


def test_calm_forecast_opens_a_spray_window_now():
    signals = spray_signals_from_operation_plan(_plan({0: _CALM, 3: _CALM}))
    assert _types(signals) == {SPRAY_WINDOW_OPEN}, f"calm weather opens a window: {signals}"
    assert signals[0].payload["opens_now"] is True, f"window should be now: {signals[0].payload}"


def test_wind_now_and_calm_later_gives_unsafe_now_and_a_later_window():
    signals = spray_signals_from_operation_plan(_plan({0: _STRONG_WIND, 6: _CALM}))
    assert _types(signals) == {SPRAY_UNSAFE, SPRAY_WINDOW_OPEN}, f"both expected: {signals}"
    window = next(s for s in signals if s.signal_type == SPRAY_WINDOW_OPEN)
    assert window.payload["hour_offset"] == 6, f"the later frame opens: {window.payload}"
    playbook = build_playbook(PlaybookContext(weather_signals=tuple(signals)))
    assert not any("الآن" in d and "نفّذ الرشّ" in d for d in playbook.do_today), (
        f"must not tell the farmer to spray now: {playbook.do_today}"
    )
    assert any("أجّل الرشّ" in d for d in playbook.do_today), f"defer expected: {playbook}"


@pytest.mark.parametrize(
    "plan",
    [None, {}, {"operations": []}, {"operations": [{"operation": "spraying", "frames": []}]}],
)
def test_no_spraying_forecast_fails_closed_to_unsafe_with_zero_confidence(plan):
    signals = spray_signals_from_operation_plan(plan)
    assert _types(signals) == {SPRAY_UNSAFE}, f"absence must not be silence: {signals}"
    assert signals[0].payload["basis"] == "unconfirmed", f"label absence: {signals[0]}"
    assert signals[0].confidence_score == 0.0, f"no confidence from no data: {signals[0]}"


def test_missing_wind_reading_fails_closed():
    sample = {k: v for k, v in _CALM.items() if not k.startswith("wind")}
    signals = spray_signals_from_operation_plan(_plan({0: sample}))
    assert _types(signals) == {SPRAY_UNSAFE}, f"unknown wind is not calm: {signals}"
    assert signals[0].payload["basis"] == "unconfirmed", f"insufficient data: {signals[0]}"


def test_thermal_product_maps_to_frost_and_heat_with_its_own_confidence():
    product = {
        "status": "ok",
        "frost_nights": 2,
        "heat_stress_days": 1,
        "confidence": 0.8,
        "night_min_c": -1.5,
        "day_max_c": 38.0,
        "risk": "high",
        "horizon_days": 3,
    }
    signals = {s.signal_type: s for s in thermal_signals(product)}
    assert set(signals) == {"frost_imminent", "heat_stress"}, f"both expected: {signals}"
    assert signals["frost_imminent"].confidence_score == 0.8, "confidence is the product's"
    assert thermal_signals({"status": "insufficient_context", "confidence": 0.8}) == [], (
        "a product that declined to judge gives no signal"
    )


def test_disease_high_only():
    assert _types(disease_signals({"risk_level": "high"})) == {"disease_risk_high"}, "high fires"
    assert disease_signals({"risk_level": "moderate"}) == [], "moderate does not fire"


def test_snapshot_id_is_deterministic_and_changes_with_the_weather():
    a = decision_weather_snapshot_id({"frames": [_CALM]})
    assert a == decision_weather_snapshot_id({"frames": [dict(_CALM)]}), "same weather, same id"
    assert a != decision_weather_snapshot_id({"frames": [_STRONG_WIND]}), "new weather, new id"
    assert a.startswith("sahool-decision-weather:v1:"), f"scheme expected: {a}"


# ── the route ──────────────────────────────────────────────────────────────


def _stub_weather(monkeypatch, *, plan, thermal=None, current=None, forecast=None, fail=()):
    async def context(user, field_id):
        assert user.tenant_id == _USER.tenant_id, "tenant comes from the authenticated user"
        return 15.35, 44.2, "wheat", "tillering"

    def _maybe(name, value):
        async def fetch(*args, **kwargs):
            if name in fail:
                raise RuntimeError(f"{name} down")
            return value

        return fetch

    monkeypatch.setattr(fdw, "fetch_decision_field_context", context)
    monkeypatch.setattr(fdw, "get_operation_plan", _maybe("operation_plan", plan))
    monkeypatch.setattr(
        fdw,
        "get_thermal_stress",
        _maybe(
            "thermal_stress",
            thermal
            or {"status": "ok", "confidence": 0.85, "frost_nights": 0, "heat_stress_days": 0},
        ),
    )
    monkeypatch.setattr(
        fdw,
        "get_current_weather",
        _maybe("current", current or {"temperature_c": 22.0, "humidity_pct": 40.0}),
    )
    monkeypatch.setattr(
        fdw,
        "get_weather_forecast",
        _maybe("forecast", forecast or {"days": [{"precipitation_mm": 0.0}] * 3}),
    )


def _call(req: DecisionPlaybookRequest, user: UserSchema = _USER) -> dict:
    return asyncio.run(decision_playbook_endpoint(req, user=user))


def test_acceptance_no_ui_keys_and_strong_wind_gives_unsafe_to_spray(monkeypatch):
    _stub_weather(monkeypatch, plan=_plan({0: _STRONG_WIND, 1: _STRONG_WIND}))
    out = _call(DecisionPlaybookRequest(field_id="fld-1"))
    assert out["mode"] == "field_bound", f"field mode expected: {out.get('mode')}"
    assert out["weather_signals_source"] == "weather-service", "weather must be server-derived"
    types = {s["signal_type"] for s in out["weather_signals"]}
    assert SPRAY_UNSAFE in types and SPRAY_WINDOW_OPEN not in types, f"unsafe only: {types}"
    assert any("لا ترشّ" in a for a in out["avoid_now"]), f"avoid spraying: {out['avoid_now']}"
    assert "الرشّ غير آمن" in out["main_judgement"], f"judgement: {out['main_judgement']}"
    assert out["weather_snapshot_id"].startswith("sahool-decision-weather:v1:"), "snapshot id"
    assert out["crop"] == "wheat", "crop comes from the field, not the request"


def test_negative_control_the_what_if_route_without_keys_has_no_spray_warning(monkeypatch):
    """The pre-W1-17 behaviour, kept as the labelled what-if tool: no keys, no weather."""
    _stub_weather(monkeypatch, plan=_plan({0: _STRONG_WIND}))
    out = _call(DecisionPlaybookRequest())
    assert out["mode"] == "what_if", f"labelled what-if: {out.get('mode')}"
    assert out["weather_signals_source"] == "caller_supplied", "what-if is caller supplied"
    assert out["weather_snapshot_id"] is None, "no snapshot for caller-supplied signals"
    assert not any("لا ترشّ" in a for a in out["avoid_now"]), (
        "what-if without keys never consulted the weather"
    )


def test_snapshot_id_follows_the_weather(monkeypatch):
    _stub_weather(monkeypatch, plan=_plan({0: _CALM}))
    calm = _call(DecisionPlaybookRequest(field_id="fld-1"))
    _stub_weather(monkeypatch, plan=_plan({0: _STRONG_WIND}))
    windy = _call(DecisionPlaybookRequest(field_id="fld-1"))
    assert calm["weather_snapshot_id"] != windy["weather_snapshot_id"], "id binds the weather"
    assert SPRAY_WINDOW_OPEN in {s["signal_type"] for s in calm["weather_signals"]}, "calm opens"


@pytest.mark.parametrize(
    "extra",
    [
        {"weather_signals": [WeatherSignalRequest(signal_type="spray_window_open")]},
        {"crop_risk_inputs": {"crop": "wheat", "frost_risk_hours": 3}},
    ],
)
def test_field_mode_refuses_weather_from_the_caller(monkeypatch, extra):
    _stub_weather(monkeypatch, plan=_plan({0: _STRONG_WIND}))
    with pytest.raises(HTTPException) as err:
        _call(DecisionPlaybookRequest(field_id="fld-1", **extra))
    assert err.value.status_code == 422, f"422 expected: {err.value.status_code}"
    assert err.value.detail["code"] == "FIELD_BOUND_WEATHER_IS_SERVER_DERIVED", err.value.detail


def test_field_mode_refuses_a_crop_that_is_not_the_fields(monkeypatch):
    _stub_weather(monkeypatch, plan=_plan({0: _CALM}))
    with pytest.raises(HTTPException) as err:
        _call(DecisionPlaybookRequest(field_id="fld-1", crop="tomato"))
    assert err.value.status_code == 422, f"crop mismatch must be refused: {err.value}"


def test_operation_plan_down_fails_closed_and_is_named(monkeypatch):
    _stub_weather(monkeypatch, plan=None, fail=("operation_plan",))
    out = _call(DecisionPlaybookRequest(field_id="fld-1"))
    unsafe = [s for s in out["weather_signals"] if s["signal_type"] == SPRAY_UNSAFE]
    assert unsafe and unsafe[0]["payload"]["basis"] == "unconfirmed", f"fail closed: {out}"
    assert "operation_plan" in out["weather_unavailable"], f"absence named: {out}"


def test_all_weather_down_is_503(monkeypatch):
    _stub_weather(
        monkeypatch, plan=None, fail=("operation_plan", "thermal_stress", "current", "forecast")
    )
    with pytest.raises(HTTPException) as err:
        _call(DecisionPlaybookRequest(field_id="fld-1"))
    assert err.value.status_code == 503, f"no weather, no decision: {err.value.status_code}"


def test_incomplete_rain_drops_disease_not_the_playbook(monkeypatch):
    _stub_weather(
        monkeypatch,
        plan=_plan({0: _CALM}),
        current={"temperature_c": 20.0, "humidity_pct": 90.0},
        forecast={"days": [{"precipitation_mm": 12.0}, {"precipitation_mm": None}, {}]},
    )
    out = _call(DecisionPlaybookRequest(field_id="fld-1"))
    assert "disease_risk" in out["weather_unavailable"], f"missing rain is absence: {out}"
    assert "disease_risk_high" not in {s["signal_type"] for s in out["weather_signals"]}, (
        "no disease signal from a partial rain series"
    )


def test_field_mode_requires_field_view(monkeypatch):
    """PLATFORM_ADMIN holds no tenant field:view; it must not read a field's decision."""
    from core.authorization import Permission, has_permission

    user = UserSchema(
        user_id="u-admin", tenant_id=_USER.tenant_id, role=UserRole.PLATFORM_ADMIN, name_ar="x"
    )
    assert not has_permission(user, Permission.FIELD_VIEW), "premise: admin lacks field:view"
    _stub_weather(monkeypatch, plan=_plan({0: _CALM}))
    with pytest.raises(HTTPException) as err:
        _call(DecisionPlaybookRequest(field_id="fld-1"), user=user)
    assert err.value.status_code == 403, f"403 expected: {err.value.status_code}"
