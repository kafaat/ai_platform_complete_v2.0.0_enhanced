"""Re-posting an ``edge_id`` with different endpoints is refused, not silently half-applied.

``upsert_edge`` used ``ON CONFLICT(edge_id) DO UPDATE SET relation, properties_json``: a
re-post that moved the edge to other nodes kept the old ``subject_id``/``object_id`` while
the API answered ``{"ok": true}``. The store now raises ``EdgeConflictError`` and
``POST /v1/edges`` maps it to 409; a re-post with the same endpoints still updates.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "knowledge-graph"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kg = _load("_kg_store_conflict_subject", SERVICE / "kg_store.py")


@pytest.fixture
def store(tmp_path):
    s = kg.SQLiteAgGraphStore(tmp_path / "kg.sqlite")
    for node_id in ("wheat", "barley", "stripe_rust", "leaf_rust"):
        s.upsert_node(kg.GraphNode(node_id, "Thing", node_id))
    s.upsert_edge(
        kg.GraphEdge("e1", "wheat", "historically_susceptible_to", "stripe_rust", properties={})
    )
    return s


def _edge(store, edge_id="e1"):
    (row,) = [r for r in store.query_edges() if r["edge_id"] == edge_id]
    return row


@pytest.mark.parametrize(
    ("subject_id", "object_id"),
    [("barley", "stripe_rust"), ("wheat", "leaf_rust"), ("barley", "leaf_rust")],
)
def test_reposting_an_edge_id_with_other_endpoints_is_refused(store, subject_id, object_id):
    with pytest.raises(kg.EdgeConflictError):
        store.upsert_edge(
            kg.GraphEdge("e1", subject_id, "historically_limits", object_id, properties={"x": 1})
        )
    row = _edge(store)
    assert (row["subject_id"], row["relation"], row["object_id"]) == (
        "wheat",
        "historically_susceptible_to",
        "stripe_rust",
    ), "a refused write must leave the stored edge untouched"
    assert store.count_edges() == 1


def test_reposting_the_same_endpoints_still_updates(store):
    store.upsert_edge(
        kg.GraphEdge("e1", "wheat", "historically_limits", "stripe_rust", properties={"v": 2})
    )
    row = _edge(store)
    assert row["relation"] == "historically_limits"
    assert row["properties_json"] == '{"v": 2}'
    assert store.count_edges() == 1


def test_a_new_edge_id_can_link_other_endpoints(store):
    store.upsert_edge(kg.GraphEdge("e2", "barley", "historically_limits", "leaf_rust"))
    assert store.count_edges() == 2


def test_the_api_answers_409_for_a_conflicting_repost(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    for path in (str(SERVICE), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.setenv("KG_SQLITE_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "t" * 32)
    monkeypatch.delitem(sys.modules, "kg_store", raising=False)
    try:
        main = _load("_kg_main_conflict_subject", SERVICE / "main.py")
    except ImportError:
        pytest.skip("knowledge-graph dependencies unavailable")
    client = TestClient(main.app)
    headers = {"X-Agent-Token": "t" * 32}
    for node_id in ("wheat", "barley", "stripe_rust"):
        r = client.post(
            "/v1/nodes", json={"node_id": node_id, "label": "T", "name": node_id}, headers=headers
        )
        assert r.status_code == 200, r.text
    edge = {
        "edge_id": "api-e1",
        "subject_id": "wheat",
        "relation": "historically_susceptible_to",
        "object_id": "stripe_rust",
    }
    assert client.post("/v1/edges", json=edge, headers=headers).status_code == 200
    moved = client.post("/v1/edges", json={**edge, "subject_id": "barley"}, headers=headers)
    assert moved.status_code == 409, moved.text
