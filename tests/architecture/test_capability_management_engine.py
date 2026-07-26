import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    s = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_management_outputs_are_complete_and_fail_closed():
    m = load("cm", "scripts/ci/capability_management_engine.py")
    objs = [m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)]
    assert m.validate(*objs) == []
    matrix, graph, dashboard = m.generate_payload(*objs)
    # Honest tri-state accounting — never inflate mapped to total. Every capability
    # is exactly one of mapped / adjudicated / unmapped; accounted_for = the first two.
    assert len(matrix) == 81 and dashboard["capabilities_total"] == 81
    assert dashboard["mapped"] + dashboard["adjudicated"] + dashboard["unmapped"] == 81
    assert dashboard["accounted_for"] == dashboard["mapped"] + dashboard["adjudicated"]
    # Current honest state: 81/81 mapped. INT-004 now has a real live consumer
    # (api/machinery_export.py + the format=isoxml export endpoint + behavioral
    # tests), so it is legitimately evidence-mapped — closed by implementation,
    # not by inflating the number. No capability is an unmapped gap.
    assert dashboard["mapped"] == 81 and dashboard["unmapped"] == 0
    assert dashboard["unmapped_capabilities"] == []
    assert dashboard["runtime_verified"] == 0 and dashboard["production_certified"] == 0
    assert len(graph["nodes"]) == 81
    assert all(
        {"id", "maturity", "evidence_level", "parity", "investment"} <= set(r) for r in matrix
    )


def test_registry_declared_existing_evidence_is_credited():
    # The capabilities the content-scanner under-credited but which declare real,
    # on-disk evidence must be credited on their SPECIFIC dimensions (union of
    # scanned ∪ registry-declared-and-existing), not merely flagged mapped.
    m = load("cm3", "scripts/ci/capability_management_engine.py")
    objs = [m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)]
    matrix, _, _ = m.generate_payload(*objs)
    by_id = {r["id"]: r for r in matrix}
    # cap -> dimensions that MUST be credited from its registry-declared, on-disk evidence.
    expected = {
        "IRR-010": ("backend", "routes"),
        "OPS-001": ("backend", "routes", "tests", "mobile"),
        "OPS-006": ("backend", "routes", "tests", "mobile"),
        "OPS-008": ("backend", "tests"),
        "PA-003": ("backend", "routes", "database", "tests"),
    }
    for cid, dims in expected.items():
        row = by_id[cid]
        assert row["mapped"] is True, cid
        assert row["coverage_dimension_count"] >= len(dims), cid
        for dim in dims:
            assert row["coverage_dimensions"][dim] is True, f"{cid}:{dim}"


def test_scaffold_with_no_specific_evidence_is_not_promoted():
    # Invariant (kept synthetic now that INT-004 is genuinely implemented): a
    # capability that declares NO specific-dimension evidence — and whose only
    # scanner hit is the catch-all other_evidence bucket (a bare capability-ID
    # mention) — must NOT be promoted to mapped. Registry presence or a title
    # alone never counts as implementation.
    m = load("cm4", "scripts/ci/capability_management_engine.py")
    reg = {
        "capabilities": [
            {
                "id": "ZZ-999",
                "title": {"en": "Pure scaffold"},
                "domain": "precision",
                "owner": "UNASSIGNED",
                "maturity": 1,
                "evidence_level": 1,
                "dependencies": [],
                "services": [],
                "apis": [],
                "tests": [],
                "ui_consumers": [],
                "mobile_consumers": [],
            }
        ]
    }
    mapping = {
        "capabilities": [{"capability_id": "ZZ-999", "other_evidence": [{"value": "ZZ-999"}]}]
    }
    empty = {"capabilities": []}
    matrix, _, dashboard = m.generate_payload(reg, mapping, empty, empty, empty)
    row = {r["id"]: r for r in matrix}["ZZ-999"]
    assert row["coverage_dimension_count"] == 0
    assert row["mapped"] is False
    assert dashboard["unmapped_capabilities"] == ["ZZ-999"]


def test_declared_evidence_paths_are_reconciled_fail_closed():
    # A registry-declared evidence pointer that does not resolve on disk is a HARD
    # error, never a silently dropped credit — the mapper must not invent or lose
    # evidence. Inject a phantom path and assert validate() rejects it.
    m = load("cm5", "scripts/ci/capability_management_engine.py")
    reg, mapping, evidence, parity, investment = (
        m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)
    )
    assert m.validate(reg, mapping, evidence, parity, investment) == []
    caps = reg["capabilities"] if isinstance(reg, dict) else reg
    caps[0].setdefault("services", []).append("services/sahool-platform/does_not_exist_phantom.py")
    errs = m.validate(reg, mapping, evidence, parity, investment)
    assert any("missing on disk" in e for e in errs), errs


def test_management_generated_json_has_no_drift():
    m = load("cm2", "scripts/ci/capability_management_engine.py")
    objs = [m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)]
    matrix, graph, dashboard = m.generate_payload(*objs)
    assert json.loads((m.OUT / "capability_management_matrix.json").read_text()) == {
        "schema_version": "1.0.0",
        "capabilities": matrix,
    }
    assert json.loads((m.OUT / "capability_knowledge_graph.json").read_text()) == graph
    assert json.loads((m.OUT / "coverage_dashboard.json").read_text()) == dashboard
