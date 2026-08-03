from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sahool_platform_path import ensure_platform_path

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ensure_platform_path()

from api.agronomic_state_consumers import (  # noqa: E402
    consume_nutrient_ledger,
    consume_phenology_state,
    consume_salinity_state,
)
from api.canonical_nutrient_ledger import CanonicalNutrientLedger, NutrientBalance  # noqa: E402
from api.canonical_phenology_state import CanonicalPhenologyState  # noqa: E402
from api.canonical_salinity_state import CanonicalSalinityState  # noqa: E402

NOW = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)
D1 = "1" * 64
D2 = "2" * 64


def test_phenology_state_is_consumed_without_reprediction():
    state = CanonicalPhenologyState(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id=None,
        as_of=NOW,
        sowing_date=NOW.date(),
        days_since_sowing=0,
        observed_stage="emergence",
        predicted_stage="emergence",
        canonical_stage="emergence",
        status="observed",
        confidence=0.9,
        accumulated_gdd=12.0,
        gdd_fraction=0.1,
        stage_divergence="none",
        observation_ids=("obs-1",),
        evidence_digests=(D1,),
        limitations=(),
        state_digest=D2,
    )
    candidate = consume_phenology_state(state)
    assert candidate.source_domain == "phenology"
    assert candidate.payload["canonical_stage"] == "emergence"
    assert candidate.action_type == "monitor"
    assert candidate.operational_allowed is False


def test_blocked_phenology_cannot_be_operational():
    state = CanonicalPhenologyState(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id=None,
        as_of=NOW,
        sowing_date=NOW.date(),
        days_since_sowing=0,
        observed_stage=None,
        predicted_stage=None,
        canonical_stage=None,
        status="blocked",
        confidence=None,
        accumulated_gdd=None,
        gdd_fraction=None,
        stage_divergence="unknown",
        observation_ids=(),
        evidence_digests=(),
        limitations=("MISSING_STAGE",),
        state_digest=D2,
    )
    candidate = consume_phenology_state(state)
    assert candidate.status == "blocked"
    assert candidate.action_type == "hold"
    assert not candidate.operational_allowed


def test_salinity_leaching_candidate_requires_operational_state():
    state = CanonicalSalinityState(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=NOW,
        status="managed",
        soil_class="moderately_saline",
        water_risk="moderate",
        sodium_hazard_class="low",
        rsc_hazard_class="low",
        effective_crop_threshold_ece_dsm=6.0,
        estimated_relative_yield=0.85,
        leaching_fraction=0.15,
        leaching_feasible=True,
        drainage_class="good",
        operational_recommendation_allowed=True,
        limitations=(),
        evidence_digests=(D1,),
        state_digest=D2,
    )
    candidate = consume_salinity_state(state)
    assert candidate.action_type == "irrigate"
    assert candidate.operational_allowed
    assert candidate.requires_human_approval
    assert candidate.payload["leaching_fraction"] == 0.15


def test_salinity_blocked_state_never_recommends_leaching():
    state = CanonicalSalinityState(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=NOW,
        status="blocked",
        soil_class=None,
        water_risk=None,
        sodium_hazard_class=None,
        rsc_hazard_class=None,
        effective_crop_threshold_ece_dsm=None,
        estimated_relative_yield=None,
        leaching_fraction=None,
        leaching_feasible=None,
        drainage_class="unknown",
        operational_recommendation_allowed=False,
        limitations=("MISSING_DRAINAGE_EVIDENCE",),
        evidence_digests=(D1,),
        state_digest=D2,
    )
    candidate = consume_salinity_state(state)
    assert candidate.action_type == "hold"
    assert not candidate.operational_allowed


def test_nutrient_ledger_produces_fertilizer_candidate_from_remaining_balance():
    ledger = CanonicalNutrientLedger(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="development",
        as_of=NOW,
        status="managed",
        operational_recommendation_allowed=True,
        balances=(
            NutrientBalance("N", 20.0, 100.0, 30.0, 50.0, 0.0),
            NutrientBalance("P", 15.0, 15.0, 0.0, 0.0, 0.0),
            NutrientBalance("K", 40.0, 40.0, 0.0, 0.0, 0.0),
        ),
        total_verified_cost=12.0,
        currency="USD",
        verified_operation_ids=("op-1",),
        limitations=(),
        evidence_digests=(D1,),
        ledger_digest=D2,
    )
    candidate = consume_nutrient_ledger(ledger)
    assert candidate.action_type == "fertilize"
    assert candidate.operational_allowed
    assert candidate.payload["remaining_requirement_kg_ha"] == {"N": 50.0}
