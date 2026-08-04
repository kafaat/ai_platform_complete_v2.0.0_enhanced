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
