"""P0 wrong-advice regressions: each test pins one way the platform used to advise wrongly.

1. unknown soil N read as zero supply ⇒ "fertilize full demand" at confidence 1.0;
2. modelled crop uptake labelled "fertilizer due", missing uptake read as 0, nutrient kg
   priced as fertilizer-product kg;
3. unrecognized crop given a yield and an invented day-count growth stage;
4. perennials (coffee/qat/citrus/date palm) told "harvest overdue";
5. UI crop labels not resolving to existing crop cards; «ذرة» meaning maize in one
   resolver and sorghum in another;
6. a lot rejected in quality check could still be sold, and a sold lot could move back.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sahool_platform_path import ensure_platform_path

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ensure_platform_path()

from api.agronomic_state_consumers import consume_nutrient_ledger  # noqa: E402
from api.canonical_nutrient_ledger import (  # noqa: E402
    CropNutrientDemand,
    SoilNutrientEvidence,
    build_canonical_nutrient_ledger,
)

NOW = datetime(2026, 8, 3, tzinfo=UTC)


# ── 1. unknown soil N is not zero supply ─────────────────────────────────────────


def _ledger(**soil_kw):
    soil = dict(
        sampled_at=NOW - timedelta(days=10),
        evidence_digest="a" * 64,
        nitrogen_kg_ha=25.0,
        phosphorus_kg_ha=5.0,
        potassium_kg_ha=45.0,
    )
    soil.update(soil_kw)
    return build_canonical_nutrient_ledger(
        tenant_id="t",
        field_id="f",
        season_id="s",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="development",
        as_of=NOW,
        soil=SoilNutrientEvidence(**soil),
        demand=CropNutrientDemand(
            evidence_digest="b" * 64,
            nitrogen_kg_ha=100.0,
            phosphorus_kg_ha=30.0,
            potassium_kg_ha=40.0,
        ),
        applications=[],
    )


def test_unknown_soil_n_has_no_remaining_requirement():
    ledger = _ledger(nitrogen_kg_ha=None)
    n = next(b for b in ledger.balances if b.nutrient == "N")
    assert n.remaining_requirement_kg_ha is None  # not the full 100 kg/ha demand
    assert n.surplus_kg_ha is None
    assert n.actionable is False
    p = next(b for b in ledger.balances if b.nutrient == "P")
    assert p.remaining_requirement_kg_ha == 25.0 and p.actionable is True


def test_consumer_never_fertilizes_n_from_unknown_supply():
    candidate = consume_nutrient_ledger(_ledger(nitrogen_kg_ha=None))
    remaining = candidate.payload["remaining_requirement_kg_ha"]
    assert "N" not in remaining
    assert remaining == {"P": 25.0}  # P stays actionable when known
    assert candidate.payload["non_actionable_nutrients"] == ["N"]
    assert candidate.confidence < 1.0
    assert candidate.status == "degraded"


def test_consumer_with_only_unknown_n_gap_does_not_fertilize():
    # P and K already covered: the only "gap" would come from N read as zero.
    candidate = consume_nutrient_ledger(_ledger(nitrogen_kg_ha=None, phosphorus_kg_ha=40.0))
    assert candidate.action_type != "fertilize"
    assert candidate.payload["remaining_requirement_kg_ha"] == {}
    assert candidate.confidence < 1.0


def test_complete_evidence_keeps_full_confidence():
    candidate = consume_nutrient_ledger(_ledger())
    assert candidate.status == "ready"
    assert candidate.confidence == 1.0
    assert candidate.payload["remaining_requirement_kg_ha"] == {"N": 75.0, "P": 25.0}


# ── 2. modelled uptake is not fertilizer due ────────────────────────────────────


def _decision(nutrient):
    from api.unified_decision import unified_decision

    twin = {"crop": "wheat", "phenology": {}, "water": {}, "nutrient": nutrient}
    plan = {"days": [], "stress_days": []}
    return unified_decision(twin, plan, {"confidence": 0.5, "data_quality": "low"})


def test_missing_uptake_to_date_is_unknown_not_zero():
    d = _decision({"stage": "mid", "target_uptake_kg_ha": 120.0})
    fert = d["fertilization"]
    assert fert["remaining_need_kg_ha"] is None  # not the full 120
    assert fert["due"] is None
    assert not any(f["code"] == "crop_uptake_remaining" for f in d["stress_flags"])


def test_remaining_uptake_labelled_as_modelled_not_fertilizer_dose():
    d = _decision({"stage": "mid", "target_uptake_kg_ha": 120.0, "uptake_to_date_kg_ha": 45.0})
    fert = d["fertilization"]
    assert fert["remaining_crop_uptake_kg_ha"] == pytest.approx(75.0)
    assert fert["basis"] == "modelled_crop_uptake"
    assert fert["soil_supply_known"] is False
    assert fert["fertilizer_dose_kg_ha"] is None
    codes = {f["code"] for f in d["stress_flags"]}
    assert "fertilization_due" not in codes
    assert "crop_uptake_remaining" in codes


def test_nutrient_salinity_ledger_declares_soil_supply_not_considered():
    from api.unified_decision import nutrient_salinity_ledger

    out = nutrient_salinity_ledger(soil_state=None, crop_demand_kg_ha={"n": 100.0})
    assert out["soil_supply_considered"] is False
    assert out["balances"]["n"]["basis"] == "crop_demand_minus_applied"


def test_profit_aware_decision_does_not_price_nutrient_kg_as_product_kg():
    import inspect

    from api.routers import crop_twin

    src = inspect.getsource(crop_twin.compose_profit_aware_decision)
    assert "fertilizer_kg_ha=None" in src
    assert "unavailable_no_nutrient_to_product_conversion" in src


# ── 3. unrecognized crop: no yield, no invented stage ───────────────────────────


def _warm(n):
    from api.season_simulation import DayWeather

    return [DayWeather(t_min_c=15.0, t_max_c=30.0, et0_mm=5.0) for _ in range(n)]


def test_unrecognized_crop_gets_no_yield():
    from api.season_simulation import SimContext, simulate_season

    gdd = [12.0] * 120  # GDD comes only from the weather engine (injected series)
    r = simulate_season(SimContext(crop="dragonfruit", weather=_warm(120), gdd_daily_override=gdd))
    assert r.crop_recognized is False
    assert r.yield_kg_ha is None and r.yield_low_kg_ha is None and r.yield_high_kg_ha is None
    assert r.yield_status == "unavailable_unrecognized_crop"
    assert "UNRECOGNIZED_CROP_NO_YIELD_ESTIMATE" in r.limitations
    known = simulate_season(SimContext(crop="wheat", weather=_warm(120), gdd_daily_override=gdd))
    assert known.yield_kg_ha and known.yield_status == "estimated"


def test_sim_response_model_accepts_missing_yield():
    from api.season_models import SeasonSimResponse

    resp = SeasonSimResponse(
        season_id="s",
        crop="dragonfruit",
        crop_recognized=False,
        days_simulated=10,
        gdd_total=1.0,
        gdd_to_maturity=1.0,
        maturity_reached=False,
        lai_max=1.0,
        biomass_kg_ha=1.0,
        yield_kg_ha=None,
        yield_low_kg_ha=None,
        yield_high_kg_ha=None,
        yield_status="unavailable_unrecognized_crop",
        water_need_mm=1.0,
        water_supply_mm=None,
        water_stress_factor=1.0,
        confidence=0.3,
        rationale_ar="-",
        assumptions_ar=[],
        warnings_ar=[],
        sim_ran_at="2026-01-01T00:00:00+00:00",
    )
    assert resp.model_dump()["yield_kg_ha"] is None


def test_unrecognized_crop_gets_no_day_count_stage():
    from api.field_context import _season_stage

    assert _season_stage("dragonfruit", 40) is None  # no invented "development"
    assert _season_stage(None, 40) is None
    assert _season_stage("wheat", 40) is not None
    assert _season_stage("ذرة صفراء", 40) is not None  # UI label now resolves to maize


# ── 4. perennials are never "harvest overdue" ───────────────────────────────────


@pytest.mark.parametrize("crop", ["coffee", "qat", "citrus", "dates", "date_palm", "قات", "بن"])
def test_perennials_get_no_harvest_window(crop):
    from api.recommendations_hub import RecommendationContext, _yield_rec

    today = date(2026, 6, 11)
    ctx = RecommendationContext(
        field_id="f1", crop=crop, today=today, sowing_date=today - timedelta(days=3 * 365)
    )
    assert _yield_rec(ctx) is None


def test_annual_still_gets_overdue_alert():
    from api.recommendations_hub import RecommendationContext, _yield_rec

    today = date(2026, 6, 11)
    ctx = RecommendationContext(
        field_id="f1", crop="wheat", today=today, sowing_date=today - timedelta(days=200)
    )
    rec = _yield_rec(ctx)
    assert rec is not None and "تأخّر الحصاد" in rec.title_ar


def test_perennial_cards_declare_life_form_and_validate():
    from core.crop_cards.loader import list_crop_cards, load_crop_card, validate_crop_card

    perennial = {c for c in list_crop_cards() if load_crop_card(c).get("life_form") == "perennial"}
    assert {"coffee", "qat", "citrus", "date_palm", "mango", "banana"} <= perennial
    assert not perennial & {"wheat", "maize", "sorghum", "tomato", "potato"}
    for crop_id in list_crop_cards():
        assert validate_crop_card(load_crop_card(crop_id))["valid"], crop_id


def test_validator_rejects_bad_life_form_and_aliases():
    from core.crop_cards.loader import load_crop_card, validate_crop_card

    card = dict(load_crop_card("wheat"))
    assert not validate_crop_card({**card, "life_form": "tree"})["valid"]
    assert not validate_crop_card({**card, "aliases": "قمح"})["valid"]
    assert not validate_crop_card({**card, "aliases": ["", "x"]})["valid"]


# ── 5. UI labels resolve; «ذرة» means one thing everywhere ──────────────────────


def _ui_crop_labels(rel: str) -> list[str]:
    src = (ROOT / rel).read_text(encoding="utf-8")
    block = re.search(r"const CROPS = \[(.*?)\];", src, re.S)
    assert block, rel
    return re.findall(r"label:\s*'([^']+)'", block.group(1))


_EXPECTED_UI = {
    "قمح صلب": "wheat",
    "شعير": "barley",
    "ذرة صفراء": "maize",
    "طماطم": "tomato",
    "بطاطس": "potato",
    "خضروات": None,  # generic — honestly unresolved
    "برسيم": "alfalfa",
    "دخن": "millet",
}


@pytest.mark.parametrize(
    "rel",
    [
        "frontend/src/components/AddSeasonWithStages.tsx",
        "frontend/src/components/fieldsetup/SeasonStep.tsx",
    ],
)
def test_ui_crop_labels_resolve_to_cards(rel):
    from core.season_phenology import resolve_crop_id

    labels = _ui_crop_labels(rel)
    assert set(labels) == set(_EXPECTED_UI), "UI CROPS changed — update the expectation"
    assert {label: resolve_crop_id(label) for label in labels} == {
        label: _EXPECTED_UI[label] for label in labels
    }


def test_card_names_resolve_with_article_and_diacritics():
    from core.season_phenology import resolve_crop_id

    assert resolve_crop_id("الذرة الشاميّة") == "maize"
    assert resolve_crop_id("نخيل التمر") == "date_palm"
    assert resolve_crop_id("Tomato") == "tomato"
    assert resolve_crop_id("بندورة") == "tomato"
    assert resolve_crop_id("grain") is None  # parenthetical qualifiers are not names


def test_dhura_alone_is_sorghum_in_every_resolver():
    from api.season_simulation import normalize_crop
    from core.engines.ky_registry import lookup_ky
    from core.season_phenology import resolve_crop_id

    assert resolve_crop_id("ذرة") == "sorghum"
    assert normalize_crop("ذرة") == ("sorghum", True)
    assert normalize_crop("ذرة صفراء") == ("maize", True)
    # «ذرة» takes sorghum's Ky (0.55 at flowering), not maize's (1.50)
    assert lookup_ky("ذرة", "flowering").crop == "sorghum"
    assert lookup_ky("ذرة شامية", "flowering").crop == "maize"


# ── 6. rejected lots cannot be sold; sold lots do not move back ─────────────────


def test_failing_quality_check_rejects_lot():
    from core.engines.harvest_traceability import status_for_event

    assert status_for_event("quality_check", "stored", {"result": "failed"}) == "rejected"
    assert status_for_event("quality_check", "stored", {"passed": False}) == "rejected"
    assert status_for_event("quality_check", "stored", {"grade": "reject"}) == "rejected"
    assert status_for_event("quality_check", "stored", {"result": "pass"}) == "stored"
    assert status_for_event("quality_check", "rejected", {"result": "pass"}) == "rejected"


def test_transition_refusals():
    from core.engines.harvest_traceability import transition_refusal

    assert transition_refusal("sales", "rejected") is not None
    assert transition_refusal("sales", "stored", quality_grade="reject") is not None
    assert transition_refusal("sales", "stored", quality_grade="A") is None
    assert transition_refusal("storage", "sold") is not None
    assert transition_refusal("harvest", "sold") is not None
    assert transition_refusal("transport", "sold") is not None
    assert transition_refusal("transport", "rejected") is None  # e.g. to disposal


def test_router_refuses_with_409_before_any_write():
    # Structural: the refusal is checked on the locked lot row before the INSERT.
    import inspect

    import api.main  # noqa: F401 — initialise api.main before importing the router
    import api.routers.harvest_traceability as route

    src = inspect.getsource(route.add_custody_event)
    assert "SELECT status, quality_grade FROM harvest_lots" in src
    refusal = src.index("transition_refusal(")
    assert src.index("status_code=409", refusal) < src.index("INSERT INTO custody_chain_events")
    assert 'status_for_event(req.event_type, lot["status"], req.event_details)' in src
