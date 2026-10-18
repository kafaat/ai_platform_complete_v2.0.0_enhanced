"""Runtime profile binding, legacy parity and actual fusion choice."""

import copy
import hashlib
import importlib
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/sahool-platform"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/rag-retrieval"))
pq = importlib.import_module("core.rag.production_qdrant")
rp = importlib.import_module("retrieval_profile")
rm = importlib.import_module("reindex_manifest")

pytestmark = pytest.mark.unit


def fixture():
    chunk = pq.KnowledgeChunk(
        chunk_id="x",
        tenant_id="a",
        text="قمح",
        source_type="uploaded_document",
        document_id="x",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "fixture://test",
            "source_revision": "v1",
        },
    )
    payload = chunk.payload
    payload["metadata"].update(
        reindex_revision="v1",
        embedding_model_digest=rp.NOMIC_DIGEST,
        document_embedding_prefix="search_document: ",
        retrieval_profile=rp.NOMIC_PROFILE,
    )
    rows = [(pq.canonical_storage_point_id("x"), payload)]
    spec = rm.ReindexSpec(
        "source",
        "sahool_rag_reindex_v1",
        "v1",
        rp.NOMIC_DIGEST,
        "a" * 64,
        document_prefix="search_document: ",
        retrieval_profile=rp.NOMIC_PROFILE,
    )
    vectors = [(rows[0][0], [1.0 / math.sqrt(768)] * 768)]
    vector_digest = hashlib.sha256(
        json.dumps(vectors, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = dict(
        query_prefix=rp.QUERY_PREFIX,
        dense_weight=0.1,
        sparse_weight=0.9,
        vector_distance="Cosine",
        candidate_vector_digest=vector_digest,
        schema="sahool.rag-shadow-reindex/v1",
        retrieval_profile=rp.NOMIC_PROFILE,
        model_digest=rp.NOMIC_DIGEST,
        document_prefix="search_document: ",
        vector_size=768,
        target_collection=spec.target_collection,
        revision="v1",
        candidate=rm.inventory(rows, spec),
        source_preserved=True,
        aliases_preserved=True,
        serving_authority_changed=False,
    )
    return rows, manifest


class Encoder:
    model = "nomic-embed-text:latest"
    base_url = "http://unused"

    def __init__(self):
        self.seen = []

    def model_digest(self):
        return rp.NOMIC_DIGEST

    def embed(self, text):
        self.seen.append(text)
        return [1.0] * 768


class Store:
    collection = "sahool_rag_reindex_v1"

    def __init__(self, rows):
        self.rows = rows
        self.vector = [1.0 / math.sqrt(768)] * 768
        self.distance = "Cosine"

    def _request(self, method, path, payload=None):
        if method == "GET":
            return {
                "result": {
                    "config": {"params": {"vectors": {"size": 768, "distance": self.distance}}}
                }
            }
        return {
            "result": {
                "points": [{"id": p, "vector": self.vector} for p, _ in self.rows],
                "next_page_offset": None,
            }
        }

    def scroll_payloads(self, **kwargs):
        return self.rows

    def search(self, *args, **kwargs):
        return [(p, 1.0, data) for p, data in self.rows]


def valid_tags(monkeypatch):
    monkeypatch.setattr(Encoder, "model_digest", lambda self: rp.NOMIC_DIGEST)


def test_profile_uses_query_prefix_and_measured_weights(monkeypatch):
    valid_tags(monkeypatch)
    rows, manifest = fixture()
    encoder = Encoder()
    retriever = pq.HybridQdrantRetriever(
        Store(rows), encoder, retrieval_profile=rp.RetrievalProfile(manifest)
    )
    retriever.rebuild_sparse_index()
    weights = []
    original = pq.weighted_rrf_scores

    def capture(*args, **kwargs):
        weights.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pq, "weighted_rrf_scores", capture)
    assert retriever.retrieve("قمح", tenant_id="a")
    assert encoder.seen == ["search_query: قمح"]
    assert weights == [{"dense_weight": 0.1, "sparse_weight": 0.9}]


def test_legacy_keeps_raw_query_and_existing_weights(monkeypatch):
    rows, _ = fixture()
    for _, p in rows:
        for key in (
            "document_embedding_prefix",
            "retrieval_profile",
            "reindex_revision",
            "embedding_model_digest",
        ):
            p["metadata"].pop(key)
    encoder = Encoder()
    store = Store(rows)
    store.collection = "sahool_agri_kb"
    retriever = pq.HybridQdrantRetriever(store, encoder)
    retriever.rebuild_sparse_index()
    weights = []
    original = pq.weighted_rrf_scores

    def capture(*args, **kwargs):
        weights.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pq, "weighted_rrf_scores", capture)
    assert retriever.retrieve("قمح", tenant_id="a")
    assert encoder.seen == ["قمح"]
    assert weights == [{"dense_weight": 0.7, "sparse_weight": 0.3}]


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_vector_digest", None),
        ("query_prefix", ""),
        ("dense_weight", 0.7),
        ("sparse_weight", 0.3),
        ("model_digest", "b" * 64),
        ("retrieval_profile", "unknown"),
        ("vector_size", 384),
        ("document_prefix", ""),
        ("serving_authority_changed", True),
    ],
)
def test_unqualified_manifest_refused(field, value):
    _, manifest = fixture()
    manifest[field] = value
    with pytest.raises(ValueError):
        rp.RetrievalProfile(manifest)


