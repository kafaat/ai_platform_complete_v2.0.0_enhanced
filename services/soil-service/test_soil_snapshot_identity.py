from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from shared.contracts.soil import canonical_soil_profile_hash


def _payload() -> dict:
    observed = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    return {
        "contract_version": "soil-profile.v1",
        "profile_id": "sp_first",
        "profile_hash": "0" * 64,
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "field_id": "field-1",
        "zone_id": None,
        "effective_at": observed,
        "data_available_at": observed + timedelta(minutes=1),
        "status": "field_guided",
        "evidence_level": "field_observed",
        "layers": [{"depth_from_cm": 0, "depth_to_cm": 30, "properties": {}}],
        "completeness_score": 0.0,
        "quality_gate": {"passed": True, "executable": False, "reasons": []},
        "conflicts": [],
        "allowed_use": ["sampling_plan"],
        "blocked_use": ["gypsum_rate"],
        "evidence_ids": ["obs-1"],
        "selection_policy_version": "soil-profile-selection.v1",
        "model_inputs": None,
    }


def test_generated_projection_metadata_does_not_change_logical_hash() -> None:
    first = _payload()
    second = deepcopy(first)
    second["profile_id"] = "sp_second"
    second["data_available_at"] = second["data_available_at"] + timedelta(hours=2)
    assert canonical_soil_profile_hash(first) == canonical_soil_profile_hash(second)


def test_governed_content_change_changes_hash() -> None:
    first = _payload()
    second = deepcopy(first)
    second["evidence_ids"] = ["obs-2"]
    assert canonical_soil_profile_hash(first) != canonical_soil_profile_hash(second)
