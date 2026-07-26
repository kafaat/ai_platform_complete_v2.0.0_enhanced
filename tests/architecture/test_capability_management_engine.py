import importlib.util, json
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
    # Current honest state: 80 mapped + 1 genuine gap (INT-004 declares no evidence).
    assert dashboard["mapped"] == 80 and dashboard["unmapped"] == 1
    assert dashboard["unmapped_capabilities"] == ["INT-004"]
    assert dashboard["runtime_verified"] == 0 and dashboard["production_certified"] == 0
    assert len(graph["nodes"]) == 81
    assert all(
        {"id", "maturity", "evidence_level", "parity", "investment"} <= set(r) for r in matrix
    )


def test_registry_declared_existing_evidence_is_credited():
    # The four capabilities the content-scanner missed but which declare real,
    # on-disk services/APIs/tests must be credited (union of scanned ∪ declared).
    m = load("cm3", "scripts/ci/capability_management_engine.py")
    objs = [m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)]
    matrix, _, _ = m.generate_payload(*objs)
    by_id = {r["id"]: r for r in matrix}
    for cid in ("IRR-010", "OPS-001", "OPS-006", "OPS-008", "PA-003"):
        row = by_id[cid]
        assert row["mapped"] is True, cid
        assert row["coverage_dimension_count"] > 0, cid
    assert by_id["PA-003"]["coverage_dimensions"]["backend"] is True
    assert by_id["PA-003"]["coverage_dimensions"]["routes"] is True
    assert by_id["PA-003"]["coverage_dimensions"]["tests"] is True


def test_real_scaffold_is_not_promoted_by_registry_presence_alone():
    # INT-004 is a genuine gap: title/registry entry exists, but it declares no
    # service, API, test, or executable evidence. Presence in the registry must NOT
    # promote it to mapped.
    m = load("cm4", "scripts/ci/capability_management_engine.py")
    objs = [m.load_json(p) for p in (m.REG, m.MAPPING, m.EVIDENCE, m.PARITY, m.INVEST)]
    matrix, _, _ = m.generate_payload(*objs)
    int004 = {r["id"]: r for r in matrix}["INT-004"]
    assert int004["coverage_dimension_count"] == 0
    assert int004["mapped"] is False


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
