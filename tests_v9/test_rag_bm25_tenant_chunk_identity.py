"""هويّةُ الفهرس المتناثر وذاكرة المقاطع: (مستأجِر، chunk_id) لا chunk_id وحده.

بعد R-H14 صارت هويّةُ التخزين في Qdrant ``(tenant_id, chunk_id)``، فلمستأجِرَين أن
يملك كلٌّ منهما مقطعاً بالـ``chunk_id`` المنطقيّ نفسه. لكنّ الطبقة الداخليّة بقيت
مفهرسةً بـ``chunk_id`` وحده:

* ``rebuild_sparse_index`` كان يرفض ``duplicate canonical chunk_id`` حين يتشارك
  مستأجِران المعرّف، فيسقط البناء وتعود ``/readyz`` والبحث 503 **لكلّ** مستأجِر.
* ``BM25Index`` كان يُفهرس بـ``chunk_id``: ابتلاعُ B للمقطع ``x`` يسحب مقطع A ``x``
  ويستبدله، فتخسر نتائجُ A المتناثرة وثيقتَها بصمت وتتغيّر إحصاءاتُ دلوِه.

العقد المُختبَر هنا:
  • مستأجِران بالـchunk_id نفسه: البناء ينجح وكلٌّ يسترجع نصّه وحده.
  • ابتلاعُ B لا يمسّ مقطع A ولا إحصاءاته.
  • التكرارُ الحقيقيّ (المستأجِر نفسه والـchunk_id نفسه في نقطتين) يبقى مرفوضاً.
  • التعليقاتُ المُعادة تحمل ``chunk_id`` المنطقيّ نصّاً كما هو.
  • مقطعُ المستأجِر ومقطعُ المرجع العامّ بالمعرّف نفسه مرشَّحان منفصلان في الدمج.

شهودُ وحدةٍ على مخزنٍ في الذاكرة؛ لا ادّعاءَ لاسترجاعٍ حيّ ولا Qdrant منشورة.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _pq():
    spec = importlib.util.spec_from_file_location("test_rag_bm25_tenant_identity_pq", PQ)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pq = _pq()


def _chunk(tenant: str, text: str, chunk_id: str = "x"):
    meta = {
        "evidence_level": "document",
        "source_uri": f"fixture://{tenant}/{chunk_id}",
        "source_revision": "r1",
        "prescriptive_eligible": False,
    }
    if tenant == pq.GLOBAL_REFERENCE_TENANT:
        meta.update(publisher="fixture", license="CC-BY-4.0", source_class="curated_reference")
    return pq.KnowledgeChunk(
        chunk_id=chunk_id,
        tenant_id=tenant,
        text=text,
        source_type="uploaded_document",
        document_id=f"doc-{tenant}-{chunk_id}",
        chunk_index=0,
        total_chunks=1,
        metadata=meta,
    )


class _Qdrant(pq.QdrantHttpClient):
    """مخزنٌ في الذاكرة يعيد الكتابة كـQdrant (PUT استبدال) ويرشّح الكثيف بالمستأجِر."""

    def __init__(self) -> None:
        super().__init__("http://qdrant", "c", vector_size=32)
        self.points: dict[str, dict] = {}
        self.extra_rows: list[tuple[str, dict]] = []

    def ensure_collection(self, *, vector_size=None):
        return None

    def _request(self, method, path, payload=None):
        for point in (payload or {}).get("points", []):
            self.points[point["id"]] = point["payload"]
        return {}

    def scroll_payloads(self, *args, **kwargs):
        return [*self.points.items(), *self.extra_rows]

    def search(self, vector, *, tenant_id, filters=None, limit=12):
        return [
            (pid, 1.0, payload)
            for pid, payload in self.points.items()
            if payload["metadata"]["tenant_id"] in {tenant_id, pq.GLOBAL_REFERENCE_TENANT}
        ]


def _store_with(*chunks):
    store = _Qdrant()
    store.upsert(list(chunks), [[0.0] * 32 for _ in chunks])
    return store


def test_two_tenants_sharing_a_chunk_id_rebuild_and_each_retrieve_only_their_own_text():
    store = _store_with(
        _chunk("tenant-a", "alpha private wheat note"),
        _chunk("tenant-b", "beta private wheat note"),
    )
    assert len(store.points) == 2  # R-H14: نقطتان لا كتابةَ فوق

    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    report = retriever.rebuild_sparse_index()

    assert report["loaded_chunks"] == 2
    assert report["serving_chunks_by_tenant"] == {"tenant-a": 1, "tenant-b": 1}
    for tenant, own, other in (("tenant-a", "alpha", "beta"), ("tenant-b", "beta", "alpha")):
        hits = retriever.retrieve("wheat", tenant_id=tenant)
        assert hits, f"{tenant} يجب أن يجد وثيقته"
        assert all(h.chunk.tenant_id == tenant for h in hits)
        assert all(own in h.chunk.text and other not in h.chunk.text for h in hits)
        sparse = retriever.bm25.search("wheat", tenant_id=tenant)
        assert [(c.tenant_id, c.chunk_id) for c, _ in sparse] == [(tenant, "x")]


def test_ingesting_tenant_b_chunk_does_not_retract_or_alter_tenant_a_chunk():
    store = _Qdrant()
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    retriever.ingest([_chunk("tenant-a", "alpha wheat salinity note")])

    stats_before = retriever.bm25.corpus_stats("tenant-a")
    sparse_before = retriever.bm25.search("wheat", tenant_id="tenant-a")
    score_before = retriever.bm25.score("wheat", "x", tenant_id="tenant-a")
    assert [(c.tenant_id, c.text) for c, _ in sparse_before] == [
        ("tenant-a", "alpha wheat salinity note")
    ]
    assert score_before > 0

    retriever.ingest([_chunk("tenant-b", "beta wheat irrigation schedule text")])

    assert retriever.bm25.corpus_stats("tenant-a") == stats_before
    assert retriever.bm25.search("wheat", tenant_id="tenant-a") == sparse_before
    assert retriever.bm25.score("wheat", "x", tenant_id="tenant-a") == score_before
    assert len(retriever.bm25) == 2
    b_rows = retriever.bm25.search("wheat", tenant_id="tenant-b")
    assert [(c.tenant_id, c.text) for c, _ in b_rows] == [
        ("tenant-b", "beta wheat irrigation schedule text")
    ]

    # إعادةُ ابتلاع المقطع نفسه للمستأجِر نفسه تبقى استبدالاً idempotent.
    retriever.ingest([_chunk("tenant-b", "beta wheat irrigation schedule text")])
    assert len(retriever.bm25) == 2
    assert retriever.bm25.corpus_stats("tenant-a") == stats_before


def test_same_tenant_same_chunk_id_at_two_points_still_fails_closed():
    first = _chunk("tenant-a", "alpha wheat note")
    second = _chunk("tenant-a", "alpha wheat note, second copy")
    store = _store_with(first)
    store.extra_rows = [("another-storage-point", second.payload)]

    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    with pytest.raises(ValueError, match="duplicate canonical chunk_id in Qdrant"):
        retriever.rebuild_sparse_index()


def test_annotations_carry_the_plain_logical_chunk_id():
    store = _store_with(
        _chunk("tenant-a", "alpha wheat note"),
        _chunk("tenant-b", "beta wheat note"),
    )
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    retriever.rebuild_sparse_index()
    for tenant in ("tenant-a", "tenant-b"):
        annotations = [h.as_annotation() for h in retriever.retrieve("wheat", tenant_id=tenant)]
        assert annotations
        assert all(a["chunk_id"] == "x" and type(a["chunk_id"]) is str for a in annotations)


def test_tenant_and_global_reference_chunks_with_one_chunk_id_stay_distinct_in_fusion():
    store = _store_with(
        _chunk("tenant-a", "alpha private wheat note"),
        _chunk(pq.GLOBAL_REFERENCE_TENANT, "public reference wheat guidance"),
    )
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    retriever.rebuild_sparse_index()

    hits = retriever.retrieve("wheat", tenant_id="tenant-a")
    by_tenant = {h.chunk.tenant_id: h for h in hits}
    assert set(by_tenant) == {"tenant-a", pq.GLOBAL_REFERENCE_TENANT}
    assert "alpha" in by_tenant["tenant-a"].chunk.text
    assert "public" in by_tenant[pq.GLOBAL_REFERENCE_TENANT].chunk.text
    for hit in hits:
        # كلُّ مرشَّح سُجِّل في الطرفين بهويّته هو، لا بهويّة شريكه في المعرّف.
        assert hit.dense_rank is not None and hit.bm25_rank is not None
        assert hit.as_annotation()["chunk_id"] == "x"

    # والمستأجِر B يرى المرجع العامّ وحده، لا مقطع A.
    b_hits = retriever.retrieve("wheat", tenant_id="tenant-b")
    assert [h.chunk.tenant_id for h in b_hits] == [pq.GLOBAL_REFERENCE_TENANT]


def test_global_seed_also_in_quarantine_still_fails_closed():
    """D08-EXT as narrowed by the owner (2026-11-13, hybrid): uniqueness is per tenant, but the
    global reference corpus and ``__seed_quarantine__`` are one domain, so the duplicated-seed
    incident the ruling was about (the same seed served globally and held in quarantine, at
    two storage points) still fails the rebuild."""
    served = _chunk(pq.GLOBAL_REFERENCE_TENANT, "public reference wheat guidance", "seed:1")
    held = _chunk(pq.SEED_QUARANTINE_TENANT, "public reference wheat guidance", "seed:1")
    store = _store_with(served)
    store.extra_rows = [("legacy-quarantine-point", held.payload)]
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    with pytest.raises(ValueError, match="duplicate canonical chunk_id in Qdrant"):
        retriever.rebuild_sparse_index()


def test_a_tenant_reusing_a_global_seed_id_does_not_take_the_corpus_down():
    store = _store_with(
        _chunk(pq.GLOBAL_REFERENCE_TENANT, "public reference wheat guidance", chunk_id="seed:1"),
        _chunk("tenant-a", "alpha private wheat note", chunk_id="seed:1"),
    )
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    report = retriever.rebuild_sparse_index()
    assert report["loaded_chunks"] == 2
