"""R-H14: مُعرِّف نقطة Qdrant مشتقٌّ من (مستأجِر أو المرجع العامّ، chunk_id) لا chunk_id وحده.

كان ``canonical_storage_point_id`` دالّةً في ``chunk_id`` وحده، و``PUT points`` على Qdrant
استبدال: فكاتبٌ لمستأجِرٍ يحمل ``chunk_id="seed:1"`` كتب فوق نقطة المرجع العامّ ``seed:1``
وفوق وثائق مستأجِرٍ آخر بالمعرّف نفسه. العقد:
  • كتابةُ مستأجِر لا تصطدم بنقطةٍ عامّة ولا بنقطة مستأجِرٍ آخر للـchunk_id نفسه.
  • نقاطُ المرجع العامّ (والحجر) تبقى على المُعرِّف التاريخيّ — البذرُ idempotent.
  • الاشتقاقُ حتميّ.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _pq():
    spec = importlib.util.spec_from_file_location("test_rag_rh14_pq", PQ)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _chunk(pq, tenant: str, chunk_id: str = "seed:1"):
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
        text=f"text for {tenant}",
        source_type="uploaded_document",
        document_id=f"doc-{chunk_id}",
        chunk_index=0,
        total_chunks=1,
        metadata=meta,
    )


def _written_ids(pq, chunks) -> list[str]:
    class Client(pq.QdrantHttpClient):
        def __init__(self):
            super().__init__("http://qdrant", "c", vector_size=2)
            self.bodies: list[dict] = []

        def _request(self, method, path, payload=None):
            self.bodies.append(payload)
            return {}

    client = Client()
    client.upsert(chunks, [[0.1, 0.2] for _ in chunks])
    return [p["id"] for p in client.bodies[-1]["points"]]


def test_tenant_write_cannot_overwrite_the_public_seed_point():
    pq = _pq()
    public_id, tenant_id = _written_ids(
        pq, [_chunk(pq, pq.GLOBAL_REFERENCE_TENANT), _chunk(pq, "tenant-a")]
    )
    assert public_id != tenant_id


def test_two_tenants_with_the_same_chunk_id_get_distinct_points():
    pq = _pq()
    a, b = _written_ids(pq, [_chunk(pq, "tenant-a"), _chunk(pq, "tenant-b")])
    assert a != b


def test_public_seed_point_id_is_unchanged_for_idempotent_seeding():
    pq = _pq()
    (public_id,) = _written_ids(pq, [_chunk(pq, pq.GLOBAL_REFERENCE_TENANT)])
    # نفس صيغة services/qdrant-seed/seed.py — نقاطٌ مبذورة سلفاً لا تُيتَّم.
    assert public_id == str(uuid.uuid5(uuid.NAMESPACE_URL, "sahool-rag:seed:1"))


def test_tenant_point_id_is_deterministic():
    pq = _pq()
    first = pq.canonical_storage_point_id("seed:1", tenant_id="tenant-a")
    assert first == pq.canonical_storage_point_id("seed:1", tenant_id="tenant-a")
    assert first == _written_ids(pq, [_chunk(pq, "tenant-a")])[0]


def test_tenant_and_chunk_boundaries_are_unambiguous():
    pq = _pq()
    # بلا بادئة الطول: "a:b" + "c" و"a" + "b:c" كانا سيعطيان الاسم نفسه "a:b:c".
    assert pq.canonical_storage_point_id("c", tenant_id="a:b") != pq.canonical_storage_point_id(
        "b:c", tenant_id="a"
    )


def test_sparse_candidate_never_resolves_to_another_tenants_text():
    """بعد فصل النقاط: ``chunk_id`` نفسه لـA وB — مرشَّح B المتناثر لا يُحَلّ إلى نصّ A.

    ``self._chunks`` مفهرسٌ بـ``chunk_id`` وحده ويكتبه استرجاعُ A الكثيف؛ فحلُّ مرشَّحي B
    منه كان يُعيد نصّ A. (حارس انحدار للمسار الذي يفتحه الإصلاح: على main كانت نقطة A
    نفسُها تُكتَب فوقها فلا يصل استرجاعُ A إليها.)
    """
    pq = _pq()

    class Qdrant(pq.QdrantHttpClient):
        def __init__(self):
            super().__init__("http://qdrant", "c", vector_size=32)
            self.points: dict[str, dict] = {}
            self.dense_for: set[str] = set()

        def ensure_collection(self, *, vector_size=None):
            return None

        def _request(self, method, path, payload=None):
            for point in (payload or {}).get("points", []):
                self.points[point["id"]] = point["payload"]
            return {}

        def search(self, vector, *, tenant_id, filters=None, limit=12):
            if tenant_id not in self.dense_for:
                return []
            return [
                (pid, 1.0, payload)
                for pid, payload in self.points.items()
                if payload["metadata"]["tenant_id"] in {tenant_id, pq.GLOBAL_REFERENCE_TENANT}
            ]

    def chunk(tenant, text):
        c = _chunk(pq, tenant, "c1")
        return pq.KnowledgeChunk(
            chunk_id=c.chunk_id,
            tenant_id=c.tenant_id,
            text=text,
            source_type=c.source_type,
            document_id=c.document_id,
            chunk_index=0,
            total_chunks=1,
            metadata={k: v for k, v in c.metadata.items() if k != "content_digest"},
        )

    store = Qdrant()
    retriever = pq.HybridQdrantRetriever(store, pq.HashEmbeddingProvider(32))
    retriever.ingest([chunk("tenant-a", "alpha private wheat note")])
    retriever.ingest([chunk("tenant-b", "beta wheat note")])
    assert len(store.points) == 2  # لا كتابةَ فوق

    store.dense_for = {"tenant-a"}
    retriever.retrieve("wheat", tenant_id="tenant-a")  # يكتب نصّ A في الذاكرة المشتركة
    store.dense_for = set()
    hits = retriever.retrieve("wheat", tenant_id="tenant-b")
    assert hits, "B يجب أن يجد وثيقته عبر الفهرس المتناثر"
    assert all(h.chunk.tenant_id == "tenant-b" for h in hits)
    assert all("alpha" not in h.chunk.text for h in hits)
