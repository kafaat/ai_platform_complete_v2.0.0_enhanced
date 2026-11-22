"""F4 — the advisor's read tools answer the arguments they were called with.

The defect: ``get_index_timeline(index, days)`` and ``get_weather_history(days)`` echoed the
caller's arguments next to the whole pre-loaded bundle, so another index or another window
fetched the same data under a different label; ``get_truecolor_scene`` did the same with a
date; and ``get_operation_windows`` answered an empty block as a successful read.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("fastapi")
from services.ai_agronomist import ai_evidence_runtime as ER  # noqa: E402
from services.ai_agronomist import tool_executor as EX  # noqa: E402
from services.ai_agronomist import tool_governance as GOV  # noqa: E402

FIELD = "field-a"


def _imagery() -> dict:
    return {
        "available": True,
        "range_days": 730,
        "since": "2024-11-22",
        "until": "2026-11-22",
        "per_indicator": {
            "truecolor": {
                "available": True,
                "dates": [{"date": "2026-11-20", "has_cog": True}, {"date": "2026-06-01"}],
                "total": 2,
            },
            "ndvi": {
                "available": True,
                "dates": [
                    {"date": "2025-03-01", "cloud_pct": 4},
                    {"date": "2026-11-20", "cloud_pct": 1},
                    {"date": "2026-10-01", "cloud_pct": 9},
                ],
                "total": 3,
            },
            "ndmi": {"available": True, "dates": [{"date": "2026-11-10"}], "total": 1},
            "ndre": {"available": False, "dates": [], "total": 0},
            "msavi": {"available": True, "dates": [], "total": 0},
        },
        "total_dates": 6,
        "ndvi_grid": [[0.1] * 40] * 40,
    }


def _weather() -> dict:
    return {
        "available": True,
        "range": {"start": "2024-11-22", "end": "2026-11-22"},
        "summary": {"days": 730, "total_precipitation_mm": 412.0},
        "monthly": [{"month": "2026-10", "precipitation_mm": 3.0}],
        "source": "weather-service",
    }


def _fetcher(**overrides):
    pack = {
        "field_id": FIELD,
        "imagery_timeline": _imagery(),
        "weather_history": _weather(),
    }
    pack.update(overrides)
    for key in [k for k, v in pack.items() if v is None]:
        del pack[key]
    return ER._build_agent_tool_fetcher(
        field_state={"field_id": FIELD}, ai_pack=pack, annotations={}
    )


def _dates(answer: dict) -> list[str]:
    return [item["date"] for item in answer["index_timeline"]["dates"]]


def _payload(answer: dict) -> dict:
    """What the tool returned, without the echo of the caller's own arguments."""
    return {k: v for k, v in answer.items() if k not in ("field_id", "index", "days")}


def test_witness_changing_the_arguments_changes_what_is_returned():
    """The audit's claim, stated on the old answer shape: another index or another window
    used to return the identical payload under a different label."""
    fetch = _fetcher()
    ndvi = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 730})
    ndmi = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndmi", "days": 730})
    assert _payload(ndvi) != _payload(ndmi), "another index returned the same payload"
    month = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 30})
    assert _payload(month) != _payload(ndvi), "another window returned the same payload"
    loaded = fetch("get_weather_history", {"field_id": FIELD, "days": 730})
    other = fetch("get_weather_history", {"field_id": FIELD, "days": 30})
    assert _payload(other) != _payload(loaded), "another weather window returned the same payload"


# ── get_index_timeline ──────────────────────────────────────────────────────────────────


def test_another_index_returns_another_series_and_never_the_bundle():
    fetch = _fetcher()
    ndvi = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 730})
    ndmi = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndmi", "days": 730})
    assert ndvi["available"] is True and ndmi["available"] is True
    assert _dates(ndvi) == ["2026-11-20", "2026-10-01", "2025-03-01"]
    assert _dates(ndmi) == ["2026-11-10"]
    for answer in (ndvi, ndmi):
        blob = json.dumps(answer)
        assert "per_indicator" not in blob and "ndvi_grid" not in blob
        assert "imagery_timeline" not in answer


