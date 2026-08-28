"""كاشفاتُ الدَّين تُختبَر على عيّنةٍ اصطناعيّة — ``RAG-CORPUS-MEASUREMENT-INTEGRITY-01``.

**العقدُ الذي يحرسه هذا الملفّ عقدُ الكاشف لا عقدُ العطل.** والفرق حاسم:

* لو أكّدنا هنا الخاصّيّةَ الصحيحة وتُرِك أحمرَ، لصار دَيناً دائماً في CI — ويتعلّم
  القارئ تجاهلَ الأحمر، وهو أسوأ من غياب الاختبار.
* ولو أكّدنا أنّ العطل **قائم**، لثُبِّت السلوك الخاطئ **عقداً**؛ فيصير الإصلاحُ
  المستقبليّ هو ما يُحمِّر الجناح، ويُقرَأ الصوابُ انحداراً.

فكلُّ كاشفٍ يُقاس من طرفين: **يرى عيباً مزروعاً**، و**يصمت على عيّنةٍ قانونيّة**.
والثاني لا يقلّ أهمّيّةً: كاشفٌ يقول «موجود» دائماً لا يكشف شيئاً — يُخضِر تقريراً
بلا معلومة، ويصير ضجيجاً يُتجاهَل بعد أوّل قراءتين.

والحالةُ القانونيّة لهذه الأربع في ``sahool-brain/gaps/registry.md`` — لا في رمز
خروجِ المِسبار ولا في خُضرة هذا الملفّ.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/architecture/rag_corpus_admissibility_probe.py"


def _probe():
    spec = importlib.util.spec_from_file_location("rag_admissibility_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rag_admissibility_probe"] = module
    spec.loader.exec_module(module)
    return module


def _canonical_meta(**extra):
    meta = {
        "tenant_id": "tenant-a",
        "chunk_id": "C1",
        "source_uri": "sahool://x",
        "source_revision": "r1",
        "publisher": "p",
        "license": "l",
        "jurisdiction": "YE",
        "language": "ar",
        "evidence_level": "document",
    }
    meta.update(extra)
    return meta


def _canonical_payload(**extra):
    return {
        "page_content": "wheat guidance",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": _canonical_meta(**extra),
    }


# ── ① المستأجِرُ في الجذر وحده ───────────────────────────────────────────────


def test_a_root_only_tenant_payload_is_healed_so_both_paths_see_it():
    """**مرساةٌ قُلِبت حين أُغلِق العطل — لا حُذِفت.**

    كانت تؤكّد أنّ الكاشفَ **يُطلِق** على حمولةٍ مزروعة، وهو الصواب ما دام العطلُ
    قائماً. وقد أُغلِق في `from_payload` (`RAG-LEGACY-DENSE-SPARSE-SCOPE-ASYMMETRY-01`):
    المستأجِرُ المُحَلُّ من الجذر يُكتَب في `metadata` عند القراءة، فيتّفق ما يراه
    البحثُ المتناثر وما يرشّح عليه الكثيف.

    **والكاشفُ لم يمت بذلك بل صار كاشفَ انحدار:** نزعُ سطر التطبيع يُعيد
    `present=True` ويُحمِّر هذا السطر. فالخاصّيّةُ المحروسة هي **اتّفاقُ المسارين
    على مجموعةٍ واحدة** — لا «العطلُ ما يزال هنا».

    وتركُ المرساة على صيغتها الأولى كان سيجعل **الإصلاحَ هو ما يكسر الجناح**، وهو
    بعينه ما حذّر منه متنُ المِسبار: «اختبارٌ يؤكّد أنّ العطل قائم يُثبِّت السلوكَ
    الخاطئ عقداً».
    """
    probe = _probe()
    module = probe.load_module()
    row = probe.detect_legacy_tenant_root_only(module)

    assert row["present"] is False, "عاد الصفُّ القديم مرئيّاً متناثراً وغائباً كثيفاً"
    assert row["sparse_visible"] is True
    assert row["dense_visible"] is True, "المستأجِرُ لا يصل `metadata` — الكثيفُ لا يراه"


def test_the_root_only_tenant_detector_stays_quiet_on_a_canonical_payload():
    """كاشفٌ يقول «موجود» دائماً لا يكشف شيئاً — يُخضِر تقريراً بلا معلومة.

    **والعيّنةُ تمرّ من الكاشف نفسه لا من بديله.** أوّلُ صياغةٍ هنا استدعت
    `from_payload` وحدها وتحقّقت من `metadata` — فكاشفٌ يعود `present=True` أبداً
    كان يمرّ عليها. أمسك ذلك مراجعٌ آليّ على #882، والعقدُ المنقوض كان **عقدي أنا**.
    """
    probe = _probe()
    module = probe.load_module()
    row = probe.detect_legacy_tenant_root_only_on(module, probe._canonical_payload())
    assert row["present"] is False
    assert row["dense_visible"] is True


# ── ② إحصاءاتُ BM25 ─────────────────────────────────────────────────────────


def test_the_bm25_stat_detector_is_quiet_and_still_reports_no_content_leak():
    """**مرساةٌ قُلِبت حين أُغلِق العطل — لا حُذِفت.**

    كانت تؤكّد أنّ الكاشفَ **يُطلِق**، وهو الصواب ما دام العطلُ قائماً. وقد أُغلِق
    بـ`corpus_stats` المقصورة على `visible_scope` (`RAG-BM25-CROSS-TENANT-CORPUS-STATS-01`).
    **والكاشفُ صار كاشفَ انحدار:** إعادةُ الإحصاء العالميّ تُعيد `present=True`.

    وتبقى الخاصّيّةُ الثانية مؤكَّدةً كما كانت: **لا إفشاءَ محتوًى** — وهي التي
    منعت رفعَ التصنيف إلى خرقِ عزلٍ ادّعاءً أوسعَ من الدليل.
    """
    probe = _probe()
    row = probe.detect_bm25_cross_tenant_stats(probe.load_module())
    assert row["present"] is False
    assert row["content_leaked_across_tenants"] == []


def test_the_bm25_score_is_stable_in_both_directions_the_drift_used_to_take():
    """الانحرافُ كان ذا اتّجاهين، وتأكيدُ واحدٍ منهما كان سيُخفي الآخر: مستنداتٌ
    تحمل المصطلح كانت تخفض عبر `df`، وطويلةٌ لا تحمله ترفع عبر `avg_len`.

    **والثباتُ هنا لا يقوم وحدَه شاهداً** — يبقى صادقاً لو صارت `score` تُعيد
    صفراً أبداً. فشاهدُ الحركة الموجب في
    `test_rag_bm25_corpus_scope.py::test_the_scoped_and_the_global_statistics_actually_differ_on_this_sample`.
    """
    probe = _probe()
    row = probe.detect_bm25_cross_tenant_stats(probe.load_module())
    alone = row["score_tenant_a_alone"]
    assert alone > 0, "درجةٌ صفريّة تُخضِر كلَّ تأكيدِ ثبات"
    assert row["score_after_other_tenant_shares_term"] == alone
    assert row["score_after_other_tenant_unrelated_long_docs"] == alone


def test_the_bm25_detector_is_quiet_on_a_single_tenant_corpus():
    """مجموعةُ مستأجِرٍ واحد ⇒ لا أثرَ عابراً: هذا ما يجعل الكاشف ذا معنًى.

    والمقياسُ هنا **الكاشف نفسه**، لا `BM25Index` مباشرةً: إضافةُ مستندٍ للمستأجِر
    نفسه تحرّك إحصاءاته — وهو سلوكُ BM25 الصحيح لا عيباً — فقياسُ الفهرس وحده كان
    يُثبِت شيئاً آخر غير الذي يدّعيه اسمُ الاختبار.
    """
    probe = _probe()
    module = probe.load_module()
    own_only = [
        probe._chunk(module, "a1", "tenant-a", "wheat irrigation wheat"),
        probe._chunk(module, "a2", "tenant-a", "wheat schedule"),
    ]
    assert probe.detect_bm25_cross_tenant_stats_on(module, own_only)["present"] is False


# ── ③ توسيعُ الجيران ────────────────────────────────────────────────────────


def test_the_neighbor_detector_fires_and_bounds_the_claim_to_scope_not_tenancy():
    """الحدُّ مقيسٌ لا مفترَض: المتجاوَزُ مرشِّحُ النطاق، وعزلُ المستأجِر محفوظ."""
    probe = _probe()
    row = probe.detect_neighbor_filter_bypass(probe.load_module())
    assert row["present"] is True
    assert row["off_scope_chunks"] == ["n"]
    assert row["cross_tenant_chunks"] == []


def test_the_neighbor_detector_is_quiet_when_the_neighbour_shares_the_scope():
    probe = _probe()
    module = probe.load_module()
    hit = probe._chunk(
        module, "h", "tenant-a", "t", document_id="doc-1", chunk_index=0, field_id="F1"
    )
    neighbour = probe._chunk(
        module, "n", "tenant-a", "t2", document_id="doc-1", chunk_index=1, field_id="F1"
    )
    row = probe.detect_neighbor_filter_bypass_on(module, hit, neighbour, "field_id")
    assert row["present"] is False
    assert row["off_scope_chunks"] == []


# ── ④ مُعرِّفُ التخزين هويّةً منطقيّة ────────────────────────────────────────


def test_the_storage_id_detector_fires_when_the_logical_key_is_absent():
    probe = _probe()
    row = probe.detect_storage_id_as_logical_id(probe.load_module())
    assert row["present"] is True
    assert row["resolved_chunk_id"] == "storage-uuid-42"


def test_the_storage_id_detector_is_quiet_when_the_logical_key_is_present():
    probe = _probe()
    module = probe.load_module()
    row = probe.detect_storage_id_as_logical_id_on(
        module, probe._canonical_payload(), "storage-uuid-42"
    )
    assert row["present"] is False
    assert row["resolved_chunk_id"] == "C1"


# ── عقدُ المِسبار نفسه ──────────────────────────────────────────────────────


def test_the_probe_reports_and_never_blocks(monkeypatch):
    """تشخيصٌ لا بوّابة: لو صار حاجباً لأدخل الدَّينَ المعروف في مسار الدمج فجأة.

    والدَّينُ يُغلَق بشرائحه المستقلّة بعد جرد المجموعة الحيّة، لا بترقيةِ مِسبار.
    """
    probe = _probe()
    report = probe.run()
    assert report["blocking"] is False
    # `main` تقرأ `sys.argv` الحقيقيّ، وتحت pytest يحمل رايات pytest — فتُضبَط.
    monkeypatch.setattr(sys, "argv", ["rag_corpus_admissibility_probe.py"])
    assert probe.main() == 0


def test_every_declared_finding_has_a_detector():
    """قائمةٌ تُعلِن ما لا يُقاس تصير وثيقةً تصف ما لا يفعله الكود."""
    probe = _probe()
    produced = {row["finding"] for row in probe.run()["findings"]}
    assert produced == set(probe.FINDINGS)
    assert len(probe.DETECTORS) == len(probe.FINDINGS)


def test_the_probe_never_emits_chunk_text():
    """التقريرُ تشخيصٌ لا نسخةُ مجموعة: مُعرِّفاتٌ وأسماءُ حقولٍ وأرقامٌ فقط."""
    probe = _probe()
    rendered = repr(probe.run())
    for leaked in ("wheat guidance", "wheat irrigation", "barley millet"):
        assert leaked not in rendered
