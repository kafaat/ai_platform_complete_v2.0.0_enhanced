"""P0 source-of-truth temporal tests; synthetic records, not receipt attestation."""

from datetime import UTC, datetime, timedelta

import pytest

from shared.continuous_learning_phase10 import (
    materialize_training_dataset,
    run_phase10_learning_cycle,
)
from shared.feature_store import (
    build_point_in_time_snapshot,
    materialize_online_feature_values,
    write_offline_feature_dataset,
)

pytestmark = pytest.mark.unit


def record(
    *,
    tenant="tenant-A",
    entity="field-1",
    event=0,
    prediction=20,
    first=4,
    second=5,
    source="s2-2025-v3",
    values=None,
):
    origin = datetime(2026, 1, 1, tzinfo=UTC)

    def stamp(i):
        return (origin + timedelta(hours=i)).isoformat()

    return {
        "tenant_id": tenant,
        "entity_type": "field",
        "entity_id": entity,
        "source_version": source,
        "event_time": stamp(event),
        "available_at": None,
        "feature_available_at": {"ndvi": stamp(first), "ec": stamp(second)},
        "ingested_at": stamp(max(first, second) + 1),
        "prediction_at": stamp(prediction),
        "features": values or {"ndvi": 0.4, "ec": 2.0},
        "labels": {"actual_yield": 10.0},
    }


def offline(rows):
    return write_offline_feature_dataset(rows, feature_set_id="trusted-feature-set")


def test_missing_availability_never_is_point_in_time_safe():
    value = record()
    del value["feature_available_at"]
    assert offline([value])["point_in_time_safe"] is False
    assert offline([value])["unsafe_reason_counts"] == {"availability_missing": 1}
    assert build_point_in_time_snapshot([value], as_of="2026-01-02T00:00:00Z")["row_count"] == 0


@pytest.mark.parametrize("field", ["ingested_at", "prediction_at", "source_version", "tenant_id"])
def test_required_temporal_lineage_is_never_assumed(field):
    value = record()
    value.pop(field)
    assert offline([value])["point_in_time_safe"] is False
    assert materialize_online_feature_values([value], feature_set_id="features")["write_count"] == 0


def test_a_feature_available_after_prediction_blocks_entire_row():
    value = record(first=18, second=21, prediction=20)
    result = offline([value])
    assert result["point_in_time_safe"] is False
    assert result["unsafe_reason_counts"] == {"feature_not_available_at_prediction": 1}


def test_naive_timestamps_are_rejected_instead_of_silent_utc_cast():
    value = record()
    value["event_time"] = "2026-01-01T00:00:00"
    assert offline([value])["point_in_time_safe"] is False
    with pytest.raises(ValueError):
        build_point_in_time_snapshot([value], as_of="2026-01-02T00:00:00")


def test_per_feature_availability_requires_all_actual_feature_keys():
    value = record()
    value["feature_available_at"].pop("ec")
    assert offline([value])["point_in_time_safe"] is False


def test_legacy_timestamp_does_not_become_a_fake_recent_online_value():
    value = {"tenant_id": "tenant-A", "entity_id": "field-1", "features": {"ndvi": 0.2}}
    online = materialize_online_feature_values([value], feature_set_id="features")
    assert online["write_count"] == 0
    assert online["excluded_count"] == 1
    assert online["freshness_checked"] is False


def test_two_tenants_never_share_snapshot_or_online_key():
    a, b = record(tenant="a"), record(tenant="b")
    assert offline([a, b])["point_in_time_safe"] is False  # mixed-tenant dataset blocked
    snapshot = build_point_in_time_snapshot([a, b], as_of="2026-01-01T21:00:00Z")
    assert snapshot["row_count"] == 2
    assert {r["tenant_id"] for r in snapshot["rows"]} == {"a", "b"}
    online = materialize_online_feature_values([a, b], feature_set_id="features")
    assert online["write_count"] == 2
    assert len({row["online_key"] for row in online["writes"]}) == 2
    assert all("labels" not in row for row in online["writes"])


def test_a_derived_feature_uses_the_latest_valid_feature_not_the_latest_row():
    first = record(event=0, prediction=10, values={"ndvi": 0.4, "ec": 2.0})
    later = record(event=1, prediction=10, first=7, second=7, values={"ndvi": 0.8, "ec": 3.0})
    # Different per-feature events: newest event for one feature is valid only
    # when that feature was available and ingested before the decision.
    later["feature_available_at"]["ec"] = "2026-01-01T11:00:00Z"
    # Per-row provenance is incomplete, thus the later row is entirely excluded.
    snapshot = build_point_in_time_snapshot([first, later], as_of="2026-01-01T10:00:00Z")
    assert snapshot["row_count"] == 1
    assert snapshot["rows"][0]["features"]["ndvi"] == 0.4
    assert snapshot["rows"][0]["features"]["ec"] == 2.0


def test_annual_embedding_not_usable_before_its_release_date():
    annual = record(event=0, first=300, second=300, prediction=400)
    # For long-lived products set an explicit age policy, but never hide release latency.
    old_decision = build_point_in_time_snapshot(
        [annual], as_of="2026-01-11T00:00:00Z", max_age_hours=9000
    )
    assert old_decision["row_count"] == 0
    approved = build_point_in_time_snapshot(
        [annual], as_of="2027-01-01T00:00:00Z", max_age_hours=9000
    )
    assert approved["row_count"] == 1


def test_unverified_temporal_lineage_blocks_phase10_model_promotion():
    value = record()
    del value["feature_available_at"]
    out = run_phase10_learning_cycle(
        phase9_cycle={"feature_store_batch": [value]},
        champion_model={"model_id": "champion", "metrics": {"score": 0.5}},
        challenger_model={"model_id": "candidate", "metrics": {"score": 0.9}},
    )
    assert out["training_dataset"]["status"] == "blocked"
    assert out["feature_store_runtime"]["offline_dataset_version"]["point_in_time_safe"] is False
    assert out["model_promotion"]["decision"] == "blocked"
    assert out["model_registry_runtime"]["serving_promotion"]["decision"] == "blocked"


def test_direct_training_dataset_entrypoint_does_not_bypass_temporal_gate():
    bad = record()
    bad.pop("ingested_at")
    direct = materialize_training_dataset([bad])
    assert direct["status"] == "blocked"
    assert "temporal_integrity_unverified" in direct["quality"]["blocked_reasons"]
