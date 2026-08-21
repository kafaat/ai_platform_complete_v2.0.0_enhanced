"""صدقُ القياس قبل إصلاحِ ما يُقاس — ``RAG-CORPUS-MEASUREMENT-INTEGRITY-01``.

ثلاثةُ عقودٍ لا تغيّر ترتيباً ولا تهاجر بياناً ولا ترفع سلطة. تجعل الرقمَ الذي
سنبني عليه الإصلاح القادم **دقيقاً ومُفسَّراً وغيرَ مدّعٍ**:

* العددُ الدقيق سلطةَ الجاهزيّة — لا ``points_count`` التقريبيّ.
* رفضٌ مُصنَّفٌ بتصنيفٍ ثابت — لا رقمٌ بلا تشريح ولا اشتقاقٌ من نصوص الاستثناءات.
* تكافؤُ مخطّط المتّجه ≠ تكافؤُ الـpayload — اسمان لحقيقتين، لا اسمٌ يمنح إحداهما
  خُضرةَ الأخرى.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
ADMISSION = ROOT / "scripts/architecture/rag_cutover_admission_guard.py"


def _pq():
    spec = importlib.util.spec_from_file_location("pq_integrity", PQ)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pq_integrity"] = module
    spec.loader.exec_module(module)
    return module


# ── ① العددُ الدقيق سلطةَ الجاهزيّة ─────────────────────────────────────────


def _store(module, count_result=None):
    store = module.QdrantHttpClient.__new__(module.QdrantHttpClient)
    store.collection = "c"
    recorded: list[tuple[str, str, dict | None]] = []

    def fake_request(method, path, payload=None):
        recorded.append((method, path, payload))
        return count_result if count_result is not None else {"result": {"count": 7}}

    store._request = fake_request  # type: ignore[method-assign]
    return store, recorded


def test_the_point_count_comes_from_the_exact_count_api() -> None:
    """``points_count`` في معلومات المجموعة **تقريبيّ بالعقد**.

    وكان يُستعمَل سلطةً دقيقة في مسار ``readyz`` الحاجب، فينتج ٥٠٣ بلا فقد نقطةٍ
    واحدة — عطلٌ يبقى قائماً حتّى بعد أن يصير ``skipped = 0`` وتُهاجَر كلّ نقطة.
    """
    module = _pq()
    store, recorded = _store(module)
    assert store.collection_point_count() == 7
    method, path, payload = recorded[-1]
    assert method == "POST"
    assert path.endswith("/points/count")
    assert payload == {"exact": True}


def test_the_approximate_collection_info_is_never_consulted() -> None:
    module = _pq()
    store, recorded = _store(module)
    store.collection_point_count()
    assert not any(path == "/collections/c" for _m, path, _p in recorded), (
        "نُودِيت معلوماتُ المجموعة — فالعددُ التقريبيّ ما يزال في المسار"
    )


def test_an_unusable_exact_count_raises_instead_of_falling_back() -> None:
    """الارتدادُ «اللطيف» يُعيد العيب تحت مسارٍ متدهور — وهو أخفى وأسوأ.

    تعذُّرُ العدّ الدقيق يعني أنّ اكتمال المجموعة **لا يمكن إثباته**؛ والصواب أن
    يُقال ذلك ويُفشَل مغلقاً، لا أن يُستبدَل برقمٍ لا يصلح للمهمّة.
    """
    module = _pq()
    for bad in ({"result": {}}, {"result": {"count": -1}}, {"result": {"points_count": 7}}):
        store, _ = _store(module, count_result=bad)
        with pytest.raises(ValueError):
            store.collection_point_count()


# ── ② تصنيفُ الرفض ──────────────────────────────────────────────────────────


def _payload(**over):
    meta = {
        "tenant_id": "t1",
        "chunk_id": "c1",
        "source_uri": "sahool://x",
        "source_revision": "r1",
        "publisher": "p",
        "license": "l",
        "jurisdiction": "YE",
        "language": "ar",
        "evidence_level": "document",
    }
    meta.update(over.pop("metadata", {}))
    body = {
        "page_content": "text",
        "source_type": "reference_document",
        "document_id": "d1",
        "metadata": meta,
    }
    body.update(over)
    return body


def test_a_payload_the_parser_accepts_is_never_given_a_reason_code() -> None:
    """التصنيفُ يُنادي المحلّلَ الحقيقيّ أوّلاً — فلا ينحرف عن قراره أبداً."""
    module = _pq()
    assert module.classify_rejection(_payload(), fallback_id="u1") is None


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        ({"page_content": None, "text": None}, "MISSING_CONTENT"),
        ({"metadata": {"tenant_id": None}}, "MISSING_TENANT"),
        ({"source_type": None}, "MISSING_SOURCE_TYPE"),
        ({"document_id": None}, "MISSING_DOCUMENT_ID"),
        ({"metadata": {"evidence_level": "lab"}}, "LAB_EVIDENCE_CLAIMED"),
        ({"metadata": {"prescriptive_eligible": True}}, "PRESCRIPTIVE_AUTHORITY_INVALID"),
        ({"metadata": {"content_digest": "0" * 64}}, "CONTENT_DIGEST_MISMATCH"),
        (
            {"source_type": "external_reference", "metadata": {"source_revision": ""}},
            "GLOBAL_REFERENCE_PROVENANCE_INCOMPLETE",
        ),
    ],
)
def test_each_rejection_class_gets_its_own_stable_code(mutate, expected) -> None:
    """رمزٌ لكلّ صنف — و``skipped = 54`` وحدها لا تقول أيَّ عقدٍ خُرِق."""
    module = _pq()
    payload = _payload(**mutate)
    with pytest.raises((TypeError, ValueError)):
        module.KnowledgeChunk.from_payload(payload, fallback_id="u1")
    code, _missing = module.classify_rejection(payload, fallback_id="u1")
    assert code == expected


def test_the_missing_provenance_fields_are_named_not_just_counted() -> None:
    """جردُ الهجرة يحتاج **أيَّ** حقلٍ نقص، لا عددَ الناقصين."""
    module = _pq()
    payload = _payload(
        source_type="external_reference",
        metadata={"source_revision": "", "publisher": ""},
    )
    code, missing = module.classify_rejection(payload, fallback_id="u1")
    assert code == "GLOBAL_REFERENCE_PROVENANCE_INCOMPLETE"
    assert set(missing) == {"publisher", "source_revision"}


def test_every_emitted_code_is_declared_in_the_taxonomy() -> None:
    """رمزٌ غيرُ مُعلَن يجعل الجردَ غيرَ قابلٍ للتجميع."""
    module = _pq()
    for mutate in ({"page_content": None, "text": None}, {"metadata": {"evidence_level": "lab"}}):
        code, _ = module.classify_rejection(_payload(**mutate), fallback_id="u1")
        assert code in module.REJECTION_REASONS


def test_the_classifier_never_returns_chunk_text() -> None:
    module = _pq()
    payload = _payload(page_content="a very distinctive secret sentence", text=None)
    payload["source_type"] = "external_reference"
    payload["metadata"]["source_revision"] = ""
    verdict = module.classify_rejection(payload, fallback_id="u1")
    assert "distinctive" not in repr(verdict)


# ── ③ تكافؤُ المتّجه ≠ تكافؤُ الـpayload ────────────────────────────────────


def test_the_admission_guard_no_longer_carries_the_wide_name() -> None:
    """اسمٌ واحد كان يحمل حقيقتين، فيمنح الثانية خُضرةَ الأولى.

    والشاهدُ الحيّ قاطع: مخطّطُ المتّجه سليمٌ تماماً بينما ٥٤ نقطة غير قابلة
    لإعادة البناء القانونيّة.
    """
    source = ADMISSION.read_text(encoding="utf-8")
    assert 'requirements["collection_vector_schema_parity"] = True' in source
    assert 'requirements["collection_schema_parity"] = True' not in source, (
        "عودةُ الاسم الواسع تمنح تكافؤَ الـpayload خُضرةَ تكافؤِ المتّجه — "
        "وهما حقيقتان قِيست إحداهما ولم تُقَس الأخرى"
    )


def test_payload_parity_is_not_raised_by_the_vector_receipt() -> None:
    """لا تُلفَّق من فحصٍ ساكن: تحتاج جردَ مجموعةٍ فعليّاً، ولا إيصالَ جردٍ بعد."""
    source = ADMISSION.read_text(encoding="utf-8")
    assert 'requirements.setdefault("canonical_payload_parity", False)' in source
    assert 'requirements["canonical_payload_parity"] = True' not in source, (
        "رفعُها من فحصٍ ساكن تلفيقٌ: تكافؤُ الـpayload يحتاج جردَ مجموعةٍ فعليّاً — "
        "عدٌّ دقيق مطابقٌ للمسح، وكلُّ نقطةٍ مصنّفة، وصفرُ غيرِ مصنّف"
    )


def test_the_admission_verdict_is_still_not_ready() -> None:
    """هذه الشريحة لا ترفع سلطة — ولو رفعتها لكانت قد فعلت ما تُصنّفه عطلاً."""
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(ADMISSION)], capture_output=True, text=True, encoding="utf-8"
    )
    payload = json.loads(proc.stdout)
    assert payload.get("cutover_capable") is False
    assert payload.get("status") != "CUTOVER_ADMISSION_READY"
