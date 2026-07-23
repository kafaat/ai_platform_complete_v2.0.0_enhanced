#!/usr/bin/env python3
"""Fail closed when the S0-S12 baseline overstates completion or loses evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
contract = json.loads(
    (ROOT / "docs/architecture/s0_s12_execution_baseline.json").read_text(encoding="utf-8")
)
milestones = contract["milestones"]
expected = {f"S{i}" for i in range(13)}
assert set(milestones) == expected, "baseline must enumerate S0 through S12 exactly"

allowed = set(contract["status_vocabulary"])
live_only = {"S1", "S4", "S6", "S7", "S9", "S12"}
for milestone, item in milestones.items():
    assert item["status"] in allowed, f"{milestone}: unknown status"
    assert item["evidence"], f"{milestone}: evidence is required"
    for relative in item["evidence"]:
        assert (ROOT / relative).exists(), f"{milestone}: missing evidence {relative}"
    if milestone in live_only:
        assert item["status"] == "live_certification_required", (
            f"{milestone}: cannot be declared ready by static code"
        )

print("S0-S12 execution baseline gate: PASS")
