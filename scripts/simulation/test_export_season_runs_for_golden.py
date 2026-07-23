from export_season_runs_for_golden import ExportError, export_rows


def test_exports_only_verified_hindcasts_without_tenant_id():
    rows = [
        {
            "run_id": "run-1",
            "tenant_id": "must-not-leak",
            "field_id": "field-1",
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
    assert out["export_summary"]["rejections"][0]["reason"] == "mode_not_historical_hindcast"


def _eligible_row(**over):
    base = {
        "run_id": "run-t",
        "field_id": "field-1",
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
