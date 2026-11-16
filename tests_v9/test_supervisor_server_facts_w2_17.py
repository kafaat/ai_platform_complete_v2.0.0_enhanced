"""W2-17 — supervisor binds season and weather from their owners; economics from agriai /v1/plan.

Findings airuntime-4 / crop-9 / weather-8 (crop and weather from the request body on the
trusted path) and airuntime-6 (optimize economics with invented unit costs). Route-level
acceptance lives in ``services/supervisor-agent/test_ai_orchestration_forensic.py`` (``w217``);
this file pins the pure pieces: season parsing, the weather window, the fail-closed weather
conversion, the key stripping, and the economics call. Pure logic — ``pytest -m unit``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, timedelta

import pytest

httpx = pytest.importorskip("httpx")

pytestmark = pytest.mark.unit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUPERVISOR = os.path.join(ROOT, "services", "supervisor-agent")
if SUPERVISOR not in sys.path:
    sys.path.insert(0, SUPERVISOR)

import server_facts as sf  # noqa: E402
from skills.crop_model_skill import plan_economics  # noqa: E402

TODAY = date(2026, 11, 16)


def _view(start: date, days: int, **overrides) -> dict:
    view = {
        "days": [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "temp_max_c": 26.0,
                "temp_min_c": 9.0,
                "precipitation_mm": 0.5,
            }
            for i in range(days)
        ],
        "derived_from": "canonical_weather_state",
        "canonical_state_id": "cws-1",
        "quality_status": "validated",
        "coverage": {"missing_days": 0},
    }
    view.update(overrides)
    return view


# ── season ────────────────────────────────────────────────────────────────────────────


def test_season_facts_bind_crop_cultivar_sowing_and_seed_rate():
    pack = {
        "active_season": {
            "season_id": "s-1",
            "crops": '["Wheat"]',  # JSONB may arrive as text
            "cultivar": " Bohoth-13 ",
            "sowing_date": "2026-10-01",
            "season_end": "2027-04-30",
            "seed_rate_kg_ha": "120.5",
        }
    }
    facts, provenance = sf.season_facts(pack)
    assert facts == {
        "crop": "wheat",
        "cultivar": "Bohoth-13",
        "planting_date": "2026-10-01",
        "season_end": "2027-04-30",
        "seed_rate_kg_ha": 120.5,
        "season_id": "s-1",
    }, facts
    assert provenance["status"] == "bound" and provenance["season_id"] == "s-1", provenance


@pytest.mark.parametrize(
    "season, reason",
    [
        (None, "no_active_season"),
        ({"season_id": "s", "crops": []}, "season_crop_missing"),
        ({"season_id": "s", "crops": ["wheat", "chickpea"]}, "multi_crop_season"),
    ],
)
def test_season_without_one_crop_binds_no_crop(season, reason):
    facts, provenance = sf.season_facts({"active_season": season})
    assert "crop" not in facts, facts
    assert provenance["reason"] == reason, provenance


# ── weather window ────────────────────────────────────────────────────────────────────


def test_weather_window_stops_at_the_archive_lag_and_the_season_end():
    start, end = sf.weather_window("2026-10-01", None, TODAY)
    assert start == date(2026, 10, 1), start
    assert end == TODAY - timedelta(days=sf.ARCHIVE_LAG_DAYS), end
    _, end = sf.weather_window("2026-10-01", "2026-10-20", TODAY)
    assert end == date(2026, 10, 20), end


@pytest.mark.parametrize(
    "planting, season_end, reason",
    [
        (None, None, "planting_date_required"),
        ("2026-12-01", None, "season_not_started"),
        ("2026-11-14", None, "season_weather_not_yet_archived"),
        ("2026-10-01", "2026-09-01", "season_window_invalid"),
        ("2025-01-01", None, "season_window_too_long"),
    ],
)
def test_weather_window_reasons(planting, season_end, reason):
    assert sf.weather_window(planting, season_end, TODAY) == reason, reason


# ── weather conversion (fail closed) ──────────────────────────────────────────────────


def test_weather_from_view_converts_to_the_engine_shape_without_inventing_values():
    start = date(2026, 10, 1)
    view = _view(start, 3)
    view["days"][1]["precipitation_mm"] = None  # one day without rain ⇒ no seasonal total
    view["days"][2]["et0_mm"] = 4.2
    weather, provenance = sf.weather_from_view(
        view, lat=15.3, lon=44.2, start=start, end=start + timedelta(days=2)
    )
    assert weather["daily"][1] == {"date": "2026-10-02", "tmax": 26.0, "tmin": 9.0}, weather
    assert weather["daily"][2]["et0_mm"] == 4.2, weather
    assert "total_rain_mm" not in weather, "a missing rain day became a seasonal total"
    assert weather["latitude"] == 15.3 and weather["canonical_state_id"] == "cws-1", weather
    assert provenance["status"] == "bound" and provenance["days"] == 3, provenance


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda v: v.update(derived_from="provider"), "weather_not_canonical"),
        (lambda v: v.update(canonical_state_id=None), "weather_not_canonical"),
        (lambda v: v.update(quality_status="insufficient"), "weather_quality_rejected"),
        (lambda v: v.update(coverage={"missing_days": 1}), "weather_coverage_incomplete"),
        (lambda v: v["days"].pop(), "weather_coverage_incomplete"),
        (lambda v: v["days"][0].update(temp_min_c=None), "weather_day_temperature_missing"),
        (lambda v: v.pop("days"), "weather_view_invalid"),
    ],
)
def test_weather_from_view_fails_closed(mutate, reason):
    start = date(2026, 10, 1)
    view = _view(start, 3)
    mutate(view)
    weather, provenance = sf.weather_from_view(
        view, lat=15.3, lon=44.2, start=start, end=start + timedelta(days=2)
    )
    assert weather is None, weather
    assert provenance["status"] == "unavailable" and provenance["reason"] == reason, provenance


# ── binding ───────────────────────────────────────────────────────────────────────────


def test_bind_server_facts_drops_every_body_asserted_fact_even_when_the_owner_has_none():
    body = {
        "crop": "maize",
        "weather": {"gdd": 9999},
        "agronomic_context": {"weather_snapshot": {"gdd": 9999}},
        "soil": {"available_water_mm": 999},
        "costs": {"seed": 1},
        "question_hint": "keep me",
    }
    out = sf.bind_server_facts(
        dict(body),
        {},
        {"season": {"status": "unavailable"}},
        {"inputs": {"weather_age_hours": 4}},
        request_context=body,
    )
    for key in ("crop", "weather", "agronomic_context", "soil", "costs"):
        assert key not in out, f"{key} from the body survived the trusted path"
    assert out["question_hint"] == "keep me", out
    assert out["weather_age_hours"] == 4, "weather age must be the field state's"
    provenance = out["_facts_provenance"]
    assert provenance["ignored_request_keys"] == [
        "agronomic_context",
        "costs",
        "crop",
        "soil",
        "weather",
    ], provenance
    assert provenance["crop_source"] is None and provenance["weather_source"] is None, provenance


def test_resolve_server_facts_without_assertion_key_reads_nothing_and_says_why():
    calls = []

    class Client:
        async def get(self, *args, **kwargs):
            calls.append(args)
            raise AssertionError("no signed headers ⇒ no call")

    facts, provenance = asyncio.run(
        sf.resolve_server_facts(
            Client(),
            field_id="f",
            tenant_id="t",
            platform_url="http://platform",
            signed_headers=lambda tenant, path: None,
            today=TODAY,
        )
    )
    assert facts == {} and calls == [], (facts, calls)
    assert provenance["season"]["reason"] == "platform_season_context_unavailable", provenance


# ── economics: agriai /v1/plan ────────────────────────────────────────────────────────

_CONTEXT = {
    "crop": "wheat",
    "planting_date": "2026-10-01",
    "weather": {"daily": [{"date": "2026-10-01", "tmax": 25.0, "tmin": 9.0}]},
}


def _route(monkeypatch, handler):
    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_plan_economics_sends_the_observed_price_and_no_costs_and_reads_agriai_profit(
    monkeypatch,
):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "ranked": [
                    {
                        "rank": 1,
                        "name": "wheat",
                        "status": "costed",
                        "price_per_kg": 250.0,
                        "total_cost": 90000.0,
                        "expected_profit": 660000.0,
                    }
                ],
                "insufficient": [],
                "best": "wheat",
                "evidence_hash": "eh-1",
            },
        )

    _route(monkeypatch, handler)
    out = asyncio.run(plan_economics(dict(_CONTEXT), 250.0))
    assert [r.url.path for r in seen] == ["/v1/plan"], seen
    body = json.loads(seen[0].content)
    assert body["candidates"] == [
        {"name": "wheat", "crop": {"name": "wheat"}, "price_per_kg": 250.0}
    ], body
    assert body["agromanagement"] == {"planting_date": "2026-10-01"}, body
    assert out["status"] == "costed" and out["best"]["expected_profit"] == 660000.0, out
    assert out["source"] == "agriai-engine /v1/plan", out


def test_plan_economics_reports_agriai_insufficient_and_rejections_by_name(monkeypatch):
    replies = [
        httpx.Response(
            200,
            json={
                "ranked": [],
                "insufficient": [{"name": "wheat", "missing_inputs": ["costs"]}],
                "best": None,
            },
        ),
        httpx.Response(422, json={"detail": {"reason": "crop_parameters_required"}}),
    ]
    _route(monkeypatch, lambda request: replies.pop(0))
    insufficient = asyncio.run(plan_economics(dict(_CONTEXT), 250.0))
    assert insufficient["status"] == "insufficient", insufficient
    assert insufficient["missing_inputs"] == ["costs"], insufficient
    rejected = asyncio.run(plan_economics(dict(_CONTEXT), 250.0))
    assert rejected["status"] == "unavailable", rejected
    assert rejected["engine_reason"] == "crop_parameters_required", rejected


def test_plan_economics_without_crop_or_weather_makes_no_call(monkeypatch):
    def never(request):
        raise AssertionError("economics planned without the season crop and weather")

    _route(monkeypatch, never)
    for context, reason in (
        ({"weather": _CONTEXT["weather"]}, "crop_required"),
        ({"crop": "wheat"}, "crop_model_weather_required"),
    ):
        out = asyncio.run(plan_economics(context, 250.0))
        assert out == {
            "status": "unavailable",
            "reason": reason,
            "source": "agriai-engine /v1/plan",
        }, out
