"""AI advisor: incomplete field context reaches the envelope; tools stay bound to the loaded field.

1. The platform's field AI context reports readiness as ``{"complete": bool, "warnings": [...]}``
   (services/sahool-platform/api/routers/field_ai_context.py). The advisory envelope only
   understood a string, so an incomplete pack never reached ``evidence_missing`` nor
   ``requires_human_review``.
2. The read-tool fetcher answers from the evidence loaded for one field, but labelled the
   answer with whatever ``field_id`` the model asked for, so field A's data could come back
   tagged as field B. A different field is now refused with no data.
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
    assert "context_pack:weather_unavailable" in env["evidence_missing"]
    assert "context_pack:imagery_stale" in env["evidence_missing"]
    assert env["requires_human_review"] is True


def test_incomplete_readiness_without_warnings_is_still_named():
    env = build_advisory_envelope({**_GOOD, "ai_context_pack_readiness": {"complete": False}})
    assert env["evidence_missing"] == ["context_pack:incomplete"]
    assert env["requires_human_review"] is True


@pytest.mark.parametrize("readiness", [{"complete": True, "warnings": []}, "ok", None])
def test_complete_readiness_adds_nothing(readiness):
    env = build_advisory_envelope({**_GOOD, "ai_context_pack_readiness": readiness})
    assert env["evidence_missing"] == []
    assert env["requires_human_review"] is False


def _fetcher():
    pytest.importorskip("fastapi")  # main imports fastapi
    from services.ai_agronomist import main as MAIN

    return MAIN._build_agent_tool_fetcher(
        field_state={"field_id": "field-A", "water_deficit": 18.0},
        ai_pack={"field_id": "field-A", "weather_history": {"t": 1}, "readiness": "ok"},
        annotations={},
    )


@pytest.mark.parametrize(
    "tool", ["get_field_state", "get_weather_history", "get_index_timeline", "get_alerts"]
)
def test_tool_for_another_field_is_refused_without_data(tool):
    out = _fetcher()(tool, {"field_id": "field-B", "days": 7, "index": "ndvi"})
    assert out["error"] == "field_scope_mismatch"
    assert out["requested_field_id"] == "field-B" and out["bound_field_id"] == "field-A"
    assert out["data"] is None
    assert "canonical_field_state" not in out and "weather_history" not in out


def test_tool_for_the_loaded_field_or_unspecified_still_answers():
    fetch = _fetcher()
    same = fetch("get_weather_history", {"field_id": "field-A", "days": 7})
    assert same["field_id"] == "field-A" and same["weather_history"] == {"t": 1}
    unspecified = fetch("get_field_state", {})
    assert unspecified["field_id"] == "field-A"
    assert unspecified["canonical_field_state"]["water_deficit"] == 18.0
