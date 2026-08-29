"""`RAG-NEIGHBOR-FILTER-SCOPE-BYPASS-01` — الجارُ يمرّ بمرشِّحات النطاق.

`retrieve` يطبّق `filters` على البحث الكثيف والمتناثر، ثمّ **يتجاوزها في آخر خطوةٍ
تُضيف صفوفاً**: `_expand_neighbors` كان يُدخِل الجارَ بالمستند والترتيب وحدَهما.
فاستعلامُ `field_id=F1` يُعيد مقطعاً من `F2` — إجابةٌ خارج نطاقها المطلوب.

**والحدُّ مقيسٌ ولا يُوسَّع فوقه:** مفتاحُ `by_doc_idx` يحمل `tenant_id`، **فعزلُ
المستأجِر كان محفوظاً ولا يزال**. عطلُ دقّةِ نطاقٍ لا خرقُ عزل — وتصنيفُه خرقاً كان
سيرفعه فوق أولويّته ويُفسِد ترتيبَ العنقود.

**والخطرُ الأوّل في اختبار هذا الإصلاح أنّه يصير خضرةً بلا معلومة.** «الجارُ لم
يظهر» يبقى صادقاً لو صار `_expand_neighbors` **لا يُضيف جاراً أبداً** — وهو انحدارٌ
أسوأ من العطل، ولا يُميّزه أيُّ تأكيدٍ على الغياب. فيحمل هذا الملفّ **شاهداً موجباً**:
جارٌ داخلَ النطاق **يُضاف فعلاً**، فيصير الإقصاءُ نتيجةَ ترشيحٍ لا عجزَ آليّة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _module():
    spec = importlib.util.spec_from_file_location("_neighbor_scope_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_neighbor_scope_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _chunk(chunk_id: str, tenant: str, text: str, **meta):
    return m.KnowledgeChunk(
        chunk_id=chunk_id,
        tenant_id=tenant,
        text=text,
        source_type="reference_document",
        document_id=meta.get("document_id", "doc-1"),
        chunk_index=meta.get("chunk_index", 0),
        total_chunks=3,
        metadata={
            "source_uri": "sahool://x",
            "source_revision": "r1",
            "publisher": "p",
            "license": "l",
            "jurisdiction": "YE",
            "language": "ar",
            "evidence_level": "document",
            **meta,
        },
    )


def _expand(hit, others, filters):
    retriever = m.HybridQdrantRetriever.__new__(m.HybridQdrantRetriever)
    retriever._chunks = {c.chunk_id: c for c in [hit, *others]}
    rows = retriever._expand_neighbors([m.RetrievedAnnotation(hit, 1.0, 0.0, 1.0)], filters=filters)
    return [r.chunk.chunk_id for r in rows]


# ── المرساة: الجارُ خارج النطاق لا يدخل ────────────────────────────────────
def test_a_neighbour_outside_the_requested_scope_is_not_admitted():
    """المرساةُ المسمّاة: الحادثةُ الأصليّةُ بحرفها — `field_id=F1` يُعيد `F2`."""
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=0, field_id="F1")
    off = _chunk("n", "tenant-a", "other", chunk_index=1, field_id="F2")

    assert _expand(hit, [off], {"field_id": "F1"}) == ["h"]


def test_a_neighbour_inside_the_scope_is_still_admitted():
    """**الشاهدُ الموجب — وبدونه كان الملفُّ كلُّه أخضرَ بلا معلومة.**

    «الجارُ لم يظهر» يبقى صادقاً لو صار التوسيعُ **لا يُضيف جاراً أبداً**، وهو
    انحدارٌ أسوأُ من العطل. فيُقاس هنا أنّ الآليّة **ما تزال تعمل**: جارٌ يتقاسم
    النطاق يدخل، وبدوره `neighbor`.
    """
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=0, field_id="F1")
    inside = _chunk("n", "tenant-a", "more", chunk_index=1, field_id="F1")

    retriever = m.HybridQdrantRetriever.__new__(m.HybridQdrantRetriever)
    retriever._chunks = {"h": hit, "n": inside}
    rows = retriever._expand_neighbors(
        [m.RetrievedAnnotation(hit, 1.0, 0.0, 1.0)], filters={"field_id": "F1"}
    )
    assert [r.chunk.chunk_id for r in rows] == ["h", "n"]
    assert rows[1].role == "neighbor"


def test_both_directions_are_filtered_not_just_the_following_chunk():
    """التوسيعُ يمتدّ للسابق واللاحق معاً — فترشيحُ أحدهما وحدَه يترك نصفَ العطل."""
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=1, field_id="F1")
    before = _chunk("b", "tenant-a", "before", chunk_index=0, field_id="F2")
    after = _chunk("a", "tenant-a", "after", chunk_index=2, field_id="F2")

    assert _expand(hit, [before, after], {"field_id": "F1"}) == ["h"]
    assert set(_expand(hit, [before, after], None)) == {"h", "b", "a"}


def test_no_filters_means_no_narrowing_not_no_neighbours():
    """`None` و`{}` تعنيان «بلا تقييد» — لا «أقصِ كلَّ شيء»، وهي الدلالةُ القائمة."""
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=0, field_id="F1")
    other = _chunk("n", "tenant-a", "other", chunk_index=1, field_id="F2")

    assert set(_expand(hit, [other], None)) == {"h", "n"}
    assert set(_expand(hit, [other], {})) == {"h", "n"}


def test_a_none_valued_filter_key_does_not_exclude_a_chunk_lacking_it():
    """مفتاحٌ قيمتُه `None` يعني «لا تُقيّد بهذا البُعد» — دلالةٌ حفظها الاستخراج."""
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=0, field_id="F1")
    neighbour = _chunk("n", "tenant-a", "other", chunk_index=1, field_id="F1")

    assert set(_expand(hit, [neighbour], {"crop": None})) == {"h", "n"}


# ── الحدُّ: عزلُ المستأجِر لم يكن مخروقاً ──────────────────────────────────
def test_tenant_isolation_was_already_intact_and_stays_intact():
    """**تأكيدٌ يمنع قراءةَ هذه الشريحة أوسعَ من دليلها.**

    مفتاحُ `by_doc_idx` يحمل `tenant_id`، فجارُ مستأجِرٍ آخر لم يكن يدخل **قبل**
    الإصلاح ولا بعده. وتصنيفُ الفجوة خرقَ عزلٍ كان سيرفعها فوق أولويّتها الحقيقيّة.
    """
    hit = _chunk("h", "tenant-a", "wheat", chunk_index=0, field_id="F1")
    foreign = _chunk("x", "tenant-b", "other", chunk_index=1, field_id="F1")

    assert _expand(hit, [foreign], {"field_id": "F1"}) == ["h"]
    assert _expand(hit, [foreign], None) == ["h"], "الجارُ الأجنبيُّ يدخل بلا مرشِّح — العزلُ مخروق"


# ── التعريفُ واحد: لا شرطان يتّفقان اليوم ──────────────────────────────────
def test_the_sparse_search_and_the_neighbour_expansion_share_one_predicate():
    """**درسُ `RAG-BM25-CROSS-TENANT-CORPUS-STATS-01` مُطبَّقاً هنا.**

    شرطانِ متطابقانِ يُكتَبان مرّتين ينحرفان عند أوّل تعديلٍ لأحدهما، ولا يُحمِّر
    ذلك شيئاً. فيُقاس أنّ الموضعين يستدعيان `matches_scope_filters` نفسَها، وأنّ لا
    نسخةَ ثانية للشرط عادت إلى المصدر.
    """
    source = MODULE.read_text(encoding="utf-8")
    assert source.count("def matches_scope_filters(") == 1
    assert source.count("matches_scope_filters(") == 3, "نسخةٌ ثانية للشرط أو موضعٌ لا يستدعيها"
    assert source.count("value is not None and chunk.metadata.get(key) != value") == 1


def test_the_predicate_is_measured_directly_in_both_directions():
    """المُسنَدُ دالّةٌ نقيّة، فيُكذَّب مباشرةً لا عبر الآليّة التي تستعمله."""
    inside = _chunk("i", "tenant-a", "t", field_id="F1", crop="wheat")

    assert m.matches_scope_filters(inside, {"field_id": "F1"}) is True
    assert m.matches_scope_filters(inside, {"field_id": "F2"}) is False
    assert m.matches_scope_filters(inside, {"field_id": "F1", "crop": "barley"}) is False
    assert m.matches_scope_filters(inside, {"region": "north"}) is False, (
        "مفتاحٌ يفتقده المقطعُ بقيمةٍ فعليّة يجب أن يُقصيه"
    )
    assert m.matches_scope_filters(inside, None) is True


def test_retrieve_passes_its_filters_through_to_the_expansion():
    """المسّ الأخير: `retrieve` يُمرِّر نطاقَه — وإلّا صحّ التوسيعُ وحدَه ولم يُستعمَل.

    **والقراءةُ بـ`ast` لا بالنصّ، وقد أخطأتُ أوّلاً فقِستُها نصّاً:** النداءُ يمتدّ
    أسطراً وفيه أقواسٌ متداخلة (`reverse=True`)، فقصُّ السلسلة عند أوّل `)` يقرأ
    نصفَ النداء ويُحمِّر على شيفرةٍ صحيحة. وهو `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`
    بصيغته الأصغر: **قارئٌ نصّيٌّ يقيس ما لا يقصده**.
    """
    import ast

    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_expand_neighbors"
    ]
    assert calls, "لا نداءَ لتوسيع الجيران — المِقياسُ صار بلا موضوع"
    for call in calls:
        passed = {kw.arg: kw.value for kw in call.keywords}
        assert "filters" in passed, "`retrieve` يوسّع الجيران بلا نطاقه"
        # **القيمةُ لا الاسم — وطفرةٌ مُسجَّلة نجت من الصياغة الأولى فكشفت ذلك.**
        # كان التأكيدُ «كلمةٌ مفتاحيّةٌ اسمُها `filters` موجودة»، و`filters=None`
        # يُرضيه حرفيّاً: الاسمُ باقٍ والنطاقُ ذهب. فتأكيدُ **وجودِ المقبس** ليس
        # تأكيدَ أنّ السلكَ موصول — وهو `MUT-SURVIVED-BECAUSE-THE-TEST-CHECKED-THE-SHAPE-NOT-THE-VALUE`.
        assert isinstance(passed["filters"], ast.Name) and passed["filters"].id == "filters", (
            "النطاقُ يُمرَّر ثابتاً لا نطاقَ الاستعلام — الاسمُ باقٍ والقيمةُ ذهبت"
        )
