"""RAG-DOCUMENT-REVISION-WITHDRAWAL-01 — re-uploading a document withdraws its old chunks.

The audit claim (RAG wiring audit 2026-11-22, L199-201): ``document_id`` is built from
tenant + file name and ``chunk_id`` includes the text, so an edited file yields new chunk
ids; the canonical writer only upserted the incoming ids, so the chunks of the earlier
revision — and the surplus ones when the file got shorter — stayed searchable, and the
neighbour key ``(tenant, document, index)`` could step from one revision into another.

Offline behavioural witnesses against an in-memory store that speaks the Qdrant HTTP
wire shapes the client emits (upsert, filtered scroll, delete by id, search). No live
Qdrant and no production claim.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import sys
from pathlib import Path

import pytest

from tests_v9.service_module import load_service_main

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/sahool-platform"))
pq = importlib.import_module("core.rag.production_qdrant")

REV1 = "sha256:" + "1" * 64
REV2 = "sha256:" + "2" * 64


def document(tenant, texts, *, revision, name="guide.txt", document_id=None, **meta):
    """Chunks shaped like the upload producer's wire chunks (id = doc + index + text)."""
    doc_id = document_id or hashlib.sha256(f"{tenant}:{name}".encode()).hexdigest()
    source_type = (
        "curated_reference" if tenant == pq.GLOBAL_REFERENCE_TENANT else "uploaded_document"
    )
    provenance = {
        "evidence_level": "document",
        "source_uri": f"tenant-upload://{tenant}/{name}",
        "publisher": "test",
        "license": "test",
    }
    if revision is not None:
        provenance["source_revision"] = revision
    return [
        pq.KnowledgeChunk(
            chunk_id=hashlib.sha256(f"{doc_id}:{idx}:{text}".encode()).hexdigest(),
            tenant_id=tenant,
            text=text,
            source_type=source_type,
            document_id=doc_id,
            chunk_index=idx,
            total_chunks=len(texts),
            metadata={**provenance, **meta},
        )
        for idx, text in enumerate(texts)
    ]


def _matches(condition, payload, point_id):
    """Interpreter for the Qdrant filter nodes this contract emits, nothing more."""
    if not all(_matches(c, payload, point_id) for c in condition.get("must", [])):
        return False
    if "should" in condition and not any(
        _matches(c, payload, point_id) for c in condition["should"]
    ):
        return False
    if any(_matches(c, payload, point_id) for c in condition.get("must_not", [])):
        return False
    if "has_id" in condition:
        return point_id in condition["has_id"]
    if "key" in condition:
        value = payload
        for part in condition["key"].split("."):
            value = value.get(part) if isinstance(value, dict) else None
        rule = condition["match"]
        return value in rule["any"] if "any" in rule else value == rule["value"]
    for operator in ("is_empty", "is_null"):
        if operator in condition:
            value = payload.get("metadata", {}).get(
                condition[operator]["key"].removeprefix("metadata.")
            )
            return value is None or (operator == "is_empty" and value == [])
    return True


class Qdrant(pq.QdrantHttpClient):
    """In-memory Qdrant: stores what the client writes and answers what it asks."""

    def __init__(self):
        super().__init__("http://qdrant", "c", vector_size=32)
        self.points: dict[str, tuple[list[float], dict]] = {}
        self.requests: list[tuple[str, str]] = []
        self.fail_delete = False
        self.ignore_scroll_filter = False

    def ensure_collection(self, *, vector_size=None):
        return None

    def _request(self, method, path, payload=None):
        body = payload or {}
        operation = path.split("/points", 1)[-1].split("?")[0] or "/upsert"
        self.requests.append((method, operation))
        if operation == "/upsert":
            for point in body["points"]:
                self.points[point["id"]] = (point["vector"], point["payload"])
            return {}
        if operation == "/delete":
            if self.fail_delete:
                raise pq.QdrantHTTPError(503, "delete unavailable")
            assert (
                "?wait=true" in path
            )  # a withdrawal the next search might not see is no withdrawal
            assert set(body) == {"points"}  # explicit ids only: never a bare filter
            for point_id in body["points"]:
                self.points.pop(point_id, None)
            return {}
        if operation == "/scroll":
            condition = {} if self.ignore_scroll_filter else body.get("filter", {})
            ids = sorted(pid for pid, (_v, p) in self.points.items() if _matches(condition, p, pid))
            start = ids.index(body["offset"]) if body.get("offset") is not None else 0
            page = ids[start : start + body["limit"]]
            rest = ids[start + body["limit"] :]
            return {
                "result": {
                    "points": [{"id": pid, "payload": self.points[pid][1]} for pid in page],
                    "next_page_offset": rest[0] if rest else None,
                }
            }
        if operation == "/search":
            rows = [
                {
                    "id": pid,
                    "score": sum(a * b for a, b in zip(body["vector"], vector, strict=True)),
                    "payload": point_payload,
                }
                for pid, (vector, point_payload) in self.points.items()
                if _matches(body["filter"], point_payload, pid)
            ]
            return {"result": sorted(rows, key=lambda r: -r["score"])[: body["limit"]]}
        raise AssertionError(f"unexpected Qdrant request: {method} {path}")

    def stored(self, tenant):
        return {
            payload["metadata"]["chunk_id"]
            for _vector, payload in self.points.values()
            if payload["metadata"]["tenant_id"] == tenant
        }

    def writes(self):
        return [op for method, op in self.requests if op in {"/upsert", "/delete"}]