@pytest.mark.parametrize("drift", ["collection", "model", "payload", "revision"])
def test_profile_mismatch_fails_before_query_embedding(monkeypatch, drift):
    valid_tags(monkeypatch)
    rows, manifest = fixture()
    store = Store(rows)
    encoder = Encoder()
    profile = rp.RetrievalProfile(manifest)
    if drift == "collection":
        store.collection = "source"
    if drift == "model":
        monkeypatch.setattr(encoder, "model_digest", lambda: "wrong")
    if drift == "payload":
        rows[0][1]["page_content"] = "changed"
    if drift == "revision":
        rows[0][1]["metadata"]["reindex_revision"] = "wrong"
    with pytest.raises(ValueError):
        pq.HybridQdrantRetriever(store, encoder, retrieval_profile=profile).retrieve(
            "q", tenant_id="a"
        )
    assert encoder.seen == []


def test_legacy_cannot_search_prefixed_collection():
    rows, _ = fixture()
    with pytest.raises(ValueError, match="legacy"):
        pq.HybridQdrantRetriever(Store(rows), Encoder()).rebuild_sparse_index()


def test_versioned_collection_cannot_be_incrementally_mutated():
    rows, manifest = fixture()
    r = pq.HybridQdrantRetriever(
        Store(rows), Encoder(), retrieval_profile=rp.RetrievalProfile(manifest)
    )
    with pytest.raises(ValueError, match="immutable"):
        r.ingest([])


@pytest.mark.parametrize("drift", ["vector", "distance", "same_count_replacement"])
def test_index_drift_fails_before_query_embedding(monkeypatch, drift):
    valid_tags(monkeypatch)
    rows, manifest = fixture()
    store, encoder = Store(rows), Encoder()
    if drift == "vector":
        store.vector[0] = 0.0
    elif drift == "distance":
        store.distance = "Dot"
    else:
        store.rows = [("different-id", p) for _, p in rows]
    with pytest.raises(ValueError):
        pq.HybridQdrantRetriever(
            store, encoder, retrieval_profile=rp.RetrievalProfile(manifest)
        ).retrieve("q", tenant_id="a")
    assert encoder.seen == []


def test_untagged_default_resolves_exact_latest_digest(monkeypatch):
    valid_tags(monkeypatch)
    rows, manifest = fixture()
    encoder = Encoder()
    encoder.model = "nomic-embed-text"
    rp.RetrievalProfile(manifest).validate_encoder(Store(rows), encoder)


def test_manifest_file_missing_or_malformed_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        rp.RetrievalProfile.from_file(tmp_path / "missing")
    path = tmp_path / "manifest.json"
    for raw in ["[]", "{}", "invalid", " " * (1024 * 1024 + 1)]:
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError):
            rp.RetrievalProfile.from_file(path)


