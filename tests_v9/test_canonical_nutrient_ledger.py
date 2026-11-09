import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "services/sahool-platform/api/canonical_nutrient_ledger.py"
spec = importlib.util.spec_from_file_location("canonical_nutrient_ledger", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader
spec.loader.exec_module(mod)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
NOW = datetime(2026, 8, 3, tzinfo=UTC)


def soil(**kw):
    base = dict(
        sampled_at=NOW - timedelta(days=10),
        evidence_digest=DIGEST_A,
        nitrogen_kg_ha=25,
        phosphorus_kg_ha=12,
        potassium_kg_ha=45,
        organic_matter_pct=1.4,
    )
    base.update(kw)
    return mod.SoilNutrientEvidence(**base)


def demand(**kw):
    base = dict(
        evidence_digest=DIGEST_B,
        nitrogen_kg_ha=100,
        phosphorus_kg_ha=30,
        potassium_kg_ha=80,
        target_yield_t_ha=4.0,
    )
    base.update(kw)
    return mod.CropNutrientDemand(**base)


def app(**kw):
    base = dict(
        operation_id="op-1",
        applied_at=NOW - timedelta(days=2),
        evidence_digest=DIGEST_C,
        verified=True,
        nitrogen_kg_ha=30,
        phosphorus_kg_ha=8,
        potassium_kg_ha=5,
        cost_amount=100,
        currency="YER",
    )
    base.update(kw)
    return mod.NutrientApplication(**base)


def build(**kw):
    base = dict(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id="bahouth-3",
        phenology_stage="development",
        as_of=NOW,
        soil=soil(),
        demand=demand(),
        applications=[app()],
    )
    base.update(kw)
    return mod.build_canonical_nutrient_ledger(**base)


def test_builds_verified_balance_and_cost():
    out = build()
    assert out.status == "managed"
    assert out.operational_recommendation_allowed is True
    assert out.total_verified_cost == 100
    n = next(x for x in out.balances if x.nutrient == "N")
    assert n.remaining_requirement_kg_ha == 45
    assert out.verified_operation_ids == ("op-1",)


def test_missing_soil_blocks_operational_recommendation():
    out = build(soil=None)
    assert out.status == "blocked"
    assert out.operational_recommendation_allowed is False
    assert "MISSING_SOIL_NUTRIENT_EVIDENCE" in out.limitations


def test_unknown_stage_blocks():
    out = build(phenology_stage="unknown")
    assert out.status == "blocked"
    assert "UNKNOWN_PHENOLOGY_STAGE" in out.limitations


def test_unverified_application_is_ignored():
    out = build(applications=[app(verified=False)])
    n = next(x for x in out.balances if x.nutrient == "N")
    assert n.applied_kg_ha == 0
    assert out.total_verified_cost is None
    assert any(x.startswith("UNVERIFIED_APPLICATION_IGNORED") for x in out.limitations)


def test_mixed_currency_rejected():
    second = app(operation_id="op-2", evidence_digest="d" * 64, currency="USD")
    try:
        build(applications=[app(), second])
    except ValueError as exc:
        assert "mixed currencies" in str(exc)
    else:
        raise AssertionError("expected mixed-currency rejection")


def test_duplicate_operation_rejected():
    try:
        build(applications=[app(), app(evidence_digest="d" * 64)])
    except ValueError as exc:
        assert "duplicate application" in str(exc)
    else:
        raise AssertionError("expected duplicate rejection")


def test_digest_is_order_independent_for_applications():
    a = app()
    b = app(operation_id="op-2", evidence_digest="d" * 64, cost_amount=50)
    assert build(applications=[a, b]).ledger_digest == build(applications=[b, a]).ledger_digest


def test_future_application_rejected():
    try:
        build(applications=[app(applied_at=NOW + timedelta(seconds=1))])
    except ValueError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("expected future rejection")


def _balance(out, nutrient):
    return next(x for x in out.balances if x.nutrient == nutrient)


# ── N3: per-nutrient soil TTL ────────────────────────────────────────────────


def test_mineral_n_older_than_ttl_is_non_actionable_while_p_k_stay_usable():
    out = build(soil=soil(sampled_at=NOW - timedelta(days=60)), applications=[])
    assert "STALE_N_SOIL_SUPPLY" in out.limitations
    assert "STALE_P_SOIL_SUPPLY" not in out.limitations
    n, p, k = (_balance(out, x) for x in ("N", "P", "K"))
    # The stale value is reported but never closes the balance.
    assert n.soil_supply_kg_ha == 25
    assert n.remaining_requirement_kg_ha is None and n.surplus_kg_ha is None
    assert n.actionable is False
    assert p.actionable and k.actionable
    assert p.remaining_requirement_kg_ha == 18
    assert out.operational_recommendation_allowed is True
    assert out.status == "managed_with_limitations"


def test_n_within_ttl_is_actionable():
    out = build(soil=soil(sampled_at=NOW - timedelta(days=45)))
    assert "STALE_N_SOIL_SUPPLY" not in out.limitations
    assert _balance(out, "N").actionable


def test_whole_soil_record_past_max_age_still_hard_blocks():
    out = build(soil=soil(sampled_at=NOW - timedelta(days=731)), applications=[])
    assert out.status == "blocked"
    assert {"STALE_SOIL_NUTRIENT_EVIDENCE", "STALE_P_SOIL_SUPPLY"} <= set(out.limitations)
    assert not any(b.actionable for b in out.balances)


def test_soil_ttl_never_exceeds_max_soil_age_days():
    out = build(soil=soil(sampled_at=NOW - timedelta(days=40)), max_soil_age_days=30)
    assert "STALE_N_SOIL_SUPPLY" in out.limitations
    assert out.status == "blocked"


# ── N4: applications before the soil sample / season start ───────────────────


def test_application_before_soil_sample_is_not_double_counted():
    early = app(operation_id="op-early", applied_at=NOW - timedelta(days=20))
    out = build(applications=[early, app()])
    assert "APPLICATION_BEFORE_SOIL_SAMPLE" in out.limitations
    assert out.verified_operation_ids == ("op-1",)
    n = _balance(out, "N")
    assert n.applied_kg_ha == 30  # only the post-sample application
    assert n.remaining_requirement_kg_ha == 45
    assert out.total_verified_cost == 100


def test_application_before_season_start_is_excluded():
    out = build(
        soil=soil(sampled_at=NOW - timedelta(days=30)),
        applications=[
            app(applied_at=NOW - timedelta(days=20)),
            app(operation_id="op-2", evidence_digest="d" * 64),
        ],
        season_start=NOW - timedelta(days=10),
    )
    assert "APPLICATION_BEFORE_SEASON_START" in out.limitations
    assert out.verified_operation_ids == ("op-2",)


def test_season_start_after_as_of_rejected():
    with pytest.raises(ValueError, match="season_start"):
        build(season_start=NOW + timedelta(days=1))


# ── N5: re-derivation of a stored ledger ─────────────────────────────────────


def test_builder_output_is_self_consistent():
    for out in (
        build(),
        build(soil=None),
        build(soil=soil(sampled_at=NOW - timedelta(days=60))),
        build(soil=soil(nitrogen_kg_ha=None)),
        build(phenology_stage="unknown"),
    ):
        assert mod.ledger_inconsistencies(out) == []


def test_tampered_operational_flag_is_detected():
    import dataclasses

    blocked = build(soil=None)
    forged = dataclasses.replace(blocked, operational_recommendation_allowed=True, status="managed")
    problems = mod.ledger_inconsistencies(forged)
    assert "OPERATIONAL_ALLOWED_MISMATCH" in problems
    assert "STATUS_MISMATCH" in problems


def test_balance_closed_on_unknown_supply_is_detected():
    import dataclasses

    out = build(soil=soil(nitrogen_kg_ha=None))
    n = _balance(out, "N")
    forged_n = dataclasses.replace(n, remaining_requirement_kg_ha=70.0, surplus_kg_ha=0.0)
    forged = dataclasses.replace(
        out, balances=tuple(forged_n if b.nutrient == "N" else b for b in out.balances)
    )
    assert "N_BALANCE_CLOSED_WITHOUT_SUPPLY" in mod.ledger_inconsistencies(forged)


def test_wrong_arithmetic_and_digest_are_detected():
    import dataclasses

    out = build()
    n = _balance(out, "N")
    forged_n = dataclasses.replace(n, remaining_requirement_kg_ha=999.0)
    forged = dataclasses.replace(
        out, balances=tuple(forged_n if b.nutrient == "N" else b for b in out.balances)
    )
    problems = mod.ledger_inconsistencies(forged)
    assert "N_BALANCE_ARITHMETIC_MISMATCH" in problems
    assert "LEDGER_DIGEST_MISMATCH" in problems
