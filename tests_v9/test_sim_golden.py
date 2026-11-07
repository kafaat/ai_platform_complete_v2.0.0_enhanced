import hashlib
import hmac
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.simulation.sim_golden import GoldenError, evaluate, verify_signed_evidence

pytestmark = pytest.mark.unit
KEY = "synthetic-golden-signing-key-only-32"
MODEL = "wofost-7.2"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/simulation/sim_golden.py"


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
                    "model_version": MODEL,
                    "input_digest": "a" * 64,
                }
            )
    return out


def policy():
    # These counts are fixture choices, not universal scientific adequacy limits.
    return {
        "schema_version": 1,
        "policy_id": "synthetic-wheat-test-policy-v1",
        "candidate_model_version": MODEL,
        "registered_at": "2025-03-01T00:00:00Z",
        "crops": {
            "wheat": {
                "holdout_season_id": "2025",
                "min_holdout_samples": 18,
                "min_holdout_farms": 3,
            }
        },
    }


def policy_digest(value):
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def admitted(data=None, supplied_policy=None, signing_key=KEY):
    supplied_policy = policy() if supplied_policy is None else supplied_policy
    return evaluate(
        {"samples": rows() if data is None else data},
        signing_key=signing_key,
        validation_policy=supplied_policy,
        expected_policy_sha256=policy_digest(supplied_policy),
    )


def verify(result, **overrides):
    expectations = {
        "expected_model_version": MODEL,
        "expected_policy_sha256": policy_digest(policy()),
        **overrides,
    }
    return verify_signed_evidence(result, KEY, **expectations)


def test_signed_metrics_without_external_policy_cannot_promote():
    result = evaluate({"samples": rows()}, signing_key=KEY)
    assert result["eligible_for_promotion"] is False
    assert result["status"] == "diagnostic"
    assert result["criteria_passed"] is True
    assert result["policy_sha256"] is None
    assert result["crops"][0]["holdout_farms"] == 3


def test_opaque_season_identifiers_do_not_hide_latest_bad_predictions():
    data = rows()
    for row in data:
        if row["season_id"] == "2025":
            row["season_id"] = "10"
            row["predicted_yield_kg_ha"] = row["observed_yield_kg_ha"] * 1.8
        else:
            row["season_id"] = "9"
    result = evaluate({"samples": data}, signing_key=KEY)
    crop = result["crops"][0]
    assert crop["holdout_season"] == "10"
    assert crop["metrics"]["mape_pct"] == 80
    assert result["eligible_for_promotion"] is False


def test_renaming_seasons_preserves_temporal_metrics():
    data = rows()
    original = evaluate({"samples": data})["crops"][0]
    for row in data:
        if row["season_id"] == "2025":
            row["season_id"] = "a-new"
        else:
            row["season_id"] = "z-old"
            row["predicted_yield_kg_ha"] = row["observed_yield_kg_ha"] * 1.5
    renamed = evaluate({"samples": data})["crops"][0]
    assert renamed["holdout_season"] == "a-new"
    assert renamed["metrics"] == original["metrics"]


@pytest.mark.parametrize("harvest", ["2025-06-01T00:00:00Z", "2025-07-01T00:00:00Z"])
def test_overlapping_or_touching_season_intervals_are_ambiguous(harvest):
    data = rows()
    data[0]["harvest_at"] = harvest
    with pytest.raises(GoldenError, match="overlap|ambiguous"):
        evaluate({"samples": data})


def test_chronology_compares_utc_instants_instead_of_timestamp_text():
    data = rows()
    for row in data:
        row["prediction_at"] = "2024-04-01T00:00:00Z"
        row["harvest_at"] = (
            "2025-06-01T01:00:00+03:00" if row["season_id"] == "2024" else "2025-05-31T23:00:00Z"
        )
    assert evaluate({"samples": data})["crops"][0]["holdout_season"] == "2025"


def test_mixed_model_versions_cannot_pool_away_a_bad_candidate():
    data = rows()
    data[-1]["model_version"] = "bad-candidate"
    data[-1]["predicted_yield_kg_ha"] *= 2
    with pytest.raises(GoldenError, match="single model|mixed model"):
        evaluate({"samples": data}, signing_key=KEY)


@pytest.mark.parametrize("value", ["", " ", None, True])
def test_model_version_is_an_explicit_nonblank_string(value):
    data = rows()
    for row in data:
        row["model_version"] = value
    with pytest.raises(GoldenError, match="model_version"):
        evaluate({"samples": data})


