"""`RAG-STORAGE-ID-AS-LOGICAL-IDENTITY-01` — الاستعارةُ تُعلَن ولا تُنزَع.

متنُ `from_payload` كان يقول إنّ مُعرِّفَ تخزين Qdrant **«لا يُسمَح»** أن يصير هويّةَ
استرجاع، والسطرُ التالي يسمح به عبر `fallback_id` — **وثيقةٌ تصف ما لا يفعله الكود**.

**والعلاجُ ليس نزعَ الارتداد، وثلاثةُ أسبابٍ مقيسة:**

* `canonical_storage_shape` يستدعي المحلّلَ بـ`fallback_id=None`، **فالخدمةُ
  القانونيّة ترفض الصفَّ المستعير اليوم**. السِّعةُ للهجرة والتدقيق، ونزعُها يُعمي
  التدقيقَ عن الصفوف التي وُجِد لأجلها.
* **الصمتُ هو العطل:** مستهلِكٌ يقرأ `chunk_id` لا يميّز هويّةً مُعلَنة من مُستعارة.
* وهو نمطُ `CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01` بعينه — أُعلِن الاقتطاعُ
  ولم يُرفَع السقف.

**والخطرُ في اختبار هذا الإصلاح مضاعَف:** «الرايةُ تقول `storage_fallback`» يبقى
صادقاً لو صارت الرايةُ **ثابتةً** لا تتبدّل. فيُقاس الطرفان: المُستعارُ يُعلَن،
**والمُعلَنُ صراحةً يُعلَن `declared`** — فالرايةُ نتيجةُ قياسٍ لا ثابتٌ يُصادِف الصواب.

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
    spec = importlib.util.spec_from_file_location("_storage_id_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_storage_id_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()

_META = {
    "tenant_id": "tenant-a",
    "source_uri": "sahool://x",
    "source_revision": "r1",
    "publisher": "p",
    "license": "l",
    "jurisdiction": "YE",
    "language": "ar",
    "evidence_level": "document",
}


def _payload(**meta):
    return {
        "page_content": "wheat guidance",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": {**_META, **meta},
    }


# ── المرساة: الاستعارةُ تُعلَن ──────────────────────────────────────────────
def test_a_borrowed_storage_id_is_declared_not_silent():
    """المرساةُ المسمّاة — والاستعارةُ باقيةٌ بالقصد، **والمُعلَن هو الجديد**."""
    chunk = m.KnowledgeChunk.from_payload(_payload(), fallback_id="storage-uuid-42")

    assert chunk.chunk_id == "storage-uuid-42", "نُزِع الارتدادُ — والهجرةُ والتدقيقُ يحتاجانه"
    assert chunk.metadata["chunk_id_source"] == "storage_fallback"


def test_a_declared_logical_id_is_marked_declared_not_borrowed():
    """**الشاهدُ الموجب — وبدونه كانت الرايةُ ثابتةً تُصادِف الصواب.**

    «الرايةُ تقول `storage_fallback`» يبقى صادقاً لو صارت ثابتةً لا تتبدّل. فيُقاس
    الطرفُ الآخر: مفتاحٌ منطقيٌّ مُعلَن ⇒ `declared`، **ولا يُستعار الارتدادُ حتّى
    حين يُمرَّر**.
    """
    chunk = m.KnowledgeChunk.from_payload(_payload(chunk_id="C1"), fallback_id="storage-uuid-42")

    assert chunk.chunk_id == "C1"
    assert chunk.metadata["chunk_id_source"] == "declared"


def test_a_root_level_chunk_id_still_counts_as_declared():
    """صفوفُ EXPAND القديمة تضع المفتاحَ في الجذر — وهي **مُعلَنةٌ لا مُستعارة**."""
    payload = _payload()
    payload["chunk_id"] = "C-root"
    chunk = m.KnowledgeChunk.from_payload(payload, fallback_id="storage-uuid-42")

    assert chunk.chunk_id == "C-root"
    assert chunk.metadata["chunk_id_source"] == "declared"


# ── الرايةُ خاصّيّةُ تحليلٍ لا خاصّيّةُ صفّ ───────────────────────────────────
def test_the_flag_is_never_written_back_to_storage():
    """إبقاؤها في المخزَن يكذب على صفٍّ أُعيدت كتابتُه بمفتاحٍ منطقيٍّ صحيح.

    فهي خاصّيّةُ **هذا التحليل** لا خاصّيّةُ الصفّ، و`payload` تنزعها.
    """
    borrowed = m.KnowledgeChunk.from_payload(_payload(), fallback_id="storage-uuid-42")
    declared = m.KnowledgeChunk.from_payload(_payload(chunk_id="C1"), fallback_id="x")

    assert "chunk_id_source" not in borrowed.payload["metadata"]
    assert "chunk_id_source" not in declared.payload["metadata"]
    # والمفتاحُ المنطقيّ يبقى مكتوباً كما هو — النزعُ لا يمسّ الهويّة.
    assert borrowed.payload["metadata"]["chunk_id"] == "storage-uuid-42"


# ── الحدّ: الخدمةُ القانونيّة ترفض المُستعار أصلاً ──────────────────────────
def test_the_canonical_serving_shape_still_rejects_a_borrowed_identity():
    """**تأكيدٌ يمنع قراءةَ الشريحة «أجزنا مُعرِّفَ التخزين».**

    `canonical_storage_shape` يمرّر `fallback_id=None`، فصفٌّ بلا `metadata.chunk_id`
    **ليس قانونيَّ الشكل** — قبل الإعلان وبعده. والإعلانُ يخدم الهجرةَ والتدقيق،
    ولا يرفع صفّاً إلى الخدمة.
    """
    assert m.canonical_storage_shape(_payload()) is False

    # **البصمةُ تُحسَب ولا تُختلَق:** أوّلُ صياغةٍ هنا وضعت `"a" * 64` فرفضتها
    # المنصّة («content_digest does not match RAG chunk text»). والعيّنةُ كانت
    # الخاطئة لا العقد — وهي ثاني مرّةٍ في هذا العنقود يُمسِكني فيها عقدُ المنصّة
    # على عيّنةٍ بنيتُها بيدي.
    canonical = _payload(
        chunk_id="C1",
        chunk_index=0,
        total_chunks=1,
        content_digest=m._content_digest("wheat guidance"),
        source_class="curated_reference",
        source_type="reference_document",
        document_id="d1",
    )
    assert m.canonical_storage_shape(canonical) is True, (
        "العيّنةُ القانونيّة تُرفَض — المِقياسُ بلا طرفٍ موجب"
    )


def test_a_payload_with_no_identity_at_all_still_fails_closed():
    """بلا مفتاحٍ منطقيٍّ **وبلا ارتداد** يُرفَض الصفّ — الإعلانُ لا يُليّن التحقّق."""
    with pytest.raises(ValueError):
        m.KnowledgeChunk.from_payload(_payload(), fallback_id=None)


# ── الوثيقةُ تصف ما يفعله الكود ─────────────────────────────────────────────
def test_the_docstring_no_longer_promises_what_the_code_does_not_do():
    """`RAG-STORAGE-ID-AS-LOGICAL-IDENTITY-01` أصلُه **متنٌ يَعِد بما لا يقع**.

    وتركُ المتن على حاله بعد الإصلاح كان يُبقي نصفَ العطل: القارئُ يصدّق أنّ
    الاستعارةَ ممنوعة، فلا يبحث عن الراية أصلاً.
    """
    doc = m.KnowledgeChunk.from_payload.__doc__ or ""
    assert "chunk_id_source" in doc, "المتنُ لا يذكر الرايةَ التي يعتمد عليها القارئ"
    assert "deliberately not allowed" not in doc, "بقي الوعدُ الذي يخالفه الكود"
