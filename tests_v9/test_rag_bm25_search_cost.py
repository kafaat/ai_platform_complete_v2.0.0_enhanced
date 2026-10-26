"""كلفةُ ``BM25Index.search``: إحصاءُ المجموعة يُحسَب **مرّةً لكلّ بحث** لا لكلّ وثيقة.

كان ``search`` يستدعي ``score`` لكلّ وثيقةٍ مرئيّة، و``score`` يُعيد دمجَ
``doc_freq`` للمجموعة المرئيّة كلّها في كلّ استدعاء — فاستعلامٌ واحد على ٢٠٠٠
مقطع كلّف ~٦ ثوانٍ (``O(وثائق × مفردات)``). والإصلاحُ لا يُغيّر أيَّ درجة: يُقاس
هنا التطابقُ مع مرجعٍ مستقلّ ومع ``score`` نفسِها، ويُقاس عددُ مرّات الحساب.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _module():
    spec = importlib.util.spec_from_file_location("_bm25_cost_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_bm25_cost_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _chunk(chunk_id: str, tenant: str, text: str):
    meta = {}
    if tenant == m.GLOBAL_REFERENCE_TENANT:
        meta["source_class"] = "curated_reference"
    return m.KnowledgeChunk.from_payload(
        {
            "page_content": text,
            "source_type": "reference_document",
            "document_id": "d1",
            "metadata": {
                "tenant_id": tenant,
                "chunk_id": chunk_id,
                "source_uri": "sahool://x",
                "source_revision": "r1",
                "publisher": "p",
                "license": "l",
                "jurisdiction": "YE",
                "language": "ar",
                "evidence_level": "document",
                **meta,
            },
        },
        fallback_id=chunk_id,
    )


FIXTURE = [
    ("a1", "tenant-a", "wheat irrigation schedule for wheat fields"),
    ("a2", "tenant-a", "drip irrigation for date palms in hadramout"),
    ("a3", "tenant-a", "wheat rust symptoms and fungicide timing"),
    ("a4", "tenant-a", "قمح ري بالتنقيط في تهامة wheat"),
    ("g1", m.GLOBAL_REFERENCE_TENANT, "reference wheat yield tables irrigation"),
    ("g2", m.GLOBAL_REFERENCE_TENANT, "soil salinity and irrigation water quality"),
    ("b1", "tenant-b", "wheat wheat wheat irrigation barley"),
]


def _index():
    index = m.BM25Index()
    index.rebuild([_chunk(*row) for row in FIXTURE])
    return index


def _reference_scores(query: str, tenant_id: str) -> dict[str, float]:
    """BM25 مستقلّ مكتوبٌ من الصفر على المجموعة المرئيّة — لا يستعمل الفهرس."""
    visible = [row for row in FIXTURE if row[1] in {tenant_id, m.GLOBAL_REFERENCE_TENANT}]
    docs = {cid: m.tokenize(text) for cid, _, text in visible}
    n_docs = len(docs)
    avg_len = sum(len(t) for t in docs.values()) / n_docs
    df: dict[str, int] = {}
    for terms in docs.values():
        for term in set(terms):
            df[term] = df.get(term, 0) + 1
    k1, b = m.BM25Index().k1, m.BM25Index().b
    out: dict[str, float] = {}
    for cid, terms in docs.items():
        score = 0.0
        for term in m.tokenize(query):
            tf = terms.count(term)
            if tf == 0:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            denom = tf + k1 * (1 - b + b * (len(terms) or 1) / avg_len)
            score += idf * (tf * (k1 + 1) / denom)
        if round(score, 6) > 0:
            out[cid] = round(score, 6)
    return out


@pytest.mark.parametrize("query", ["wheat", "wheat irrigation", "قمح ري", "irrigation water"])
def test_search_scores_are_unchanged(query):
    index = _index()
    got = {chunk.chunk_id: score for chunk, score in index.search(query, tenant_id="tenant-a")}
    assert got, "عيّنةٌ بلا نتائج تُخضِر كلَّ تطابق"
    assert got == _reference_scores(query, "tenant-a")
    for cid, score in got.items():
        assert score == index.score(query, cid, tenant_id="tenant-a")


def test_corpus_stats_is_computed_once_per_search():
    index = _index()
    calls = 0
    real = index.corpus_stats

    def counting(tenant_id):
        nonlocal calls
        calls += 1
        return real(tenant_id)

    index.corpus_stats = counting  # type: ignore[method-assign]
    rows = index.search("wheat irrigation", tenant_id="tenant-a")
    assert len(rows) >= 3
    assert calls == 1, f"corpus_stats حُسِب {calls} مرّة لبحثٍ واحد"


def test_query_terms_are_capped():
    index = _index()
    cap = m.MAX_BM25_QUERY_TERMS
    assert 32 <= cap <= 1024
    capped = index.search("wheat " * cap, tenant_id="tenant-a")
    flooded = index.search("wheat " * (cap * 20), tenant_id="tenant-a")
    assert flooded == capped
    assert index.score("wheat " * (cap * 20), "a1", tenant_id="tenant-a") == index.score(
        "wheat " * cap, "a1", tenant_id="tenant-a"
    )
