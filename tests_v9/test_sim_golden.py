from datetime import UTC, datetime, timedelta

import pytest

from scripts.simulation.sim_golden import GoldenError, evaluate, verify_signed_evidence

pytestmark = pytest.mark.unit


def rows(error=0.03):
    out = []
    for season in ("2024", "2025"):
        for i in range(18):
            observed = 4000 + i * 90
            out.append(
                {
                    "sample_id": f"{season}-{i}",
                    "crop": "wheat",
                    "season_id": season,
                    "farm_id": f"farm-{i % 3}",
                    "observed_yield_kg_ha": observed,
                    "predicted_yield_kg_ha": observed * (1 + error),
                    "observation_source": "certified_scale",
                    "prediction_at": f"{season}-04-01T00:00:00Z",
                    "harvest_at": f"{season}-06-01T00:00:00Z",
                    "model_version": "wofost-7.2",
                    "input_digest": "a" * 64,
                }
            )
    return out


def test_good_temporal_holdout_requires_signature_for_promotion():
    unsigned = evaluate({"samples": rows()})
    assert unsigned["status"] == "verified"
    assert unsigned["eligible_for_promotion"] is False
    signed = evaluate({"samples": rows()}, signing_key="k" * 32)
    assert signed["eligible_for_promotion"] is True
    assert len(signed["signature_hmac_sha256"]) == 64
    assert verify_signed_evidence(signed, "k" * 32)
    signed["status"] = "rejected"
    assert not verify_signed_evidence(signed, "k" * 32)


def test_bad_accuracy_is_rejected():
    result = evaluate({"samples": rows(error=0.45)}, signing_key="k" * 32)
    assert result["status"] == "rejected"
    assert result["eligible_for_promotion"] is False


def test_post_harvest_prediction_is_target_leakage():
    data = rows()
    data[0]["prediction_at"] = "2024-07-01T00:00:00Z"
    with pytest.raises(GoldenError, match="target leakage"):
        evaluate({"samples": data})
