"""Regression guard: the WX-10.6 crop→decision-candidate endpoint UI-coverage waiver
is a **permanent, documented machine-boundary** waiver (owner decision 2026-07-25).

`POST /api/v1/crop-twin/decision-candidate` is a machine-consumed producer
(crop-intelligence → decision-service); no human UI hits it by design — the human
review surface is ApprovalsConsole, which reads the resulting candidate downstream.
So the waiver must NOT be temporary (it isn't closeable by building UI) and must NOT
carry an expiry (an expiry-bearing waiver fails the waiver-expiry guard once past).
This test pins that permanence so it isn't silently reverted to a temporary/expiring
waiver.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WAIVERS = ROOT / "config" / "endpoint_ui_coverage_waivers.json"
ENDPOINT = "/api/v1/crop-twin/decision-candidate"


def _waiver() -> dict:
    data = json.loads(WAIVERS.read_text(encoding="utf-8"))
    entries = data["waivers"] if isinstance(data, dict) else data
    match = [w for w in entries if isinstance(w, dict) and w.get("endpoint") == ENDPOINT]
    assert len(match) == 1, f"expected exactly one waiver for {ENDPOINT}, found {len(match)}"
    return match[0]


def test_decision_candidate_waiver_is_permanent_machine_boundary() -> None:
    w = _waiver()
    # Permanent (owner decision): not temporary, and no expiry (an expiry would make
    # the waiver-expiry guard fail once past, contradicting the permanent intent).
    assert w.get("temporary") is False, "WX-10.6 waiver must be permanent (temporary: false)"
    assert not w.get("expiry"), "a permanent waiver must not carry an expiry date"
    # It is permanent *because* it is a machine boundary with no human UI by design.
    assert w.get("intended_consumer") == "machine"
    assert w.get("ui_surface_hint") == "no-ui-required"
