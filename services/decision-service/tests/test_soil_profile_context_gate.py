from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
for path in (str(ROOT), str(REPO)):
    if path not in sys.path:
        sys.path.insert(0, path)

from agronomic_context.contracts import ContextComposeIn, HistoricalContextIn  # noqa: E402
from agronomic_context.point_in_time import validate_composition  # noqa: E402

NOW = datetime.now(UTC)


def _soil() -> dict:
    return {
        "contract_version": "soil-profile.v1",
        "profile_id": "soil1",
        "profile_hash": "b" * 64,
        "field_id": "f1",
        "effective_at": NOW.isoformat(),
        "data_available_at": NOW.isoformat(),
        "status": "regional_guided",
        "evidence_level": "analog_guided",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": 30,
                "properties": {
                    "texture": {
                        "value": "sandy_loam",
                        "evidence_class": "analog_estimate",
                        "selected_source": "analog-field-engine",
                        "confidence": 0.61,
                        "verification_required": True,
                    }
                },
            }
        ],
        "completeness_score": 0.45,
        "quality_gate": {"passed": True, "executable": False},
        "selection_policy_version": "soil-policy.v1",
        "allowed_use": ["sampling_planning"],
        "blocked_use": ["gypsum_rate"],
    }


def _payload(soil: dict) -> ContextComposeIn:
    return ContextComposeIn(
        field_id="f1",
        season_id="s1",
        as_of_time=NOW,
        decision_cutoff_time=NOW + timedelta(minutes=1),
        context={
            "crop": {},
            "soil": soil,
            "irrigation": {},
            "weather": {},
            "climate": {},
            "terrain": {},
            "operations": {},
        },
        historical=HistoricalContextIn(
            history_from=NOW - timedelta(days=30),
            history_to=NOW - timedelta(seconds=1),
        ),
        idempotency_key="soil-gate-1",
    )


def test_canonical_soil_profile_is_accepted(monkeypatch):
    monkeypatch.setenv("DECISION_REQUIRE_SOIL_PROFILE", "true")
    assert validate_composition(_payload(_soil())) == []


def test_legacy_soil_profile_is_rejected(monkeypatch):
    monkeypatch.setenv("DECISION_REQUIRE_SOIL_PROFILE", "true")
    violations = validate_composition(_payload({"texture": "sandy_loam"}))
    assert any(v["code"] == "canonical_soil_profile_required" for v in violations)