def retriever(store=None):
    return pq.HybridQdrantRetriever(store or Qdrant(), pq.HashEmbeddingProvider(32))


def ids(chunks):
    return {c.chunk_id for c in chunks}


LONG = ["barley sowing calendar", "obsolete zebra dosage table", "withdrawn quagga appendix"]
SHORT = ["barley sowing calendar revised", "current irrigation notes"]


# ── The claim: earlier-revision chunks survive a re-upload ───────────────────────────────


def test_shorter_revision_withdraws_every_earlier_chunk_from_the_store():
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    new = document("tenant-a", SHORT, revision=REV2)
    r.ingest(new)
    assert r.qdrant.stored("tenant-a") == ids(new)


@pytest.mark.parametrize("stale_term", ["zebra", "quagga"])
def test_search_never_returns_a_chunk_of_a_withdrawn_revision(stale_term):
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    r.ingest(document("tenant-a", SHORT, revision=REV2))
    rows = r.retrieve(stale_term, tenant_id="tenant-a", final_k=10)
    assert {row.chunk.metadata["source_revision"] for row in rows} <= {REV2}
    assert not r.bm25.search(stale_term, tenant_id="tenant-a")


def test_neighbour_expansion_never_steps_into_a_withdrawn_revision():
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    r.ingest(document("tenant-a", SHORT, revision=REV2))
    # The hit is the last chunk of the short revision; index + 1 exists only in the old one.
    rows = r.retrieve("current irrigation notes", tenant_id="tenant-a", final_k=10)
    assert rows and rows[0].chunk.text == "current irrigation notes"
    assert all(row.chunk.metadata["source_revision"] == REV2 for row in rows)


def test_restart_does_not_resurrect_withdrawn_chunks():
    store = Qdrant()
    first = retriever(store)
    first.ingest(document("tenant-a", LONG, revision=REV1))
    first.ingest(document("tenant-a", SHORT, revision=REV2))
    restarted = retriever(store)
    report = restarted.rebuild_sparse_index()
    assert report["loaded_chunks"] == len(SHORT)
    assert not restarted.bm25.search("zebra", tenant_id="tenant-a")


def test_neighbour_lookup_is_keyed_by_revision():
    """Two revisions side by side in memory (a store written before this contract)."""
    r = retriever()
    old = document("tenant-a", LONG, revision=REV1)
    new = document("tenant-a", SHORT, revision=REV2)
    r._chunks = {pq.chunk_identity(c): c for c in [*new, *old]}
    hit = pq.RetrievedAnnotation(new[0], 1.0, 1.0, 1.0)
    neighbours = [row.chunk for row in r._expand_neighbors([hit]) if row.role == "neighbor"]
    assert neighbours == [new[1]]


# ── The contract: receipt, idempotency ───────────────────────────────────────────────────


