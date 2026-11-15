"""The knowledge graph is a global reference store only (#1472, ADR-0038).

Owner decision of 14 November 2026: ``services/knowledge-graph`` holds public,
non-tenant agricultural reference knowledge. Its tables have no tenant column and
every authenticated caller reads the same rows, so:

1. every write path refuses a node or edge that carries a tenant, farm, field or
   user identifier (top level, ``properties`` or nested metadata) or is marked
   private, with ``422`` and the stable code ``kg_tenant_scoped_data_forbidden``;
   a pure reference write still succeeds;
2. REST and GraphQL reads return identical results for two different tenants. That
   is the declared behaviour of a global store, not an isolation failure;
3. ``X-Tenant-Id`` is still required for authentication (missing or blank is
   refused with ``403 missing_tenant``) and is not used as a row filter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "knowledge-graph"
TOKEN = "k" * 32
WRITE_HEADERS = {"X-Agent-Token": TOKEN}
CODE = "kg_tenant_scoped_data_forbidden"

# Every forbidden identifier named in the decision, plus spelling variants the
# normaliser must catch.
FORBIDDEN_KEYS = [
    "tenant_id",
    "field_id",
    "farm_id",
    "user_id",
    "owner",
    "owner_id",
    "tenantId",
    "Field-ID",
    "FARM_ID",
]
PRIVATE_MARKS = [
    {"private": True},
    {"is_private": True},
    {"visibility": "private"},
    {"scope": "tenant"},
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kg = _load("_kg_store_global_reference_subject", SERVICE / "kg_store.py")


@pytest.fixture
def store(tmp_path):
    s = kg.SQLiteAgGraphStore(tmp_path / "kg.sqlite")
    for node_id in ("wheat", "stripe_rust"):
        s.upsert_node(kg.GraphNode(node_id, "Thing", node_id))
    return s


@pytest.fixture
def api(tmp_path, monkeypatch):
    for path in (str(SERVICE), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.setenv("KG_SQLITE_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.delitem(sys.modules, "kg_store", raising=False)
    main = _load("_kg_main_global_reference_subject", SERVICE / "main.py")
    return main, TestClient(main.app, raise_server_exceptions=False)


def _assert_refused(response, key_fragment: str) -> None:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == CODE
    assert key_fragment in detail["path"]


# ── 1. the store's write boundary ────────────────────────────────────────────────


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
@pytest.mark.parametrize("nest", ["flat", "metadata"])
def test_store_refuses_a_node_carrying_a_scope_key(store, key, nest):
    props = {key: "x-1"} if nest == "flat" else {"metadata": {"source": "fao", key: "x-1"}}
    with pytest.raises(kg.TenantScopedDataError) as exc:
        store.upsert_node(kg.GraphNode("barley", "Crop", "Barley", props))
    assert exc.value.code == CODE
    assert [r for r in store.query_edges()] == []
    assert "barley" not in {n for n in _node_ids(store)}


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
def test_store_refuses_an_edge_carrying_a_scope_key(store, key):
    with pytest.raises(kg.TenantScopedDataError):
        store.upsert_edge(
            kg.GraphEdge(
                "e1",
                "wheat",
                "historically_susceptible_to",
                "stripe_rust",
                properties={"evidence": [{"doc": "ref", key: None}]},
            )
        )
    assert store.count_edges() == 0


@pytest.mark.parametrize("mark", PRIVATE_MARKS)
def test_store_refuses_a_record_marked_private(store, mark):
    with pytest.raises(kg.TenantScopedDataError):
        store.upsert_node(kg.GraphNode("barley", "Crop", "Barley", dict(mark)))
    with pytest.raises(kg.TenantScopedDataError):
        store.upsert_edge(
            kg.GraphEdge(
                "e1", "wheat", "historically_susceptible_to", "stripe_rust", properties=dict(mark)
            )
        )
    assert store.count_edges() == 0


def test_store_accepts_a_pure_reference_write(store):
    store.upsert_node(
        kg.GraphNode(
            "barley",
            "Crop",
            "Barley",
            {"source": "FAO", "private": False, "visibility": "global", "fields_of_use": ["feed"]},
        )
    )
    store.upsert_edge(
        kg.GraphEdge(
            "e1",
            "barley",
            "historically_susceptible_to",
            "stripe_rust",
            properties={"human_review_required": True},
        )
    )
    assert store.count_edges() == 1


def test_seed_reference_ontology_passes_the_guard(tmp_path):
    s = kg.SQLiteAgGraphStore(tmp_path / "seed.sqlite")
    assert kg.seed_reference_ontology(s) == 4


def _node_ids(store):
    with store._connect() as conn:
        return [row[0] for row in conn.execute("SELECT node_id FROM kg_nodes")]


# ── 1b. the REST write paths ─────────────────────────────────────────────────────


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
@pytest.mark.parametrize("where", ["top", "properties", "metadata"])
def test_rest_node_write_with_a_scope_key_is_refused(api, key, where):
    _main, client = api
    body = {"node_id": "barley", "label": "Crop", "name": "Barley"}
    if where == "top":
        body[key] = "t-1"
    elif where == "properties":
        body["properties"] = {key: "t-1"}
    else:
        body["metadata"] = {"ingest": {key: "t-1"}}
    _assert_refused(client.post("/v1/nodes", json=body, headers=WRITE_HEADERS), key)


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
@pytest.mark.parametrize("where", ["top", "properties"])
def test_rest_edge_write_with_a_scope_key_is_refused(api, key, where):
    main, client = api
    before = main.store.count_edges()
    body = {
        "edge_id": "e-new",
        "subject_id": "wheat",
        "relation": "historically_susceptible_to",
        "object_id": "stripe_rust",
    }
    if where == "top":
        body[key] = "f-1"
    else:
        body["properties"] = {"metadata": {key: "f-1"}}
    _assert_refused(client.post("/v1/edges", json=body, headers=WRITE_HEADERS), key)
    assert main.store.count_edges() == before


@pytest.mark.parametrize("mark", PRIVATE_MARKS)
def test_rest_write_marked_private_is_refused(api, mark):
    _main, client = api
    body = {"node_id": "barley", "label": "Crop", "name": "Barley", **mark}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 422 and r.json()["detail"]["code"] == CODE


def test_rest_pure_reference_write_still_succeeds(api):
    main, client = api
    before = main.store.count_edges()
    r = client.post(
        "/v1/nodes",
        json={"node_id": "barley", "label": "Crop", "name": "Barley", "properties": {"src": "FAO"}},
        headers=WRITE_HEADERS,
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/edges",
        json={
            "edge_id": "e-barley",
            "subject_id": "barley",
            "relation": "historically_susceptible_to",
            "object_id": "stripe_rust",
            "properties": {"human_review_required": True},
        },
        headers=WRITE_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert main.store.count_edges() == before + 1


def test_graphql_mutation_with_tenant_data_is_refused(api):
    main, client = api
    before = main.store.count_edges()
    r = client.post(
        "/graphql",
        json={"query": 'mutation { upsertNode(node_id:"x", tenant_id:"t-1") { ok } }'},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert r.status_code == 400
    assert main.store.count_edges() == before


# ── 2. reads are global ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "params", [{}, {"subject_id": "wheat"}, {"relation": "historically_favored_by"}]
)
def test_rest_reads_are_identical_for_two_tenants(api, params):
    _main, client = api
    a = client.get("/v1/edges", params=params, headers={"X-Tenant-Id": "tenant-a"})
    b = client.get("/v1/edges", params=params, headers={"X-Tenant-Id": "tenant-b"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert a.json()["edges"], "the seeded reference ontology is visible to every tenant"


@pytest.mark.parametrize(
    "query", ["{ edges { edge_id } }", '{ edges(subject:"wheat") { edge_id } }']
)
def test_graphql_reads_are_identical_for_two_tenants(api, query):
    _main, client = api
    a = client.post("/graphql", json={"query": query}, headers={"X-Tenant-Id": "tenant-a"})
    b = client.post("/graphql", json={"query": query}, headers={"X-Tenant-Id": "tenant-b"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert a.json()["edges"]


def test_tenant_header_is_not_a_row_filter(api):
    """A write made without any tenant is read back by every tenant alike."""
    _main, client = api
    client.post(
        "/v1/nodes", json={"node_id": "barley", "label": "Crop", "name": "B"}, headers=WRITE_HEADERS
    )
    client.post(
        "/v1/edges",
        json={
            "edge_id": "e-b",
            "subject_id": "barley",
            "relation": "historically_limits",
            "object_id": "stripe_rust",
        },
        headers=WRITE_HEADERS,
    )
    for tenant in ("tenant-a", "tenant-b", "some-other-tenant"):
        r = client.get(
            "/v1/edges", params={"subject_id": "barley"}, headers={"X-Tenant-Id": tenant}
        )
        assert [e["edge_id"] for e in r.json()["edges"]] == ["e-b"]


# ── 3. the header still authenticates ────────────────────────────────────────────


@pytest.mark.parametrize("headers", [{}, {"X-Tenant-Id": ""}, {"X-Tenant-Id": "   "}])
def test_reads_without_a_valid_tenant_identity_are_still_refused(api, headers):
    _main, client = api
    r = client.get("/v1/edges", headers=headers)
    assert r.status_code == 403 and r.json()["detail"] == "missing_tenant"
    r = client.post("/graphql", json={"query": "{ edges { edge_id } }"}, headers=headers)
    assert r.status_code == 403 and r.json()["detail"] == "missing_tenant"


def test_writes_still_require_the_service_token(api):
    _main, client = api
    r = client.post("/v1/nodes", json={"node_id": "barley", "label": "Crop", "name": "B"})
    assert r.status_code == 403 and r.json()["detail"] == "service_token_required"
