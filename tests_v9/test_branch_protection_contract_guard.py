"""`MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01` — القفل يُدقَّق، ولا يُدَّعى أنّه هنا.

هذه اختباراتُ **وحدة** بمعطياتٍ مُركَّبة: لا شبكة ولا GitHub. وهذا شرطُ صحّتها لا
تبسيطٌ لها — حارسٌ لا يُختبَر إلّا بوجود رمزٍ وصلاحيّة يصير تكذيبُه متخطًّى في كلّ
وظيفة، وهو صنف `STABLE_WRONG_TEST` الذي يُصنّفه `guard_mutation_guard`.

**والمعطيات تُحاكي `rules/branches/{branch}`** — القواعد **النافذة** على الفرع مصفوفةً،
لا استجابة الحماية الكلاسيكيّة. سببُ التحوّل مقيس لا مُفضَّل: القفل فُعِّل عبر Ruleset،
فأجابت النقطة الكلاسيكيّة `Branch not protected (HTTP 404)` — أي أنّ الحارس كان يسأل عن
آليّةٍ غير المستعمَلة.

**وحدّ صدقٍ يُقال مرّةً هنا ومرّةً في الحارس:** هذا **مدقّقٌ للإعداد لا بديلٌ عنه**.
لا يمنع دمجاً ولا يرى خيط مراجعة. يمنع أن يُطفَأ القفل **صامتاً** بعد تفعيله.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "branch_protection_contract_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_branch_protection_contract_guard", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل {_SCRIPT} — صحّح المسار"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()

REPO = "kafaat/ai_platform_complete_v2.0.0_enhanced"
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def _envelope(rules, **overrides) -> dict:
    """ظرف الدليل كما تكتبه خطوة الجلب — تُبدَّل حقولُه في التكذيبات."""
    document = {
        "schema_version": MOD.EVIDENCE_SCHEMA,
        "repository": REPO,
        "branch": "main",
        "endpoint": f"https://api.github.com/repos/{REPO}/rules/branches/main",
        "http_status": 200,
        "commit_sha": SHA,
        "rules": rules,
    }
    document.update(overrides)
    return document


def _protection(tmp_path: Path, document) -> Path:
    path = tmp_path / "protection.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _run(path: Path, *, repository: str = REPO, sha: str = SHA) -> int:
    return MOD.main(
        [
            "--protection-file",
            str(path),
            "--expect-repository",
            repository,
            "--expect-sha",
            sha,
        ]
    )


def _canonical() -> list[str]:
    """السياقات القانونيّة من العقد نفسه — لا نسخةٌ ثانية تبيت عنه."""
    return MOD.canonical_required_contexts()


def _checks_rule(contexts=None) -> dict:
    return {
        "type": "required_status_checks",
        "ruleset_source_type": "Repository",
        "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [
                {"context": c, "integration_id": 15368}
                for c in (_canonical() if contexts is None else contexts)
            ],
        },
    }


def _rules(resolution, *, with_params: bool = True, checks: dict | None = None) -> list:
    """قواعد نافذة نموذجيّة: حذف + عدم-تقديم + قاعدة PR تحمل الشرط + الفحوص المطلوبة.

    قاعدةُ `required_status_checks` جزءٌ من النموذج منذ
    `REQUIRED-CHECKS-DRIFT-IS-INVISIBLE-IN-BOTH-DIRECTIONS-01`: الحارس صار يفرض
    مساواةَ سياقاتها للعقد، فنموذجٌ بلا هذه القاعدة يقيس عالماً لا يشبه main.
    """
    pull_request: dict = {"type": "pull_request", "ruleset_source_type": "Repository"}
    if with_params:
        pull_request["parameters"] = {
            "required_approving_review_count": 0,
            "required_review_thread_resolution": resolution,
        }
    return [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        pull_request,
        _checks_rule() if checks is None else checks,
    ]


_ENABLED = _envelope(_rules(True))


def test_the_enabled_lock_passes(tmp_path):
    """المرساة المقابلة: بلا هذا قد تمرّ كلّ التكذيبات لأنّ الحارس يرفض دائماً."""
    assert _run(_protection(tmp_path, _ENABLED)) == 0


def test_conversation_resolution_disabled_is_a_failure(tmp_path):
    """**الحالة التي وقعت مرّتين:** القفل مُطفَأ، فزرُّ الدمج يعمل والخيوط مفتوحة.

    #810 دُمِج قبل وصول `REQUEST_CHANGES`، و#816 بعد إنشاء التعليقين بـ٤١ ثانية.
    والفرق بين الحالتين لا يعني شيئاً للقفل: كلتاهما كانت ستُمنَع.
    """
    assert _run(_protection(tmp_path, _envelope(_rules(False)))) == 1


def test_a_missing_key_is_not_read_as_enabled(tmp_path):
    """**الغياب «لم يُقرأ» لا «مُفعَّل».**

    قاعدة `pull_request` نافذة لكنّ `parameters` لا تحمل الشرط — إصدارُ API تغيّر، أو
    رمزٌ رأى حقولاً جزئيّة. تُقرأ قبولاً إن كان الافتراضيّ متساهلاً، وهذا بعينه «نتيجةٌ
    عن سؤالٍ لم يُطرَح»: الصنف الذي عولج ستّ مرّات في الشريحة التي أنشأت هذه الفجوة.
    """
    # قاعدةُ الفحوص سليمةٌ عمداً — `COVERAGE-MASKED-BY-A-NEIGHBOURING-GUARD-01`:
    # بلاها يبتلع فحصُ سطح الإنفاذ الحالةَ قبل الحارس المقصود، فينجو زرعُ هذا البند
    # ويبقى الرمز `1` عن سببٍ آخر. مقيسٌ بالزرع في preflight لا مفترَض.
    rules = [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
        _checks_rule(),
    ]
    assert _run(_protection(tmp_path, _envelope(rules))) == 1


def test_no_pull_request_rule_is_a_failure(tmp_path, capsys):
    """**قواعد نافذة بلا قاعدة `pull_request` ⇒ لا شيء يشترط حلّ المحادثات.**

    حالةٌ يُنتجها الشكل الجديد وحده: الفرع محميّ من الحذف والدفع القسريّ (فالاستجابة
    ليست فارغة ولا خطأً) بينما شرطُ المراجعة غائبٌ تماماً. قراءةُ «ثمّة قواعد» قبولاً
    تُبلِّغ خضرةً عن حمايةٍ لا تشمل المقصود.

    **ويقيس السببَ لا رمزَ الخروج وحده — عن عمد:** نزعُ هذا الفحص يُسقِط الحالة في فرع
    «`parameters` غائبة» التالي، فيبقى الرمز `1` وتمرّ الطفرة صامتةً. ورمزُ خروجٍ صحيح
    عن سببٍ خاطئ هو نفسه «نتيجةٌ صحيحة عن سؤالٍ لم يُطرَح».
    """
    # وقاعدةُ الفحوص سليمةٌ هنا للسبب نفسه: الحالة يجب أن تُحسَم بغياب قاعدة الـPR
    # وحدَه، لا بغياب قاعدةِ فحوصٍ ثانية معه.
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}, _checks_rule()]
    assert _run(_protection(tmp_path, _envelope(rules))) == 1
    assert f"لا قاعدة `{MOD.CONTRACT_RULE_TYPE}` نافذة" in capsys.readouterr().out


def test_an_empty_rule_set_is_a_failure(tmp_path):
    """لا قواعد أصلاً ⇒ الفرع بلا حماية نافذة. القائمة الفارغة ليست موافقة."""
    assert _run(_protection(tmp_path, _envelope([]))) == 1


@pytest.mark.parametrize(
    "value,label",
    [
        ("true", "نصّ `true` لا منطقيّ — قيمةٌ صادقة في بايثون وليست العقد"),
        (1, "عددٌ صادق"),
        (None, "null"),
        ({}, "كائنٌ فارغ — صادقٌ؟ لا: `{}` كاذبة، لكنّ الاختبار يُثبِّت الرفض صراحةً"),
    ],
)
def test_a_non_boolean_enabled_is_rejected(tmp_path, value, label):
    """الشرط ليس منطقيّاً ⇒ رفض. المقارنة `is True` لا `if value`.

    `"false"` نصّاً **صادقةٌ** في بايثون، فمقارنةٌ بالصدق وحدها تقرأ القفل مُفعَّلاً
    وهو مُطفَأ. والعقد قيمةٌ منطقيّة بعينها لا «شيءٌ يشبه الصدق».
    """
    assert _run(_protection(tmp_path, _envelope(_rules(value)))) == 1, label


def test_one_enabling_rule_among_several_is_enough(tmp_path):
    """**الاتّحاد لا التقاطع:** GitHub يطبّق الأشدّ حين تنفُذ قواعد متعدّدة.

    فقاعدةٌ من Ruleset تُفعّل الشرط وأخرى كلاسيكيّة لا تُفعّله ⇒ الشرط **نافذ**.
    ولو قرأناها تقاطعاً لأبلغنا أحمرَ عن قفلٍ قائم — إنذارٌ كاذب يُدرِّب قارئه على التجاهل.
    """
    rules = [
        {"type": "pull_request", "parameters": {"required_review_thread_resolution": False}},
        {"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
        _checks_rule(),
    ]
    assert _run(_protection(tmp_path, _envelope(rules))) == 0


def test_an_unreadable_protection_file_fails_closed(tmp_path):
    """**«لم يُقرأ» ليس «مضبوط».**

    رمزٌ بلا صلاحية قراءة القواعد، أو خطوةُ جلبٍ لم تُنفَّذ، يُنتِجان ملفّاً غائباً أو
    استجابة خطأ — وهي الحالة المرجَّحة عند سوء الإعداد لا حالةٌ نادرة. وقبولُها يجعل
    الحارس أخضرَ **بالضبط حين لا يُقاس شيء**.
    """
    # الاسم ASCII عمداً: هذا التأكيد عن **ملفّ غائب**، وتشغيل `pytest -m unit` تحت
    # `LC_ALL=C PYTHONUTF8=0` (خطوة ١٠) يجعل ترميز نظام الملفّات ASCII، فاسمٌ عربيّ
    # يرفع `UnicodeEncodeError` **قبل** أن يبلغ الحارس — فيسقط الاختبار على تجهيزته لا
    # على ما يقيسه. CI-GUARDS-CRASH-ON-NON-UTF8-CONSOLE-01
    with pytest.raises(SystemExit):
        _run(tmp_path / "absent-protection.json")

    broken = tmp_path / "protection.json"
    broken.write_text("{ليس JSON", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run(broken)


def test_a_github_error_object_is_rejected(tmp_path):
    """استجابةُ خطأٍ من GitHub لا تُقرأ عقداً.

    `{"message": "Not Found"}` هو بالضبط ما تُعيده النقطة عند خطأ صلاحيّة أو مسار —
    وقراءتُه ظرفَ دليلٍ تُنتِج قبولاً صامتاً. (يُمسَك بفحص `schema_version`.)
    """
    with pytest.raises(SystemExit):
        _run(_protection(tmp_path, {"message": "Not Found", "status": "404"}))


@pytest.mark.parametrize("document", ["Not Found", 404, None, True])
def test_a_scalar_json_document_is_rejected(tmp_path, document):
    """**جسمٌ ليس كائناً ولا مصفوفةً — والطفرة أثبتت أنّه لم يكن مقيساً.**

    فحصُ «ليس كائناً» كان أخضر تحت طفرته لأنّ كلّ معطياتي كانت كائناتٍ أو مصفوفات؛
    فالفحص قائمٌ ولا يمرّ به شيء. وهذه أجسامٌ حقيقيّة: خنقٌ يُعيد نصّاً، أو `null`
    تُجسّدها خطوة الجلب حين يتعذّر تحليل الجسم.

    والرفض هنا `SystemExit` لا رمز خروج: قبل هذا الفحص لا يُعرَف حتّى **شكلُ** ما قُرِئ.
    """
    with pytest.raises(SystemExit):
        _run(_protection(tmp_path, document))


def test_a_bare_rule_array_is_rejected_as_evidence_without_a_source(tmp_path):
    """**شكل الدليل القديم يُرفَض صراحةً — لا يُقرأ تساهلاً.**

    مصفوفةٌ عارية تقول «قواعدُ ما، من مكانٍ ما، في وقتٍ ما». قبولُها للتوافق الخلفيّ
    يُبقي البابَ الذي فُتِح لأجله هذا الظرف مفتوحاً: ملفٌّ لفرعٍ آخر أو من تشغيلٍ سابق
    يمرّ بلا أثر. والرفض يُسمّي الترقية بدل أن يترك قارئه يخمّن.
    """
    with pytest.raises(SystemExit):
        _run(_protection(tmp_path, _rules(True)))


@pytest.mark.parametrize("schema", ["v0", None, "sahool.branch-protection-evidence.v2"])
def test_an_unknown_envelope_schema_is_rejected(tmp_path, schema):
    """ظرفٌ لا يُعرَف شكلُه لا يُقرأ دليلاً — وإلّا قُرِئت حقولٌ غائبة قبولاً.

    والنسخة التالية (`v2`) مرفوضةٌ كسابقتها عمداً: ظرفٌ أحدث قد ينقل معنى حقلٍ قائم،
    فالتوافق يُقرَّر بترقية الحارس لا بقبوله ما لم يُقرأ بعد.
    """
    with pytest.raises(SystemExit):
        _run(_protection(tmp_path, _envelope(_rules(True), schema_version=schema)))


@pytest.mark.parametrize(
    "status,label",
    [
        (401, "رمزٌ غائب أو منتهٍ"),
        (403, "رمزٌ بلا صلاحية — أو مُقيَّد بـSSO"),
        (404, "مستودعٌ/فرعٌ غير المقصود، أو نقطةٌ خاطئة"),
        (429, "خنقٌ — «أعِد المحاولة» لا «مضبوط»"),
        (500, "عطلٌ عند GitHub"),
        (503, "خدمةٌ غير متاحة"),
        (0, "لم يُنفَّذ النداء أصلاً (curl فشل)"),
    ],
)
def test_a_non_200_response_fails_closed(tmp_path, status, label, capsys):
    """**استجابةٌ غير `200` ليست قراءةً — وجسمُها صالحُ البنية فيمرّ لو لم يُفحَص الرمز.**

    وهذه هي بالضبط الحالة التي يُغري فيها التساهل: `{"message": "..."}` يُحلَّل، و`rules`
    قد تُجسَّد `[]` — فيصير السؤال «هل من قاعدة؟» بينما الصحيح «هل قُرِئ شيء أصلاً؟».
    ولذلك الرمز بندٌ في العقد لا تفصيلٌ في الصدفة: تركُ الحكم لـ`set -e` يدفن المنطق
    في `run: |` حيث لا يُقاس إلّا بتشغيل الوظيفة كاملةً.

    **والقواعد هنا صحيحةٌ عمداً — وهذا هو الفرق بين قياسٍ وصدفة:** أوّل صياغةٍ لهذا
    الاختبار وضعت `rules: []`، فكان يُحمِرّ عبر «لا قاعدة» لا عبر الرمز؛ وتعطيلُ فحص
    الرمز بطفرةٍ أبقاه **أخضر**. فالنسخة الحاضرة تحمل قفلاً مُفعَّلاً تامّاً: لا شيء
    يمكن أن يُحمِرَّها إلّا الحقل المقصود، وتُقاس الرسالة لا الرمز وحده.
    """
    envelope = _envelope(_rules(True), http_status=status)
    assert _run(_protection(tmp_path, envelope)) == 1, label
    assert "http_status" in capsys.readouterr().out, label


def test_a_success_status_as_text_is_not_read_as_success(tmp_path):
    """`"200"` نصّاً ليست `200` — والمقارنة بالمساواة لا بالصدق.

    حقلٌ يصل نصّاً من `jq` بلا `--argjson` يُنتِج بالضبط هذا، وقراءتُه نجاحاً تُعيد
    الحارس إلى «نتيجةٌ صحيحة عن سؤالٍ لم يُطرَح».
    """
    assert _run(_protection(tmp_path, _envelope(_rules(True), http_status="200"))) == 1


def test_evidence_from_another_repository_is_rejected(tmp_path, capsys):
    """دليلٌ عن مستودعٍ آخر ليس دليلاً عن هذا — ولو كان قفلُه مُفعَّلاً.

    **والنقطة تُترَك سليمةً عمداً:** لو بُدِّلت معها لأحمرّ فحصُ النقطة وحده، فيبقى
    فحصُ المستودع غيرَ مقيس — وهو ما أثبتته الطفرة: تعطيلُه أبقى الاختبار أخضر.
    فيُعزَل الحقل المقصود ليكون هو **الوحيد** الذي يمكن أن يُحمِرّ.
    """
    envelope = _envelope(_rules(True), repository="kafaat/some-other-repo")
    assert _run(_protection(tmp_path, envelope)) == 1
    assert "repository" in capsys.readouterr().out


def test_evidence_for_another_branch_is_rejected(tmp_path, capsys):
    """**فرعٌ محميّ آخر يُخضِر الحارس عن سؤالٍ ليس هو السؤال.**

    والحالة واقعيّة لا مفترَضة: فروع العمل في هذا المستودع تحمل حمايةً، فقراءةُ قواعد
    أحدها بدل `main` تُنتِج خضرةً كاملةً بينما الفرع الافتراضيّ مكشوف. ولذلك الفرع
    **مثبَّتٌ في الحارس** ولا يُمرَّر معاملاً — معاملٌ يعني أنّ من يُخطئ الإعداد يُخطئ
    السؤال معه.

    وتُعزَل الحقول كسابقتها: الإعلان وحده يُبدَّل، فلا يُحمِرّ إلّا فحصُ الفرع.
    """
    envelope = _envelope(_rules(True), branch="claude/feature")
    assert _run(_protection(tmp_path, envelope)) == 1
    assert "branch" in capsys.readouterr().out


def test_a_wholly_misdirected_read_is_rejected(tmp_path):
    """والحالة الواقعيّة الكاملة — إعلانٌ ونقطةٌ يشيران معاً إلى فرعٍ آخر — مرفوضة أيضاً.

    الاختباران أعلاه يعزلان حقلاً حقلاً ليكون كلٌّ منهما قابلاً للتكذيب؛ وهذا يؤكّد أنّ
    العزل لم يترك الحالة المُركَّبة بلا تغطية.
    """
    envelope = _envelope(
        _rules(True),
        branch="claude/feature",
        endpoint=f"https://api.github.com/repos/{REPO}/rules/branches/claude/feature",
    )
    assert _run(_protection(tmp_path, envelope)) == 1


def test_a_declared_branch_cannot_launder_a_different_endpoint(tmp_path, capsys):
    """**النقطة المُستدعاة هي القياس؛ `repository`/`branch` إعلانٌ يُصاحبه.**

    ظرفٌ يُعلن `branch: "main"` بينما النداء ذهب إلى فرعٍ آخر هو الشكل الذي يُنتجه خطأ
    تحريرٍ في الوظيفة (تغيير المسار وحده). ولو فُحِص الإعلان دون النقطة لمرّ الخطأ
    كاملاً — فالإعلان يُصدَّق بالنقطة لا العكس.
    """
    envelope = _envelope(
        _rules(True),
        endpoint=f"https://api.github.com/repos/{REPO}/rules/branches/claude/feature",
    )
    assert _run(_protection(tmp_path, envelope)) == 1
    assert "endpoint" in capsys.readouterr().out


def test_evidence_from_an_older_commit_is_rejected(tmp_path, capsys):
    """**دليلٌ من SHA سابق ليس دليلاً على هذا الالتزام.**

    مصنوعٌ مُعاد استعماله بين تشغيلين، أو ملفٌّ بقي في مساحة العمل، يُنتِج خضرةً عن حالةٍ
    انقضت — وهو الصنف نفسه الذي أضاع ثلاث جولات حين قُرِئ سجلٌّ بختمٍ زمنيّ قديم بوصفه
    نتيجةً جديدة. الدليل يُقاس عند الـSHA الذي يُحكَم عليه.
    """
    envelope = _envelope(_rules(True), commit_sha=OTHER_SHA)
    assert _run(_protection(tmp_path, envelope)) == 1
    assert "commit_sha" in capsys.readouterr().out


@pytest.mark.parametrize("sha", ["", "abc123", SHA.upper(), SHA + "0"])
def test_a_matching_but_malformed_commit_sha_is_still_rejected(tmp_path, capsys, sha):
    """**بصمةٌ سيّئة الشكل تُرفَض ولو طابقت المُنتظَر — وهذا هو موضع القياس.**

    والعزل هنا غير بديهيّ وقد أمسكته الطفرة: لو مُرِّرت بصمةٌ مشوَّهة مع `--expect-sha`
    **صحيحة**، لأحمرّ فحصُ **المطابقة** وبقي فحصُ **الشكل** غيرَ مقيس. فتُمرَّر القيمة
    المشوَّهة نفسها في الطرفين: المطابقة تنجح، فلا يبقى ما يُحمِرّ إلّا الشكل.

    وهذه ليست حالةً نظريّة: ظرفٌ يحمل `""` في الطرفين — لأنّ سياق GitHub لم يُملأ —
    يجعل «الدليل يطابق نفسه» ولا يربطه بشيء. و`SHA.upper()` تحرس الحسّاسيّة لحالة
    الأحرف: مقارنةٌ متساهلة تجعل شكلاً خاطئاً يمرّ.
    """
    assert _run(_protection(tmp_path, _envelope(_rules(True), commit_sha=sha)), sha=sha) == 1
    assert "commit_sha" in capsys.readouterr().out


@pytest.mark.parametrize("sha", [None, 12345, ["a"]])
def test_a_non_string_commit_sha_is_rejected(tmp_path, sha):
    """قيمةٌ ليست نصّاً في موضع البصمة ⇒ رفضٌ لا انهيار.

    `--expect-sha` نصٌّ دائماً (argparse)، فالمطابقة تفشل هنا أيضاً — وهذا مقصود:
    الغرض ألّا **ينهار** الحارس على نوعٍ غير متوقَّع، لا عزلُ فحصٍ بعينه.
    """
    assert _run(_protection(tmp_path, _envelope(_rules(True), commit_sha=sha))) == 1


@pytest.mark.parametrize("rules", [None, {}, "[]", 0])
def test_a_non_array_rules_field_fails_closed(tmp_path, rules):
    """`rules` ليست مصفوفةً ⇒ جسمُ خطأٍ في موضع القواعد.

    خطوةُ الجلب تُجسّد `null` حين يتعذّر تحليل الجسم (خنقٌ يُعيد HTML مثلاً)، فهذه
    الحالة مسارٌ حقيقيّ لا افتراض. وقراءتُها «صفر قاعدة» تُنتِج رسالةً صحيحة عن سببٍ خاطئ.
    """
    assert _run(_protection(tmp_path, _envelope(rules))) == 1


def test_the_pass_line_states_what_was_examined(tmp_path, capsys):
    """**خضرةٌ بلا عدّ لا يفرّق قارئُها بين «فُحِص فمرّ» و«لم يُفحَص شيء».**

    وهذا هو بند «صفر assertions/صفر checks» بصيغته القابلة للقياس: الخضرة تُصرّح
    بعدد القواعد المفحوصة وبكم منها من نوع `pull_request`، وبالمستودع والفرع والـSHA.
    فمن يقرأ `PASS` يرى **ما قِيس**، لا كلمةً تُطمئنه.
    """
    assert _run(_protection(tmp_path, _ENABLED)) == 0
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "فُحِصت 4 قاعدة نافذة" in out
    assert "منها 1 من نوع pull_request" in out
    # الخضرة تُصرّح بعدد السياقات المطابقة أيضاً — وإلّا لم يُعرَف أنّ سطح الإنفاذ قِيس.
    assert f"{len(_canonical())} سياقاً مطلوباً مطابقاً للعقد" in out
    assert REPO in out and "main" in out and SHA[:8] in out


def test_the_failure_names_the_remedy_and_its_place():
    """رسالة الحارس جزءٌ منه: العلاج **خارج** المستودع، فمن يقرأ الأحمر يجب أن يعرف ذلك.

    ولو سكتت الرسالة عن أنّ الموضع إعداداتُ GitHub، لبحث قارئُها في الكود عن سببٍ ليس
    فيه — وهو الوجه العمليّ لِما تعالجه هذه الشريحة. وتسمية **Enforcement=Active** ليست
    زينة: قاعدةٌ `Disabled` تُعرَض مضبوطةً بالكامل ولا تفرض شيئاً.
    """
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "Require conversation resolution before merging" in body
    assert "Rulesets" in body
    assert "Active" in body


def test_the_guard_reads_no_github_state():
    """**الحكم هنا والشبكة في الوظيفة — وهذا يُقاس لا يُوعَد به.**

    `scripts/ci/**` في هذا المستودع لا يستدعي GitHub إطلاقاً، وعقدُ
    `test_local_preflight_contract` يمنع ذلك على الأداة المحلّيّة. فلو زحف الاستدعاء إلى
    هنا لصار الحارس غيرَ قابل للاختبار بلا رمزٍ وصلاحيّة — أي لصار تكذيبُه متخطًّى.

    **والـGit المحلّي ليس GitHub:** الحارس قد يحتاج قراءة نسخة الأساس من الشجرة عبر
    `git show` ليميّز ختم `CONSUMED` الصرف من تعديل تفويضٍ حيّ. هذا لا يُدخل حالةَ
    GitHub ولا شبكةً؛ الممنوع هنا هو استدعاءُ الشبكة نفسها من داخل الحارس.

    **ويُقاس الكودُ لا النثر:** الصياغة الأولى بحثت في **نصّ الملفّ كلّه**، فاحمرّت حين
    وثّق الحارسُ في تعليقه النقطةَ التي تجلبها الوظيفة. وهذا عيبٌ في القياس لا في الكود:
    ذِكرُ عنوانٍ في شرحٍ ليس استدعاءً له، وقياسٌ يخلط بينهما يُعاقِب التوثيق ويُدرِّب
    كاتبه على حذفه. فتُسقَط النصوص والتعليقات بـ`tokenize` ويُفحَص ما يُنفَّذ — وهو
    **أشدّ** لا أضعف: `httpx.get("…")` يبقى مكشوفاً باسمه ولو أُخفي عنوانُه في نصّ.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    executable = " ".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    for name in ("requests", "urllib", "httpx", "socket", "http"):
        assert name not in executable.split(), f"وصولُ شبكةٍ داخل الحارس: {name!r}"


