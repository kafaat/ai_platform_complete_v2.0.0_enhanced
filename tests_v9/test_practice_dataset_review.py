"""Synthetic operations prove export checks, not Yemeni agronomic outcomes."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shared.feature_store.practice_review import review_practice_dataset

pytestmark = pytest.mark.unit


def request():
    records = []
    for customer, month in (("train-customer", "06"), ("held-out-customer", "08")):
        records.append(
            {
                "tenant_id": "t1",
                "customer_id": customer,
                "field_id": "field-" + customer,
                "operation_id": "op-" + customer,
                "source_record_id": "ledger-" + customer,
                "region": "synthetic-region",
                "crop": "synthetic-crop",
                "language": "ar",
                "season_id": "synthetic-2026",
                "features": {"water_m3": 0.0},
                "feature_units": {"water_m3": "m3"},
                "labels": {"yield_kg": 100.0},
                "label_unit": "kg",
                "reported_result": "unchanged",
                "event_time": f"2026-{month}-01T00:00:00Z",
                "feature_available_at": f"2026-{month}-01T01:00:00Z",
                "decision_at": f"2026-{month}-02T00:00:00Z",
                "matures_at": f"2026-{month}-10T00:00:00Z",
                "outcome_at": f"2026-{month}-11T00:00:00Z",
                "outcome_recorded_at": f"2026-{month}-12T00:00:00Z",
            }
        )
    return {
        "records": records,
        "policy": {
            "tenant_id": "t1",
            "as_of": "2026-09-13T00:00:00Z",
            "split_at": "2026-07-01T00:00:00Z",
            "held_out_customers": ["held-out-customer"],
            "feature_names": ["water_m3"],
            "feature_units": {"water_m3": "m3"},
            "label_name": "yield_kg",
            "label_unit": "kg",
        },
        "consents": {
            customer: {
                "tenant_id": "t1",
                "purpose": "shared_learning",
                "status": "active",
                "source_record_id": "consent-" + customer,
                "granted_at": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
            }
            for customer in ("train-customer", "held-out-customer")
        },
    }


def review(payload=None):
    payload = request() if payload is None else payload
    return review_practice_dataset(
        payload["records"], consents=payload["consents"], **payload["policy"]
    )


def test_valid_candidates_reuse_manifest_and_preserve_zero_and_provenance():
    result = review()
    assert result["status"] == "prepared_for_review"
    assert {name: len(rows) for name, rows in result["partitions"].items()} == {
        "train": 1,
        "evaluation": 1,
    }
    training = result["partitions"]["train"][0]
    assert training["features"]["water_m3"] == 0.0
    assert training["quality"]["tenant_id"] == "t1"
    assert result["manifests"]["train"]["row_count"] == 1
    assert result["training_started"] is False and result["model_promotion_allowed"] is False
    assert result["agronomic_validation"] == "not_established" and result["persisted"] is False


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("matures_at", "2026-12-01T00:00:00Z", "outcome_not_mature"),
        ("feature_available_at", "2026-06-03T00:00:00Z", "feature_not_available_at_decision"),
        ("outcome_recorded_at", "2026-07-02T00:00:00Z", "training_case_not_known_at_split"),
        ("outcome_at", "2026-06-05T00:00:00Z", "outcome_measured_before_maturity"),
        ("decision_at", "2026-06-02T00:00:00", "invalid_decision_at"),
        ("features", {"water_m3": None}, "missing_selected_feature"),
        ("labels", {"yield_kg": None}, "missing_outcome"),
        ("labels", {"yield_kg": True}, "invalid_numeric_outcome"),
        ("feature_units", {"water_m3": "pump_hours"}, "feature_unit_mismatch"),
        ("label_unit", "kg/ha", "label_unit_mismatch"),
    ],
)
def test_unusable_cases_are_excluded_with_a_reason(key, value, reason):
    payload = request()
    payload["records"][0][key] = value
    result = review(payload)
    assert result["status"] == "blocked" and result["partitions"]["train"] == []
    assert reason in result["excluded"][0]["reasons"]
    assert result["cohorts"][0]["cases"] == 2


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "revoked"},
        {"valid_until": "2026-08-01T00:00:00Z"},
        {"purpose": "provide_service"},
        {"tenant_id": "another-tenant"},
        {"source_record_id": None},
    ],
)
def test_consent_is_purpose_scoped_current_and_traceable(updates):
    payload = request()
    payload["consents"]["train-customer"].update(updates)
    result = review(payload)
    assert result["partitions"]["train"] == []
    assert "missing_or_inactive_learning_consent" in result["excluded"][0]["reasons"]


def test_same_customer_and_transferred_field_cannot_cross_partitions():
    payload = request()
    # Even a field transferred between customers remains held out.
    payload["records"][1]["field_id"] = payload["records"][0]["field_id"]
    result = review(payload)
    assert result["partitions"]["train"] == []
    assert "held_out_field" in result["excluded"][0]["reasons"]
    payload = request()
    old = copy.deepcopy(payload["records"][0])
    old.update(customer_id="held-out-customer", operation_id="old-held-out", field_id="old-field")
    payload["records"].append(old)
    result = review(payload)
    assert {r["quality"]["customer_id"] for r in result["partitions"]["train"]} == {
        "train-customer"
    }
    assert "held_out_case_before_split" in next(
        r["reasons"] for r in result["excluded"] if r["operation_id"] == "old-held-out"
    )


def test_repeated_messages_do_not_become_independent_cases_and_conflicts_fail():
    payload = request()
    payload["records"].extend([copy.deepcopy(payload["records"][0]) for _ in range(30)])
    result = review(payload)
    assert result["duplicates"] == 30 and result["unique_cases"] == 2
    assert result["cohorts"][0]["customers"] == 2
    payload["records"][-1]["labels"]["yield_kg"] = 500
    with pytest.raises(ValueError, match="conflicting"):
        review(payload)


def test_foreign_tenant_batch_fails_before_returning_any_record():
    payload = request()
    payload["records"][1]["tenant_id"] = "t2"
    with pytest.raises(PermissionError):
        review(payload)


def test_missing_followup_and_harm_remain_in_descriptive_denominator():
    payload = request()
    payload["records"][0].update(labels={}, reported_result="no_response")
    payload["records"][1]["reported_result"] = "worse"
    result = review(payload)
    assert result["cohorts"][0]["reported_results"] == {"no_response": 1, "worse": 1}
    assert result["cohorts"][0]["cases"] == 2
    assert result["causal_effect"] == "not_estimated"


def test_input_and_consent_changes_change_review_fingerprints():
    payload = request()
    first = review(payload)
    payload["records"][0]["labels"]["yield_kg"] = 101
    second = review(payload)
    assert first["source_sha256"] != second["source_sha256"]
    assert (
        first["manifests"]["train"]["content_hash"] != second["manifests"]["train"]["content_hash"]
    )
    payload["consents"]["train-customer"]["status"] = "revoked"
    third = review(payload)
    assert second["consents_sha256"] != third["consents_sha256"]
    assert third["partitions"]["train"] == []


def test_offline_review_cli(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "review.json"
    source.write_text(json.dumps(request()), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "shared.feature_store.practice_review",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=True,
        timeout=20,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "prepared_for_review" and result["training_started"] is False
