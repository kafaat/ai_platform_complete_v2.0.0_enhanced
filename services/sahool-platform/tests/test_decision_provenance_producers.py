"""Platform-side decision provenance and replay integrity (pure, no database).

- ``_replayed_decision_matches``: a write on an existing decision_id is a replay only when it is
  the same record; any difference is a 409 conflict instead of a silently dropped success.
- the irrigation confidence heuristic is named and versioned, and the typed provenance the
  recommendation producer sends to decision-service carries the rule version and method.
"""

import json

import api.main  # noqa: F401 — initialise api.main before importing routers
import pytest
from api.irrigation_recommendation_policy import (
    IRRIGATION_CONFIDENCE_METHOD,
    IRRIGATION_RULE_VERSION,
    irrigation_candidate_confidence,
    irrigation_decision_provenance,
)
from api.routers.decision_record import _replayed_decision_matches

pytestmark = pytest.mark.unit

_ROW = {
    "field_id": "fld_1",
    "decision_type": "irrigation_plan",
    "stage": "decision",
    "decision_value": json.dumps({"mm": 12.5, "plan": {"days": [1, 2]}}),
}
_WRITE = dict(
    decision_value={"mm": 12.5, "plan": {"days": [1, 2]}},
    field_id="fld_1",
    decision_type="irrigation_plan",
    stage="decision",
)


def test_the_same_record_is_a_replay():
    assert _replayed_decision_matches(_ROW, **_WRITE)
    assert _replayed_decision_matches(
        {**_ROW, "decision_value": json.loads(_ROW["decision_value"])}, **_WRITE
    )


@pytest.mark.parametrize(
    "change",
    [
        {"decision_value": {"mm": 30.0, "plan": {"days": [1, 2]}}},
        {"field_id": "fld_2"},
        {"decision_type": "crop_twin"},
        {"stage": "outcome"},
    ],
)
def test_a_different_record_under_the_same_id_is_not_a_replay(change):
    assert not _replayed_decision_matches(_ROW, **{**_WRITE, **change})


def test_an_id_invisible_to_this_tenant_is_not_a_replay():
    assert not _replayed_decision_matches(None, **_WRITE)


@pytest.mark.parametrize(
    "dep_conf, limitations, penalty, expected",
    [
        (None, [], 0.0, 0.5),
        (0.9, ["a"], 0.0, 0.75),
        (0.8, ["a", "b"], 0.1, 0.4),
        (0.2, ["a", "b"], 0.0, 0.0),
    ],
)
def test_confidence_heuristic_is_the_declared_formula(dep_conf, limitations, penalty, expected):
    assert irrigation_candidate_confidence(dep_conf, limitations, penalty) == expected


def test_irrigation_provenance_is_typed_and_versioned():
    rec = {
        "policy": "net_only",
        "policy_knobs": {"policy": "water_saving"},
        "rationale_ar": "الاستنزاف بلغ عتبة الإطلاق",
        "trigger_reason": "depletion_at_trigger",
    }
    provenance = irrigation_decision_provenance(rec, evidence_refs=["et0:s1", 7])
    assert set(provenance) == {
        "producer_id",
        "model_or_rule_version",
        "policy_version",
        "explanation",
        "confidence_method",
        "evidence_refs",
    }
    assert provenance["model_or_rule_version"] == IRRIGATION_RULE_VERSION
    assert provenance["confidence_method"] == IRRIGATION_CONFIDENCE_METHOD
    assert "uncalibrated" in IRRIGATION_CONFIDENCE_METHOD
    assert provenance["policy_version"] == "irrigation-policy:water_saving/salinity:net_only"
    assert provenance["evidence_refs"] == ["et0:s1", "7"]