def test_the_measurement_of_no_network_would_catch_a_real_call():
    """**والقياس نفسه يُقاس — وإلّا كان «أخضرَ لأنّه لا ينظر».**

    فحصٌ يُسقِط النصوص والتعليقات قد يُسقِط معه الاستدعاء الحقيقيّ لو أخطأ في التصنيف.
    فنُمرِّر عليه مصدراً مزروعاً فيه نداءٌ فعليّ ونؤكّد أنّه يُمسَك — الطفرةُ هنا في
    **أداة القياس** لا في الحارس، وهي الموضع الذي لا يحرسه سجلّ الطفرات.
    """
    planted = 'import httpx\n\n\ndef f():\n    return httpx.get("https://example.invalid")\n'
    executable = " ".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(planted).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    assert "httpx" in executable.split()

    documented = '"""شرحٌ يذكر httpx وurllib."""\n# وتعليقٌ يذكر subprocess\nX = 1\n'
    executable = " ".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(documented).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    assert "httpx" not in executable.split()


# ── البند المشروط: منشأ التفويض — GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01 ──
#
# طبقة AUTHORIZATION في GATE-01 تقرأ `approved_by: owner` من ملفٍّ **في نفس الـPR**
# ولا تُثبِت منشأه: من يحتاج التفويض يستطيع إصداره. ومراجعةُ مالكي الكود هي ما تجعل
# المنشأ هويّةً مستقلّة. والبند **مشروط بالمسّ** لا دائم — بندٌ دائم كان يحجب كلّ دمجٍ
# في المستودع حتّى يُفعَّل إعدادٌ لا يملكه وكيل، وذلك ثمنٌ لا تُبرّره فجوةٌ نطاقُها ملفّان.

