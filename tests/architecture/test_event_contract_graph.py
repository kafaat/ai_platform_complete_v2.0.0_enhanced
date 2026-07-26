from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "event_contract_graph.py"
OUT = ROOT / "event-audit" / "generated" / "event_contract_graph.json"


def load_module():
    spec = importlib.util.spec_from_file_location("event_contract_graph", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_event_graph_matches_repository():
    module = load_module()
    generated = json.loads(OUT.read_text(encoding="utf-8"))
    assert generated == module.build()


def test_static_inventory_does_not_claim_runtime_truth():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert data["summary"]["runtime_verified"] is False
    assert data["summary"]["production_certified"] is False


def test_subjects_and_references_are_deterministically_sorted():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    subjects = [item["subject"] for item in data["subjects"]]
    assert subjects == sorted(subjects)
    for item in data["subjects"]:
        for key in ("producers", "consumers"):
            refs = item[key]
            assert refs == sorted(
                refs, key=lambda r: (r["subject"] or "~", r["kind"], r["file"], r["line"])
            )


def test_dynamic_subjects_are_not_reported_as_missing_contracts():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert all(row["subject"] is None for row in data["dynamic_contracts"])
    literal_subjects = {row["subject"] for row in data["subjects"]}
    assert None not in literal_subjects
