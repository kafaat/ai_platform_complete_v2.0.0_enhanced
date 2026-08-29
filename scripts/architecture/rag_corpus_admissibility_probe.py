#!/usr/bin/env python3
"""كاشفاتُ دَينٍ لمجموعة RAG — تُبلِغ ولا تحجب. ``RAG-CORPUS-MEASUREMENT-INTEGRITY-01``.

أربعُ خصائص مؤكَّدة بالزرع على الشيفرة القائمة، ولا واحدةَ منها مُصلَحةٌ هنا **بالقصد**:
إصلاحُ الترتيب قبل معرفة المجموعة التي نقيسها يُصلِح رقماً لا يُعرَف مصدره.

**ولماذا مِسبارٌ لا اختباراتٌ حمراء.** الطريقان المُغرِيان كلاهما يخلق ديناً:

* اختبارٌ يؤكّد الخاصّيّةَ الصحيحة ويُترَك أحمرَ ⇒ دَينٌ دائم في CI، ويتعلّم القارئ
  تجاهلَ الأحمر — وهو أسوأ من غياب الاختبار.
* اختبارٌ يؤكّد أنّ العطل **قائم** ⇒ يُثبِّت السلوك الخاطئ **عقداً**، فيصير الإصلاحُ
  المستقبليّ هو ما يكسر الجناح.

فالكاشفُ هنا يُختبَر على **عيّنةٍ اصطناعيّة**: يُثبَت أنّه يرى عيباً مزروعاً، وأنّه
يصمت على عيّنةٍ قانونيّة. فتبقى القدرةُ على كشف الدَّين محفوظةً قبل إصلاحه، ولا يصير
السلوكُ الخاطئ عقداً، ويبقى الجناح أخضر. والحالةُ القانونيّة في سجلّ الفجوات لا هنا.

الاستعمال::

    python3 scripts/architecture/rag_corpus_admissibility_probe.py            # تقرير
    python3 scripts/architecture/rag_corpus_admissibility_probe.py --json     # آليّ
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
_PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"

FINDINGS = (
    "LEGACY_TENANT_ROOT_ONLY",
    "BM25_CROSS_TENANT_STAT_INFLUENCE",
    "NEIGHBOR_FILTER_BYPASS",
    "STORAGE_ID_USED_AS_LOGICAL_ID",
)


def load_module():
    spec = importlib.util.spec_from_file_location("rag_probe_pq", _PQ)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rag_probe_pq"] = module
    spec.loader.exec_module(module)
    return module


def _chunk(m, cid: str, tenant: str, text: str, **extra):
    meta = {
        "source_uri": "sahool://probe",
        "source_revision": "r1",
        "publisher": "probe",
        "license": "probe",
        "jurisdiction": "YE",
        "language": "ar",
        "evidence_level": "document",
    }
    meta.update(extra)
    return m.KnowledgeChunk(
        chunk_id=cid,
        tenant_id=tenant,
        text=text,
        source_type="reference_document",
        document_id=extra.get("document_id", f"doc-{cid}"),
        chunk_index=extra.get("chunk_index", 0),
        total_chunks=2,
        metadata=meta,
    )


# ── ① مُدخَلٌ قديم: مرئيٌّ للمتناثر، غيرُ مرئيٍّ للكثيف ────────────────────────
def detect_legacy_tenant_root_only(m) -> dict:
    """المستأجِرُ في جذر الـpayload وحده ⇒ يقبله المحلّل ويعميه مرشّحُ Qdrant.

    ``from_payload`` يقرأ ``metadata.tenant_id`` **أو** ``payload.tenant_id``، بينما
    البحث الكثيف يرشّح على ``metadata.tenant_id`` حصراً. فالنقطة تدخل BM25 وتظهر
    للمستأجِر متناثرةً، ولا تظهر له كثيفةً أبداً — وهو تفسيرٌ بنيويّ لاختلاف
    المسارين، لا مسألةَ تسجيلِ درجات.
    """
    payload = {
        "page_content": "wheat guidance",
        "tenant_id": "tenant-a",
        "chunk_id": "L1",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": {
            "source_uri": "sahool://x",
            "source_revision": "r1",
            "publisher": "p",
            "license": "l",
            "jurisdiction": "YE",
            "language": "ar",
            "evidence_level": "document",
        },
    }
    chunk = m.KnowledgeChunk.from_payload(payload, fallback_id="uuid-1")
    sparse_visible = bool(chunk.tenant_id)
    dense_visible = chunk.metadata.get("tenant_id") is not None
    return {
        "finding": "LEGACY_TENANT_ROOT_ONLY",
        "present": sparse_visible and not dense_visible,
        "sparse_visible": sparse_visible,
        "dense_visible": dense_visible,
        "note": "قُبِل بمستأجِرٍ في الجذر بلا metadata.tenant_id",
    }


# ── ② إحصاءاتُ BM25 عابرةٌ للمستأجِرين ───────────────────────────────────────
def detect_bm25_cross_tenant_stats(m) -> dict:
    """مستندُ مستأجِرٍ آخر لا يظهر — **ولم يعد يحرّك ``idf``** لمن لا يراه.

    كان ``search`` يرشّح بالمستأجِر بينما ``score`` يقرأ ``n_docs`` و``doc_freq``
    و``avg_len`` **العالميّة** قبل أيّ عزل. لم يكن إفشاءَ محتوًى، لكنّه كان تأثيراً
    عابراً للمستأجِرين في الترتيب — ومُربِكاً مباشراً لأيّ قياس تكافؤ.

    وأُغلِق بـ``corpus_stats`` المقصورة على ``visible_scope``. **والكاشفُ لم يمت
    بذلك بل صار كاشفَ انحدار:** إعادةُ الإحصاء العالميّ تُعيد ``present=True``.

    ويُقاس الاتّجاهان معاً لأنّ الانحراف كان ذا اتّجاهين: مستنداتٌ تحمل المصطلح
    كانت تخفض الدرجة، ومستنداتٌ **لا تحمله** ترفعها عبر ``avg_len``. فالثباتُ
    المُبلَّغ يجب أن يصمد للاتّجاهين، لا لواحدٍ يُخفي الآخر.
    """
    base = _chunk(m, "a1", "tenant-a", "wheat irrigation schedule for wheat fields")

    alone = m.BM25Index()
    alone.rebuild([base])
    score_alone = alone.score("wheat", "a1", tenant_id="tenant-a")

    with_term = m.BM25Index()
    with_term.rebuild([base] + [_chunk(m, f"b{i}", "tenant-b", "wheat barley") for i in range(50)])
    score_with_term = with_term.score("wheat", "a1", tenant_id="tenant-a")

    without_term = m.BM25Index()
    without_term.rebuild(
        [base]
        + [_chunk(m, f"c{i}", "tenant-b", " ".join(["barley millet"] * 40)) for i in range(50)]
    )
    score_without_term = without_term.score("wheat", "a1", tenant_id="tenant-a")

    visible = without_term.search("wheat", tenant_id="tenant-a", limit=10)
    leaked = [c.chunk_id for c, _ in visible if c.tenant_id != "tenant-a"]

    return {
        "finding": "BM25_CROSS_TENANT_STAT_INFLUENCE",
        "present": score_with_term != score_alone or score_without_term != score_alone,
        "score_tenant_a_alone": round(score_alone, 6),
        "score_after_other_tenant_shares_term": round(score_with_term, 6),
        "score_after_other_tenant_unrelated_long_docs": round(score_without_term, 6),
        "content_leaked_across_tenants": leaked,
        "note": "إحصاءُ الترتيب مقصورٌ على المجموعة المرئيّة؛ ولا إفشاءَ محتوًى",
    }


# ── ③ توسيعُ الجيران يتجاوز المرشِّحات ────────────────────────────────────────
def detect_neighbor_filter_bypass(m) -> dict:
    """الجارُ كان يدخل بالمستند والترتيب — **والآن يمرّ بمرشِّحات النطاق**.

    وحدُّه مقيسٌ ولم يتبدّل: ``by_doc_idx`` مفتاحُه يحمل ``tenant_id``، **فعزلُ
    المستأجِر كان محفوظاً ولا يزال**. المتجاوَزُ كان مرشِّحاتِ النطاق وحدها — عطلَ
    دقّةٍ لا خرقَ عزل، وتصنيفُه خرقاً كان سيرفعه فوق أولويّته.

    وأُغلِق بتمرير ``filters`` إلى ``_expand_neighbors`` وتطبيقِها بـ
    ``matches_scope_filters`` — **التعريفُ نفسُه** الذي يرشّح به المتناثر، لا نسخةٌ
    ثانية تنحرف. **والكاشفُ صار كاشفَ انحدار:** نزعُ التمرير يُعيد ``present=True``.
    """
    hit = _chunk(
        m, "h", "tenant-a", "wheat text", document_id="doc-1", chunk_index=0, field_id="F1"
    )
    neighbor = _chunk(
        m, "n", "tenant-a", "other text", document_id="doc-1", chunk_index=1, field_id="F2"
    )
    retriever = m.HybridQdrantRetriever.__new__(m.HybridQdrantRetriever)
    retriever._chunks = {"h": hit, "n": neighbor}
    rows = retriever._expand_neighbors(
        [m.RetrievedAnnotation(hit, 1.0, 0.0, 1.0)], filters={"field_id": "F1"}
    )
    off_scope = [r.chunk.chunk_id for r in rows if r.chunk.metadata.get("field_id") != "F1"]
    cross_tenant = [r.chunk.chunk_id for r in rows if r.chunk.tenant_id != "tenant-a"]
    return {
        "finding": "NEIGHBOR_FILTER_BYPASS",
        "present": bool(off_scope),
        "off_scope_chunks": off_scope,
        "cross_tenant_chunks": cross_tenant,
        "note": "الجارُ يمرّ بمرشِّحات النطاق؛ وعزلُ المستأجِر محفوظ",
    }


# ── ④ مُعرِّفُ التخزين يصير هويّةً منطقيّة ───────────────────────────────────
def detect_storage_id_as_logical_id(m) -> dict:
    """الاستعارةُ قائمةٌ بالقصد — **والمقيسُ هنا أنّها مُعلَنة لا صامتة**.

    كان التوثيقُ يقول إنّ مُعرِّفَ التخزين «لا يُسمَح» أن يصير هويّةَ استرجاع
    والكودُ يسمح — **وثيقةٌ تصف ما لا يفعله الكود**. وأُغلِق العطلُ بإعلان
    الاستعارة في ``metadata["chunk_id_source"]`` لا بنزعِ الارتداد:
    ``canonical_storage_shape`` يرفض الصفَّ المستعير أصلاً (يمرّر ``fallback_id=None``)،
    والسِّعةُ هنا للهجرة والتدقيق.

    **فالكاشفُ يقيس الصمتَ لا الاستعارة:** هويّةٌ مُستعارةٌ **بلا إعلان** ⇒ ``present``.
    ونزعُ سطر الإعلان يُعيدها ``True`` — كاشفُ انحدارٍ لا شاهدُ عطلٍ قائم.
    """
    payload = {
        "page_content": "wheat guidance",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": {
            "tenant_id": "tenant-a",
            "source_uri": "sahool://x",
            "source_revision": "r1",
            "publisher": "p",
            "license": "l",
            "jurisdiction": "YE",
            "language": "ar",
            "evidence_level": "document",
        },
    }
    chunk = m.KnowledgeChunk.from_payload(payload, fallback_id="storage-uuid-42")
    borrowed = chunk.chunk_id == "storage-uuid-42"
    declared = chunk.metadata.get("chunk_id_source") == "storage_fallback"
    return {
        "finding": "STORAGE_ID_USED_AS_LOGICAL_ID",
        "present": borrowed and not declared,
        "resolved_chunk_id": chunk.chunk_id,
        "chunk_id_source": chunk.metadata.get("chunk_id_source"),
        "borrowed": borrowed,
        "declared": declared,
        "note": "الاستعارةُ مُعلَنةٌ في chunk_id_source؛ والشكلُ القانونيّ يرفضها",
    }


# ── العيّناتُ القانونيّة: الجانبُ الصامت من العقد ────────────────────────────
#
# كاشفٌ يقول «موجود» دائماً يُخضِر تقريراً بلا معلومة. فلكلّ كاشفٍ عيّنةٌ قانونيّة
# **تمرّ من الكاشف نفسه** — لا من بدائله. وأمسك مراجعٌ آليّ على #882 أنّ اختبارات
# الجانب الصامت كانت تقيس البدائل (`from_payload` · `BM25Index` · `_expand_neighbors`)
# ولا تستدعي الكاشف قطّ: فكاشفٌ يعود `present=True` أبداً كان يمرّ عليها كلّها.


def _canonical_payload() -> dict:
    return {
        "page_content": "wheat guidance",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": {
            "tenant_id": "tenant-a",
            "chunk_id": "C1",
            "source_uri": "sahool://x",
            "source_revision": "r1",
            "publisher": "p",
            "license": "l",
            "jurisdiction": "YE",
            "language": "ar",
            "evidence_level": "document",
        },
    }


def detect_legacy_tenant_root_only_on(m, payload: dict) -> dict:
    chunk = m.KnowledgeChunk.from_payload(payload, fallback_id="uuid-1")
    dense_visible = chunk.metadata.get("tenant_id") is not None
    return {
        "finding": "LEGACY_TENANT_ROOT_ONLY",
        "present": bool(chunk.tenant_id) and not dense_visible,
        "dense_visible": dense_visible,
    }


def detect_bm25_cross_tenant_stats_on(m, corpus: list) -> dict:
    """يقيس أثرَ **مستأجِرٍ آخر** وحده: يُبنى مؤشّران بمستأجِر A نفسه ومن دون سواه."""
    own = [c for c in corpus if c.tenant_id == "tenant-a"]
    isolated, mixed = m.BM25Index(), m.BM25Index()
    isolated.rebuild(own)
    mixed.rebuild(corpus)
    target = own[0].chunk_id
    return {
        "finding": "BM25_CROSS_TENANT_STAT_INFLUENCE",
        "present": isolated.score("wheat", target, tenant_id="tenant-a")
        != mixed.score("wheat", target, tenant_id="tenant-a"),
    }


def detect_neighbor_filter_bypass_on(m, hit, neighbour, scope_key: str) -> dict:
    retriever = m.HybridQdrantRetriever.__new__(m.HybridQdrantRetriever)
    retriever._chunks = {hit.chunk_id: hit, neighbour.chunk_id: neighbour}
    want = hit.metadata.get(scope_key)
    rows = retriever._expand_neighbors(
        [m.RetrievedAnnotation(hit, 1.0, 0.0, 1.0)], filters={scope_key: want}
    )
    off = [r.chunk.chunk_id for r in rows if r.chunk.metadata.get(scope_key) != want]
    return {"finding": "NEIGHBOR_FILTER_BYPASS", "present": bool(off), "off_scope_chunks": off}


def detect_storage_id_as_logical_id_on(m, payload: dict, fallback_id: str) -> dict:
    chunk = m.KnowledgeChunk.from_payload(payload, fallback_id=fallback_id)
    borrowed = chunk.chunk_id == fallback_id
    declared = chunk.metadata.get("chunk_id_source") == "storage_fallback"
    return {
        "finding": "STORAGE_ID_USED_AS_LOGICAL_ID",
        "present": borrowed and not declared,
        "resolved_chunk_id": chunk.chunk_id,
        "chunk_id_source": chunk.metadata.get("chunk_id_source"),
        "borrowed": borrowed,
    }


DETECTORS = (
    detect_legacy_tenant_root_only,
    detect_bm25_cross_tenant_stats,
    detect_neighbor_filter_bypass,
    detect_storage_id_as_logical_id,
)


def run() -> dict:
    module = load_module()
    results = [detector(module) for detector in DETECTORS]
    return {
        "schema": "sahool.rag-corpus-admissibility-probe/v1",
        "gap": "RAG-CORPUS-MEASUREMENT-INTEGRITY-01",
        "blocking": False,
        "findings": results,
        "open_findings": sorted(r["finding"] for r in results if r["present"]),
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = run()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("مِسبارُ قبول مجموعة RAG — تشخيصٌ لا حجب\n")
    for row in report["findings"]:
        mark = "🔴" if row["present"] else "✓"
        print(f"  {mark} {row['finding']}")
        print(f"      {row['note']}")
    print(f"\n  دَينٌ مفتوح: {len(report['open_findings'])} من {len(DETECTORS)}")
    print("  الحالةُ القانونيّة في sahool-brain/gaps/registry.md — لا في رمز خروج هذا المِسبار.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