def test_another_window_returns_another_series():
    fetch = _fetcher()
    month = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 30})
    quarter = fetch("get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 90})
    assert _dates(month) == ["2026-11-20"]
    assert _dates(quarter) == ["2026-11-20", "2026-10-01"]
    assert month["window"] == {"since": "2026-10-23", "until": "2026-11-22"}
    assert month["index_timeline"]["returned"] == 1
    assert month["index_timeline"]["total_in_window"] == 1
    assert month["index_timeline"]["truncated"] is False


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"index": "ndvi", "days": 900}, "requested_window_wider_than_loaded_window"),
        ({"index": "evi", "days": 30}, "index_not_in_owner_product"),
        ({"index": "ndre", "days": 30}, "owner_read_unavailable_for_index"),
        ({"index": "ndvi", "days": 0}, "invalid_days"),
        ({"index": "ndvi", "days": "30"}, "invalid_days"),
        ({"index": "ndvi", "days": True}, "invalid_days"),
        ({"days": 30}, "index_not_in_owner_product"),
    ],
)
def test_index_timeline_refuses_explicitly_and_carries_no_series(params, reason):
    answer = _fetcher()("get_index_timeline", {"field_id": FIELD, **params})
    assert answer["available"] is False
    assert answer["reason"] == reason
    assert answer["note_ar"]
    assert "index_timeline" not in answer and "imagery_timeline" not in answer


def test_index_with_no_scene_in_window_is_an_empty_series_not_a_refusal():
    answer = _fetcher()("get_index_timeline", {"field_id": FIELD, "index": "msavi", "days": 30})
    assert answer["available"] is True
    assert answer["index_timeline"] == {
        "dates": [],
        "returned": 0,
        "total_in_window": 0,
        "truncated": False,
    }


@pytest.mark.parametrize(
    ("imagery", "reason"),
    [
        (None, "imagery_timeline_not_loaded"),
        ({"per_indicator": {"ndvi": {"available": True, "dates": []}}}, "loaded_window_unknown"),
        (
            {"range_days": 730, "until": "not-a-date", "per_indicator": {"ndvi": {}}},
            "loaded_window_unknown",
        ),
    ],
)
def test_index_timeline_refuses_when_the_owner_block_cannot_prove_the_window(imagery, reason):
    answer = _fetcher(imagery_timeline=imagery)(
        "get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 30}
    )
    assert answer["available"] is False and answer["reason"] == reason


def test_long_series_is_cut_to_the_result_budget_and_says_so():
    imagery = _imagery()
    imagery["per_indicator"]["ndvi"]["dates"] = [
        {"date": f"2026-{month:02d}-{day:02d}", "scene_id": "S2A_MSIL2A_" + "x" * 60}
        for month in range(1, 11)
        for day in range(1, 25)
    ]
    answer = _fetcher(imagery_timeline=imagery)(
        "get_index_timeline", {"field_id": FIELD, "index": "ndvi", "days": 730}
    )
    series = answer["index_timeline"]
    assert series["total_in_window"] == 240
    assert 0 < series["returned"] < 240 and series["returned"] == len(series["dates"])
    assert series["truncated"] is True
    assert series["dates"][0]["date"] == "2026-10-24"  # newest kept
    governed = GOV.sanitize_tool_result(
        {"tool": "get_index_timeline", "outcome": "executed", "data": answer}
    )
    assert governed["data"] != "[omitted:result_too_large]"


# ── get_weather_history ─────────────────────────────────────────────────────────────────


def test_weather_for_another_window_is_refused_not_relabelled():
    answer = _fetcher()("get_weather_history", {"field_id": FIELD, "days": 30})
    assert answer["available"] is False
    assert answer["reason"] == "requested_window_not_loaded"
    assert answer["loaded_window"] == {"start": "2024-11-22", "end": "2026-11-22", "days": 730}
    assert "weather_history" not in answer
    assert "412" not in json.dumps(answer)


