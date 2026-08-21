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
    """رمزٌ غيرُ مُعلَن يجعل الجردَ غيرَ قابلٍ للتجميع.

    وأوّلُ صياغةٍ هنا جرّبت حالتين فقط رغم اسمها — ففرعٌ جديد كان يستطيع أن يُصدِر
    رمزاً غير مُعلَن والعقدُ يمرّ. أمسكه مراجعٌ آليّ على #882.
    """
    module = _pq()
    mutations = [
        {"page_content": None, "text": None},
        {"metadata": {"chunk_id": None}},
        {"metadata": {"tenant_id": None}},
        {"metadata": {"tenant_id": ""}},
        {"source_type": None},
        {"source_type": ""},
        {"document_id": None},
        {"metadata": {"evidence_level": "lab"}},
        {"metadata": {"prescriptive_eligible": True}},
        {"metadata": {"content_digest": "0" * 64}},
        {"metadata": {"content_digest": ""}},
        {"metadata": {"content_digest": None}},
        {"source_type": "external_reference", "metadata": {"source_revision": ""}},
        {"metadata": {"chunk_index": "ليس رقماً"}},
    ]
    emitted = set()
    for mutate in mutations:
        verdict = module.classify_rejection(_payload(**mutate), fallback_id="u1")
        if verdict is None:
            continue
        code, _ = verdict
        assert code in module.REJECTION_REASONS, f"رمزٌ غير مُعلَن: {code}"
        emitted.add(code)
    assert len(emitted) >= 8, f"التغطيةُ ضاقت — {sorted(emitted)}"


def test_no_rejected_payload_falls_into_the_catch_all() -> None:
    """`OTHER_SCHEMA_ERROR` ملاذُ الأخير، وامتلاؤه يُفسِد الجرد صامتاً.

    والانحرافُ الذي أمسكه المراجع كان بالضبط من هذا الصنف: `source_type=""` وثلاثُ
    صيغٍ لـ`content_digest` يرفضها المحلّل بسببٍ مسمًّى وكانت تُبتلَع في الملاذ —
    فيهاجر الرقمُ إلى الصنف الخطأ في تحكيمٍ سيُبنى عليه قرارُ هجرة.
    """
    module = _pq()
    for mutate in (
        {"source_type": ""},
        {"metadata": {"tenant_id": ""}},
        {"metadata": {"content_digest": ""}},
        {"metadata": {"content_digest": None}},
        {"metadata": {"content_digest": 0}},
    ):
        payload = _payload(**mutate)
        with pytest.raises((TypeError, ValueError)):
            module.KnowledgeChunk.from_payload(payload, fallback_id="u1")
        code, _ = module.classify_rejection(payload, fallback_id="u1")
        assert code != "OTHER_SCHEMA_ERROR", f"ابتُلِع في الملاذ: {mutate}"