def test_ingest_answers_with_an_indexing_receipt_per_document():
    r = retriever()
    old = document("tenant-a", LONG, revision=REV1)
    other = document("tenant-a", ["unrelated note"], revision=REV1, name="other.txt")
    first = r.ingest_documents([*old, *other])
    assert [x.as_dict() for x in first] == [
        {
            "tenant_id": "tenant-a",
            "document_id": doc[0].document_id,
            "revision": REV1,
            "chunks_written": len(doc),
            "chunks_withdrawn": 0,
        }
        for doc in (old, other)
    ]
    new = document("tenant-a", SHORT, revision=REV2)
    (receipt,) = r.ingest_documents(new)
    assert (receipt.revision, receipt.chunks_written, receipt.chunks_withdrawn) == (REV2, 2, 3)
    assert r.qdrant.stored("tenant-a") == ids(new) | ids(other)  # the other document is untouched


def test_reingesting_the_same_revision_is_idempotent():
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    new = document("tenant-a", SHORT, revision=REV2)
    r.ingest(new)
    points, sparse = dict(r.qdrant.points), dict(r.bm25.doc_freq)
    (receipt,) = r.ingest_documents(new)
    assert (receipt.chunks_written, receipt.chunks_withdrawn) == (2, 0)

    def unstamped(stored):
        return {
            pid: (vector, {k: v for k, v in payload.items() if k != pq.PUBLICATION_STAMP_KEY})
            for pid, (vector, payload) in stored.items()
        }

    # Same ids, vectors and payloads; only the publication stamp moves forward, because a
    # re-ingest is a new publication of that revision.
    assert unstamped(r.qdrant.points) == unstamped(points)
    assert all(
        r.qdrant.points[pid][1][pq.PUBLICATION_STAMP_KEY] > points[pid][1][pq.PUBLICATION_STAMP_KEY]
        for pid in points
    )
    assert (dict(r.bm25.doc_freq), len(r.bm25)) == (sparse, 2)
    assert r.qdrant.writes()[-1] == "/upsert"  # nothing to withdraw, so no delete is sent


def test_same_revision_rechunked_leaves_no_surplus_chunk():
    """Same file bytes, different chunk boundaries: still one document, not two."""
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    rechunked = document("tenant-a", [" ".join(LONG)], revision=REV1)
    (receipt,) = r.ingest_documents(rechunked)
    assert receipt.chunks_withdrawn == 3
    assert r.qdrant.stored("tenant-a") == ids(rechunked)


def test_a_document_without_a_declared_revision_is_still_replaced():
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=None, source_class="internal_document"))
    new = document("tenant-a", SHORT, revision=None, source_class="internal_document")
    (receipt,) = r.ingest_documents(new)
    assert (receipt.revision, receipt.chunks_withdrawn) == (None, 3)
    assert r.qdrant.stored("tenant-a") == ids(new)


def test_empty_batch_writes_and_withdraws_nothing():
    r = retriever()
    assert r.ingest_documents([]) == []
    assert r.ingest([]) == 0
    assert r.qdrant.requests == []


# ── Tenant isolation of the withdrawal ───────────────────────────────────────────────────


def seeded_store(document_id="shared-document-id"):
    """Tenant A, tenant B and both reference tenants hold the *same* document id."""
    store = Qdrant()
    kept = {}
    for tenant in ("tenant-b", pq.GLOBAL_REFERENCE_TENANT, pq.SEED_QUARANTINE_TENANT):
        # Own text per tenant: the two reference tenants share one point-id namespace.
        texts = [f"{text} of {tenant}" for text in LONG]
        chunks = document(tenant, texts, revision=REV1, document_id=document_id)
        store.upsert(chunks, [[0.0] * 32 for _ in chunks])
        kept[tenant] = ids(chunks)
    return store, kept


@pytest.mark.parametrize("store_filters", [True, False], ids=["filtering", "filter-ignored"])
def test_withdrawal_never_touches_another_tenant_or_the_reference_corpus(store_filters):
    store, kept = seeded_store()
    store.ignore_scroll_filter = not store_filters  # the payload check, not the store, decides
    r = retriever(store)
    r.ingest(document("tenant-a", LONG, revision=REV1, document_id="shared-document-id"))
    new = document("tenant-a", SHORT, revision=REV2, document_id="shared-document-id")
    (receipt,) = r.ingest_documents(new)
    assert receipt.chunks_withdrawn == 3
    assert store.stored("tenant-a") == ids(new)
    for tenant, chunk_ids in kept.items():
        assert store.stored(tenant) == chunk_ids


