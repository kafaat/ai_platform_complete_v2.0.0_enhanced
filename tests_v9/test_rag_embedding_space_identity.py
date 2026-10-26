"""توافقُ الأبعاد ليس توافقَ فضاء التضمين (REPORT3-RAG-05-01) — الشريحةُ غيرُ المتّصلة.

**العطل:** فحصُ التوافق الوحيد قبل الكتابة في ``qdrant-seed`` هو ``live_dim != dim``، وفحصُ
``/readyz`` في ``rag-retrieval`` يقارن طولَ المتّجه ببُعد المجموعة ثمّ يُعلن
``embedding_contract_parity: True``. مجموعةُ إعادة فهرسةٍ Nomic (``search_document:``، 768)
تمرّ بفحص البُعد مع متّجهاتٍ خامٍ من المُرمِّز القديم (768 أيضاً): فالبذرُ كان يخلط متّجهاتٍ
غيرَ متكافئة في مجموعةٍ مُبادَأة، و``/readyz`` لا يقول إنّ ما أثبته البُعدُ وحدَه.

**ما لا تغلقه هذه الشريحة:** ربطُ المسار الافتراضيّ (``sahool_agri_kb`` بلا profile) بـdigest
النموذج والبادئة والمراجعة، وإثباتُه بمسبار تكافؤٍ حيّ — يحتاج Qdrant/Ollama حيّين وقرارَ مالكٍ
بالتحويل أو إعادة الختم بعد قياسٍ عربيّ قبل/بعد. لا بادئةَ ولا بذرَ ولا سلطةَ استجابةٍ تغيّرت هنا.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "services" / "qdrant-seed" / "seed.py"
RAG_MAIN = ROOT / "services" / "rag-retrieval" / "main.py"
PRODUCTION_QDRANT = ROOT / "services" / "sahool-platform" / "core" / "rag" / "production_qdrant.py"

_PREFIXED = {"metadata": {"tenant_id": "t", "document_embedding_prefix": "search_document: "}}
_LEGACY = {"metadata": {"tenant_id": "__seed_quarantine__", "chunk_id": "seed:1"}}


# ── qdrant-seed: لا متّجهاتٌ خامٌ في مجموعةٍ مُبادَأة ────────────────────────────────────────


def _seed_module(monkeypatch, collection: str):
    monkeypatch.setenv("COLLECTION_NAME", collection)
    for name in (
        "QDRANT_SEED_TENANT_ID",
        "QDRANT_SEED_PROVENANCE_FILE",
        "QDRANT_SEED_PROVENANCE_JSON",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE", raising=False)
    monkeypatch.syspath_prepend(str(SEED.parent))
    spec = importlib.util.spec_from_file_location("_rag05_seed", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Info:
    def __init__(self, dim: int):
        self._dim = dim
        self.points_count = 0

    def model_dump(self):
        return {"config": {"params": {"vectors": {"size": self._dim, "distance": "Cosine"}}}}


class _FakeQdrant:
    """يكفي ما يستدعيه ``seed()`` — ويُسجّل كلَّ كتابة."""

    instances: list[_FakeQdrant] = []

    def __init__(self, payloads, **_kw):
        self.payloads = payloads
        self.upserts: list[int] = []
        _FakeQdrant.instances.append(self)

    async def collection_exists(self, _name):
        return True

    async def get_collection(self, _name):
        return _Info(768)

    async def scroll(self, collection_name, limit, with_payload, with_vectors, **_kw):
        assert with_payload is True and with_vectors is False
        rows = [types.SimpleNamespace(id=i, payload=p) for i, p in enumerate(self.payloads)]
        return rows[:limit], None

    async def upsert(self, collection_name, points):
        self.upserts.append(len(points))

    async def close(self):
        return None


def _wire_seed(monkeypatch, module, payloads):
    embeds: list[str] = []
    _FakeQdrant.instances = []

    async def _embed(text, _http):
        embeds.append(text)
        return [0.1] * 768

    monkeypatch.setattr(module, "_embed", _embed)
    monkeypatch.setattr(module, "AsyncQdrantClient", lambda **kw: _FakeQdrant(payloads, **kw))
    return embeds


def test_seed_refuses_a_reindex_collection_before_any_embedding_or_qdrant_io(monkeypatch):
    module = _seed_module(monkeypatch, "sahool_rag_reindex_nomic_v1")
    embeds = _wire_seed(monkeypatch, module, [])
    with pytest.raises(RuntimeError, match="QDRANT_ENCODING_PROFILE_MISMATCH"):
        asyncio.run(module.seed())
    assert embeds == []
    assert _FakeQdrant.instances == []


def test_seed_refuses_a_prefixed_collection_under_a_legacy_name(monkeypatch):
    """البُعدُ يطابق (768 = 768) — وهذا بالضبط ما كان يُمرِّر الكتابة. الـpayload يكشف الفضاء."""
    module = _seed_module(monkeypatch, "sahool_agri_kb")
    _wire_seed(monkeypatch, module, [_LEGACY, _PREFIXED])
    with pytest.raises(RuntimeError, match="QDRANT_ENCODING_PROFILE_MISMATCH"):
        asyncio.run(module.seed())
    assert _FakeQdrant.instances[0].upserts == []


def test_seed_still_writes_a_legacy_collection(monkeypatch):
    module = _seed_module(monkeypatch, "sahool_agri_kb")
    _wire_seed(monkeypatch, module, [_LEGACY])
    asyncio.run(module.seed())
    assert _FakeQdrant.instances[0].upserts and _FakeQdrant.instances[0].upserts[0] > 0


def test_seed_prefix_matches_the_canonical_retriever(monkeypatch):
    module = _seed_module(monkeypatch, "sahool_agri_kb")
    assert f'"{module.REINDEX_COLLECTION_PREFIX}"' in PRODUCTION_QDRANT.read_text(encoding="utf-8")


# ── rag-retrieval /readyz: يقول ما أثبته — البُعدُ وحدَه أم الـprofile المربوط ─────────────────


@pytest.fixture
def rag(monkeypatch):
    pytest.importorskip("fastapi")
    for path in (str(RAG_MAIN.parent), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.delenv("RAG_REINDEX_PROFILE_MANIFEST", raising=False)
    spec = importlib.util.spec_from_file_location("_rag05_rag_main", RAG_MAIN)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 — تبعيّاتٌ ناقصةٌ في بيئةٍ خفيفة
        pytest.skip("تعذّر استيراد rag-retrieval (تبعيّات ناقصة)")
    module._embedding_provider = types.SimpleNamespace(embed=lambda _t: [0.0] * 768)
    module._qdrant = types.SimpleNamespace(collection_vector_size=lambda: 768)
    monkeypatch.setattr(module, "_ensure_sparse_index", lambda: {"loaded_chunks": 3})
    return module


def test_readyz_says_a_legacy_collection_is_matched_by_dimension_only(rag):
    rag._profile = None
    body = asyncio.run(rag.readyz())
    assert body["status"] == "ready"
    assert body["embedding_space_identity"] == {"basis": "dimension_only"}
    # A matching dimension is not the embedding contract: no digest, prefix or revision
    # was shown, so parity must not be claimed (the live certification reads this key).
    assert body["embedding_contract_parity"] is False


def test_readyz_names_the_bound_profile_when_one_is_served(rag):
    rag._profile = types.SimpleNamespace(
        manifest={
            "retrieval_profile": "nomic-ar-seed-v1",
            "revision": "rev-7",
            "model_digest": "d" * 64,
            "target_collection": "sahool_rag_reindex_v1",
        }
    )
    body = asyncio.run(rag.readyz())
    assert body["embedding_space_identity"] == {
        "basis": "profile_bound",
        "retrieval_profile": "nomic-ar-seed-v1",
        "reindex_revision": "rev-7",
        "embedding_model_digest": "d" * 64,
    }
    # الحقلُ إضافيّ: المفاتيحُ التي تقرؤها الشهادةُ الحيّة لم تتغيّر.
    assert body["embedding_contract_parity"] is True
    assert body["collection_vector_schema_parity"] is True
