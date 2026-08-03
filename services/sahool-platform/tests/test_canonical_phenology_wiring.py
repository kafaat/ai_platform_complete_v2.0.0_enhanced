"""canonical_phenology_state: the reconciled stage contract + its production consumer.

``GET /api/v1/fields/{field_id}/phenology`` derived ``current_stage`` from calendar age
alone — ``current_stage(crop_id, days_after_sowing)`` — and presented that guess with no
mark distinguishing it from something a scout actually saw in the field. A recorded
observation could not change it, and two agronomists disagreeing produced the same
serene calendar answer as perfect agreement.

These tests pin the repaired contract on both halves: the core separates an observed
stage from a predicted one and blocks on conflict, and the router really consumes it
without reimplementing the rule or inventing the GDD it does not have.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from api.canonical_phenology_state import (
    PhenologyObservation,
    build_canonical_phenology_state,
)

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "phenology.py"
AS_OF = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
# 75 days after sowing — inside the wheat cycle, so a calendar prediction exists and the
# observed-vs-predicted distinction is actually exercised. Past ~120 days the card defines
# no stage at all; that case is pinned separately below.
SOWING = date(2026, 5, 20)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _state(**overrides):
    kwargs = {
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "field_id": "field-1",
        "season_id": "season-1",
        "crop": "wheat",
        "cultivar_id": None,
        "sowing_date": SOWING,
        "as_of": AS_OF,
        "accumulated_gdd": None,
    }
    kwargs.update(overrides)
    return build_canonical_phenology_state(**kwargs)


def _observation(**overrides):
    row = {
        "observation_id": "obs-1",
        "source": "agronomist",
        "stage": "mid",
        "observed_at": datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        "confidence": 0.9,
        "evidence_digest": DIGEST_A,
    }
    row.update(overrides)
    return PhenologyObservation(**row)


# ── what the wiring buys: an observation outranks the calendar ───────────────
def test_a_recent_trusted_observation_becomes_the_canonical_stage():
    state = _state(observations=[_observation(stage="late")])
    assert state.status == "observed"
    assert state.observed_stage == "late"
    assert state.canonical_stage == "late"
    assert state.observation_ids == ("obs-1",)
    assert DIGEST_A in state.evidence_digests


def test_without_observations_the_state_says_predicted_not_observed():
    """The old endpoint could not say this: the calendar answer is now labelled."""
    state = _state()
    assert state.status == "predicted"
    assert state.observed_stage is None
    assert state.canonical_stage == state.predicted_stage


def test_conflicting_high_confidence_observations_block_instead_of_falling_back():
    """Two trusted disagreements must not resolve into the serene calendar guess."""
    state = _state(
        observations=[
            _observation(observation_id="obs-1", stage="mid", evidence_digest=DIGEST_A),
            _observation(observation_id="obs-2", stage="late", evidence_digest=DIGEST_B),
        ]
    )
    assert state.status == "blocked"
    assert state.canonical_stage is None
    assert state.confidence is None


@pytest.mark.parametrize(
    "override,limitation",
    [
        ({"confidence": 0.10}, "LOW_CONFIDENCE_OBSERVATION:obs-1"),
        ({"observed_at": datetime(2026, 1, 1, tzinfo=UTC)}, "STALE_OBSERVATION:obs-1"),
        ({"stage": "not_a_stage"}, "UNKNOWN_STAGE:obs-1"),
        ({"observed_at": datetime(2026, 12, 1, tzinfo=UTC)}, "FUTURE_OBSERVATION:obs-1"),
    ],
)
def test_a_rejected_observation_names_itself_and_never_becomes_observed(override, limitation):
    state = _state(observations=[_observation(**override)])
    assert limitation in state.limitations
    assert state.status != "observed"
    assert state.observed_stage is None


def test_age_beyond_the_defined_cycle_blocks_instead_of_guessing_a_stage():
    """No card stage covers the age ⇒ no stage. The old endpoint returned null silently."""
    state = _state(sowing_date=date(2026, 1, 1))
    assert state.status == "blocked"
    assert state.canonical_stage is None
    assert "PREDICTED_STAGE_UNAVAILABLE" in state.limitations


def test_absent_gdd_leaves_the_fraction_unknown_rather_than_zero():
    """missing != zero — the endpoint passes None, so no fraction may be invented."""
    state = _state()
    assert state.accumulated_gdd is None
    assert state.gdd_fraction is None


# ── the production consumer ─────────────────────────────────────────────────
def _executable_source(path: Path) -> str:
    """Source with docstrings blanked, so prose naming a status never false-trips.

    Mirrors scripts/ci/consumer_contract_gate.py. This router's docstring legitimately
    *describes* the observed/predicted/blocked vocabulary; it must not *implement* it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""
    return ast.unparse(tree)


def test_router_consumes_the_state_builder_and_adds_no_route():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "api.canonical_phenology_state"
        for alias in node.names
    }
    assert "build_canonical_phenology_state" in imported, "router must consume the module"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "build_canonical_phenology_state" in called, (
        "importing the symbol is not consuming it — the router must call it"
    )

    routes = sorted(
        d.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.args
        and isinstance(d.args[0], ast.Constant)
    )
    assert routes == [
        "/api/v1/fields/{field_id}/phenology",
        "/api/v1/fields/{field_id}/stage-actions",
    ], "no route may be added; the canonical state folds into the existing GET"


def test_the_router_does_not_reimplement_the_reconciliation():
    """The decision vocabulary belongs to the module; the router may only relay it."""
    source = _executable_source(ROUTER)
    for verdict in ('"observed"', "'observed'", '"blocked"', "'blocked'"):
        assert verdict not in source, f"router must not decide {verdict} itself"


def test_the_router_never_sources_gdd_from_the_simulation_table():
    """wofost_seasons.gdd_accumulated is simulation output, not measured heat."""
    source = _executable_source(ROUTER)
    assert "wofost_seasons" not in source
    assert "gdd_accumulated" not in source
    assert "accumulated_gdd=None" in source, "the absent GDD must be passed explicitly"


def test_the_canonical_state_is_opt_in_and_the_default_response_is_unchanged():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    endpoint = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "field_phenology"
    )
    names = [arg.arg for arg in endpoint.args.args]
    assert "canonical" in names, "the canonical state must be reachable"
    default = endpoint.args.defaults[
        names.index("canonical") - (len(names) - len(endpoint.args.defaults))
    ]
    assert isinstance(default, ast.Call), "canonical must be a Query(...) parameter"
    assert default.args and default.args[0].value is False, (
        "canonical must default to False so the existing response is untouched"
    )
    source = _executable_source(ROUTER)
    assert "if not canonical:" in source, "the default path must return before any new read"
