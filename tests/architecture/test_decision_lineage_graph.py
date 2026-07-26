from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "decision-lineage/generated/decision_lineage_graph.json"
SUMMARY = ROOT / "decision-lineage/generated/decision_lineage_summary.json"


def _graph():
    return json.loads(GRAPH.read_text(encoding="utf-8"))


def test_lineage_makes_no_runtime_or_production_claim():
    graph = _graph()
    assert graph["runtime_verified"] is False
    assert graph["production_certified"] is False
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["runtime_verified"] is False
    assert summary["production_certified"] is False


def test_lineage_reports_complete_static_chain_consistently():
    graph = _graph()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    # complete_static_chain is derived from having no missing stages / unsupported relations.
    assert graph["complete_static_chain"] == summary["complete_static_chain"]
    if summary["complete_static_chain"]:
        assert summary["missing_stages"] == []
        assert summary["unsupported_relations"] == []
    else:
        assert summary["missing_stages"] or summary["unsupported_relations"]


def test_lineage_summary_counts_are_coherent():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["stages_with_evidence"] <= summary["stages"]
    assert summary["static_supported_relations"] <= summary["relations"]
