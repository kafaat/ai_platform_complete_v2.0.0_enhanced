"""Active season owns the crop used to interpret a water-twin scenario (pure adapter)."""

from __future__ import annotations

import inspect
from datetime import date

import pytest
from core.field_twin import water_twin_crop_context

pytestmark = pytest.mark.unit

LEGACY = {"crop": "peanut", "planting_date": date(2026, 1, 1)}


def test_active_season_wins_over_legacy_field_crop():
    ctx = water_twin_crop_context(
        {"season_id": "season-wheat", "crops": ["wheat"], "sowing_date": date(2026, 10, 20)}, LEGACY
    )
    assert ctx == {
        "crop": "wheat",
        "planting_date": date(2026, 10, 20),
        "season_id": "season-wheat",
        "source": "seasons.active",
        "limitations": [],
    }


@pytest.mark.parametrize("crops", [["wheat", "faba_bean"], [], "not json", None])
def test_mixed_or_empty_season_crops_infer_nothing_and_do_not_fall_back(crops):
    ctx = water_twin_crop_context(
        {"season_id": "s-mix", "crops": crops, "sowing_date": None}, LEGACY
    )
    assert ctx["crop"] is None and ctx["planting_date"] is None
    assert ctx["season_id"] == "s-mix"
    assert ctx["limitations"] == ["active_season_crop_ambiguous"]


def test_no_active_season_uses_legacy_crop_marked_unverified():
    ctx = water_twin_crop_context(None, LEGACY)
    assert ctx["crop"] == "peanut" and ctx["source"] == "fields_legacy_unverified"
    assert ctx["limitations"] == ["no_active_season"]


def test_router_resolves_crop_through_the_adapter_and_stays_preview_only():
    import api.main  # noqa: F401  (import the app before its routers, as production does)
    import api.routers.water_twin as router

    src = inspect.getsource(router.field_water_twin)
    assert "FROM seasons" in src and "status = 'active'" in src
    assert "water_twin_crop_context(active_season, field_row)" in src
    assert 'result["preview_only"] = True' in src
    assert '"decision_authority": "none"' in src
