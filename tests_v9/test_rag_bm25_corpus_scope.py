"""`RAG-BM25-CROSS-TENANT-CORPUS-STATS-01` — الترتيبُ يُحسَب داخل المجموعة المرئيّة.

كان `search` يرشّح بالمستأجِر و`score` يقرأ `n_docs` و`doc_freq` و`avg_len`
**العالميّة**، فترتيبُ مستأجِرٍ دالّةٌ في محتوًى لا يراه. ولا إفشاءَ محتوًى فيه —
لكنّه يُبطِل أيّ قياسِ تكافؤ: الدرجةُ نفسُها تتبدّل بابتلاعِ مستأجِرٍ آخر لوثائقَ
لا صلةَ لها.

**والخطرُ الأوّل في اختبارِ هذا الإصلاح أنّه يصير خضرةً بلا معلومة.** بعد الإغلاق
صار «الدرجةُ لم تتحرّك» صادقاً — ويبقى صادقاً **أيضاً لو صارت `score` تُعيد صفراً
أبداً**، أو لو كانت العيّنةُ ممّا لا تتحرّك عليه الأرقامُ أصلاً. فتأكيدُ ثباتٍ بلا
شاهدِ حركةٍ يقيس سكونَ العيّنة لا عملَ الآليّة.

فيحمل هذا الملفّ **شاهداً موجباً**: يُثبِت أنّ الإحصاءَين — المُنطاق والعالميّ —
**يختلفان فعلاً على هذه العيّنة**، فيصير الثباتُ نتيجةً مقيسةً للنطاق لا صدفةَ
مجموعةٍ متّفقة.

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
    spec = importlib.util.spec_from_file_location("_bm25_scope_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_bm25_scope_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _chunk(chunk_id: str, tenant: str, text: str, **meta):
    """وثيقةُ المرجع العامّ تُصنَّف صراحةً — عقدُ `KnowledgeChunk` لا مجاملةُ عيّنة.

    أوّلُ صياغةٍ هنا بنت وثيقةً عامّةً بلا `source_class`، فرفضتها المنصّة:
    «global RAG chunks must be explicitly classified reference data». والعيّنةُ
    كانت الخاطئة لا العقد — فتُصحَّح العيّنة ويبقى العقدُ مفروضاً.
    """
    if tenant == m.GLOBAL_REFERENCE_TENANT:
        meta.setdefault("source_class", "curated_reference")
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


BASE = "wheat irrigation schedule for wheat fields"


def _index(*chunks):
    index = m.BM25Index()
    index.rebuild(list(chunks))
    return index


# ── المرساة: الاتّجاهان اللذان كان ينحرف فيهما ──────────────────────────────
def test_another_tenants_corpus_never_moves_a_score():
    """**مرساةٌ قُلِبت حين أُغلِق العطل — لا حُذِفت.**

    والاتّجاهان معاً لأنّ الانحراف كان ذا اتّجاهين، وأحدُهما وحدَه كان سيُخفي
    الآخر: وثائقُ مستأجِرٍ آخر **تحمل** المصطلح كانت ترفع `df` فتخفض الدرجة،
    ووثائقُه الطويلةُ **التي لا تحمله** ترفع `avg_len` فترفع الدرجة.
    """
    base = _chunk("a1", "tenant-a", BASE)
    alone = _index(base).score("wheat", "a1", tenant_id="tenant-a")

    shares_term = _index(
        base, *[_chunk(f"b{i}", "tenant-b", "wheat barley") for i in range(50)]
    ).score("wheat", "a1", tenant_id="tenant-a")

    long_unrelated = _index(
        base,
        *[_chunk(f"c{i}", "tenant-b", " ".join(["barley millet"] * 40)) for i in range(50)],
    ).score("wheat", "a1", tenant_id="tenant-a")

    assert shares_term == alone, "مستأجِرٌ آخر يحمل المصطلح ما يزال يخفض الترتيب عبر df"
    assert long_unrelated == alone, "وثائقُ مستأجِرٍ آخر الطويلة ما تزال ترفع الترتيب عبر avg_len"


def test_the_scoped_and_the_global_statistics_actually_differ_on_this_sample():
    """**الشاهدُ الموجب — وبدونه كان الملفُّ كلُّه أخضرَ بلا معلومة.**

    «لم تتحرّك الدرجة» يبقى صادقاً لو كانت `score` معطوبةً تُعيد صفراً، أو لو
    كانت العيّنةُ ممّا يتّفق عليه الإحصاءان أصلاً. فيُقاس هنا أنّ الإحصاءَين
    **مختلفان فعلاً** على هذه المجموعة بعينها — والدرجةُ غيرُ صفريّة.
    """
    base = _chunk("a1", "tenant-a", BASE)
    index = _index(base, *[_chunk(f"b{i}", "tenant-b", "wheat barley") for i in range(50)])

    scoped_n, scoped_df, scoped_avg = index.corpus_stats("tenant-a")
    assert (scoped_n, scoped_df.get("wheat")) == (1, 1), "النطاقُ يرى وثائقَ مستأجِرٍ آخر"

    global_n = len(index.docs)
    assert global_n == 51 and index.doc_freq["wheat"] == 51, "العيّنةُ لا تُفرِّق الإحصاءَين"
    assert not math.isclose(scoped_avg, index.avg_len), "متوسّطُ الطول متساوٍ — العيّنةُ لا تقيس"

    assert index.score("wheat", "a1", tenant_id="tenant-a") > 0, "درجةٌ صفريّة تُخضِر كلَّ ثبات"


# ── تعريفُ المجموعة: واحدٌ للطرفين ──────────────────────────────────────────
def test_the_visible_corpus_is_the_pair_the_dense_filter_also_uses():
    """مجموعةٌ واحدة يُشتقّ منها المسارانِ — لا شرطانِ متطابقانِ ينحرفان لاحقاً."""
    scope = m.BM25Index().visible_scope("tenant-a")
    assert scope == {"tenant-a", m.GLOBAL_REFERENCE_TENANT}

    index = _index(
        _chunk("a1", "tenant-a", BASE),
        _chunk("g1", m.GLOBAL_REFERENCE_TENANT, "wheat reference"),
        _chunk("b1", "tenant-b", "wheat barley"),
    )
    admitted = {chunk.chunk_id for chunk, _ in index.search("wheat", tenant_id="tenant-a")}
    assert admitted == {"a1", "g1"}, "ما يُرتَّب ليس ما يُرى — والمجموعتانِ افترقتا ثانيةً"


def test_the_global_reference_asking_about_itself_counts_its_documents_once():
    """`visible_scope` مجموعةٌ لا قائمة: وإلّا ضُوعِفت وثائقُ المرجع العامّ لنفسه."""
    index = _index(
        _chunk("g1", m.GLOBAL_REFERENCE_TENANT, BASE),
        _chunk("g2", m.GLOBAL_REFERENCE_TENANT, "wheat barley"),
    )
    n_docs, doc_freq, _ = index.corpus_stats(m.GLOBAL_REFERENCE_TENANT)
    assert (n_docs, doc_freq["wheat"]) == (2, 2)


def test_a_document_outside_the_visible_corpus_scores_zero():
    """خلطُ `tf` من وثيقةٍ مع `idf` من مجموعةٍ لا تضمّها حسابٌ بلا معنًى."""
    index = _index(_chunk("a1", "tenant-a", BASE), _chunk("b1", "tenant-b", "wheat barley"))
    assert index.score("wheat", "b1", tenant_id="tenant-a") == 0.0
    assert index.score("wheat", "b1", tenant_id="tenant-b") > 0.0


def test_scoring_requires_naming_the_asking_tenant():
    """افتراضُ «مستأجِرِ الوثيقة» يبدو مقبولاً ويكون خاطئاً: وثيقةُ المرجع العامّ
    تُقاس داخل مجموعةِ **السائل** فتختلف درجتُها باختلافه. فالمُعامل مطلوبٌ صراحةً
    لئلّا يعود العطلُ من بابِ افتراضٍ صامت."""
    index = _index(_chunk("a1", "tenant-a", BASE))
    with pytest.raises(TypeError):
        index.score("wheat", "a1")  # type: ignore[call-arg]


# ── مسكُ الإحصاء: الدلاءُ لا تنحرف ─────────────────────────────────────────
def test_re_ingesting_a_chunk_under_a_new_tenant_moves_its_whole_contribution():
    """النزعُ من **دلوِ المستأجِر المسجَّل** لا من دلوِ الوارد.

    ولو نُزِعت المساهمةُ من الدلو الجديد لبقيت في القديم أبداً، فيرى مستأجِرٌ
    وثيقةً غادرته في إحصائه — وهو العطلُ نفسُه بثوبٍ آخر.
    """
    index = m.BM25Index()
    index.add(_chunk("x1", "tenant-a", "wheat barley"))
    index.add(_chunk("x1", "tenant-b", "wheat barley"))

    assert index.corpus_stats("tenant-a")[:2] == (0, {}), "بقيت مساهمةُ صفٍّ غادر المستأجِر"
    n_docs, doc_freq, _ = index.corpus_stats("tenant-b")
    assert (n_docs, doc_freq["wheat"]) == (1, 1)


def test_the_derived_aggregate_equals_the_sum_of_the_buckets():
    """المجموعُ **مُشتَقٌّ** لا مُمسَكٌ بجانبها: نسختانِ بيدَين تنحرفان صامتتَين.

    وتساوي **المجموعات** لا العدّادات: مجموعٌ يطابق في العدد ويغفل مصطلحاً
    ويزيد آخرَ يمرّ على أيّ تأكيدٍ على الحجم.
    """
    index = _index(
        _chunk("a1", "tenant-a", "wheat barley"),
        _chunk("b1", "tenant-b", "wheat millet"),
        _chunk("g1", m.GLOBAL_REFERENCE_TENANT, "wheat"),
    )
    summed: dict[str, int] = {}
    for bucket in index._tenant_doc_freq.values():
        for term, df in bucket.items():
            summed[term] = summed.get(term, 0) + df

    assert index.doc_freq == summed
    assert index.doc_freq["wheat"] == 3
    assert index.avg_len == sum(index.doc_len.values()) / len(index.doc_len)


def test_a_removed_term_leaves_no_bucket_behind():
    """رفعٌ مُكرَّرٌ يبدّل نصَّ الصفّ: المصطلحُ الزائل يخرج من الدلو لا يبقى بصفر."""
    index = m.BM25Index()
    index.add(_chunk("x1", "tenant-a", "legacyterm maize"))
    index.add(_chunk("x1", "tenant-a", "replacementterm maize"))

    _, doc_freq, _ = index.corpus_stats("tenant-a")
    assert "legacyterm" not in doc_freq
    assert (doc_freq["maize"], doc_freq["replacementterm"]) == (1, 1)