def test_withdrawal_leaves_other_tenants_in_process_memory():
    r = retriever()
    theirs = document("tenant-b", LONG, revision=REV1, document_id="shared-document-id")
    r.ingest(theirs)
    r.ingest(document("tenant-a", LONG, revision=REV1, document_id="shared-document-id"))
    r.ingest(document("tenant-a", SHORT, revision=REV2, document_id="shared-document-id"))
    assert {c.chunk_id for c, _score in r.bm25.search("zebra", tenant_id="tenant-b")} == {
        theirs[1].chunk_id
    }
    assert not r.bm25.search("zebra", tenant_id="tenant-a")


def legacy_row(tenant, name, text, *, root_tenant=None):
    """A row of the pre-convergence direct writer: no chunk id, no document id."""
    metadata = {
        "source_file": name,
        "source_class": "tenant_document",
        "source_uri": f"tenant-upload://{tenant}/{name}",
        "source_revision": REV1,
    }
    if root_tenant is None:
        metadata["tenant_id"] = tenant
    payload = {"page_content": text, "metadata": metadata}
    if root_tenant is not None:
        payload["tenant_id"] = root_tenant
    return payload


@pytest.mark.parametrize("tenant_at_root", [False, True], ids=["nested-tenant", "root-tenant"])
def test_legacy_rows_the_reader_serves_as_the_document_are_withdrawn_with_it(tenant_at_root):
    store = Qdrant()
    root = "tenant-a" if tenant_at_root else None
    store.points["legacy-a"] = (
        [0.0] * 32,
        legacy_row("tenant-a", "guide.txt", "zebra", root_tenant=root),
    )
    store.points["legacy-other-file"] = (
        [0.0] * 32,
        legacy_row("tenant-a", "other.txt", "zebra", root_tenant=root),
    )
    store.points["legacy-b"] = ([0.0] * 32, legacy_row("tenant-b", "guide.txt", "zebra"))
    r = retriever(store)
    assert r.rebuild_sparse_index()["loaded_chunks"] == 3  # the reader does serve them
    new = document("tenant-a", SHORT, revision=REV2)
    (receipt,) = r.ingest_documents(new)
    assert receipt.chunks_withdrawn == 1
    assert "legacy-a" not in store.points
    assert {"legacy-other-file", "legacy-b"} <= set(store.points)


def test_row_claimed_at_the_root_but_owned_by_another_tenant_is_not_withdrawn():
    """``metadata.tenant_id`` is the reference: a root value cannot hand a row over."""
    store = Qdrant()
    row = legacy_row("tenant-b", "guide.txt", "zebra")
    row["tenant_id"] = "tenant-a"
    row["metadata"]["document_id"] = document("tenant-a", SHORT, revision=REV2)[0].document_id
    store.points["theirs"] = ([0.0] * 32, row)
    (receipt,) = retriever(store).ingest_documents(document("tenant-a", SHORT, revision=REV2))
    assert receipt.chunks_withdrawn == 0
    assert "theirs" in store.points


def test_row_the_reader_rejects_is_left_alone():
    store = Qdrant()
    store.points["unparseable"] = ([0.0] * 32, {"metadata": {"tenant_id": "tenant-a"}})
    (receipt,) = retriever(store).ingest_documents(document("tenant-a", SHORT, revision=REV2))
    assert receipt.chunks_withdrawn == 0
    assert "unparseable" in store.points


@pytest.mark.parametrize("tenant", [pq.GLOBAL_REFERENCE_TENANT, pq.SEED_QUARANTINE_TENANT])
def test_reference_corpus_is_never_withdrawn_even_by_its_own_ingest(tenant):
    r = retriever()
    old = document(tenant, LONG, revision=REV1)
    r.ingest(old)
    new = document(tenant, SHORT, revision=REV2)
    (receipt,) = r.ingest_documents(new)
    assert receipt.chunks_withdrawn == 0
    assert r.qdrant.stored(tenant) == ids(old) | ids(new)
    assert "/delete" not in r.qdrant.writes()


@pytest.mark.parametrize(
    "tenant", [pq.GLOBAL_REFERENCE_TENANT, pq.SEED_QUARANTINE_TENANT, "", "  "]
)
def test_client_refuses_to_withdraw_reserved_or_missing_tenant(tenant):
    store, kept = seeded_store()
    with pytest.raises(ValueError):
        store.withdraw_document_points(
            tenant_id=tenant, document_id="shared-document-id", keep_point_ids=set()
        )
    assert store.requests == [("PUT", "/upsert")] * 3
    assert all(store.stored(t) == chunk_ids for t, chunk_ids in kept.items())


