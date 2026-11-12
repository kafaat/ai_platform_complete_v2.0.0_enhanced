"""v26 workstream 01: field management forwards every season input; PATCH carries the
land-preparation dates and checks their chronology the way chk_seasons_dates (v47) does.

The runtime round trip (POST from the web form payload, then GET, on a real database under
tenant RLS) was run against a disposable PostgreSQL by the porting session; these are the
pure and structural halves that must stay true in every environment.
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORM_KEYS = (
    "target_yield_kg_ha",
    "actual_yield_kg_ha",
    "tillage_type",
    "seed_variety_source",
    "plant_density",
    "row_spacing_cm",
    "maturity",
    "notes_ar",
    "initial_status",
    "seed_rate_kg_ha",
    "land_leveling_date",
    "plowing_date",
)


def _save_season_body() -> str:
    source = (ROOT / "frontend/src/sections/FieldManagementPage.tsx").read_text(encoding="utf-8")
    return source[source.index("const handleSaveSeason =") : source.index("const handleDelete =")]


def test_field_management_forwards_agronomic_inputs():
    body = _save_season_body()
    for key in FORM_KEYS:
        assert f"{key}: data.{key}" in body, key


def test_numeric_inputs_keep_zero_and_send_null_when_absent():
    # `||` would turn a measured 0 into null; numbers must use `??`.
    body = _save_season_body()
    for key in ("target_yield_kg_ha", "actual_yield_kg_ha", "plant_density", "row_spacing_cm"):
        assert f"{key}: data.{key} ?? null" in body, key


def test_every_forwarded_key_is_accepted_by_the_create_contract():
    from api.season_models import SeasonCreateRequest

    request = SeasonCreateRequest(
        crops=["wheat"],
        target_yield_kg_ha=0,
        actual_yield_kg_ha=0,
        plant_density=0,
        row_spacing_cm=0,
        tillage_type="conventional",
        seed_variety_source="certified",
        maturity="medium",
    )
    dumped = request.model_dump()
    assert {k for k in FORM_KEYS if k != "initial_status"} <= set(dumped)
    assert dumped["target_yield_kg_ha"] == 0 and dumped["plant_density"] == 0


def test_season_patch_supports_land_preparation_dates():
    from api.season_models import SeasonUpdateRequest

    request = SeasonUpdateRequest(land_leveling_date="2026-10-10", plowing_date="2026-10-11")
    assert request.model_fields_set == {"land_leveling_date", "plowing_date"}
    router = (ROOT / "services/sahool-platform/api/routers/fields.py").read_text(encoding="utf-8")
    assert 'updates.append(("plowing_date", plow, False))' in router
    assert 'updates.append(("land_leveling_date", land, False))' in router
    assert "land_leveling_date, plowing_date FROM seasons" in router


D = date


@pytest.mark.parametrize(
    ("land", "plow", "sow", "end", "expected"),
    [
        (D(2026, 10, 1), D(2026, 10, 5), D(2026, 10, 9), D(2027, 3, 1), None),
        (None, None, None, None, None),
        (D(2026, 10, 5), D(2026, 10, 1), None, None, "تاريخ الحراثة قبل تسوية الأرض"),
        # No plowing date in between: v47 still compares levelling with sowing and end.
        (D(2026, 10, 9), None, D(2026, 10, 1), None, "تاريخ البذار قبل تسوية الأرض"),
        (D(2027, 4, 1), None, None, D(2027, 3, 1), "نهاية الموسم قبل تسوية الأرض"),
        (None, D(2026, 10, 9), D(2026, 10, 1), None, "تاريخ البذار قبل الحراثة"),
        (None, D(2027, 4, 1), None, D(2027, 3, 1), "نهاية الموسم قبل الحراثة"),
        (None, None, D(2027, 4, 1), D(2027, 3, 1), "نهاية الموسم قبل البذار"),
        (D(2026, 10, 1), D(2026, 10, 1), D(2026, 10, 1), D(2026, 10, 1), None),
    ],
)
def test_chronology_matches_every_pair_of_the_v47_constraint(land, plow, sow, end, expected):
    from api.season_integrity import chronology_error

    assert chronology_error(land, plow, sow, end) == expected


def _req(**fields):
    base = {
        "sowing_date": None,
        "season_end": None,
        "land_leveling_date": None,
        "plowing_date": None,
    }
    base.update(fields)
    return SimpleNamespace(model_fields_set=set(fields), **base)


STORED = {
    "sowing_date": D(2026, 10, 20),
    "season_end": D(2027, 3, 1),
    "land_leveling_date": D(2026, 10, 10),
    "plowing_date": D(2026, 10, 15),
}


def test_final_chronology_checks_untouched_stored_dates():
    from api.season_integrity import validate_final_season_date_order

    req = _req(plowing_date="2026-10-09")
    got = validate_final_season_date_order(STORED, req, None, None, None, D(2026, 10, 9))
    assert got == "تاريخ الحراثة قبل تسوية الأرض"


def test_new_sowing_before_stored_plowing_is_refused():
    from api.season_integrity import validate_final_season_date_order

    req = _req(sowing_date="2026-10-12")
    got = validate_final_season_date_order(STORED, req, D(2026, 10, 12), None, None, None)
    assert got == "تاريخ البذار قبل الحراثة"


def test_explicit_null_clears_a_land_date_and_lifts_its_constraint():
    from api.season_integrity import validate_final_season_date_order

    stored = {**STORED, "plowing_date": D(2026, 10, 25)}  # already out of order with sowing
    req = _req(plowing_date=None)
    assert validate_final_season_date_order(stored, req, None, None, None, None) is None


def test_valid_partial_update_passes_and_end_before_stored_sowing_keeps_old_message():
    from api.season_integrity import validate_final_season_date_order

    ok = _req(land_leveling_date="2026-10-01")
    assert validate_final_season_date_order(STORED, ok, None, None, D(2026, 10, 1), None) is None
    bad = _req(season_end="2026-10-01")
    got = validate_final_season_date_order(STORED, bad, None, D(2026, 10, 1), None, None)
    assert got.startswith("نهاية الموسم قبل البذار")


def test_patch_pre_db_check_covers_dates_sent_together():
    from api.season_integrity import season_update_dates

    def parse(value, _label):
        return date.fromisoformat(value)

    req = SimpleNamespace(
        sowing_date="2026-10-05",
        season_end=None,
        land_leveling_date=None,
        plowing_date="2026-10-09",
    )
    sow, end, land, plow, error = season_update_dates(req, parse)
    assert (sow, end, land, plow) == (D(2026, 10, 5), None, None, D(2026, 10, 9))
    assert error == "تاريخ البذار قبل الحراثة"
