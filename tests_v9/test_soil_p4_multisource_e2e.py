"""Contract-level multi-source soil E2E certification."""

import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/soil-service"))
from p4_governance import build_learning, evaluate_action  # noqa: E402

from shared.contracts.soil.p4 import SoilExecutionRecord, SoilOutcomeRecord  # noqa: E402


def test_multisource_profile_to_decision_execution_outcome_learning():
    now = datetime.now(UTC).isoformat()
    profile = {
        "profile_hash": "ph",
        "evidence_level": "lab_verified",
        "quality_gate": {"passed": True},
        "conflicts": [],
        "properties": {
            k: {"value": 1, "observed_at": now}
            for k in ["ph", "ec", "organic_matter", "nitrogen", "phosphorus", "potassium"]
        },
        "evidence_ids": ["soilgrids:1", "mobile:1", "analog:1", "lab:1", "sensor:1"],
    }
    gate = evaluate_action(profile, "fertilizer_rate")
    assert gate.allowed
    execution = SoilExecutionRecord(
        tenant_id="t",
        field_id="f",
        decision_id="d",
        action_type="fertilizer_rate",
        profile_hash="ph",
        approved_by=["soil_specialist"],
        actual={"n_kg_ha": 80},
    )
    outcome = SoilOutcomeRecord(
        tenant_id="t",
        field_id="f",
        execution_id=execution.execution_id,
        verification_id="v1",
        effectiveness_score=0.84,
        metrics={"yield_uniformity": 0.78},
    )
    learning = build_learning(outcome, execution, profile)
    assert learning.eligible_for_training
    assert learning.source_profile_hash == "ph"
    assert len(profile["evidence_ids"]) == 5