def test_the_classifier_and_the_parser_never_disagree() -> None:
    """العقدُ الجامع: يُصنَّف ما رُفِض، ولا يُصنَّف ما قُبِل — مقيسٌ على الحالتين معاً."""
    module = _pq()
    cases = [
        _payload(),
        _payload(source_type=""),
        _payload(metadata={"tenant_id": ""}),
        _payload(metadata={"content_digest": ""}),
        _payload(page_content=None, text=None),
        _payload(metadata={"evidence_level": "lab"}),
        _payload(document_id=None),
    ]
    for payload in cases:
        try:
            module.KnowledgeChunk.from_payload(payload, fallback_id="u1")
            rejected = False
        except (TypeError, ValueError):
            rejected = True
        verdict = module.classify_rejection(payload, fallback_id="u1")
        assert (verdict is not None) is rejected, payload


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
    # D08-C: إيصالُ المتّجه وحده يتركها False، والمسار الوحيد لرفعها هو إيصالُ
    # جردٍ مستقل يمرّ بالحارس القانوني. فلا تُورَث من وثيقة الحالة ولا تُكتب True
    # مباشرةً داخل حارس القبول.
    assert "payload_parity_observed = False" in source
    assert "rag_corpus_audit_receipt_guard.py" in source
    assert 'requirements["canonical_payload_parity"] = payload_parity_observed' in source
    assert 'requirements.setdefault("canonical_payload_parity"' not in source, (
        "`setdefault` يُورِّث `True` من وثيقة الحالة بلا إيصال جرد — "
        "فيصير تكافؤُ الـpayload مُعلَناً بلا قياس"
    )
    assert 'requirements["canonical_payload_parity"] = True' not in source, (
        "رفعُها مباشرةً تلفيقٌ: تكافؤُ الـpayload يحتاج إيصالَ جردٍ قانونياً"
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


# ── ④ `/readyz` لا يدّعي تكافؤ الـpayload ────────────────────────────────────


def test_readyz_does_not_claim_canonical_payload_parity() -> None:
    """الفصلُ يمرّ إلى المستهلك، لا يقف عند الحارس.

    كان `readyz` يُعيد `collection_schema_parity: True` بلا شرط — فيقرأ كلُّ مستهلكٍ
    تكافؤَ الـpayload أخضرَ لمجرّد نجاح إعادة البناء، ويبقى الادّعاءُ الواسع حيّاً في
    المسار الذي يقرؤه التشغيل فعلاً. وفصلُ الاسمين في حارس القبول وحده لا يكفي.

    أمسك هذا الحدَّ تنفيذٌ مستقلٌّ للشريحة نفسها؛ نُقِل ومعه شاهدُه.
    """
    source = (ROOT / "services/rag-retrieval/main.py").read_text(encoding="utf-8")
    assert '"collection_vector_schema_parity": True' in source
    assert '"canonical_payload_parity": False' in source
    assert '"collection_schema_parity"' not in source, (
        "الاسمُ الواسع عاد إلى مسار الجاهزيّة — فيقرأ المستهلكُ تكافؤَ الـpayload "
        "أخضرَ بلا جردِ مجموعةٍ يُثبِته"
    )


def test_the_live_certification_reads_the_measured_name() -> None:
    """الشهادةُ تشهد لِما قِيس: تكافؤَ مخطّط المتّجه لا تكافؤَ الـpayload."""
    source = (ROOT / "scripts/ci/ai_rag_live_certification.py").read_text(encoding="utf-8")
    assert 'r.get("collection_vector_schema_parity") is True' in source
    assert 'r.get("collection_schema_parity")' not in source, (
        "الشهادةُ تقرأ الاسم الواسع — فتشهد لتكافؤٍ لا يُثبِته أيُّ فحصٍ فيها"
    )


# ── ⑤ الخاصّيّةُ على كلّ المُنتِجين، لا على ملفٍّ بعينه ──────────────────────


def test_the_wide_name_is_gone_from_every_producer_not_just_the_ones_named_above() -> None:
    """**العطلُ الذي أفلت من كلّ ما سبق — ``M0-C2``.**

    التأكيداتُ أعلاه تُثبِّت كلٌّ منها **ملفّاً** سُمّي بعينه، وبنصّ الإسناد الحرفيّ
    (``requirements[...]`` · ``r.get(...)``). و``c8_rag_production_certification.py``
    مسارُ شهادةٍ ثانٍ محجوزٌ في ``ci.yml`` — يستعمل متغيّراً محلّيّاً اسمه ``effective``،
    فلم يطابق أيَّ نصٍّ مثبَّت، ومرّ الاسمُ الواسع فيه أخضرَ عبر الشريحة كلّها.

    **فثُبِّت الملفُّ لا الخاصّيّة** — وهو صنفُ العطل الذي وُجِدت هذه الشريحة لأجله،
    واقعاً في حارسها. والحسابُ وقتها: حارسُ تكافؤِ الـpayload الوحيد في ``c8`` كان
    **مصادفةَ** بقاءِ ``direct_qdrant_revocation_ready`` كاذبةً — ويومَ تُقلَب، وهي
    غايةُ البرنامج نفسه، تُصدَر شهادةُ قدرةٍ كاملة على إيصالٍ أثبت تكافؤَ المتّجه وحده.

    **ويُقرأ الشجرُ بـ``ast`` لا بالنصّ:** التعليقاتُ تذكر الاسمَ القديم لتشرح الهجرة —
    وفحصٌ نصّيّ كان سيحمرّ عليها، وهو ``TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01``
    المسجَّل في هذا المستودع. فيُقاس ما يُنفَّذ: ثوابتُ النصّ في الشجر، لا ما يُقال عنه.
    """
    import ast

    wide = "collection_schema_parity"
    offenders: list[str] = []
    for path in sorted((ROOT / "scripts").rglob("*.py")) + sorted(
        (ROOT / "services").rglob("*.py")
    ):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - ليس موضوع هذا العقد
            continue
        # **ترشيحٌ نصّيّ قبل التحليل — وحدُّه يُقال لا يُسكَت عنه.** تحليلُ الشجرة
        # لكلّ ملفّ كان يكلّف ٣٫١١ ثانية مقابل ٠٫٠٥ بعد الترشيح (٢١٠٥ ملفّاً، مقيس) —
        # وثلاثُ ثوانٍ في كلّ تشغيلِ وحدةٍ تُقتطَع من الهامش الذي تدافع عنه هذه الـPR
        # نفسها. رفعه مراجعٌ آليّ على #883، وبرهانُه مقيس.
        #
        # **والحدّ:** الترشيحُ يفترض أنّ الاسم يظهر **حرفيّاً**. ونصٌّ مُقسَّم عمداً
        # (`"collection_schema" "_parity"`) يُنتِج الثابتَ نفسه ولا يحوي الاسمَ نصّاً —
        # مُتحقَّقٌ منه لا مفترَض. فيمرّ من هذا الترشيح. وهو انحدارٌ متكلَّف لا يقع
        # سهواً، والشاهدُ المُسجَّل يزرع الصيغةَ الحرفيّة لأنّها شكلُ الانحدار الحقيقيّ.
        # يُوصَف هنا صراحةً كي لا تُقرأ خُضرةُ هذا العقد أوسعَ ممّا قاست.
        if wide not in source:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:  # pragma: no cover - ليس موضوع هذا العقد
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == wide:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not offenders, (
        f"الاسمُ الواسع `{wide}` ما يزال مفتاحاً مُنفَّذاً في: {offenders}.\n"
        "اسمٌ واحد يحمل حقيقتين يمنح تكافؤَ الـpayload خُضرةَ إيصالِ المتّجه — "
        "والإيصالُ الحيّ يقيس هويّةَ المجموعة وبُعدَ المتّجه وهويّةَ النموذج، "
        "ولا يجرد payload كلّ نقطة."
    )


def test_the_adjudicated_state_carries_the_split_vocabulary_itself() -> None:
    """المفردةُ المحفوظة هي ما يقرؤه **كلُّ** مُنتِج — فلا يكفي إصلاحُ القارئين.

    كانت وثيقةُ الحالة تحمل ``collection_schema_parity`` ولا تحمل
    ``canonical_payload_parity`` **إطلاقاً**. فمُنتِجٌ يكتب الاسمَ الواسع ``True``
    كان يُسقِط شرطَ الـpayload من الحساب رأساً — لا يُخالِفه، بل لا يراه.
    """
    state = json.loads(
        (ROOT / "docs/architecture/rag_authority_convergence.json").read_text(encoding="utf-8")
    )
    reqs = state.get("cutover_requirements") or {}
    assert "collection_schema_parity" not in reqs, "الاسمُ الواسع عاد إلى وثيقة الحالة"
    assert reqs.get("collection_vector_schema_parity") is False
    assert reqs.get("canonical_payload_parity") is False, (
        "تكافؤُ الـpayload يحتاج إيصالَ جردٍ فعليّاً — عدٌّ دقيق مطابقٌ للمسح، "
        "وكلُّ نقطةٍ مصنّفة، وصفرُ غيرِ مصنّف. ولا يُرفَع من فحصٍ ساكن."
    )
    assert state.get("version") == 2, (
        "رفعُ النسخة صريحٌ لا تجميليّ: يُبطِل أيَّ دليلٍ قديم بمفرداتٍ سابقة بدل أن يُقرَأ نقصُه قبولاً"
    )


def test_no_producer_can_certify_cutover_on_a_vector_only_receipt() -> None:
    """الخاصّيّةُ التي كُسِرت فعلاً — تُقاس بالحساب لا بوجود سطر.

    قبل ``M0-C2`` كان ``c8`` يُصدِر ``CERTIFIED_CUTOVER_CAPABLE`` بمجرّد قلبِ
    ``direct_qdrant_revocation_ready``؛ الآن يبقى تكافؤُ الـpayload حاجزاً قائماً.
    """
    state = json.loads(
        (ROOT / "docs/architecture/rag_authority_convergence.json").read_text(encoding="utf-8")
    )
    # ما يرفعه إيصالٌ حيّ صالح، وما لا يرفعه — بأقصى سخاءٍ ممكن للإيصال.
    effective = dict(state["cutover_requirements"])
    effective["collection_vector_schema_parity"] = True
    effective["live_shadow_parity_receipt"] = True
    effective["direct_qdrant_revocation_ready"] = True  # الفرضُ الأسخى: قُلِبت

    blockers = sorted(k for k, v in effective.items() if not bool(v))
    assert blockers == ["canonical_payload_parity"], (
        f"بإيصالٍ يقيس المتّجه وحده صارت الحاجباتُ {blockers} — وتكافؤُ الـpayload "
        "يجب أن يبقى وحده قائماً حتّى يأتي إيصالُ جردِ المجموعة."
    )
