"""SAHOOL -> Unified Local Lab contract candidate tests, synthetic only."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from shared.feature_store.ml_quality_bridge import export_ml_quality_candidate

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def at(day):
    return (T0 + timedelta(days=day)).isoformat()


def manifest():
    return {
        "schema_version": "ml-quality/v1",
        "dataset_id": "fixture-dataset",
        "tenant_id": "tenant-a",
        "model_id": "fixture-model",
        "model_artifact_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "dataset_freeze_at": at(30),
        "evaluation_policy": {
            "min_independent_groups_per_split": 2,
            "min_relative_mae_improvement": 0.05,
            "temporal_embargo_hours": 24,
        },
    }


def records():
    result = []
    for i, split in enumerate(["train", "train", "validation", "validation", "test", "test"]):
        day = [1, 2, 8, 9, 15, 16][i]
        result.append(
            {
                "case_id": f"case-{i}",
                "tenant_id": "tenant-a",
                "field_id": f"field-{i}",
                "season_id": "season-2026",
                "split": split,
                "prediction_at": at(day),
                "feature_event_at": at(day - 1),
                "feature_available_at": at(day - 1),
                "label_measured_at": at(day + 1),
                "label_available_at": at(day + 2),
                "measurement_origin": "soil_sensor",
                "measurement_receipt_sha256": "c" * 64,
                "target_mm": 5.0,
                "prediction_mm": 5.1,
                "baseline_mm": 6.0,
            }
        )
    return result


def good(*args):
    return True


def screen(rows=None, evidence=good, m=None):
    return export_ml_quality_candidate(
        manifest() if m is None else m,
        records() if rows is None else rows,
        receipt_verifier=evidence,
    )


def test_candidate_remains_not_evaluated_and_no_operational_authority():
    r = screen()
    assert r["status"] == "CANDIDATE_NOT_EVALUATED"
    assert not r["claims"]["scientific_screen_executed"]
    assert not r["claims"]["production_authorized"]
    assert not r["claims"]["data_source_authenticated_by_adapter"]
    assert not r["claims"]["water_ledger_modified"]
    assert not r["claims"]["actuator_authorized"]


def test_exact_lab_contract_shapes_and_hashes():
    r = screen()
    assert set(r["manifest"]) == {
        "schema_version",
        "dataset_id",
        "tenant_id",
        "model_id",
        "model_artifact_sha256",
        "source_bundle_sha256",
        "evaluation_policy",
        "dataset_freeze_at",
    }
    assert len(r["rows"]) == 6
    assert set(r["rows"][0]) == {
        "case_id",
        "tenant_id",
        "field_id",
        "season_id",
        "split",
        "prediction_at",
        "feature_event_at",
        "feature_available_at",
        "label_measured_at",
        "label_available_at",
        "label_source",
        "target_mm",
        "prediction_mm",
        "baseline_mm",
    }
    assert r["rows"][0]["label_source"] == "soil_sensor_verified"
    assert len(r["candidate_rows_sha256"]) == 64


def test_missing_verifier_blocks_all_observations():
    r = screen(evidence=None)
    assert r["status"] == "BLOCKED"
    assert len(r["blocking_reasons"]) == 6
    assert all("MEASUREMENT_VERIFIER_NOT_CONFIGURED" in x for x in r["blocking_reasons"])
    assert all(row["label_source"] == "unverified_claim" for row in r["rows"])


def test_derived_water_ledger_never_masquerades_as_sensor():
    rows = records()
    rows[0]["measurement_origin"] = "derived_ledger_balance"
    r = screen(rows)
    assert "case-0:NOT_INDEPENDENT_MEASUREMENT" in r["blocking_reasons"]
    assert r["rows"][0]["label_source"] == "unverified_claim"


def test_manual_estimate_never_becomes_verified():
    rows = records()
    rows[0]["measurement_origin"] = "manual_estimate"
    assert "case-0:NOT_INDEPENDENT_MEASUREMENT" in screen(rows)["blocking_reasons"]


def test_callback_cannot_be_used_to_verify_derived_value():
    seen = []
    rows = records()
    rows[0]["measurement_origin"] = "derived_ledger_balance"
    r = screen(rows, evidence=lambda *parts: seen.append(parts) or True)
    assert r["status"] == "BLOCKED"
    assert len(seen) == 5


def test_failing_verifier_denies_a_sensor():
    r = screen(evidence=lambda *parts: False)
    assert r["status"] == "BLOCKED"
    assert all(row["label_source"] == "unverified_claim" for row in r["rows"])


def test_verifier_exception_denies_a_sensor():
    def fail(*args):
        raise OSError("database unavailable")

    assert screen(evidence=fail)["status"] == "BLOCKED"


def test_receipt_verified_with_exact_tenant_field_season_and_source():
    seen = []

    def verifier(*args):
        seen.append(args)
        return args == ("tenant-a", "field-0", "season-2026", "soil_sensor", "c" * 64)

    r = screen(evidence=verifier)
    assert seen[0] == ("tenant-a", "field-0", "season-2026", "soil_sensor", "c" * 64)
    assert r["rows"][0]["label_source"] == "soil_sensor_verified"
    assert r["status"] == "BLOCKED"  # the other 5 rows lack accepted receipts


def test_tenant_isolation_before_verifier_invocation():
    rows = records()
    rows[0]["tenant_id"] = "other"
    seen = []
    r = screen(rows, evidence=lambda *a: seen.append(a) or True)
    assert "case-0:TENANT_SCOPE_MISMATCH" in r["blocking_reasons"]
    assert len(seen) == 5


def test_feature_arrived_too_late_blocks():
    rows = records()
    rows[0]["feature_available_at"] = at(18)
    assert "case-0:FUTURE_OR_LATE_FEATURE" in screen(rows)["blocking_reasons"]


def test_feature_event_time_after_availability_blocks():
    rows = records()
    rows[0]["feature_event_at"] = at(2)
    assert "case-0:FUTURE_OR_LATE_FEATURE" in screen(rows)["blocking_reasons"]


def test_target_before_prediction_blocks():
    rows = records()
    rows[0]["label_measured_at"] = rows[0]["prediction_at"]
    assert "case-0:LABEL_MATURITY_INVALID" in screen(rows)["blocking_reasons"]


def test_label_not_available_before_freeze_blocks():
    rows = records()
    rows[0]["label_available_at"] = at(31)
    assert "case-0:LABEL_MATURITY_INVALID" in screen(rows)["blocking_reasons"]


def test_naive_timestamp_blocks():
    rows = records()
    rows[0]["prediction_at"] = "2026-09-02T00:00:00"
    assert "case-0:TIMESTAMP_INVALID" in screen(rows)["blocking_reasons"]


def test_duplicate_case_refused():
    rows = records()
    rows[1]["case_id"] = rows[0]["case_id"]
    assert any("CASE_ID_INVALID_OR_DUPLICATE" in x for x in screen(rows)["blocking_reasons"])


def test_wrong_row_schema_never_becomes_ready():
    rows = records()
    rows[1]["debug"] = "unexpected"
    assert screen(rows)["status"] == "BLOCKED"


def test_boolean_measurement_not_numeric():
    rows = records()
    rows[0]["target_mm"] = True
    assert "case-0:DEPTH_INVALID" in screen(rows)["blocking_reasons"]


def test_nonfinite_and_negative_predictions_block():
    for value in (float("nan"), float("inf"), -1, 1e308):
        rows = records()
        rows[0]["prediction_mm"] = value
        assert "case-0:DEPTH_INVALID" in screen(rows)["blocking_reasons"]


def test_invalid_and_missing_receipt_rejected():
    for value in (None, "bad", "A" * 64):
        rows = records()
        rows[0]["measurement_receipt_sha256"] = value
        assert "case-0:MEASUREMENT_RECEIPT_INVALID" in screen(rows)["blocking_reasons"]


def test_invalid_manifest_artifact_hash_rejected():
    m = manifest()
    m["model_artifact_sha256"] = "placeholder"
    with pytest.raises(ValueError, match="MANIFEST_DIGEST_INVALID"):
        screen(m=m)


def test_invalid_manifest_policy_rejected():
    m = manifest()
    m["evaluation_policy"]["min_relative_mae_improvement"] = float("nan")
    with pytest.raises(ValueError, match="MANIFEST_POLICY_INVALID"):
        screen(m=m)


def test_empty_dataset_explicitly_blocked():
    assert screen([])["blocking_reasons"] == ["EMPTY_DATASET"]


def test_unchanged_source_objects_and_deterministic_digests():
    src = records()
    m = manifest()
    before = deepcopy((src, m))
    a = screen(src, m=m)
    b = screen(deepcopy(src), m=deepcopy(m))
    assert a == b
    assert before == (src, m)


def test_replay_of_well_formed_candidate_requires_no_other_services():
    r = screen()
    assert json.loads(json.dumps(r, allow_nan=False))["status"] == "CANDIDATE_NOT_EVALUATED"


def test_whitelisted_field_measurement_maps_only_after_callback_approval():
    rows = records()
    rows[0]["measurement_origin"] = "field_measurement"
    assert screen(rows)["rows"][0]["label_source"] == "field_measurement_verified"


def test_unconfigured_verifier_callback_is_rejected():
    with pytest.raises(ValueError, match="RECEIPT_VERIFIER_INVALID"):
        screen(evidence=object())


def test_invalid_source_dict_is_blocked_not_exception():
    rows = records()
    rows[0]["measurement_origin"] = {}
    assert "case-0:NOT_INDEPENDENT_MEASUREMENT" in screen(rows)["blocking_reasons"]


def test_expected_schema_does_not_contain_receipt_evidence_as_label():
    r = screen()
    assert "measurement_receipt_sha256" not in r["rows"][0]
    assert r["claimed_verified_receipt_sha256s"] == ["c" * 64]


def test_huge_integer_never_causes_overflow():
    rows = records()
    rows[0]["target_mm"] = 10**1000
    assert "case-0:DEPTH_INVALID" in screen(rows)["blocking_reasons"]


def test_huge_integer_policy_never_causes_overflow():
    m = manifest()
    m["evaluation_policy"]["min_relative_mae_improvement"] = 10**1000
    with pytest.raises(ValueError, match="MANIFEST_POLICY_INVALID"):
        screen(m=m)