def test_client_refuses_to_withdraw_without_a_document():
    store, _kept = seeded_store()
    with pytest.raises(ValueError):
        store.withdraw_document_points(tenant_id="tenant-b", document_id="", keep_point_ids=set())
    assert len(store.points) == 9


# ── Refusals: a batch that cannot replace a document writes nothing ──────────────────────


def _mixed():
    return [
        document("tenant-a", SHORT, revision=REV1)[0],
        document("tenant-a", SHORT, revision=REV2)[1],
    ]


def _missing_index():
    return document("tenant-a", LONG, revision=REV2)[:2]


def _duplicate_index():
    chunks = document("tenant-a", SHORT, revision=REV2)
    return [chunks[0], chunks[0]]


def _total_disagrees():
    return [
        document("tenant-a", SHORT, revision=REV2)[0],
        document("tenant-a", LONG, revision=REV2)[1],
    ]


def _index_out_of_range():
    chunk = document("tenant-a", LONG, revision=REV2)[2]
    return [chunk]


@pytest.mark.parametrize(
    "batch,code",
    [
        (_mixed, "MIXED_DOCUMENT_REVISION"),
        (_missing_index, "INCOMPLETE_DOCUMENT_REVISION"),
        (_duplicate_index, "INCOMPLETE_DOCUMENT_REVISION"),
        (_total_disagrees, "INCOMPLETE_DOCUMENT_REVISION"),
        (_index_out_of_range, "INCOMPLETE_DOCUMENT_REVISION"),
    ],
)
def test_batch_that_is_not_one_complete_revision_is_refused_before_any_write(batch, code):
    r = retriever()
    live = document("tenant-a", LONG, revision=REV1)
    r.ingest(live)
    before = list(r.qdrant.requests)
    with pytest.raises(pq.DocumentRevisionError) as exc:
        r.ingest_documents(batch())
    assert exc.value.code == code
    assert r.qdrant.requests == before  # nothing embedded into the store, nothing withdrawn
    assert r.qdrant.stored("tenant-a") == ids(live)
    assert len(r.bm25) == len(live)


def test_one_refused_document_refuses_the_whole_batch():
    r = retriever()
    good = document("tenant-a", ["a complete other document"], revision=REV1, name="other.txt")
    with pytest.raises(pq.DocumentRevisionError):
        r.ingest_documents([*good, *_missing_index()])
    assert r.qdrant.requests == []


def test_failed_withdrawal_raises_and_issues_no_receipt():
    r = retriever()
    r.ingest(document("tenant-a", LONG, revision=REV1))
    r.qdrant.fail_delete = True
    with pytest.raises(pq.QdrantHTTPError):
        r.ingest_documents(document("tenant-a", SHORT, revision=REV2))
    # Retrying the same revision once the store answers converges on one revision.
    r.qdrant.fail_delete = False
    new = document("tenant-a", SHORT, revision=REV2)
    (receipt,) = r.ingest_documents(new)
    assert receipt.chunks_withdrawn == 3
    assert r.qdrant.stored("tenant-a") == ids(new)


def test_versioned_collection_stays_immutable():
    r = retriever()
    r.retrieval_profile = object()
    with pytest.raises(pq.RetrievalAdmissionError, match="immutable"):
        r.ingest_documents(document("tenant-a", SHORT, revision=REV2))
    assert r.qdrant.requests == []


# ── The service answer (POST /v1/ingest) ─────────────────────────────────────────────────


@pytest.fixture
def rag():
    module = load_service_main(
        str(ROOT / "services/rag-retrieval"), required_attrs=("_ingest_blocking", "ingest")
    )
    module._retriever = pq.HybridQdrantRetriever(Qdrant(), pq.HashEmbeddingProvider(32))
    module._sparse_ready = True
    return module


def wire(rag, chunks):
    return rag.IngestRequest(
        chunks=[
            {
                "chunk_id": c.chunk_id,
                "tenant_id": c.tenant_id,
                "text": c.text,
                "source_type": c.source_type,
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "total_chunks": c.total_chunks,
                "metadata": {
                    k: v for k, v in c.metadata.items() if k in {"source_uri", "source_revision"}
                },
            }
            for c in chunks
        ]
    )


