"""انحرافُ المجموعة حالةُ **جاهزيّة**، لا شرطُ تصفيةٍ لكلّ نتيجة — ``D09``.

**العطلُ الذي يُغلِقه هذا العقد ليس غيابَ حماية، بل حمايةً في الطبقة الخطأ.**

صياغةٌ أولى لـD09 رشّحت الصفوفَ واحداً واحداً: الكثيفُ يتخطّى ما ليس قانونيّاً،
والمتناثرُ يُرشَّح بمجموعة أهليّة. وذلك ينقل العطلَ من ``503`` صريحٍ إلى **``200``
بنتائجَ ناقصة لا يعرف المستهلكُ نقصَها** — إجابةٌ مبتورة تُقرَأ كاملة. والصياغةُ
الحاكمة المُعتمَدة:

    D09 removes row-level eligibility filtering from dense and sparse retrieval.
    Corpus drift is a service-level readiness failure, not a per-result filtering
    condition.

**والهويّةُ مركّبة لا عدد.** حارسٌ يقارن ``count == N`` يمرّ على تبدُّلِ المحتوى كلِّه
ما دام العددُ ثابتاً. فالاختبارُ الحاسم هنا **نفسُ العدد ونفسُ المُعرِّفات ومحتوًى
مختلف** — إن مرّ ذلك بينما يُمسَك الحذف، فما بُني حارسُ عدد لا حارسُ سلامة.

**وتُثبَّت اختباراتُ نزع السلوك بـ``ast`` على جسم التنفيذ**، لا بـ``grep`` على نصّ:
التعليقُ الشارح يذكر المِصفاةَ المنزوعة، ففحصٌ نصّيّ يحمرّ على شرحه لا على شيفرته —
وهو ``TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`` المسجَّل في هذا المستودع.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
MAIN = ROOT / "services/rag-retrieval/main.py"


def _pq(name: str = "d09_identity_pq"):
    spec = importlib.util.spec_from_file_location(name, PQ)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _payload(pq, chunk_id: str, tenant: str = "tenant-a", text: str = "wheat irrigation"):
    return pq.KnowledgeChunk(
        chunk_id=chunk_id,
        tenant_id=tenant,
        text=text,
        source_type="uploaded_document",
        document_id=f"doc-{chunk_id}",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": f"tenant-upload://{tenant}/{chunk_id}",
            "source_revision": "r1",
            "prescriptive_eligible": False,
        },
    ).payload


def _root_legacy(payload: dict) -> dict:
    """ارتدادٌ قديم: الهويّةُ في الجذر لا في ``metadata`` — يقبله المحلّل ولا يكون قانونيّاً."""
    out = {"page_content": payload["page_content"], "metadata": dict(payload["metadata"])}
    for key in ("chunk_id", "tenant_id", "source_type", "document_id"):
        out[key] = out["metadata"].pop(key)
    return out


def _retrieve_body() -> ast.FunctionDef:
    """جسمُ ``retrieve`` كما يُنفَّذ — لا نصُّ الملفّ ولا تعليقاته."""
    tree = ast.parse(PQ.read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HybridQdrantRetriever"
    )
    return next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == "retrieve")


# ── ① D09-C — المُسنَدُ حتميّ ومحلّيّ ────────────────────────────────────────


def test_canonical_shape_is_a_pure_local_predicate() -> None:
    """لا إيصالَ ولا أساس: جوابُه دالّةٌ في الـpayload وحده."""
    pq = _pq("d09_pure")
    canonical = _payload(pq, "c1")
    assert pq.canonical_storage_shape(canonical) is True
    assert pq.canonical_storage_shape(_root_legacy(canonical)) is False
    # نفسُ المُدخَل ⇒ نفسُ الجواب، مهما تكرّر.
    assert all(pq.canonical_storage_shape(canonical) for _ in range(3))


def test_the_second_parse_asks_a_different_question_and_is_not_redundant() -> None:
    """التحليلُ الثاني ليس تكراراً، فلا يُلغى «توفيراً».

    مراجعةٌ آليّة على #885 لاحظت أنّ كلّ صفٍّ يُحلَّل مرّتين في ``rebuild_sparse_index``:
    مرّةً في الحلقة بـ``fallback_id=point_id``، ومرّةً داخل المُسنَد بـ``fallback_id=None``.
    والملاحظةُ صحيحةٌ وصفاً، لكنّ علاجَها الضمنيّ — إعادةُ استعمال المقطع المُحلَّل —
    **انحدارُ صحّةٍ لا تسريع**: المُعرِّفُ المُستعار يمرّ عندئذٍ قانونيّاً.

    وهذا الاختبار يُثبِّت الفرق كي لا يُلغى التحليلُ الثاني في «تحسينٍ» لاحق.
    """
    pq = _pq("d09_fallback_semantics")
    borrowed = _payload(pq, "c-borrowed")
    # الهويّةُ المنطقيّة تُنزَع من الـpayload — كما في ارتدادٍ يعتمد على مُعرِّف التخزين.
    borrowed["metadata"].pop("chunk_id")

    # الحلقةُ تقبله: المُعرِّفُ يُستعار من نقطة التخزين.
    assert pq.KnowledgeChunk.from_payload(borrowed, fallback_id="POINT-1") is not None
    # والمُسنَدُ يرفضه: الشكلُ القانونيّ يحمل هويّتَه ولا يستعيرها.
    with pytest.raises((TypeError, ValueError)):
        pq.KnowledgeChunk.from_payload(borrowed, fallback_id=None)
    assert pq.canonical_storage_shape(borrowed) is False


def test_the_policy_predicate_reads_no_receipt_or_baseline() -> None:
    """اقترانُ «جردٌ حيّ ⇒ أهليّة ⇒ نتائج» ممنوعٌ بالبناء، ويُقاس هنا."""
    source = PQ.read_text(encoding="utf-8")
    for forbidden in ("corpus_audit_receipt", "rag_live_corpus_audit", "receipt_path"):
        assert forbidden not in source, (
            f"مُشغِّلُ الاسترجاع صار يقرأ `{forbidden}` — فتوفُّرُ قياسٍ حيّ يغيّر النتائج"
        )


# ── ② D09-M — الهويّةُ المركّبة تُمسِك ما لا يمسكه العدّ ─────────────────────


def test_deleting_one_point_drifts_the_identity() -> None:
    pq = _pq("d09_delete")
    rows = [(f"p{i}", _payload(pq, f"c{i}")) for i in range(3)]
    before, after = pq.corpus_identity(rows), pq.corpus_identity(rows[:-1])
    assert after["point_count"] == before["point_count"] - 1
    assert after["id_set_digest"] != before["id_set_digest"]


def test_same_count_same_ids_but_altered_content_still_drifts() -> None:
    """**الاختبارُ الحاسم.** إن مرّ هذا، فما بُني حارسُ عدد لا حارسُ سلامة."""
    pq = _pq("d09_content")
    rows = [(f"p{i}", _payload(pq, f"c{i}", text="wheat irrigation")) for i in range(3)]
    tampered = [(f"p{i}", _payload(pq, f"c{i}", text="barley schedule")) for i in range(3)]
    before, after = pq.corpus_identity(rows), pq.corpus_identity(tampered)

    assert after["point_count"] == before["point_count"], "العددُ ثابتٌ بالقصد"
    assert after["id_set_digest"] == before["id_set_digest"], "المُعرِّفاتُ ثابتةٌ بالقصد"
    assert after["content_digest"] != before["content_digest"], (
        "محتوًى مختلفٌ بعددٍ ومُعرِّفاتٍ ثابتة لم يُحرّك الهويّة — فهذا حارسُ عدد"
    )


def test_a_balanced_swap_keeps_the_count_but_drifts_the_id_set() -> None:
    """حذفُ واحدٍ وإضافةُ آخر يُبقي العدد — والمجموعةُ ليست هي."""
    pq = _pq("d09_swap")
    rows = [(f"p{i}", _payload(pq, f"c{i}")) for i in range(3)]
    swapped = rows[:-1] + [("p9", _payload(pq, "c9"))]
    before, after = pq.corpus_identity(rows), pq.corpus_identity(swapped)
    assert after["point_count"] == before["point_count"]
    assert after["id_set_digest"] != before["id_set_digest"]


def test_identity_never_emits_document_text() -> None:
    pq = _pq("d09_noleak")
    rendered = repr(pq.corpus_identity([("p0", _payload(pq, "c0", text="wheat secret plan"))]))
    assert "wheat secret plan" not in rendered


# ── ③ الاسترجاع لا يُصفّي الصفوف ────────────────────────────────────────────


def test_retrieval_serves_every_row_including_noncanonical_ones() -> None:
    """``READY`` ⇒ لا تصفية. الحمايةُ في الجاهزيّة لا في حذف النتائج."""
    pq = _pq("d09_nofilter")
    canonical = _payload(pq, "canonical")
    legacy = _root_legacy(_payload(pq, "legacy"))

    class Qdrant:
        vector_size = 32

        def scroll_payloads(self):
            return [("s-c", canonical), ("s-l", legacy)]

        def search(self, vector, *, tenant_id, filters=None, limit=12):
            return [("s-l", 0.99, legacy), ("s-c", 0.80, canonical)]

    retriever = pq.HybridQdrantRetriever(Qdrant(), pq.HashEmbeddingProvider(32))
    report = retriever.rebuild_sparse_index()
    assert report["noncanonical_serving_points"] == 1, "القياسُ يبقى — هو الدليل"

    served = {
        row.chunk.chunk_id for row in retriever.retrieve("wheat irrigation", tenant_id="tenant-a")
    }
    assert served == {"canonical", "legacy"}, (
        "أُسقِط صفٌّ من النتائج بصمت — وهذا `200` بنتائجَ ناقصة؛ الانحرافُ يُعالَج بـNOT_READY لا بالحذف"
    )


def test_the_executed_retrieve_body_carries_no_eligibility_filter() -> None:
    """يُقاس الغيابُ في **الشجر** لا في النصّ — فالتعليقُ يذكر المِصفاةَ المنزوعة."""
    body = _retrieve_body()

    for node in ast.walk(body):
        # `if not canonical_storage_shape(payload): continue`
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            call = node.operand
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                assert call.func.id != "canonical_storage_shape", (
                    "عادت مِصفاةُ الكثيف إلى جسم `retrieve` — إسقاطٌ صامت"
                )
        # `if chunk.chunk_id in self._serving_eligible_ids`
        if isinstance(node, ast.Attribute):
            assert node.attr != "_serving_eligible_ids", (
                "عادت مِصفاةُ المتناثر — نفسُ الإسقاط الصامت من الباب الآخر"
            )


def test_quarantine_is_declared_nonserving_not_counted_as_drift() -> None:
    """الحجرُ المُعلَن ليس انحرافاً — وإلّا مُنِعت الجاهزيّةُ بحالةٍ مقصودة."""
    pq = _pq("d09_quarantine")
    quarantined = _root_legacy(_payload(pq, "q1", tenant=pq.SEED_QUARANTINE_TENANT))

    class Qdrant:
        vector_size = 32

        def scroll_payloads(self):
            return [("s-q", quarantined), ("s-c", _payload(pq, "c1"))]

    report = pq.HybridQdrantRetriever(Qdrant(), pq.HashEmbeddingProvider(32)).rebuild_sparse_index()
    assert report["noncanonical_serving_points"] == 0


# ── ④ D09-E — الجاهزيّةُ هي البوّابة ────────────────────────────────────────


_HEALTHY = {
    "noncanonical_serving_points": 0,
    "corpus_identity": {"point_count": 3, "id_set_digest": "a" * 64, "content_digest": "b" * 64},
}


def test_a_healthy_corpus_is_ready() -> None:
    """الطرفُ الصامت: حكمٌ يقول ``NOT_READY`` أبداً لا يحرس شيئاً."""
    assert _pq("d09_ready").readiness_problems(_HEALTHY) == []


def test_readiness_fails_closed_on_active_noncanonical_rows() -> None:
    """يُستدعى الحكمُ بتقريرٍ مُختلَق — فتعطيلُه يُكذَّب بالسلوك لا بالنصّ."""
    pq = _pq("d09_notready")
    report = {**_HEALTHY, "noncanonical_serving_points": 2, "noncanonical_serving_samples": ["p1"]}
    problems = pq.readiness_problems(report)
    assert problems and "NOT_READY" in problems[0]
    assert "p1" in problems[0], "التشخيصُ يدخل الرسالة — رقمٌ بلا عيّنةٍ لا يُبنى عليه"


def test_readiness_refuses_an_unmeasured_identity() -> None:
    """غيابُ البصمة يعني «لم تُقَس»، لا «سليمة»."""
    pq = _pq("d09_nomeasure")
    for broken in ({**_HEALTHY, "corpus_identity": None}, {"noncanonical_serving_points": 0}):
        problems = pq.readiness_problems(broken)
        assert problems and "EVIDENCE_MISSING" in problems[0]


def test_readiness_refuses_an_empty_corpus_as_parity() -> None:
    """صفرٌ في كلّ عدّاد يجعل كلَّ شرطٍ «متحقّقاً» شكلاً — وهي حالةُ لا-دليل."""
    pq = _pq("d09_empty")
    empty = {
        "noncanonical_serving_points": 0,
        "corpus_identity": {
            "point_count": 0,
            "id_set_digest": "c" * 64,
            "content_digest": "d" * 64,
        },
    }
    problems = pq.readiness_problems(empty)
    assert problems and "empty parity is not parity" in problems[0]


def test_the_readiness_path_consumes_the_single_verdict() -> None:
    """سلطةٌ واحدة للحكم: نسخُه في المسار يُعيد إمكانَ انحراف النسختين."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_ensure_sparse_index"
    )
    calls = [
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "readiness_problems" in calls, "مسارُ الجاهزيّة لم يعد يستدعي الحكمَ القانونيّ"