@pytest.mark.parametrize("prediction", ["2024-06-01T00:00:00Z", "2024-07-01T00:00:00Z"])
def test_prediction_must_strictly_precede_harvest(prediction):
    data = rows()
    data[0]["prediction_at"] = prediction
    with pytest.raises(GoldenError, match="target leakage"):
        evaluate({"samples": data})


def test_good_policy_and_metrics_require_signature_for_promotion():
    unsigned = admitted(signing_key="")
    assert unsigned["status"] == "verified"
    assert unsigned["eligible_for_promotion"] is False
    signed = admitted()
    assert signed["schema_version"] == 2
    assert signed["eligible_for_promotion"] is True
    assert signed["candidate_model_version"] == MODEL
    assert signed["policy_sha256"] == policy_digest(policy())
    assert signed["validation_policy"] == policy()
    assert signed["crops"][0]["holdout_samples"] == 18
    assert signed["crops"][0]["holdout_farms"] == 3
    assert verify(signed)
    signed["status"] = "rejected"
    assert not verify(signed)


def test_bad_accuracy_is_rejected():
    result = admitted(rows(error=0.45))
    assert result["status"] == "rejected"
    assert result["eligible_for_promotion"] is False


def test_old_samples_and_farms_cannot_satisfy_holdout_policy():
    data = rows()
    old = data[:18]
    old += [{**row, "sample_id": f"extra-{i}"} for i, row in enumerate(data[:14])]
    heldout = data[18:20]
    for row in heldout:
        row["farm_id"] = "farm-0"
    result = admitted(old + heldout)
    crop = result["crops"][0]
    assert crop["samples"] == 34
    assert crop["holdout_samples"] == 2
    assert crop["holdout_farms"] == 1
    assert crop["checks"]["sample_count"]
    assert crop["checks"]["farm_diversity"]
    assert not crop["checks"]["holdout_sample_count"]
    assert not crop["checks"]["holdout_farm_diversity"]
    assert result["status"] == "rejected"
    assert result["eligible_for_promotion"] is False


def test_holdout_farm_diversity_cannot_be_borrowed_from_prior_seasons():
    data = rows()
    for row in data[18:]:
        row["farm_id"] = "farm-0"
    result = admitted(data)
    assert result["crops"][0]["checks"]["holdout_sample_count"]
    assert not result["crops"][0]["checks"]["holdout_farm_diversity"]
    assert result["eligible_for_promotion"] is False


def test_separate_policy_without_trusted_pin_is_only_diagnostic():
    result = evaluate({"samples": rows()}, signing_key=KEY, validation_policy=policy())
    assert result["status"] == "diagnostic"
    assert result["eligible_for_promotion"] is False


def test_dataset_policy_and_approval_claim_cannot_confer_authority():
    result = evaluate(
        {"samples": rows(), "validation_policy": policy(), "approved": True}, signing_key=KEY
    )
    assert result["eligible_for_promotion"] is False
    assert result["policy_sha256"] is None


def test_tampered_policy_does_not_match_the_external_pin():
    supplied = policy()
    supplied["crops"]["wheat"]["min_holdout_samples"] = 4
    with pytest.raises(GoldenError, match="policy.*digest|policy.*pin"):
        evaluate(
            {"samples": rows()},
            signing_key=KEY,
            validation_policy=supplied,
            expected_policy_sha256=policy_digest(policy()),
        )


def test_policy_candidate_must_match_every_dataset_row():
    supplied = policy()
    supplied["candidate_model_version"] = "different-model"
    with pytest.raises(GoldenError, match="candidate"):
        admitted(supplied_policy=supplied)


def test_policy_cannot_select_an_older_holdout():
    supplied = policy()
    supplied["crops"]["wheat"]["holdout_season_id"] = "2024"
    result = admitted(supplied_policy=supplied)
    assert result["crops"][0]["holdout_season"] == "2025"
    assert not result["crops"][0]["checks"]["declared_holdout_matches"]
    assert result["eligible_for_promotion"] is False


@pytest.mark.parametrize("registered", ["2025-04-01T00:00:00Z", "2025-05-01T00:00:00Z"])
def test_policy_registration_must_precede_heldout_prediction(registered):
    supplied = policy()
    supplied["registered_at"] = registered
    result = admitted(supplied_policy=supplied)
    assert not result["crops"][0]["checks"]["policy_registered_before_prediction"]
    assert result["eligible_for_promotion"] is False


