import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_c5_met_is_descriptive_and_stability_only():
    m = _load("trial_engine_c5", "services/sahool-platform/api/trial_engine.py")
    obs = [
        m.METObservation(g, e, y)
        for g, e, y in [("A", "E1", 10), ("A", "E2", 12), ("B", "E1", 11), ("B", "E2", 10)]
    ]
    met = m.analyze_met(obs)
    out = met.to_dict()
    assert out["decision_eligible"] is False
    assert out["automatic_model_promotion_eligible"] is False
    envelope = m.build_digital_trial_envelope(
        season_id="season-1", study_id="study-1", trial_id="trial-1", met=met
    )
    assert envelope["lifecycle_authority"] == "caller_provided_season_reference"
    assert envelope["season_binding_verified"] is False
    assert envelope["parallel_trial_season_created"] is False


def test_c5_met_requires_complete_matrix():
    m = _load("trial_engine_c5b", "services/sahool-platform/api/trial_engine.py")
    with pytest.raises(ValueError):
        m.analyze_met(
            [
                m.METObservation("A", "E1", 1),
                m.METObservation("B", "E1", 2),
                m.METObservation("A", "E2", 3),
            ]
        )


def test_c6_mutating_tool_returns_candidate_without_direct_action():
    m = _load("tool_executor_c6", "services/ai_agronomist/tool_executor.py")
    r = m.execute_read_tool(
        "schedule_irrigation",
        {"field_id": "f"},
        ["can_send_recommendations"],
        lambda *_: (_ for _ in ()).throw(AssertionError("must not execute")),
        tenant_id="t",
        actor="a",
        timestamp="z",
    )
    assert r["outcome"] == "pending_approval"
    assert r["candidate"]["direct_action_permitted"] is False
    assert r["candidate"]["required_chain"][-2:] == ["evidence", "outcome"]
    assert r["candidate"]["tenant_id"] == "t"
    assert r["candidate"]["actor"] == "a"
    assert r["candidate"]["requested_at"] == "z"
    assert r["candidate"]["input_hash"] == m.input_hash({"field_id": "f"})


def test_c6_read_tool_still_executes():
    m = _load("tool_executor_c6b", "services/ai_agronomist/tool_executor.py")
    r = m.execute_read_tool(
        "get_field_state",
        {},
        None,
        lambda *_: {"ok": True},
        tenant_id="t",
        actor="a",
        timestamp="z",
    )
    assert r["outcome"] == "executed" and r["candidate"] is None
