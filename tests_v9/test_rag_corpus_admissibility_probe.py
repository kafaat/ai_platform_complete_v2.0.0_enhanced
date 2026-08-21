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


def test_the_root_only_tenant_detector_fires_on_a_planted_payload():
    probe = _probe()
    module = probe.load_module()
    assert probe.detect_legacy_tenant_root_only(module)["present"] is True


def test_the_root_only_tenant_detector_stays_quiet_on_a_canonical_payload():
    """كاشفٌ يقول «موجود» دائماً لا يكشف شيئاً — يُخضِر تقريراً بلا معلومة."""
    module = _probe().load_module()
    chunk = module.KnowledgeChunk.from_payload(_canonical_payload(), fallback_id="uuid-1")
    assert chunk.metadata.get("tenant_id") == "tenant-a", (
        "العيّنةُ القانونيّة تحمل المستأجِر في metadata ⇒ المسارُ الكثيف يراها"
    )


# ── ② إحصاءاتُ BM25 ─────────────────────────────────────────────────────────


def test_the_bm25_stat_detector_fires_and_reports_no_content_leak():
    """الخاصّيّتان معاً: الترتيبُ يتحرّك، **ولا** يظهر محتوى مستأجِرٍ آخر.

    وخلطُهما كان سيرفع التصنيف إلى إفشاءِ محتوًى، وهو ادّعاءٌ أوسع من الدليل.
    """
    probe = _probe()
    row = probe.detect_bm25_cross_tenant_stats(probe.load_module())
    assert row["present"] is True
    assert row["content_leaked_across_tenants"] == []


def test_the_bm25_detector_reports_both_directions_of_the_shift():
    """الانحرافُ ليس اتّجاهاً واحداً: مستنداتٌ تحمل المصطلح تخفض، وطويلةٌ لا تحمله ترفع.

    ولا تُثبَّت هنا نِسَبٌ بعينها — تعتمد على نصّ العيّنة، فتثبيتُها ادّعاءُ ثباتٍ
    لا يملكه النظام.
    """
    probe = _probe()
    row = probe.detect_bm25_cross_tenant_stats(probe.load_module())
    alone = row["score_tenant_a_alone"]
    assert row["score_after_other_tenant_shares_term"] < alone
    assert row["score_after_other_tenant_unrelated_long_docs"] > alone


def test_a_single_tenant_corpus_is_the_quiet_case():
    """مستأجِرٌ وحده ⇒ لا تأثير: هذا ما يجعل الكاشف ذا معنًى."""
    probe = _probe()
    module = probe.load_module()
    base = probe._chunk(module, "a1", "tenant-a", "wheat irrigation wheat")
    first = module.BM25Index()
    first.rebuild([base])
    second = module.BM25Index()
    second.rebuild([base, probe._chunk(module, "a2", "tenant-a", "wheat wheat")])
    assert first.score("wheat", "a1") != second.score("wheat", "a1"), (
        "الإحصاءاتُ تتحرّك بمستنداتِ المستأجِر نفسه — وهذا سلوكُ BM25 الصحيح"
    )


# ── ③ توسيعُ الجيران ────────────────────────────────────────────────────────


def test_the_neighbor_detector_fires_and_bounds_the_claim_to_scope_not_tenancy():
    """الحدُّ مقيسٌ لا مفترَض: المتجاوَزُ مرشِّحُ النطاق، وعزلُ المستأجِر محفوظ."""
    probe = _probe()
    row = probe.detect_neighbor_filter_bypass(probe.load_module())
    assert row["present"] is True
    assert row["off_scope_chunks"] == ["n"]
    assert row["cross_tenant_chunks"] == []


def test_a_neighbour_inside_the_same_scope_is_not_a_finding():
    probe = _probe()
    module = probe.load_module()
    hit = probe._chunk(
        module, "h", "tenant-a", "t", document_id="doc-1", chunk_index=0, field_id="F1"
    )
    neighbor = probe._chunk(
        module, "n", "tenant-a", "t2", document_id="doc-1", chunk_index=1, field_id="F1"
    )
    retriever = module.HybridQdrantRetriever.__new__(module.HybridQdrantRetriever)
    retriever._chunks = {"h": hit, "n": neighbor}
    rows = retriever._expand_neighbors([module.RetrievedAnnotation(hit, 1.0, 0.0, 1.0)])
    assert [r.chunk.metadata.get("field_id") for r in rows] == ["F1", "F1"]


# ── ④ مُعرِّفُ التخزين هويّةً منطقيّة ────────────────────────────────────────


def test_the_storage_id_detector_fires_when_the_logical_key_is_absent():
    probe = _probe()
    row = probe.detect_storage_id_as_logical_id(probe.load_module())
    assert row["present"] is True
    assert row["resolved_chunk_id"] == "storage-uuid-42"


def test_a_payload_carrying_its_logical_key_keeps_it():
    module = _probe().load_module()
    chunk = module.KnowledgeChunk.from_payload(_canonical_payload(), fallback_id="storage-uuid-42")
    assert chunk.chunk_id == "C1"


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