def test_complete_reindex_spec_requires_matching_profile():
    _, manifest = fixture()
    with pytest.raises(ValueError, match="matching query profile"):
        rm.ReindexSpec(
            "source",
            "sahool_rag_reindex_v1",
            "v1",
            rp.NOMIC_DIGEST,
            "a" * 64,
            document_prefix="search_document: ",
        )
    with pytest.raises(ValueError, match="requires measured model"):
        rm.ReindexSpec(
            "source",
            "sahool_rag_reindex_v1",
            "v1",
            "b" * 64,
            "a" * 64,
            document_prefix="search_document: ",
            retrieval_profile=rp.NOMIC_PROFILE,
        )


def test_shadow_collection_without_manifest_never_uses_warm_sparse_or_dense():
    rows, _ = fixture()
    store = Store(rows)
    store.search = lambda *args, **kwargs: []
    bm25 = pq.BM25Index()
    encoder = Encoder()
    with pytest.raises(ValueError, match="requires an explicit serving profile"):
        pq.HybridQdrantRetriever(store, encoder, bm25)
    assert encoder.seen == []


@pytest.mark.parametrize("drift", ["model", "vector", "payload", "transport"])
def test_warm_search_profile_failure_is_sanitized_unavailable(monkeypatch, drift):
    import urllib.error

    from fastapi.testclient import TestClient

    from tests_v9.service_module import load_service_main

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "profile-regression-service-token")
    rag = load_service_main(
        str(Path(__file__).resolve().parents[1] / "services/rag-retrieval"),
        required_attrs=("search", "_ensure_sparse_index"),
    )
    rows, manifest = fixture()
    store, encoder = Store(rows), Encoder()
    store.collection_point_count = lambda: len(store.rows)
    rag._qdrant = store
    rag._retriever = pq.HybridQdrantRetriever(
        store, encoder, retrieval_profile=rp.RetrievalProfile(manifest)
    )
    rag._sparse_ready = False
    headers = {"X-Agent-Token": "profile-regression-service-token", "X-Tenant-Id": "a"}
    client = TestClient(rag.app, raise_server_exceptions=False)
    assert (
        client.post(
            "/v1/search", json={"query": "قمح", "tenant_id": "a"}, headers=headers
        ).status_code
        == 200
    )
    assert rag._sparse_ready is True
    if drift == "model":
        encoder.model_digest = lambda: "wrong"
    elif drift == "vector":
        store.vector[0] = 0.0
    elif drift == "payload":
        store.rows[0][1]["page_content"] = "changed"
    else:

        def unavailable():
            raise urllib.error.URLError("http://private-origin.invalid?token=do-not-return")

        encoder.model_digest = unavailable
    response = client.post("/v1/search", json={"query": "قمح", "tenant_id": "a"}, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "rag_retrieval_unavailable"}
    # Authentication and tenant resolution still precede retrieval admission.
    assert client.post("/v1/search", json={"query": "قمح", "tenant_id": "a"}).status_code == 403
    assert (
        client.post(
            "/v1/search", json={"query": "قمح", "tenant_id": "b"}, headers=headers
        ).status_code
        == 403
    )


def test_warm_search_does_not_hide_programming_error(monkeypatch):
    from fastapi.testclient import TestClient

    from tests_v9.service_module import load_service_main

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "profile-regression-service-token")
    rag = load_service_main(
        str(Path(__file__).resolve().parents[1] / "services/rag-retrieval"),
        required_attrs=("search", "_ensure_sparse_index"),
    )
    rows, manifest = fixture()
    store, encoder = Store(rows), Encoder()
    store.collection_point_count = lambda: len(store.rows)
    rag._qdrant = store
    rag._retriever = pq.HybridQdrantRetriever(
        store, encoder, retrieval_profile=rp.RetrievalProfile(manifest)
    )
    rag._sparse_ready = False
    headers = {"X-Agent-Token": "profile-regression-service-token", "X-Tenant-Id": "a"}
    client = TestClient(rag.app, raise_server_exceptions=False)
    assert (
        client.post(
            "/v1/search", json={"query": "قمح", "tenant_id": "a"}, headers=headers
        ).status_code
        == 200
    )

    def broken(*args, **kwargs):
        raise ValueError("unexpected application programming error")

    rag._retriever.retrieve = broken
    response = client.post("/v1/search", json={"query": "قمح", "tenant_id": "a"}, headers=headers)
    assert response.status_code == 500
