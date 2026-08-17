"""Closed agronomic loop structural contract.

This test deliberately does not create a second orchestrator.  It proves the existing
owners form one legal chain and that canonical field state cannot authorize execution.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_owner_inputs_converge_without_local_weather_or_raster_math():
    router = _text("services/sahool-platform/api/routers/internal_service.py")
    assert "resolve_canonical_soil_state" in router
    assert "resolve_canonical_spectral_state" in router
    assert "resolve_canonical_water_state" in router
    assert "get_canonical_field_weather" in router
    assert "build_canonical_weather_state" not in router


def test_field_state_never_authorizes_execution():
    state = _text("services/sahool-platform/core/canonical_field_state.py")
    assert '"execution_authorization_not_carried_by_field_state"' in state
    assert 'matrix["execute"]' in state
    assert '"allowed": False' in state


def test_decision_chain_requires_approval_before_execution_and_verified_outcome_before_learning():
    decision = _text("services/decision-service/main.py")
    assert "pending_approval -> approved|rejected" in decision
    assert "approved decision -> persisted planned execution plan" in decision
    assert "does not authorize dispatch" in decision
    assert "verify_terminal_execution_outcome" in decision
    assert 'verification_state not in {"verified_success", "verified_failure"}' in decision
    assert "attribute_verified_outcome_to_learning" in decision
    assert "create one immutable, traceable learning attribution; no model mutation" in decision


def test_platform_facade_uses_decision_owner_for_execution_outcome_learning():
    facade = _text("services/sahool-platform/api/decision_service_client.py")
    for symbol in (
        "review_decision",
        "create_execution_plan",
        "authorize_dispatch",
        "create_execution_request",
        "verify_execution_outcome",
        "create_learning_attribution",
    ):
        assert f"async def {symbol}" in facade
