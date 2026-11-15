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
import json
import sqlite3
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

# Keys shaped like a scope identifier, or carrying personal/location data: the
# decision's keys, the near-variants of the #1478 reviews, and encodings the
# normaliser must see through (full-width, zero-width, Cyrillic, dotless i, Arabic).
FORBIDDEN_KEYS = [
    "tenant_id",
    "field_id",
    "farm_id",
    "user_id",
    "owner",
    "owner_id",
    "tenantId",
    "tenantID",
    "tenant.id",
    "Field-ID",
    "FARM_ID",
    "farmer_id",
    "plot_id",
    "parcel_id",
    "org_id",
    "organization_id",
    "customer_id",
    "account_id",
    "grower_name",
    "site_code",
    "plot_no",
    "field_number",
    "farmname",
    "tenantid",
    "tenant_uuid",
    "field_uuid",
    "tenants",
    "farm_ids",
    "created_by",
    "submitted_by",
    "author",
    "email",
    "contact_phone",
    "geometry",
    "geo_point",
    "coordinates",
    "location",
    "lat",
    "lon",
    "latitude",
    "longitude",
    "boundary",
    "address",
    "ｔｅｎａｎｔ_id",  # full-width tenant_id
    "t\u200benant_id",  # zero-width space inside
    "tеnant_id",  # Cyrillic e
    "tenant_ıd",  # dotless i
    "حقل",  # حقل
    "معرف_المزرعة",  # معرف_المزرعة
    "مزرعة_رقم",  # مزرعة_رقم
]
PRIVATE_MARKS = [
    {"private": True},
    {"private": "true"},
    {"is_private": True},
    {"isPrivate": 1},
    {"visibility": "private"},
    {"visibility": ["private"]},
    {"visibility": "restricted"},
    {"scope": "tenant"},
    {"scope": "organization"},
    {"access": "internal"},
    {"sharing_policy": "tenant"},
    {"public": False},
    {"is_public": "false"},
    {"shared_with": ["t-1"]},
]
# Reference properties that merely contain a scope word: regression tests for the
# false positives of the broad token rule (#1478 re-review).
FALSE_POSITIVE_KEYS = [
    "field_resistance",
    "field_trial_results",
    "field_emergence_pct",
    "farm_size_ha",
    "plot_size_m2",
    "user_guide_url",
    "source_organization",
    "data_owner",
    "owner_institution",
    "field_capacity",
    "fieldCapacity",
]
# Free-text values under visibility-like keys that are not private markers.
FREE_TEXT_VISIBILITY = [
    {"scope": "Applies to cereals in arid zones"},
    {"access": "open data"},
    {"visibility": "global"},
    {"visibility": "public"},
    {"shared_with": []},
    {"public": True},
]
# Ids, labels and names that encode a tenant/farm/field scope.
SCOPED_IDENTIFIERS = [
    ("node_id", "tenant:acme/farm:12/field:7"),
    ("node_id", "tenant-acme-wheat"),
    ("node_id", "acme-tenant"),
    ("node_id", "org:7"),
    ("node_id", "field:7"),
    ("node_id", "7:field"),
    ("node_id", "farm-12"),
    ("node_id", "farm12"),
    ("node_id", "field7"),
    ("node_id", "customerId42"),
    ("node_id", "مزرعة:12"),  # مزرعة:12
    ("label", "Tenant#acme"),
    ("name", "field/7 wheat"),
]
# Reference vocabulary and prose that contain a scope word: still allowed.
REFERENCE_IDENTIFIERS = [
    ("label", "Field"),
    ("label", "Farm"),
    ("label", "FieldTrial2019"),
    ("node_id", "field_crops"),
    ("node_id", "field_pea"),
    ("node_id", "field_capacity"),
    ("node_id", "plot_2x2_design"),
    ("name", "Field trial"),
    ("name", "Farmer field schools"),
    ("name", "Tenant farming systems"),
    ("name", "User guide to wheat"),
    ("name", "Field capacity of sandy loam"),
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
            {
                "source": "FAO",
                "private": False,
                "visibility": "global",
                "field_capacity": 0.31,
                "access": "public",
            },
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


# ── #1478 reviews: shapes, encodings, ids and labels ──────────────────────────────


@pytest.mark.parametrize("key", FALSE_POSITIVE_KEYS)
def test_reference_keys_containing_a_scope_word_are_accepted(store, key):
    store.upsert_node(kg.GraphNode("loam", "SoilTexture", "Loam", {key: 0.3}))
    assert "loam" in _node_ids(store)


@pytest.mark.parametrize("mark", FREE_TEXT_VISIBILITY)
def test_free_text_under_visibility_keys_is_accepted(store, mark):
    store.upsert_node(kg.GraphNode("loam", "SoilTexture", "Loam", dict(mark)))
    assert "loam" in _node_ids(store)


@pytest.mark.parametrize("gtype", ["Point", "Polygon", "MultiPolygon", "LineString", "Feature"])
def test_a_geojson_value_is_refused_under_any_key(store, gtype):
    with pytest.raises(kg.TenantScopedDataError) as exc:
        store.upsert_node(
            kg.GraphNode("loam", "SoilTexture", "Loam", {"shape": {"type": gtype, "x": []}})
        )
    assert exc.value.path == "properties.shape"


@pytest.mark.parametrize(
    "blob",
    [
        '{"tenant_id": "acme"}',
        ' {"meta": {"farm_id": 12}} ',
        '[{"visibility": "private"}]',
        '\ufeff{"tenant_id": "acme"}',
        json.dumps(json.dumps({"farm_id": 12})),
    ],
)
def test_json_string_values_are_parsed_and_checked(api, blob):
    _main, client = api
    body = {"node_id": "barley", "label": "Crop", "name": "Barley", "properties": {"raw": blob}}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 422 and r.json()["detail"]["code"] == CODE
    assert "<json>" in r.json()["detail"]["path"]


def test_a_field_polygon_under_geometry_is_refused(api):
    _main, client = api
    polygon = {"type": "Polygon", "coordinates": [[[44.1, 15.3], [44.2, 15.3], [44.1, 15.4]]]}
    body = {"node_id": "barley", "label": "Crop", "name": "B", "properties": {"geometry": polygon}}
    _assert_refused(client.post("/v1/nodes", json=body, headers=WRITE_HEADERS), "geometry")


@pytest.mark.parametrize("value", ["false", "False", "no", "0", False, 0])
def test_private_false_does_not_count_as_private(store, value):
    store.upsert_node(kg.GraphNode("loam", "SoilTexture", "Loam", {"private": value}))
    assert "loam" in _node_ids(store)


@pytest.mark.parametrize("value", ["global", "public", "Public"])
def test_global_or_public_visibility_is_accepted(store, value):
    for key in ("visibility", "scope", "access"):
        store.upsert_node(kg.GraphNode("loam", "SoilTexture", "Loam", {key: value}))
    assert "loam" in _node_ids(store)


@pytest.mark.parametrize(("field", "value"), SCOPED_IDENTIFIERS)
def test_rest_node_with_a_scoped_id_or_label_is_refused(api, field, value):
    _main, client = api
    body = {"node_id": "barley", "label": "Crop", "name": "Barley", field: value}
    _assert_refused(client.post("/v1/nodes", json=body, headers=WRITE_HEADERS), field)


@pytest.mark.parametrize("edge_id", ["tenant-acme-e", "farm:12:e1", "e-field-7"])
def test_rest_edge_with_a_scoped_edge_id_is_refused_and_never_read_back(api, edge_id):
    main, client = api
    body = {
        "edge_id": edge_id,
        "subject_id": "wheat",
        "relation": "historically_susceptible_to",
        "object_id": "stripe_rust",
    }
    _assert_refused(client.post("/v1/edges", json=body, headers=WRITE_HEADERS), "edge_id")
    r = client.get("/v1/edges", headers={"X-Tenant-Id": "tenant-b"})
    assert edge_id not in {e["edge_id"] for e in r.json()["edges"]}


@pytest.mark.parametrize(("field", "value"), REFERENCE_IDENTIFIERS)
def test_reference_vocabulary_ids_and_labels_are_accepted(api, field, value):
    _main, client = api
    body = {"node_id": "barley", "label": "Crop", "name": "Barley", field: value}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 200, r.text


# ── read-only scan of rows stored before the guard ───────────────────────────────


def test_scan_reports_existing_violations_without_deleting(tmp_path):
    db = tmp_path / "legacy.sqlite"
    s = kg.SQLiteAgGraphStore(db)
    kg.seed_reference_ontology(s)
    # Simulate rows written before the guard existed, bypassing upsert_*.
    with s._connect() as conn:
        conn.execute(
            "INSERT INTO kg_nodes VALUES(?,?,?,?)",
            ("tenant:acme/field:7", "Field", "Acme field 7", "{}"),
        )
        conn.execute(
            "INSERT INTO kg_nodes VALUES(?,?,?,?)",
            ("barley", "Crop", "Barley", '{"meta": {"farm_id": 12}}'),
        )
        conn.execute(
            "INSERT INTO kg_edges VALUES(?,?,?,?,?,?,?)",
            (
                "e-legacy",
                "wheat",
                "historically_limits",
                "barley",
                "reference",
                0,
                '{"private": true}',
            ),
        )
    before = db.read_bytes()
    findings = kg.scan_existing_rows(db)
    assert sorted((f["table"], f["id"], f["path"]) for f in findings) == [
        ("kg_edges", "e-legacy", "properties.private"),
        ("kg_nodes", "barley", "properties.meta.farm_id"),
        ("kg_nodes", "tenant:acme/field:7", "node_id"),
    ]
    assert db.read_bytes() == before, "the scan must not write"
    assert s.count_edges() == 5


def test_scan_cli_exit_codes(tmp_path, capsys):
    clean = tmp_path / "clean.sqlite"
    kg.seed_reference_ontology(kg.SQLiteAgGraphStore(clean))
    assert kg._main(["--scan", str(clean)]) == 0
    assert '"violations": []' in capsys.readouterr().out
    dirty = tmp_path / "dirty.sqlite"
    s = kg.SQLiteAgGraphStore(dirty)
    with s._connect() as conn:
        conn.execute("INSERT INTO kg_nodes VALUES('org:9','Org','x','{}')")
    assert kg._main(["--scan", str(dirty)]) == 1


def test_scan_connection_refuses_writes(tmp_path):
    db = tmp_path / "ro.sqlite"
    kg.SQLiteAgGraphStore(db)
    conn = kg.open_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO kg_nodes VALUES('x','X','x','{}')")
    finally:
        conn.close()
    assert kg.scan_existing_rows(db) == []


def test_scan_reports_rows_with_invalid_properties_json(tmp_path):
    db = tmp_path / "bad.sqlite"
    s = kg.SQLiteAgGraphStore(db)
    with s._connect() as conn:
        conn.execute("INSERT INTO kg_nodes VALUES('loam','SoilTexture','Loam','{not json')")
    assert kg.scan_existing_rows(db) == [
        {
            "table": "kg_nodes",
            "id": "loam",
            "path": "properties_json",
            "reason": "properties_json is not valid JSON",
        }
    ]


# ── robustness: 4xx, never 500 or a stall ───────────────────────────────────────


def _nested(depth: int) -> dict:
    root: dict = {}
    cur = root
    for _ in range(depth):
        cur["a"] = {}
        cur = cur["a"]
    return root


@pytest.mark.parametrize("depth", [65, 200, 900])
def test_deep_nesting_is_refused_with_422(api, depth):
    _main, client = api
    body = {"node_id": "loam", "label": "S", "name": "L", "properties": _nested(depth)}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 422, r.text[:200]
    assert r.json()["detail"]["code"] == "kg_payload_too_deep"


def test_deep_json_inside_a_string_is_refused_with_422(api):
    _main, client = api
    blob = "[" * 5000 + "]" * 5000
    body = {"node_id": "loam", "label": "S", "name": "L", "properties": {"raw": blob}}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 422, r.text[:200]
    assert r.json()["detail"]["code"] == "kg_payload_too_deep"


def test_nesting_within_the_cap_is_accepted(store):
    store.upsert_node(kg.GraphNode("loam", "SoilTexture", "Loam", _nested(60)))
    assert "loam" in _node_ids(store)


def test_too_many_keys_is_refused_with_413(api):
    _main, client = api
    props = {f"k{i}": i for i in range(10_001)}
    body = {"node_id": "loam", "label": "S", "name": "L", "properties": props}
    r = client.post("/v1/nodes", json=body, headers=WRITE_HEADERS)
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "kg_payload_too_large"
