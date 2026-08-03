from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sahool_platform_path import ensure_platform_path

pytestmark = pytest.mark.unit
ensure_platform_path()

from api.canonical_phenology_state import (  # noqa: E402
    PhenologyObservation,
    RemoteSensingStageEvidence,
    build_canonical_phenology_state,
)

D1 = "a" * 64
D2 = "b" * 64
NOW = datetime(2026, 2, 10, 12, tzinfo=UTC)


def obs(
    stage="development", *, days_ago=1, confidence=0.9, source="field_scout", oid="o1", digest=D1
):
    return PhenologyObservation(
        observation_id=oid,
        source=source,
        stage=stage,
        observed_at=NOW - timedelta(days=days_ago),
        confidence=confidence,
        evidence_digest=digest,
    )


def base(**extra):
    args = dict(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        crop="wheat",
        cultivar_id="bahouth-3",
        sowing_date=date(2025, 12, 20),
        as_of=NOW,
        accumulated_gdd=430,
    )
    args.update(extra)
    return build_canonical_phenology_state(**args)


def test_recent_field_observation_is_authoritative():
    state = base(observations=[obs()])
    assert state.status == "observed"
    assert state.canonical_stage == "development"
    assert state.observed_stage == "development"
    assert state.confidence == 0.9
    assert state.evidence_digests == (D1,)


def test_prediction_is_used_when_observation_is_absent():
    state = base()
    assert state.status == "predicted"
    assert state.canonical_stage in {"initial", "development", "mid", "late"}
    assert state.observed_stage is None
    assert state.confidence in {0.45, 0.65}


def test_low_confidence_observation_does_not_override_prediction():
    state = base(observations=[obs(confidence=0.4)])
    assert state.status == "predicted"
    assert "LOW_CONFIDENCE_OBSERVATION:o1" in state.limitations


def test_stale_observation_does_not_override_prediction():
    state = base(observations=[obs(days_ago=30)])
    assert state.status == "predicted"
    assert "STALE_OBSERVATION:o1" in state.limitations


def test_conflicting_recent_high_confidence_observations_block_state():
    state = base(
        observations=[obs("development", oid="o1"), obs("mid", oid="o2", days_ago=2, digest=D2)]
    )
    assert state.status == "blocked"
    assert state.canonical_stage is None
    assert "CONFLICTING_HIGH_CONFIDENCE_OBSERVATIONS" in state.limitations


def test_remote_sensing_can_support_but_not_override_field_observation():
    remote = RemoteSensingStageEvidence(
        stage="development", observed_at=NOW, confidence=0.8, evidence_digest=D2
    )
    state = base(observations=[obs()], remote_sensing=remote)
    assert state.canonical_stage == "development"
    assert state.confidence == pytest.approx(0.98)
    assert set(state.evidence_digests) == {D1, D2}

    divergent = RemoteSensingStageEvidence(
        stage="mid", observed_at=NOW, confidence=0.9, evidence_digest=D2
    )
    state2 = base(observations=[obs()], remote_sensing=divergent)
    assert state2.canonical_stage == "development"
    assert "REMOTE_SENSING_STAGE_DIVERGENCE" in state2.limitations


def test_future_and_unknown_observations_fail_closed():
    future = PhenologyObservation("future", "field_scout", "mid", NOW + timedelta(days=1), 0.9, D1)
    unknown = PhenologyObservation("unknown", "field_scout", "invented", NOW, 0.9, D2)
    state = base(observations=[future, unknown])
    assert state.status == "predicted"
    assert "FUTURE_OBSERVATION:future" in state.limitations
    assert "UNKNOWN_STAGE:unknown" in state.limitations


def test_unknown_crop_is_blocked_not_fabricated():
    state = base(crop="not-a-real-crop", accumulated_gdd=None)
    assert state.status == "blocked"
    assert state.canonical_stage is None
    assert "UNKNOWN_CROP_CARD" in state.limitations


def test_digest_is_deterministic_for_same_evidence():
    a = base(observations=[obs()])
    b = base(observations=[obs()])
    assert a.state_digest == b.state_digest
    assert len(a.state_digest) == 64


def test_rejects_naive_time_negative_gdd_and_duplicate_ids():
    with pytest.raises(ValueError, match="timezone-aware"):
        base(as_of=datetime(2026, 2, 10, 12))
    with pytest.raises(ValueError, match="accumulated_gdd"):
        base(accumulated_gdd=-1)
    with pytest.raises(ValueError, match="duplicate observation_id"):
        base(observations=[obs(), obs(stage="mid")])
