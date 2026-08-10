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
import json
import sys
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


def _protection(tmp_path: Path, document) -> Path:
    path = tmp_path / "protection.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _run(path: Path) -> int:
    return MOD.main(["--protection-file", str(path)])


def _rules(resolution, *, with_params: bool = True) -> list:
    """قواعد نافذة نموذجيّة: حذف + عدم-تقديم + قاعدة PR تحمل الشرط."""
    pull_request: dict = {"type": "pull_request", "ruleset_source_type": "Repository"}
    if with_params:
        pull_request["parameters"] = {
            "required_approving_review_count": 0,
            "required_review_thread_resolution": resolution,
        }
    return [{"type": "deletion"}, {"type": "non_fast_forward"}, pull_request]


_ENABLED = _rules(True)


def test_the_enabled_lock_passes(tmp_path):
    """المرساة المقابلة: بلا هذا قد تمرّ كلّ التكذيبات لأنّ الحارس يرفض دائماً."""
    assert _run(_protection(tmp_path, _ENABLED)) == 0


def test_conversation_resolution_disabled_is_a_failure(tmp_path):
    """**الحالة التي وقعت مرّتين:** القفل مُطفَأ، فزرُّ الدمج يعمل والخيوط مفتوحة.

    #810 دُمِج قبل وصول `REQUEST_CHANGES`، و#816 بعد إنشاء التعليقين بـ٤١ ثانية.
    والفرق بين الحالتين لا يعني شيئاً للقفل: كلتاهما كانت ستُمنَع.
    """
    assert _run(_protection(tmp_path, _rules(False))) == 1


def test_a_missing_key_is_not_read_as_enabled(tmp_path):
    """**الغياب «لم يُقرأ» لا «مُفعَّل».**

    قاعدة `pull_request` نافذة لكنّ `parameters` لا تحمل الشرط — إصدارُ API تغيّر، أو
    رمزٌ رأى حقولاً جزئيّة. تُقرأ قبولاً إن كان الافتراضيّ متساهلاً، وهذا بعينه «نتيجةٌ
    عن سؤالٍ لم يُطرَح»: الصنف الذي عولج ستّ مرّات في الشريحة التي أنشأت هذه الفجوة.
    """
    rules = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}]
    assert _run(_protection(tmp_path, rules)) == 1


def test_no_pull_request_rule_is_a_failure(tmp_path, capsys):
    """**قواعد نافذة بلا قاعدة `pull_request` ⇒ لا شيء يشترط حلّ المحادثات.**

    حالةٌ يُنتجها الشكل الجديد وحده: الفرع محميّ من الحذف والدفع القسريّ (فالاستجابة
    ليست فارغة ولا خطأً) بينما شرطُ المراجعة غائبٌ تماماً. قراءةُ «ثمّة قواعد» قبولاً
    تُبلِّغ خضرةً عن حمايةٍ لا تشمل المقصود.

    **ويقيس السببَ لا رمزَ الخروج وحده — عن عمد:** نزعُ هذا الفحص يُسقِط الحالة في فرع
    «`parameters` غائبة» التالي، فيبقى الرمز `1` وتمرّ الطفرة صامتةً. ورمزُ خروجٍ صحيح
    عن سببٍ خاطئ هو نفسه «نتيجةٌ صحيحة عن سؤالٍ لم يُطرَح».
    """
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}]
    assert _run(_protection(tmp_path, rules)) == 1
    assert "لا قاعدة" in capsys.readouterr().out


def test_an_empty_rule_set_is_a_failure(tmp_path):
    """لا قواعد أصلاً ⇒ الفرع بلا حماية نافذة. القائمة الفارغة ليست موافقة."""
    assert _run(_protection(tmp_path, [])) == 1


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
    assert _run(_protection(tmp_path, _rules(value))) == 1, label


def test_one_enabling_rule_among_several_is_enough(tmp_path):
    """**الاتّحاد لا التقاطع:** GitHub يطبّق الأشدّ حين تنفُذ قواعد متعدّدة.

    فقاعدةٌ من Ruleset تُفعّل الشرط وأخرى كلاسيكيّة لا تُفعّله ⇒ الشرط **نافذ**.
    ولو قرأناها تقاطعاً لأبلغنا أحمرَ عن قفلٍ قائم — إنذارٌ كاذب يُدرِّب قارئه على التجاهل.
    """
    rules = [
        {"type": "pull_request", "parameters": {"required_review_thread_resolution": False}},
        {"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
    ]
    assert _run(_protection(tmp_path, rules)) == 0


def test_an_unreadable_protection_file_fails_closed(tmp_path):
    """**«لم يُقرأ» ليس «مضبوط».**

    رمزٌ بلا صلاحية قراءة القواعد، أو خطوةُ جلبٍ لم تُنفَّذ، يُنتِجان ملفّاً غائباً أو
    استجابة خطأ — وهي الحالة المرجَّحة عند سوء الإعداد لا حالةٌ نادرة. وقبولُها يجعل
    الحارس أخضرَ **بالضبط حين لا يُقاس شيء**.
    """
    with pytest.raises(SystemExit):
        _run(tmp_path / "لا-وجود-له.json")

    broken = tmp_path / "protection.json"
    broken.write_text("{ليس JSON", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run(broken)


def test_a_non_object_response_is_rejected(tmp_path):
    """استجابةٌ ليست قائمة (كائن خطأ من GitHub مثلاً) لا تُقرأ عقداً.

    `{"message": "Not Found"}` هو بالضبط ما تُعيده النقطة عند خطأ صلاحيّة أو مسار —
    وقراءتُه كائنَ قواعد تُنتِج قبولاً صامتاً.
    """
    with pytest.raises(SystemExit):
        _run(_protection(tmp_path, {"message": "Not Found", "status": "404"}))


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
    """
    body = _SCRIPT.read_text(encoding="utf-8")
    for token in ("api.github.com", "requests.", "urllib", "httpx", "subprocess"):
        assert token not in body, f"وصولُ شبكةٍ داخل الحارس: {token!r}"
