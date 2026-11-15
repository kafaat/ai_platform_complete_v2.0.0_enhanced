"""Point-in-time claims of the feature store must follow ``available_at`` and an as-of time.

Re-homed from ``fix/feature-store-pit-available-at`` (465b35bef) onto the phase-12
temporal-integrity model: every row now also carries tenant, ``source_version``,
``ingested_at`` and ``prediction_at``. Each test pairs a positive case with a
negative control in the same input shape, so the assertion that flips is the one
the fix is about.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from shared.continuous_learning_phase10 import run_phase10_learning_cycle
from shared.feature_store import build_point_in_time_snapshot, write_offline_feature_dataset
from shared.feature_store.runtime import resolve_learning_as_of

pytestmark = pytest.mark.unit

AS_OF = "2026-06-26T12:00:00+00:00"


def _row(entity_id: str, event_time: str | None, available_at: str | None = None) -> dict:
    """A row whose ingestion and prediction follow its availability (or event)."""
    known = available_at if available_at is not None else event_time
    row = {
        "tenant_id": "tenant-one",
        "source_version": "fixture-source-v1",
        "feature_id": f"feat_{entity_id}_{event_time}",
        "entity_type": "field",
        "entity_id": entity_id,
        "event_time": event_time,
        "ingested_at": known,
        "prediction_at": known,
        "features": {"ndvi": 0.5},
        "labels": {"net_benefit": 1},
    }
    if available_at is not None:
        row["available_at"] = available_at
    return row


def _offline(records, **kwargs):
    return write_offline_feature_dataset(records, feature_set_id="fset_test", **kwargs)


def test_future_available_at_is_not_point_in_time_safe():
    future = [_row("f1", "2026-06-26T08:00:00+00:00", "2030-01-01T00:00:00+00:00")]
    out = _offline(future, as_of=AS_OF)
    assert out["point_in_time_safe"] is False
    assert out["future_available_count"] == 1
    assert "feature_not_available_at_snapshot" in out["pit_unsafe_reasons"]
    # The row is internally ordered: only the as-of time exposes it.
    assert _offline(future)["temporal_integrity"] == "chronology_checked"
    assert _offline(future)["point_in_time_safe"] is False
    # Negative control: the same row published before as_of is safe.
    historic = [_row("f1", "2026-06-26T08:00:00+00:00", "2026-06-26T09:00:00+00:00")]
    control = _offline(historic, as_of=AS_OF)
    assert control["point_in_time_safe"] is True
    assert control["future_available_count"] == 0


def test_historically_available_rows_are_safe_and_each_condition_is_required():
    rows = [
        _row("f1", "2026-06-26T08:00:00+00:00", "2026-06-26T08:30:00+00:00"),
        _row("f2", "2026-06-26T09:00:00Z", "2026-06-26T12:00:00Z"),  # available == as_of
    ]
    out = _offline(rows, as_of=AS_OF)
    assert out["point_in_time_safe"] is True
    assert out["pit_unsafe_reasons"] == []
    assert out["missing_available_at_count"] == 0
    assert out["as_of"] == AS_OF

    # Negative controls, one condition each.
    no_as_of = _offline(rows)
    assert no_as_of["point_in_time_safe"] is False
    assert no_as_of["pit_unsafe_reasons"] == ["as_of_missing"]
    assert no_as_of["future_available_count"] is None

    missing = _offline([*rows, _row("f3", "2026-06-26T10:00:00+00:00")], as_of=AS_OF)
    assert missing["point_in_time_safe"] is False
    assert missing["missing_available_at_count"] == 1

    reversed_order = _offline(
        [_row("f1", "2026-06-26T08:30:00+00:00", "2026-06-26T08:00:00+00:00")], as_of=AS_OF
    )
    assert reversed_order["point_in_time_safe"] is False
    assert reversed_order["available_before_event_count"] == 1


def test_naive_available_at_is_not_safe():
    naive = [_row("f1", "2026-06-26T08:00:00+00:00", "2026-06-26T09:00:00")]
    out = _offline(naive, as_of=AS_OF)
    assert out["point_in_time_safe"] is False
    assert out["naive_timestamp_count"] == 1
    assert "naive_timestamp" in out["pit_unsafe_reasons"]
    # Negative control: the same instant with an explicit offset is safe.
    aware = [_row("f1", "2026-06-26T08:00:00+00:00", "2026-06-26T09:00:00+00:00")]
    assert _offline(aware, as_of=AS_OF)["point_in_time_safe"] is True
    # A naive as_of is no as-of time either.
    assert _offline(aware, as_of="2026-06-26T12:00:00")["pit_unsafe_reasons"] == ["as_of_naive"]


def test_rows_without_available_at_hash_as_before():
    # Existing manifests (no lineage keys) keep their content_hash and version id.
    legacy = {
        "feature_id": "feat_legacy",
        "entity_type": "field",
        "entity_id": "f1",
        "event_time": "2026-06-26T11:00:00+03:00",
        "features": {"ndvi": 0.5},
        "labels": {"net_benefit": 1},
    }
    assert _offline([legacy])["content_hash"] == _offline([legacy], as_of=AS_OF)["content_hash"]
    # The exact normalization the manifest always used (offset kept, no extra keys).
    historical = [
        {
            "entity_type": "field",
            "entity_id": "f1",
            "feature_id": "feat_legacy",
            "event_time": "2026-06-26T11:00:00+03:00",
            "features": {"ndvi": 0.5},
            "labels": {"net_benefit": 1},
            "quality": {},
        }
    ]
    expected = sha256(
        json.dumps(historical, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert _offline([legacy])["content_hash"] == expected
    with_availability = {**legacy, "available_at": "2026-06-26T09:00:00+00:00"}
    assert _offline([with_availability])["content_hash"] != expected


def test_snapshot_excludes_future_and_missing_availability_rows():
    records = [
        _row("a", "2026-06-26T10:00:00+00:00", "2026-06-26T10:05:00+00:00"),
        # Later event for "a", published after as_of: must not leak into the snapshot.
        _row("a", "2026-06-26T11:00:00+00:00", "2030-01-01T00:00:00+00:00"),
        # Legacy row with no available_at. The PIT branch kept it and counted it;
        # the reconciled rule is the safer one: excluded, and still counted.
        _row("b", "2026-06-26T11:30:00+00:00"),
    ]
    snap = build_point_in_time_snapshot(records, as_of=AS_OF)
    by_entity = {r["entity_id"]: r for r in snap["rows"]}
    assert by_entity["a"]["event_time"] == "2026-06-26T10:00:00+00:00"
    assert by_entity["a"]["available_at"] == "2026-06-26T10:05:00+00:00"
    assert "b" not in by_entity
    assert snap["future_available_count"] == 1
    assert snap["missing_available_at_count"] == 1
    assert snap["excluded_count"] == 2
    assert snap["row_count"] == 1

    # Negative control: once the later row is published before as_of it wins.
    records[1].update(
        available_at="2026-06-26T11:10:00+00:00",
        ingested_at="2026-06-26T11:10:00+00:00",
        prediction_at="2026-06-26T11:10:00+00:00",
    )
    control = build_point_in_time_snapshot(records, as_of=AS_OF)
    by_entity = {r["entity_id"]: r for r in control["rows"]}
    assert by_entity["a"]["event_time"] == "2026-06-26T11:00:00+00:00"
    assert control["future_available_count"] == 0
    assert control["excluded_count"] == 1  # only the legacy row


def test_snapshot_excludes_naive_rows_and_rejects_naive_as_of():
    records = [
        _row("a", "2026-06-26T10:00:00"),  # naive event_time
        _row("b", "2026-06-26T10:00:00+00:00", "2026-06-26T10:30:00"),  # naive available_at
        _row("c", "2026-06-26T10:00:00+00:00", "2026-06-26T10:30:00+00:00"),
    ]
    snap = build_point_in_time_snapshot(records, as_of=AS_OF)
    assert [r["entity_id"] for r in snap["rows"]] == ["c"]
    assert snap["naive_timestamp_count"] == 2
    assert snap["excluded_count"] == 2
    with pytest.raises(ValueError, match="timezone-aware"):
        build_point_in_time_snapshot(records, as_of="2026-06-26T12:00:00")
    # Negative control: an aware as_of with the same wall-clock is accepted.
    assert build_point_in_time_snapshot(records, as_of="2026-06-26T12:00:00Z")["row_count"] == 1


def test_learning_as_of_is_capped_so_future_rows_cannot_certify_themselves():
    future = [_row("a", "2030-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00")]
    assert resolve_learning_as_of(future) < "2030"
    past = [_row("a", "2026-06-26T10:00:00+00:00", "2026-06-26T10:00:00+00:00")]
    assert resolve_learning_as_of(past) == "2026-06-26T10:00:00+00:00"


def test_learning_as_of_compares_instants_not_strings():
    # 12:00+03:00 is 09:00Z, earlier than 10:00Z, although it sorts later as text.
    rows = [
        _row("a", "2026-06-26T08:00:00+00:00", "2026-06-26T12:00:00+03:00"),
        _row("b", "2026-06-26T08:00:00+00:00", "2026-06-26T10:00:00+00:00"),
    ]
    assert max(r["prediction_at"] for r in rows) == "2026-06-26T12:00:00+03:00"
    assert resolve_learning_as_of(rows) == "2026-06-26T10:00:00+00:00"
    # Naive and missing prediction times are ignored, not read as UTC.
    rows.append({**_row("c", "2026-06-26T08:00:00+00:00"), "prediction_at": "2026-06-27T00:00:00"})
    assert resolve_learning_as_of(rows) == "2026-06-26T10:00:00+00:00"
    now = datetime(2026, 6, 26, 9, 30, tzinfo=UTC)
    assert resolve_learning_as_of(rows, now=now) == now.isoformat()


def _cycle(records):
    return run_phase10_learning_cycle(
        phase9_cycle={"cycle_id": "auto-pit", "feature_store_batch": records}
    )["feature_store_runtime"]


def test_phase10_cycle_reports_future_available_data_as_unsafe():
    past_event = "2026-06-26T10:00:00+00:00"
    fs = _cycle([_row("a", past_event, "2030-01-01T00:00:00+00:00")])
    assert fs["offline_dataset_version"]["point_in_time_safe"] is False
    assert fs["offline_dataset_version"]["future_available_count"] == 1
    assert fs["point_in_time_snapshot"]["row_count"] == 0
    # Negative control: published at the event time, the same row is safe and kept.
    fs = _cycle([_row("a", past_event, past_event)])
    assert fs["offline_dataset_version"]["point_in_time_safe"] is True
    assert fs["point_in_time_snapshot"]["row_count"] == 1
    # A future-dated event cannot move as_of forward to certify its own publication.
    fs = _cycle([_row("a", "2030-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00")])
    assert fs["offline_dataset_version"]["point_in_time_safe"] is False