def test_registration_precedes_earliest_heldout_prediction_in_every_crop():
    data = rows()
    barley = deepcopy(data)
    for row in barley:
        row["crop"] = "barley"
        row["sample_id"] = "barley-" + row["sample_id"]
        if row["season_id"] == "2025":
            row["prediction_at"] = "2025-02-01T00:00:00Z"
    supplied = policy()
    supplied["crops"]["barley"] = deepcopy(supplied["crops"]["wheat"])
    result = admitted(data + barley, supplied_policy=supplied)
    checks = {crop["crop"]: crop["checks"] for crop in result["crops"]}
    assert checks["wheat"]["policy_registered_before_prediction"]
    assert not checks["barley"]["policy_registered_before_prediction"]
    assert result["eligible_for_promotion"] is False


@pytest.mark.parametrize(
    "coverage", [{}, {"barley": {}}, {"Wheat": {}}, {"wheat": {}, "barley": {}}]
)
def test_policy_requires_exact_crop_coverage(coverage):
    supplied = policy()
    supplied["crops"] = coverage
    with pytest.raises(GoldenError, match="crop|holdout"):
        admitted(supplied_policy=supplied)


@pytest.mark.parametrize("field", ["min_holdout_samples", "min_holdout_farms"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "3", float("nan"), float("inf")])
def test_policy_counts_are_strict_positive_integers(field, value):
    supplied = policy()
    supplied["crops"]["wheat"][field] = value
    with pytest.raises(GoldenError, match="positive integer"):
        evaluate({"samples": rows()}, validation_policy=supplied, expected_policy_sha256="f" * 64)


def test_policy_farms_cannot_exceed_policy_samples():
    supplied = policy()
    supplied["crops"]["wheat"]["min_holdout_samples"] = 2
    with pytest.raises(GoldenError, match="farms.*samples"):
        admitted(supplied_policy=supplied)


@pytest.mark.parametrize("location", ["policy", "crop", "thresholds"])
def test_unknown_policy_fields_fail_closed(location):
    supplied = policy()
    target = supplied
    if location == "crop":
        target = supplied["crops"]["wheat"]
    elif location == "thresholds":
        target = supplied.setdefault("thresholds", {})
    target["approved"] = True
    with pytest.raises(GoldenError, match="unknown"):
        admitted(supplied_policy=supplied)


@pytest.mark.parametrize("value", [True, "20", float("nan"), float("inf"), -1])
def test_policy_error_thresholds_are_finite_nonnegative_numbers(value):
    supplied = policy()
    supplied["thresholds"] = {"max_mape_pct": value}
    with pytest.raises(GoldenError, match="finite|nonnegative"):
        evaluate({"samples": rows()}, validation_policy=supplied, expected_policy_sha256="f" * 64)


def test_dataset_cannot_override_policy_thresholds():
    with pytest.raises(GoldenError, match="dataset.*thresholds"):
        evaluate(
            {"samples": rows(), "thresholds": {"max_mape_pct": 1000}},
            signing_key=KEY,
            validation_policy=policy(),
            expected_policy_sha256=policy_digest(policy()),
        )


def test_diagnostic_threshold_overrides_never_grant_promotion():
    result = evaluate({"samples": rows(), "thresholds": {"max_mape_pct": 1000}}, signing_key=KEY)
    assert result["eligible_for_promotion"] is False


def test_zero_variance_holdout_has_finite_json_and_fails_r2():
    data = rows()
    for row in data[18:]:
        row["observed_yield_kg_ha"] = 5000
        row["predicted_yield_kg_ha"] = 5000
    result = admitted(data)
    assert result["crops"][0]["metrics"]["r2"] is None
    assert not result["crops"][0]["checks"]["r2"]
    assert result["eligible_for_promotion"] is False
    json.dumps(result, allow_nan=False)


def test_verifier_requires_external_candidate_and_policy_expectations():
    result = admitted()
    assert not verify_signed_evidence(result, KEY)
    assert not verify_signed_evidence(result, KEY, expected_model_version=MODEL)
    assert not verify_signed_evidence(result, KEY, expected_policy_sha256=policy_digest(policy()))
    assert not verify(result, expected_model_version="another-candidate")
    assert not verify(result, expected_policy_sha256="f" * 64)
    assert verify(result)


@pytest.mark.parametrize("field", ["candidate_model_version", "policy_sha256", "dataset_sha256"])
def test_signed_evidence_binds_subject_policy_and_dataset(field):
    result = admitted()
    result[field] = "tampered"
    assert not verify(result)


def test_signed_evidence_binds_embedded_policy():
    result = admitted()
    result["validation_policy"]["crops"]["wheat"]["min_holdout_samples"] = 3
    assert not verify(result)


