from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"


def _caps():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["capabilities"]


def test_no_service_or_test_pointer_is_missing():
    for cap in _caps():
        for field in ("services", "tests", "ui_consumers", "mobile_consumers"):
            for pointer in cap.get(field, []):
                assert (ROOT / pointer).exists(), f"{cap['id']} missing {field}: {pointer}"


def test_high_confidence_requires_service_api_and_test():
    for cap in _caps():
        if cap["confidence"] == "high":
            assert cap["services"], cap["id"]
            assert cap["apis"], cap["id"]
            assert cap["tests"], cap["id"]


def test_known_missing_precision_capabilities_are_not_inflated():
    by_id = {c["id"]: c for c in _caps()}
    for cid in ("PA-003", "PA-004"):
        assert by_id[cid]["maturity"] <= 2
        assert not by_id[cid]["production_certified"]


def test_decision_chain_is_explicit():
    by_id = {c["id"]: c for c in _caps()}
    expected = {
        "DEC-002": "DEC-001",
        "DEC-003": "DEC-002",
        "DEC-004": "DEC-003",
        "DEC-005": "DEC-004",
        "DEC-006": "DEC-005",
        "DEC-007": "DEC-006",
        "DEC-008": "DEC-007",
        "DEC-009": "DEC-008",
        "DEC-010": "DEC-009",
    }
    for cid, dep in expected.items():
        assert dep in by_id[cid]["dependencies"]
