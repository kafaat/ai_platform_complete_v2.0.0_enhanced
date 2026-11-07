from datetime import date, datetime

import pytest

from scripts.simulation.export_season_runs_for_golden import ExportError, export_rows
from scripts.simulation.sim_golden import _time

pytestmark = pytest.mark.unit


def test_exports_only_verified_hindcasts_without_tenant_id():
    rows = [
        {
            "run_id": "run-1",
            "tenant_id": "must-not-leak",
            "field_id": "field-1",
            "farm_id": "farm-1",
            "season_id": "2025",
            "crop": "Wheat",
            "mode": "historical_hindcast",
            "observed_yield_kg_ha": 4100,
            "result": {"yield_kg_ha": 4000},
            "observation_source": "certified_scale",
            "harvest_at": "2025-06-01T00:00:00+00:00",
            "created_at": "2025-05-01T00:00:00+00:00",
            "engine_version": "pcse-1",
            "input_digest": "a" * 64,
        },
        {"run_id": "run-2", "mode": "what_if"},
    ]
    out = export_rows(rows, pseudonym_salt="0123456789abcdef")
    assert len(out["samples"]) == 1
    assert "tenant_id" not in out["samples"][0]
    assert out["samples"][0]["farm_id"] != "field-1"
    assert out["samples"][0]["farm_id"] != "farm-1"
    assert out["export_summary"]["rejections"][0]["reason"] == "mode_not_historical_hindcast"


def _eligible_row(**over):
    base = {
        "run_id": "run-t",
        "field_id": "field-1",
        "farm_id": "farm-1",
        "season_id": "2025",
        "crop": "wheat",
        "mode": "historical_hindcast",
        "observed_yield_kg_ha": 4100,
        "result": {"yield_kg_ha": 4000},
        "observation_source": "certified_scale",
        "harvest_at": "2025-06-01T00:00:00+00:00",
        "created_at": "2025-05-01T00:00:00+00:00",
        "engine_version": "pcse-1",
        "input_digest": "a" * 64,
    }
    return base | over


def test_prediction_at_or_after_harvest_is_rejected_as_temporal_leak():
    # Prediction produced AFTER harvest → could encode the actual outcome → excluded.
    leaked = _eligible_row(run_id="leak", created_at="2025-07-01T00:00:00+00:00")
    # Prediction exactly AT harvest is also a leak (not strictly before).
    tied = _eligible_row(run_id="tie", created_at="2025-06-01T00:00:00+00:00")
    out = export_rows([leaked, tied], pseudonym_salt="0123456789abcdef")
    assert out["samples"] == []
    reasons = {r["reason"] for r in out["export_summary"]["rejections"]}
    assert reasons == {"temporal_leak_prediction_not_before_harvest"}


def test_unparseable_timestamps_fail_closed():
    out = export_rows(
        [_eligible_row(run_id="bad", harvest_at="not-a-date")],
        pseudonym_salt="0123456789abcdef",
    )
    assert out["samples"] == []
    assert out["export_summary"]["rejections"][0]["reason"] == "unparseable_timestamps"


def test_prediction_strictly_before_harvest_is_eligible():
    out = export_rows([_eligible_row()], pseudonym_salt="0123456789abcdef")
    assert len(out["samples"]) == 1


def test_short_salt_is_rejected():
    try:
        export_rows([], pseudonym_salt="short")
    except ExportError:
        return
    raise AssertionError("short pseudonym salt accepted")


def test_field_only_rows_cannot_be_counted_as_distinct_farms():
    rows = [_eligible_row(run_id=f"run-{i}", field_id=f"field-{i}") for i in range(3)]
    for row in rows:
        row.pop("farm_id")
    out = export_rows(rows, pseudonym_salt="0123456789abcdef")
    assert out["samples"] == []
    assert out["export_summary"]["rejected"] == 3
    assert {row["reason"] for row in out["export_summary"]["rejections"]} == {"missing_farm"}


@pytest.mark.parametrize("farm_id", [None, "", " ", True, 1])
def test_unknown_or_invalid_farm_identity_is_excluded(farm_id):
    out = export_rows([_eligible_row(farm_id=farm_id)], pseudonym_salt="0123456789abcdef")
    assert out["samples"] == []
    assert out["export_summary"]["rejections"][0]["reason"] == "missing_farm"


def test_multiple_fields_from_one_farm_keep_one_farm_pseudonym():
    rows = [_eligible_row(run_id=f"run-{i}", field_id=f"field-{i}") for i in range(3)]
    out = export_rows(rows, pseudonym_salt="0123456789abcdef")
    assert len(out["samples"]) == 3
    assert len({row["farm_id"] for row in out["samples"]}) == 1


# ── Follow-up to the 2026-11-07 audit: exported rows must be admissible by the evaluator ──


@pytest.mark.parametrize(
    ("harvest", "prediction", "expected_prediction"),
    [
        (date(2025, 6, 1), "2025-05-01", "2025-05-01T00:00:00Z"),  # DB date + naive ISO
        (datetime(2025, 6, 1, 12, 0), "2025-05-01T08:00:00+03:00", "2025-05-01T05:00:00Z"),
    ],
)
def test_exported_timestamps_are_explicit_utc_and_admissible_by_the_evaluator(
    harvest, prediction, expected_prediction
):
    out = export_rows(
        [_eligible_row(harvest_at=harvest, created_at=prediction)],
        pseudonym_salt="0123456789abcdef",
    )
    sample = out["samples"][0]
    for key in ("harvest_at", "prediction_at"):
        assert sample[key].endswith("Z"), sample[key]
        _time(sample[key])  # the evaluator refuses timezone-less timestamps
    assert sample["prediction_at"] == expected_prediction


def test_a_non_object_row_is_rejected_not_a_crash():
    out = export_rows(["not-a-row", _eligible_row()], pseudonym_salt="0123456789abcdef")
    assert len(out["samples"]) == 1
    assert out["export_summary"]["rejections"][0]["reason"] == "malformed_row"