@pytest.mark.parametrize(
    "change",
    [
        "missing_check",
        "arbitrary_approval",
        "tiny_holdout",
        "wrong_season",
        "late_registration",
        "contradictory_range",
    ],
)
def test_verifier_rejects_correctly_signed_but_inconsistent_reports(change):
    # A public fixture key exercises the signed-output contract, not a key-compromise attack.
    result = admitted()
    crop = result["crops"][0]
    if change == "missing_check":
        crop["checks"].pop("holdout_sample_count")
    elif change == "arbitrary_approval":
        crop["checks"] = {"approved": True}
    elif change == "tiny_holdout":
        crop["holdout_samples"] = crop["holdout_farms"] = 1
    elif change == "wrong_season":
        crop["holdout_season"] = "2024"
    elif change == "late_registration":
        crop["holdout_first_prediction_at_utc"] = policy()["registered_at"]
    else:
        crop["holdout_harvest_start_utc"] = "2024-06-01T00:00:00Z"
    result.pop("signature_hmac_sha256")
    result["signature_hmac_sha256"] = hmac.new(
        KEY.encode(),
        json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert not verify(result)


def test_legacy_signature_alone_is_not_eligible_evidence():
    evidence = {"schema_version": 1, "signature_status": "signed", "eligible_for_promotion": True}
    evidence["signature_hmac_sha256"] = hmac.new(
        KEY.encode(),
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert not verify_signed_evidence(evidence, KEY)
    assert not verify(evidence)


def run_cli(tmp_path, *, with_policy, expected_pin=""):
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps({"samples": rows()}), encoding="utf-8")
    output = tmp_path / "evidence.json"
    command = [
        sys.executable,
        str(SCRIPT),
        str(dataset_file),
        "--output",
        str(output),
        "--require-promotion-eligible",
    ]
    if with_policy:
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy(), indent=4), encoding="utf-8")
        command += ["--policy", str(policy_file)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={
            **os.environ,
            "SIM_GOLDEN_EVIDENCE_KEY": KEY,
            "SIM_GOLDEN_POLICY_SHA256": expected_pin,
        },
    )
    return result, json.loads(output.read_text(encoding="utf-8")) if output.exists() else None


def test_cli_require_promotion_rejects_missing_policy(tmp_path):
    result, evidence = run_cli(tmp_path, with_policy=False)
    assert result.returncode == 1
    assert evidence["status"] == "diagnostic"


def test_cli_accepts_pinned_canonical_policy_not_file_byte_digest(tmp_path):
    result, evidence = run_cli(tmp_path, with_policy=True, expected_pin=policy_digest(policy()))
    assert result.returncode == 0, result.stderr
    assert evidence["policy_sha256"] == policy_digest(policy())
    assert verify(evidence)


def test_cli_rejects_mismatched_protected_policy_pin(tmp_path):
    result, evidence = run_cli(tmp_path, with_policy=True, expected_pin="f" * 64)
    assert result.returncode == 1
    assert "policy" in result.stderr
    assert evidence is None


# ── Follow-up to the 2026-11-07 audit: future evidence and an expected dataset digest ──


@pytest.mark.parametrize("field", ["prediction_at", "harvest_at"])
def test_timestamps_after_the_evaluation_time_are_refused(field):
    data = rows()
    data[-1] = data[-1] | {field: "2999-06-01T00:00:00Z"}
    if field == "prediction_at":
        data[-1]["harvest_at"] = "2999-07-01T00:00:00Z"
    with pytest.raises(GoldenError, match="later than the evaluation time"):
        admitted(data)


def test_policy_registered_in_the_future_is_refused():
    future = policy() | {"registered_at": "2999-01-01T00:00:00Z"}
    with pytest.raises(GoldenError, match="later than the evaluation time"):
        admitted(supplied_policy=future)


def test_evaluation_time_is_the_signed_generation_time():
    from datetime import UTC, datetime

    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    supplied = policy()
    result = evaluate(
        {"samples": rows()},
        signing_key=KEY,
        validation_policy=supplied,
        expected_policy_sha256=policy_digest(supplied),
        now=fixed,
    )
    assert result["generated_at_utc"] == fixed.isoformat()


def test_verifier_can_pin_the_expected_dataset():
    result = admitted()
    digest = result["dataset_sha256"]
    assert verify(result, expected_dataset_sha256=digest)
    assert verify(result, expected_dataset_sha256=digest.upper())
    assert not verify(result, expected_dataset_sha256="0" * 64)
    assert not verify(result, expected_dataset_sha256="not-a-digest")
