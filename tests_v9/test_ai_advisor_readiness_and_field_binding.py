"""AI advisor: incomplete field context reaches the envelope; tools stay bound to the loaded field.

1. The platform's field AI context reports readiness as ``{"complete": bool, "warnings": [...]}``
   (services/sahool-platform/api/routers/field_ai_context.py). The advisory envelope only
   understood a string, so an incomplete pack never reached ``evidence_missing`` nor
   ``requires_human_review``.
2. The read-tool fetcher answers from the evidence loaded for one field, but labelled the
   answer with whatever ``field_id`` the model asked for, so field A's data could come back
   tagged as field B. A different field is now refused (the call fails, no data).

Merged with the owner's patch SAHOOL_AI_Advisor_P1_Cumulative_Fix_2026-11-13: missing or
malformed readiness is not accepted, a fetcher whose field state and context pack disagree
refuses everything, and an unbound fetcher cannot claim a requested field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist.advisory_contract import build_advisory_envelope  # noqa: E402

_GOOD = {
    "answer_ar": "الحقل ضمن المدى الطبيعيّ لمؤشّر NDVI مع رطوبة كافية.",
    "confidence": 0.82,
    "evidence_ids": ["ndvi:2026-06", "weather:nasa_power"],
    "pending_approvals": [],
    "generation_provider": "openrouter",
}


def test_structured_incomplete_readiness_requires_human_review():
    env = build_advisory_envelope(
        {
            **_GOOD,
            "ai_context_pack_readiness": {
                "complete": False,
                "warnings": ["weather_unavailable", "imagery_stale"],
            },
        }
    )
    assert env["evidence_missing"] == [
        "context_pack:incomplete",
        "context_pack:weather_unavailable",
        "context_pack:imagery_stale",
    ]
    assert env["requires_human_review"] is True


def test_incomplete_readiness_without_warnings_is_still_named():
    env = build_advisory_envelope({**_GOOD, "ai_context_pack_readiness": {"complete": False}})
    assert env["evidence_missing"] == ["context_pack:incomplete"]
    assert env["requires_human_review"] is True


def test_malformed_readiness_is_unverified_not_accepted():
    env = build_advisory_envelope({**_GOOD, "ai_context_pack_readiness": {"warnings": "x"}})
    assert env["evidence_missing"] == ["context_pack:unverified", "context_pack:warnings_invalid"]
    assert env["requires_human_review"] is True


@pytest.mark.parametrize("readiness", [{"complete": True, "warnings": []}, "ok", None])
def test_complete_readiness_adds_nothing(readiness):
    env = build_advisory_envelope({**_GOOD, "ai_context_pack_readiness": readiness})
    assert env["evidence_missing"] == []
    assert env["requires_human_review"] is False


def _main():
    pytest.importorskip("fastapi")  # main imports fastapi
    from services.ai_agronomist import main as MAIN

    return MAIN


def _fetcher():
    return _main()._build_agent_tool_fetcher(
        field_state={"field_id": "field-A", "water_deficit": 18.0},
        ai_pack={"field_id": "field-A", "weather_history": {"t": 1}, "readiness": "ok"},
        annotations={},
    )


@pytest.mark.parametrize(
    "tool",
    [
        "get_field_state",
        "get_weather_history",
        "get_index_timeline",
        "get_alerts",
        "generate_report",
    ],
)
def test_tool_for_another_field_is_refused(tool):
    with pytest.raises(ValueError, match="field_context_identity_mismatch"):
        _fetcher()(tool, {"field_id": "field-B", "days": 7, "index": "ndvi"})


def test_a_non_string_field_id_is_refused():
    with pytest.raises(ValueError, match="field_context_identity_mismatch"):
        _fetcher()("get_field_state", {"field_id": 123})


def test_disagreeing_field_state_and_context_pack_refuse_every_call():
    fetch = _main()._build_agent_tool_fetcher(
        field_state={"field_id": "field-A"}, ai_pack={"field_id": "field-B"}, annotations={}
    )
    with pytest.raises(ValueError, match="field_context_identity_mismatch"):
        fetch("get_field_state", {"field_id": "field-A"})


def test_an_unbound_fetcher_cannot_claim_a_requested_field():
    fetch = _main()._build_agent_tool_fetcher(field_state={}, ai_pack={}, annotations={})
    with pytest.raises(ValueError, match="field_context_identity_mismatch"):
        fetch("get_field_state", {"field_id": "field-B"})


def test_the_executor_records_a_refusal_as_failed_with_no_data():
    from services.ai_agronomist import tool_executor

    src = Path(tool_executor.__file__).read_text(encoding="utf-8")
    assert 'outcome, reason = OUTCOME_FAILED, "fetcher_error"' in src


def test_tool_for_the_loaded_field_or_unspecified_still_answers():
    fetch = _fetcher()
    same = fetch("get_weather_history", {"field_id": "field-A", "days": 7})
    assert same["field_id"] == "field-A" and same["weather_history"] == {"t": 1}
    unspecified = fetch("get_field_state", {})
    assert unspecified["field_id"] == "field-A"
    assert unspecified["canonical_field_state"]["water_deficit"] == 18.0
