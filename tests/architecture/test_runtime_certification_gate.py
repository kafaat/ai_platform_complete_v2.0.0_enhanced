from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_certification_gate_is_fail_closed():
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_certification_summary.json").read_text()
    )
    assert data["fail_closed"] is True
    assert data["gate_passed"] is True
    assert data["production_certified_services"] == []


def test_no_capability_or_service_claim_violations():
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_certification_summary.json").read_text()
    )
    assert data["service_claim_violations"] == []
    assert data["capability_claim_violations"] == []
