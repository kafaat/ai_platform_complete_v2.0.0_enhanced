import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "architecture_graph", ROOT / "scripts/ci/architecture_graph.py"
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def test_architecture_graph_is_deterministic_and_nonempty():
    first = MOD.build()
    second = MOD.build()
    assert first == second
    assert first["summary"]["nodes"] > 0
    assert first["summary"]["edges"] > 0


def test_edges_reference_existing_nodes_and_no_self_edges():
    graph = MOD.build()
    nodes = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in nodes
        assert edge["target"] in nodes
        assert edge["source"] != edge["target"]
        assert (ROOT / edge["evidence"]).exists()


def test_legal_erp_bridge_name_is_canonical():
    graph = MOD.build()
    nodes = {n["id"] for n in graph["nodes"]}
    assert "odoo-bridge" not in nodes
