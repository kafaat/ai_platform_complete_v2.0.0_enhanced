"""``GET /v1/edges`` is bounded and deterministically ordered (exploration bug, agent-10).

``query_edges`` (services/knowledge-graph/kg_store.py) had no ``ORDER BY`` and no ``LIMIT``,
and ``GET /v1/edges`` with no filter enumerated the whole graph. ai_agronomist calls it with
no parameters when a question names no crop. Now:

* every read is ordered by (subject_id, relation, object_id, edge_id);
* ``limit`` has a hard maximum (``EDGE_QUERY_MAX_LIMIT``); above it the API refuses with 422;
* a read with no filter is capped at ``EDGE_QUERY_UNFILTERED_MAX`` rows and reports
  ``filtered: false`` and ``truncated``, so callers keep working but cannot dump the graph.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "knowledge-graph"
TOKEN = "k" * 32
READ = {"X-Tenant-Id": "tenant-a"}
N_EDGES = 160  # above the unfiltered cap (100), below the hard maximum (500)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kg = _load("_kg_store_bounded_read_subject", SERVICE / "kg_store.py")


def _fill(store) -> list[str]:
    """N_EDGES edges from ``wheat``, written in shuffled order so insertion order is not sorted."""
    relations = kg.SEED_REFERENCE_RELATIONS
    store.upsert_node(kg.GraphNode("wheat", "Crop", "Wheat"))
    ids = []
    for i in range(N_EDGES):
        store.upsert_node(kg.GraphNode(f"obj_{i:03d}", "Thing", f"Object {i}"))
        ids.append(i)
    random.Random(7).shuffle(ids)
    for i in ids:
        store.upsert_edge(
            kg.GraphEdge(f"e_{i:03d}", "wheat", relations[i % len(relations)], f"obj_{i:03d}")
        )
    return [f"e_{i:03d}" for i in ids]


def _sort_key(row: dict) -> tuple:
    return (row["subject_id"], row["relation"], row["object_id"], row["edge_id"])


@pytest.fixture
def store(tmp_path):
    s = kg.SQLiteAgGraphStore(tmp_path / "kg.sqlite")
    _fill(s)
    return s


@pytest.fixture
def client(tmp_path, monkeypatch):
    for path in (str(SERVICE), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.setenv("KG_SQLITE_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.delitem(sys.modules, "kg_store", raising=False)
    main = _load("_kg_main_bounded_read_subject", SERVICE / "main.py")
    _fill(main.store)
    return TestClient(main.app, raise_server_exceptions=False)


def test_store_reads_are_ordered_whatever_the_insertion_order(store):
    rows = store.query_edges(subject_id="wheat")
    assert len(rows) == N_EDGES, (
        f"a filtered read under the hard max returns every match: {len(rows)}"
    )
    assert rows == sorted(rows, key=_sort_key), (
        "edges must come back in (subject, relation, object, id) order"
    )


def test_store_unfiltered_read_is_capped_and_flags_truncation(store):
    page = store.query_edges_page()
    assert page["filtered"] is False, f"no filter given: {page['filtered']}"
    assert page["limit"] == kg.EDGE_QUERY_UNFILTERED_MAX, (
        f"unfiltered cap not applied: {page['limit']}"
    )
    assert len(page["edges"]) == kg.EDGE_QUERY_UNFILTERED_MAX, f"got {len(page['edges'])} rows"
    assert page["truncated"] is True, "more edges exist than the capped page returned"
    assert page["edges"] == sorted(page["edges"], key=_sort_key), "the capped page must be ordered"


def test_store_limit_is_clamped_to_the_hard_maximum_and_validated(store):
    page = store.query_edges_page(subject_id="wheat", limit=10_000)
    assert page["limit"] == kg.EDGE_QUERY_MAX_LIMIT, (
        f"limit must clamp to the hard max: {page['limit']}"
    )
    small = store.query_edges_page(subject_id="wheat", limit=5)
    assert len(small["edges"]) == 5 and small["truncated"] is True, f"limit=5 page: {small}"
    assert small["edges"] == store.query_edges(subject_id="wheat")[:5], (
        "pages must be stable prefixes"
    )
    for bad in (0, -1, True, "5"):
        with pytest.raises(ValueError):
            store.query_edges_page(subject_id="wheat", limit=bad)


def test_graphql_facade_is_bounded_too(store):
    out = kg.graphql_readonly(store, "{ edges { edge_id } }")
    assert len(out["edges"]) == kg.EDGE_QUERY_UNFILTERED_MAX, (
        f"graphql unfiltered not capped: {len(out['edges'])}"
    )
    assert out["truncated"] is True, "graphql must report truncation"


def test_api_unfiltered_read_is_capped_but_still_answers(client):
    # The ai_agronomist caller sends no parameters when the question names no crop.
    r = client.get("/v1/edges", headers=READ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["edges"]) <= kg.EDGE_QUERY_UNFILTERED_MAX, (
        f"unfiltered read returned {len(body['edges'])}"
    )
    assert body["filtered"] is False and body["truncated"] is True, f"flags missing: {body.keys()}"
    assert body["edges"] == sorted(body["edges"], key=_sort_key), "API rows must be ordered"


def test_api_filtered_read_honours_limit(client):
    r = client.get("/v1/edges", params={"subject_id": "wheat", "limit": 7}, headers=READ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["edges"]) == 7 and body["truncated"] is True, f"limit=7 page: {body}"
    full = client.get("/v1/edges", params={"subject_id": "wheat"}, headers=READ).json()
    assert full["truncated"] is False, "a subject filter under the hard max returns everything"
    assert body["edges"] == full["edges"][:7], "a limited page is a prefix of the ordered result"


@pytest.mark.parametrize("limit", [0, kg.EDGE_QUERY_MAX_LIMIT + 1])
def test_api_refuses_a_limit_outside_the_bounds(client, limit):
    r = client.get("/v1/edges", params={"subject_id": "wheat", "limit": limit}, headers=READ)
    assert r.status_code == 422, f"limit={limit} must be refused, got {r.status_code}: {r.text}"