ADJUDICATION = "docs/architecture/gates/adjudications/GATE01-ADJ-2026-08-13-001.json"


def _rules_with_code_owner(value) -> list:
    # بالنوع لا بالموضع: `_rules` صارت تُلحِق قاعدة `required_status_checks` بعد قاعدة
    # الـPR، فمؤشّرٌ من الذيل كان يكتب البند في القاعدة الخطأ ويقيس عالماً آخر.
    rules = _rules(True)
    pull_request = next(r for r in rules if r.get("type") == MOD.CONTRACT_RULE_TYPE)
    pull_request["parameters"][MOD.CODE_OWNER_PARAMETER] = value
    return rules


def _run_changed(tmp_path: Path, document, changed: list[str], *extra_args: str) -> int:
    listing = tmp_path / "changed.txt"
    listing.write_text("\n".join(changed), encoding="utf-8")
    return MOD.main(
        [
            "--protection-file",
            str(_protection(tmp_path, document)),
            "--expect-repository",
            REPO,
            "--expect-sha",
            SHA,
            "--changed-files",
            str(listing),
            *extra_args,
        ]
    )


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_authorization_repo(tmp_path: Path, after: dict) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)

    rel = Path(ADJUDICATION)
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)

    before = {
        "schema": "sahool.gate01_adjudication/v1",
        "version": 1,
        "adjudication_id": "GATE01-ADJ-2026-08-13-001",
        "gate_id": "GATE-01",
        "status": "ISSUED",
        "approved_by": "owner",
        "consumption": {
            "status_values": ["ISSUED", "CONSUMED", "REVOKED"],
            "$must_be_stamped_after_merge_ar": "اختمه بعد الدمج.",
        },
        "allowed_paths": ["docs/architecture/db_ownership.yml"],
        "authorized_blobs": {"docs/architecture/db_ownership.yml": "abc123"},
    }
    target.write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git("add", str(rel), cwd=repo)
    _git("commit", "-m", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    target.write_text(json.dumps(after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return repo, base


def test_touching_the_authorization_path_requires_code_owner_review(tmp_path):
    """PR تُصدِر تفويضاً ومراجعةُ مالكي الكود غير مفروضة ⇒ حجب."""
    assert _run_changed(tmp_path, _envelope(_rules(True)), [ADJUDICATION]) == 1


def test_touching_the_authorization_path_passes_when_code_owners_are_required(tmp_path):
    assert _run_changed(tmp_path, _envelope(_rules_with_code_owner(True)), [ADJUDICATION]) == 0


def test_an_unrelated_pr_is_not_blocked_by_the_conditional_term(tmp_path):
    """البند مشروط بالمسّ — وإلّا حجب كلّ دمجٍ في المستودع على إعدادٍ لا يملكه وكيل.

    وهذا هو الفرق بين حمايةٍ متناسبة و«أساسٍ يُدرَّب قارئه على تعطيله».
    """
    assert _run_changed(tmp_path, _envelope(_rules(True)), ["README.md"]) == 0


def test_a_missing_code_owner_key_is_not_read_as_enabled(tmp_path):
    """الغياب مخالفةٌ لا سكوت — نفس قاعدة البند الدائم."""
    assert _run_changed(tmp_path, _envelope(_rules(True)), [ADJUDICATION]) == 1


def test_a_policy_change_alone_does_not_trigger_the_term(tmp_path):
    """الشرط على مسار **نُسخ التفويض** لا على كلّ ما في `docs/architecture`.

    وسياسةُ البوّابة نفسها يحرسها `claim_base_guard` ومسحُ المستوى الأعلى — فتوسيعُ
    هذا الشرط إليها كان سيُضاعِف الحجب بلا قياسٍ يُبرّره.
    """
    assert MOD.touches_authorization(["docs/architecture/gate01_policy.json"]) is False
    assert MOD.touches_authorization([ADJUDICATION]) is True


def test_a_consumption_only_seal_does_not_trigger_the_conditional_term(tmp_path, monkeypatch):
    after = {
        "schema": "sahool.gate01_adjudication/v1",
        "version": 1,
        "adjudication_id": "GATE01-ADJ-2026-08-13-001",
        "gate_id": "GATE-01",
        "status": "CONSUMED",
        "approved_by": "owner",
        "consumption": {
            "status_values": ["ISSUED", "CONSUMED", "REVOKED"],
            "$must_be_stamped_after_merge_ar": "اختمه بعد الدمج.",
            "merge_sha": SHA,
            "consumed_on": "2026-09-04",
            "$consumption_record_ar": "خُتِم بعد الدمج.",
        },
        "allowed_paths": ["docs/architecture/db_ownership.yml"],
        "authorized_blobs": {"docs/architecture/db_ownership.yml": "abc123"},
    }
    repo, base = _init_authorization_repo(tmp_path, after)
    monkeypatch.chdir(repo)
    assert (
        _run_changed(
            tmp_path,
            _envelope(_rules(True)),
            [ADJUDICATION],
            "--authorization-diff-base",
            base,
        )
        == 0
    )


def test_a_consumption_stamp_plus_scope_change_still_requires_code_owner_review(
    tmp_path, monkeypatch
):
    after = {
        "schema": "sahool.gate01_adjudication/v1",
        "version": 1,
        "adjudication_id": "GATE01-ADJ-2026-08-13-001",
        "gate_id": "GATE-01",
        "status": "CONSUMED",
        "approved_by": "owner",
        "consumption": {
            "status_values": ["ISSUED", "CONSUMED", "REVOKED"],
            "$must_be_stamped_after_merge_ar": "اختمه بعد الدمج.",
            "merge_sha": SHA,
            "consumed_on": "2026-09-04",
        },
        "allowed_paths": [
            "docs/architecture/db_ownership.yml",
            "migrations/MANIFEST.txt",
        ],
        "authorized_blobs": {
            "docs/architecture/db_ownership.yml": "abc123",
            "migrations/MANIFEST.txt": "def456",
        },
    }
    repo, base = _init_authorization_repo(tmp_path, after)
    monkeypatch.chdir(repo)
    assert (
        _run_changed(
            tmp_path,
            _envelope(_rules(True)),
            [ADJUDICATION],
            "--authorization-diff-base",
            base,
        )
        == 1
    )


def test_a_consumption_stamp_with_malformed_date_still_requires_code_owner_review(
    tmp_path, monkeypatch
):
    after = {
        "schema": "sahool.gate01_adjudication/v1",
        "version": 1,
        "adjudication_id": "GATE01-ADJ-2026-08-13-001",
        "gate_id": "GATE-01",
        "status": "CONSUMED",
        "approved_by": "owner",
        "consumption": {
            "status_values": ["ISSUED", "CONSUMED", "REVOKED"],
            "$must_be_stamped_after_merge_ar": "اختمه بعد الدمج.",
            "merge_sha": SHA,
            "consumed_on": "tomorrow",
        },
        "allowed_paths": ["docs/architecture/db_ownership.yml"],
        "authorized_blobs": {"docs/architecture/db_ownership.yml": "abc123"},
    }
    repo, base = _init_authorization_repo(tmp_path, after)
    monkeypatch.chdir(repo)
    assert (
        _run_changed(
            tmp_path,
            _envelope(_rules(True)),
            [ADJUDICATION],
            "--authorization-diff-base",
            base,
        )
        == 1
    )


def test_a_consumption_stamp_with_impossible_calendar_date_still_requires_code_owner_review(
    tmp_path, monkeypatch
):
    after = {
        "schema": "sahool.gate01_adjudication/v1",
        "version": 1,
        "adjudication_id": "GATE01-ADJ-2026-08-13-001",
        "gate_id": "GATE-01",
        "status": "CONSUMED",
        "approved_by": "owner",
        "consumption": {
            "status_values": ["ISSUED", "CONSUMED", "REVOKED"],
            "$must_be_stamped_after_merge_ar": "اختمه بعد الدمج.",
            "merge_sha": SHA,
            "consumed_on": "2026-99-99",
        },
        "allowed_paths": ["docs/architecture/db_ownership.yml"],
        "authorized_blobs": {"docs/architecture/db_ownership.yml": "abc123"},
    }
    repo, base = _init_authorization_repo(tmp_path, after)
    monkeypatch.chdir(repo)
    assert (
        _run_changed(
            tmp_path,
            _envelope(_rules(True)),
            [ADJUDICATION],
            "--authorization-diff-base",
            base,
        )
        == 1
    )


def test_an_unreadable_changed_file_list_fails_closed(tmp_path):
    """راية مُمرَّرة لملفٍّ غير موجود تعني أنّ الاشتقاق لم يعمل — لا أنّ شيئاً لم يُمَسّ."""
    with pytest.raises(SystemExit):
        MOD.main(
            [
                "--protection-file",
                str(_protection(tmp_path, _ENABLED)),
                "--expect-repository",
                REPO,
                "--expect-sha",
                SHA,
                "--changed-files",
                str(tmp_path / "absent.txt"),
            ]
        )


def test_codeowners_names_the_authorization_path() -> None:
    """الملفّ خاملٌ بلا الإعداد — لكنّ غيابَه يجعل الإعداد بلا مالكٍ يُراجع.

    فيُفحَص وجودُ السطر، **ولا يُقرأ تفعيلاً**: التفعيل يقيسه البند المشروط أعلاه على
    القواعد النافذة فعلاً.
    """
    codeowners = (Path(__file__).resolve().parents[1] / ".github/CODEOWNERS").read_text(
        encoding="utf-8"
    )
    owned = [
        line
        for line in codeowners.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert any("gates/adjudications" in line and "@" in line for line in owned)


# ── REQUIRED-CHECKS-DRIFT-IS-INVISIBLE-IN-BOTH-DIRECTIONS-01: سطحُ الإنفاذ ──


def test_the_contract_matches_the_live_enforcement_shape(tmp_path):
    """المرساة المقابلة: نموذجٌ سياقاتُه = العقد يمرّ — وإلّا كان ما تحته يرفض دائماً."""
    assert _run(_protection(tmp_path, _envelope(_rules(True)))) == 0


def test_a_context_missing_from_enforcement_is_a_silent_advisory_gate(tmp_path, capsys):
    """**العطل المخيف:** سياقٌ يسقط من الـRuleset ⇒ بوّابتُه تحمرّ ولا تحجب."""
    contexts = [c for c in _canonical() if c != "Unit Tests"]
    envelope = _envelope(_rules(True, checks=_checks_rule(contexts)))
    assert _run(_protection(tmp_path, envelope)) == 1
    out = capsys.readouterr().out
    assert "Unit Tests" in out
    assert "إرشاديّةٌ صامتة" in out


def test_an_enforced_context_absent_from_the_contract_is_a_failure(tmp_path, capsys):
    """الاتّجاه الآخر: اسمٌ مفروضٌ لا تُبلِّغه وظيفة يُعلِّق كلّ PR إلى الأبد."""
    envelope = _envelope(_rules(True, checks=_checks_rule([*_canonical(), "Ghost Check"])))
    assert _run(_protection(tmp_path, envelope)) == 1
    assert "Ghost Check" in capsys.readouterr().out


def test_no_required_status_checks_rule_means_nothing_blocks(tmp_path, capsys):
    """قاعدةٌ غائبة = **لا فحص يحجب**، وخضرةُ البوّابات كلّها إرشاديّة.

    **ويقيس السببَ لا رمزَ الخروج — مقيسٌ بالزرع لا مفترَض:** نزعُ الفرع المبكر
    يُسقِط الحالة في فرع «سياقاتٌ ناقصة» فيبقى الرمز `1` وتمرّ الطفرة صامتةً (وقع
    فعلاً في أوّل صياغة). فالمُثبَت هو **الرسالة المميِّزة** — نفس درس
    `test_no_pull_request_rule_is_a_failure` المكتوب فوقه.
    """
    rules = [r for r in _rules(True) if r.get("type") != "required_status_checks"]
    assert _run(_protection(tmp_path, _envelope(rules))) == 1
    out = capsys.readouterr().out
    assert "لا قاعدة `required_status_checks` نافذة" in out
    assert "لا فحص" in out, "التشخيص يجب أن يقول «لا شيء يحجب» لا «سياقاتٌ ناقصة»"


def test_unreadable_check_parameters_are_not_read_as_enforcement(tmp_path):
    """قاعدةٌ بلا `parameters` مقروءة لا تُقرأ إنفاذاً — فاشل-مغلق لا تخطٍّ صامت."""
    broken = {"type": "required_status_checks", "ruleset_source_type": "Repository"}
    assert _run(_protection(tmp_path, _envelope(_rules(True, checks=broken)))) == 1
    scalar = {"type": "required_status_checks", "parameters": {"required_status_checks": {}}}
    assert _run(_protection(tmp_path, _envelope(_rules(True, checks=scalar)))) == 1


def test_the_contract_file_is_the_single_source_read_by_both_readers():
    """العقد ملفُّ بياناتٍ واحد — والاختبارُ الآخر يقرؤه هو نفسه (لا نسخة ثانية)."""
    pipeline_test = (ROOT / "tests_v9/test_ci_pipeline_settings.py").read_text(encoding="utf-8")
    assert "required_status_checks_contract.json" in pipeline_test
    contexts = _canonical()
    assert len(contexts) == len(set(contexts)), "تكرارٌ في العقد يجعل المساواة كاذبة"
    assert "Frontend E2E (Playwright · MapLibre/WebGL QA)" in contexts, (
        "الاسم الخامس عشر المقيس على الـRuleset — غيابُه هو الانحراف الذي فُتِح العقد لأجله"
    )