def test_weather_for_the_loaded_window_is_returned_with_its_window():
    answer = _fetcher()("get_weather_history", {"field_id": FIELD, "days": 730})
    assert answer["available"] is True
    assert answer["window"] == {"start": "2024-11-22", "end": "2026-11-22"}
    assert answer["weather_history"]["summary"]["total_precipitation_mm"] == 412.0


@pytest.mark.parametrize(
    ("weather", "days", "reason"),
    [
        (None, 730, "weather_history_not_loaded"),
        (
            {"available": False, "range": {"start": "2024-11-22", "end": "2026-11-22"}},
            730,
            "weather_history_unavailable_from_owner",
        ),
        ({"available": True, "summary": {"days": 730}}, 730, "loaded_window_unknown"),
        ({"available": True, "range": {"start": "x", "end": "y"}}, 730, "loaded_window_unknown"),
        (_weather(), 0, "invalid_days"),
        (_weather(), None, "invalid_days"),
    ],
)
def test_weather_refusals_are_explicit(weather, days, reason):
    answer = _fetcher(weather_history=weather)(
        "get_weather_history", {"field_id": FIELD, "days": days}
    )
    assert answer["available"] is False and answer["reason"] == reason
    assert answer["note_ar"] and "weather_history" not in answer


# ── get_operation_windows ───────────────────────────────────────────────────────────────


def test_operation_windows_absent_from_the_pack_is_said_not_answered_empty():
    answer = _fetcher()("get_operation_windows", {"field_id": FIELD})
    assert answer["available"] is False
    assert answer["reason"] == "operation_windows_not_in_context_pack"
    assert answer["note_ar"] and "operation_windows" not in answer


def test_operation_windows_supplied_by_the_owner_are_returned():
    block = {"spray": [{"start": "2026-11-23T05:00:00Z"}]}
    answer = _fetcher(operation_windows=block)("get_operation_windows", {"field_id": FIELD})
    assert answer == {"field_id": FIELD, "available": True, "operation_windows": block}


# ── get_truecolor_scene ─────────────────────────────────────────────────────────────────


def test_truecolor_scene_answers_the_requested_date_only():
    fetch = _fetcher()
    hit = fetch("get_truecolor_scene", {"field_id": FIELD, "date": "2026-06-01"})
    assert hit["available"] is True and hit["scene"] == {"date": "2026-06-01"}
    latest = fetch("get_truecolor_scene", {"field_id": FIELD})
    assert latest["scene"]["date"] == "2026-11-20" and latest["requested_date"] is None
    miss = fetch("get_truecolor_scene", {"field_id": FIELD, "date": "2026-06-02"})
    assert miss["available"] is False
    assert miss["reason"] == "no_truecolor_scene_on_requested_date"
    for answer in (hit, latest, miss):
        assert "imagery_timeline" not in answer and "ndvi" not in json.dumps(answer)


def test_a_refused_read_is_audited_as_unavailable_not_as_a_plain_success():
    result = EX.execute_read_tool(
        "get_weather_history",
        {"field_id": FIELD, "days": 30},
        None,
        _fetcher(),
        tenant_id="t1",
        actor="u1",
        timestamp="2026-11-22T00:00:00Z",
    )
    assert result["outcome"] == EX.OUTCOME_EXECUTED
    assert result["data"]["available"] is False
    assert result["audit"]["result_summary"] == "unavailable:requested_window_not_loaded"


def test_reads_stay_bound_to_the_loaded_field():
    for tool in ("get_index_timeline", "get_weather_history", "get_operation_windows"):
        with pytest.raises(ValueError, match="field_context_identity_mismatch"):
            _fetcher()(tool, {"field_id": "field-b", "index": "ndvi", "days": 30})
