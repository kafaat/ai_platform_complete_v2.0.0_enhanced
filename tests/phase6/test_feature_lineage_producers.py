"""In-repo producers of feature rows send the lineage the temporal gate needs.

Each producer copies times it already records; none reads the clock to fill a
gap. A row whose source lacks a time stays blocked. Each positive case has a
negative control in the same shape.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest

from shared.autonomous_farm_os_phase9 import (
    build_feature_store_batch,
    run_phase9_autonomy_cycle,
    runtime_feature_lineage,
)
from shared.continuous_learning_phase10 import run_phase10_learning_cycle
from shared.feature_store.practice_review import review_practice_dataset

pytestmark = pytest.mark.unit


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _runtime(*, generated_at: str | None, created_at: str | None) -> dict:
    state = {
        "state_id": "cfs_lineage_1",
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "schema_version": "canonical_field_state.v2",
        "fusion_strategy_version": "fusion.v3",
        "state": {"confidence": 0.82, "operational_truths": {"ndvi": 0.42}},
    }
    if generated_at is not None:
        state["generated_at"] = generated_at
    runtime = {
        "runtime_id": "frt_lineage_1",
        "canonical_state": state,
        "digital_twin_view": {"field_id": "field-1", "limitations": []},
        "phase6_runtime_inputs": {"features": {"crop_vigor": "low", "etc_mm": 5.2, "kc": 0.9}},
        "recommendation_lifecycle": {
            "recommendation_id": "rec_lineage_1",
            "source_state_id": "cfs_lineage_1",
            "field_id": "field-1",
            "tenant_id": "tenant-1",
            "status": "approved",
            "action_type": "irrigation",
            "decision": {
                "action_type": "irrigation",
                "water_mm": 10,
                "operator_approved": True,
                "risk_score": 0.1,
            },
            "evidence": {},
        },
    }
    if created_at is not None:
        runtime["created_at"] = created_at
    return runtime


def _recent_runtime() -> dict:
    now = datetime.now(UTC)
    return _runtime(
        generated_at=_iso(now - timedelta(hours=2)), created_at=_iso(now - timedelta(hours=1))
    )


def test_phase9_rows_copy_recorded_times_and_versions():
    rt = _runtime(generated_at="2026-06-26T08:00:00+00:00", created_at="2026-06-26T08:05:00+00:00")
    row = build_feature_store_batch(canonical_runtime=rt, decision_at="2026-06-26T08:10:00+00:00")[
        0
    ]
    assert row["tenant_id"] == "tenant-1"
    assert (
        row["source_version"]
        == "canonical_field_state/canonical_field_state.v2/fusion.v3/cfs_lineage_1"
    )
    assert row["event_time"] == "2026-06-26T08:00:00+00:00"
    assert row["available_at"] == "2026-06-26T08:00:00+00:00"
    assert row["ingested_at"] == "2026-06-26T08:05:00+00:00"
    assert row["prediction_at"] == "2026-06-26T08:10:00+00:00"


def test_phase9_never_fills_a_missing_time_from_the_clock():
    # Before: event_time was datetime.now() for every row. Now a time the runtime
    # does not record stays None, and str(None) is not accepted as a time.
    rt = _runtime(generated_at=None, created_at=None)
    rt["canonical_state"]["generated_at"] = "None"
    lineage = runtime_feature_lineage(rt)
    assert lineage["event_time"] is None
    assert lineage["available_at"] is None
    assert lineage["ingested_at"] is None
    assert lineage["prediction_at"] is None
    row = build_feature_store_batch(canonical_runtime=rt)[0]
    assert row["event_time"] is None


def test_phase9_prefers_the_state_valid_time_over_its_generation_time():
    rt = _runtime(generated_at="2026-06-26T08:00:00+00:00", created_at="2026-06-26T08:05:00+00:00")
    rt["canonical_state"]["state"]["as_of_time"] = "2026-06-26T07:00:00+00:00"
    lineage = runtime_feature_lineage(rt)
    assert lineage["event_time"] == "2026-06-26T07:00:00+00:00"
    assert lineage["available_at"] == "2026-06-26T08:00:00+00:00"


def test_phase9_cycle_feeds_a_point_in_time_safe_phase10_cycle():
    cycle = run_phase9_autonomy_cycle(canonical_runtime=_recent_runtime())
    row = cycle["feature_store_batch"][0]
    assert row["prediction_at"] == cycle["execution_plan"]["created_at"]
    out = run_phase10_learning_cycle(phase9_cycle=cycle)
    fs = out["feature_store_runtime"]
    assert fs["offline_dataset_version"]["point_in_time_safe"] is True
    assert fs["point_in_time_snapshot"]["row_count"] == 1
    assert (
        "temporal_integrity_unverified" not in out["training_dataset"]["quality"]["blocked_reasons"]
    )

    # Negative control: the same runtime without the state's generation time.
    rt = _recent_runtime()
    del rt["canonical_state"]["generated_at"]
    blocked = run_phase10_learning_cycle(
        phase9_cycle=run_phase9_autonomy_cycle(canonical_runtime=rt)
    )
    assert (
        blocked["feature_store_runtime"]["offline_dataset_version"]["point_in_time_safe"] is False
    )
    assert blocked["training_dataset"]["status"] == "blocked"
    assert (
        "temporal_integrity_unverified" in blocked["training_dataset"]["quality"]["blocked_reasons"]
    )


def _practice_request(*, ingested: bool) -> dict:
    records = []
    for customer, month in (("train-customer", "06"), ("held-out-customer", "08")):
        row = {
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
        if ingested:
            row["feature_ingested_at"] = f"2026-{month}-01T02:00:00Z"
        records.append(row)
    consents = {
        customer: {
            "tenant_id": "t1",
            "purpose": "shared_learning",
            "status": "active",
            "source_record_id": "consent-" + customer,
            "granted_at": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
        }
        for customer in ("train-customer", "held-out-customer")
    }
    return {
        "records": records,
        "consents": consents,
        "tenant_id": "t1",
        "as_of": "2026-09-13T00:00:00Z",
        "split_at": "2026-07-01T00:00:00Z",
        "held_out_customers": ["held-out-customer"],
        "feature_names": ["water_m3"],
        "feature_units": {"water_m3": "m3"},
        "label_name": "yield_kg",
        "label_unit": "kg",
    }


def _review(request: dict) -> dict:
    request = copy.deepcopy(request)
    return review_practice_dataset(request.pop("records"), **request)


def test_practice_export_lineage_reaches_the_manifest():
    result = _review(_practice_request(ingested=True))
    assert result["status"] == "prepared_for_review"
    for name in ("train", "evaluation"):
        manifest = result["manifests"][name]
        assert manifest["point_in_time_safe"] is True
        assert manifest["as_of"] == "2026-09-13T00:00:00+00:00"
    row = result["partitions"]["train"][0]
    assert row["tenant_id"] == "t1"
    assert row["available_at"] == "2026-06-01T01:00:00Z"
    assert row["ingested_at"] == "2026-06-01T02:00:00Z"
    assert row["prediction_at"] == "2026-06-02T00:00:00Z"
    assert row["source_version"].startswith("sha256:") and len(row["source_version"]) == 71


def test_practice_export_without_ingestion_time_stays_blocked():
    # Negative control: the export does not record ingestion; none is invented.
    result = _review(_practice_request(ingested=False))
    assert result["status"] == "blocked"
    assert result["blocked_reasons"] == [
        "temporal_lineage_unverified_train",
        "temporal_lineage_unverified_evaluation",
    ]
    assert result["partitions"]["train"][0]["ingested_at"] is None
    assert result["manifests"]["train"]["unsafe_reason_counts"] == {
        "ingestion_time_missing_or_invalid": 1
    }