def post(rag, chunks, tenant="tenant-a"):
    return asyncio.run(rag.ingest(wire(rag, chunks), x_tenant_id=tenant, _token=None))


def test_service_ingest_answers_with_receipts_and_keeps_the_total_the_uploader_checks(rag):
    old = document("tenant-a", LONG, revision=REV1)
    assert post(rag, old)["receipts"][0]["chunks_withdrawn"] == 0
    rag._sparse_ready = True
    out = post(rag, document("tenant-a", SHORT, revision=REV2))
    assert out == {
        "ingested": 2,
        "receipts": [
            {
                "tenant_id": "tenant-a",
                "document_id": old[0].document_id,
                "revision": REV2,
                "chunks_written": 2,
                "chunks_withdrawn": 3,
            }
        ],
    }
    assert rag._sparse_ready is False  # the next read rebuilds from the store


def test_service_refuses_an_incomplete_revision_with_422_and_writes_nothing(rag):
    with pytest.raises(rag.HTTPException) as exc:
        post(rag, _missing_index())
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "INCOMPLETE_DOCUMENT_REVISION"
    assert rag._retriever.qdrant.requests == []


def test_service_cannot_withdraw_for_a_tenant_the_gateway_did_not_name(rag):
    store = rag._retriever.qdrant
    theirs = document("tenant-b", LONG, revision=REV1)
    store.upsert(theirs, [[0.0] * 32 for _ in theirs])
    with pytest.raises(rag.HTTPException) as exc:
        post(rag, document("tenant-b", SHORT, revision=REV2), tenant="tenant-a")
    assert exc.value.status_code == 403
    assert store.stored("tenant-b") == ids(theirs)


def test_service_reports_a_failed_withdrawal_and_drops_its_local_index(rag):
    post(rag, document("tenant-a", LONG, revision=REV1))
    rag._sparse_ready = True
    rag._retriever.qdrant.fail_delete = True
    with pytest.raises(rag.HTTPException) as exc:
        post(rag, document("tenant-a", SHORT, revision=REV2))
    assert exc.value.status_code == 502
    assert rag._sparse_ready is False


# ── Review finding on #1582: two replicas publishing at once ─────────────────────────────


@pytest.mark.parametrize("first_withdraws", ["earlier", "later"])
def test_two_replicas_publishing_revisions_at_once_never_erase_both(monkeypatch, first_withdraws):
    """Production runs two retrieval replicas on one collection, and the ingest lock is per
    process. Both writes can land before either withdrawal scans; a withdrawal that keeps
    only its own ids then deletes the other replica's revision, and the two together leave
    nothing searchable while both report success. With a publication stamp, a withdrawal
    removes only rows published before it, so the later revision always survives."""
    stamps = iter(range(1000, 2000))
    monkeypatch.setattr(pq, "_publication_stamp", lambda: next(stamps))
    store = Qdrant()
    deferred = []
    real_withdraw = store.withdraw_document_points

    def defer(**kwargs):
        deferred.append(kwargs)
        return []

    store.withdraw_document_points = defer
    early = document("tenant-a", ["first replica revision"], revision=REV1)
    late = document("tenant-a", ["second replica revision"], revision=REV2)
    retriever(store).ingest_documents(early)
    retriever(store).ingest_documents(late)
    assert len(deferred) == 2 and store.stored("tenant-a") == ids(early) | ids(late)

    order = deferred if first_withdraws == "earlier" else list(reversed(deferred))
    for call in order:
        real_withdraw(**call)
    assert store.stored("tenant-a") == ids(late), "the later revision must survive"


def test_rows_written_before_publication_stamps_are_withdrawn_as_older(monkeypatch):
    """Rows already in the store carry no stamp; they belong to an earlier publication."""
    store = Qdrant()
    old = document("tenant-a", LONG, revision=REV1)
    store.upsert(old, [pq.HashEmbeddingProvider(32).embed(c.text) for c in old])
    assert all(pq.PUBLICATION_STAMP_KEY not in p for _v, p in store.points.values())
    new = document("tenant-a", SHORT, revision=REV2)
    retriever(store).ingest_documents(new)
    assert store.stored("tenant-a") == ids(new)
