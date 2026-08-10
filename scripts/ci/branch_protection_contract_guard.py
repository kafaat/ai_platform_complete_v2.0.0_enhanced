#!/usr/bin/env python3
"""القفل الذي يمنع الدمج لا يعيش في المستودع — فيُدقَّق وجودُه.

``MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01``

**العطل المقيس مرّتين، لا مرّة:** #810 دُمِج قبل وصول ``REQUEST_CHANGES``، و#816 دُمِج
بعد إنشاء تعليقَي المراجعة بـ**٤١ ثانية** — والخيطان ``is_resolved=false`` وقتها،
والملاحظتان صحيحتان (عولجتا في #817). والدرس كان مكتوباً في ``sahool-brain/hot.md``
منذ 2026-08-07 بنصّه: «الاخضرار ليس إذناً بالدمج حين تكون المراجعة معلنة ومنتظَرة».

**فتكرارُه بعد تسجيله هو الدليل:** التسجيل لا يفرض. وقراءةُ الخيوط قبل الدمج انضباطٌ
يدويّ، والانضباط اليدويّ لا يُغلِق سباقاً — خيطٌ يُفتَح **بين** القراءة والدمج غير مرئيّ
لمن قرأ قبله بثوانٍ.

**والذي يُغلِقه إعدادٌ في GitHub لا كودٌ هنا:** ``Require conversation resolution before
merging`` يُعطّل زرّ الدمج نفسه.

**ولماذا القواعد النافذة لا الحماية الكلاسيكيّة — قياسٌ لا تفضيل:** أوّل صياغةٍ لهذا
الحارس قرأت ``branches/main/protection`` (الحماية الكلاسيكيّة). ولمّا فُعِّل القفل فعلاً —
عبر **Ruleset** باسم ``main-protection`` نافذاً على ``main`` — أجابت تلك النقطة
``Branch not protected (HTTP 404)`` (تشغيل 31407522822). أي أنّ الحارس كان يسأل عن
**آليّةٍ غير التي تُستعمَل**، فأحمرُه وأخضرُه كلاهما عن سؤالٍ خاطئ — وهو بعينه صنف
«نتيجةٌ صحيحة عن سؤالٍ لم يُطرَح» الذي وُجِد هذا الملفّ ليطارده.

فصار المقروء ``rules/branches/main``: **القواعد النافذة فعلاً** على الفرع، مجموعةً من
مصدرَيها معاً (الحماية الكلاسيكيّة + الـRulesets). فيقيس **ما ينفُذ** لا ما ضُبِط بآليّةٍ
بعينها — ولا ينكسر إن هاجر الفريق بين الآليّتين.

**وما يفعله هذا الحارس بالضبط:** لا يمنع دمجاً ولا يرى خيطاً. يمنع أن **يُطفَأ القفل
صامتاً** بعد تفعيله: يُحوِّل إعداداً غير مرئيّ في واجهةٍ إلى **قياسٍ أحمر** في CI.

**ولماذا الحكم هنا والشبكة هناك:** ``scripts/ci/**`` لا يستدعي GitHub في هذا المستودع
إطلاقاً (مقيس)، والوظيفة وحدها تجلب. وهذا يُرضي درسين متعارضين معاً — منطقٌ مدفون في
``run: |`` لا يُقاس إلّا بتشغيل الوظيفة كاملةً (درس ``resilient_docker_pull.sh``)، وحالةُ
GitHub لا تدخل أداةً محلّيّة (عقد ``test_local_preflight_contract``). فالوظيفة تُجسّد
الاستجابة في ملفّ، والحارس يحكم عليه — تماماً كما يفعل
``pr_capability_impact_gate.py --pr-body-file``.

    gh api "repos/${REPO}/rules/branches/main" > protection.json
    python scripts/ci/branch_protection_contract_guard.py --protection-file protection.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: نوع القاعدة التي تحمل شروط الـPR في استجابة القواعد النافذة.
CONTRACT_RULE_TYPE = "pull_request"

#: البند الوحيد المفروض — اسمه في الـRulesets مقابل `required_conversation_resolution`
#: في الحماية الكلاسيكيّة. **ولا يُوسَّع إلى جردٍ عامّ للحماية عمداً:** جردٌ يَبيت مع كلّ
#: تغيير إعدادٍ مشروع يُدرَّب قارئه على تجاهله فيُبطِل الحارس بدل أن يُشدّده — وهو الخطأ
#: الموصوف حرفيّاً في عقد `live_pg_schema_contract`. الفجوة المفتوحة واحدة، فالمفروض واحد.
CONTRACT_PARAMETER = "required_review_thread_resolution"

#: نصّ العلاج — يُطبَع مع الفشل لأنّ من يقرأ الأحمر يجب أن يعرف أين يذهب.
REMEDY = (
    "العلاج في إعدادات GitHub لا في هذا المستودع:\n"
    "  Rulesets → قاعدة على main → Require a pull request before merging\n"
    "            → Require conversation resolution before merging\n"
    "  (أو Branch protection rules الكلاسيكيّة — كلتاهما تظهران في القواعد النافذة)\n"
    "  وتأكّد أنّ Enforcement status = Active: قاعدةٌ Disabled تُعرَض مضبوطةً ولا تفرض شيئاً.\n"
    "  ولا يُغني عنه انضباطٌ يدويّ: خيطٌ يُفتَح بين القراءة والدمج لا يراه من قرأ قبله."
)


def _load(path: Path) -> list:
    """الفشل المغلق يبدأ من القراءة.

    ملفٌّ غائب أو غير قابل للتحليل يعني أنّ **الاستجابة لم تُقرأ** — لا أنّ الحماية
    مضبوطة. ورمزٌ بلا صلاحية قراءة القواعد يُعيد استجابة خطأ لا عقداً، فتقع هنا.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"✗ لا ملفّ قواعد في {path} — لم تُجلَب الاستجابة أصلاً.\n"
            "  تحقّق من أنّ خطوة `gh api repos/<owner>/<repo>/rules/branches/main` نُفِّذت "
            "برمزٍ له صلاحية قراءة قواعد المستودع."
        ) from None
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ تعذّرت قراءة {path}: {exc} — «لم يُقرأ» ليس «مضبوط».") from None
    if not isinstance(document, list):
        raise SystemExit(
            f"✗ {path} ليس قائمة JSON — القواعد النافذة تُعاد مصفوفةً؛ استجابةٌ لا تُفهَم فشلٌ لا قبول."
        )
    return document


def violations(rules: list) -> list[str]:
    """المخالفات — والغياب مخالفةٌ لا سكوت.

    **ولا يُقرأ الغائب قبولاً:** استجابةٌ بلا قاعدة `pull_request`، أو قاعدةٌ بلا
    `required_review_thread_resolution`، تعني أنّ الشرط **لم يُرَ** — وقراءتُه «مُفعَّل»
    هي بعينها «نتيجةٌ عن سؤالٍ لم يُطرَح».

    **والاتّحاد لا التقاطع:** قد تنفُذ أكثر من قاعدة `pull_request` على الفرع نفسه
    (Ruleset + حماية كلاسيكيّة، أو Rulesets متعدّدة)، وGitHub يطبّق **الأشدّ**. فيكفي
    أن تُفعّله واحدةٌ ليكون القفل قائماً فعليّاً.
    """
    found: list[str] = []

    pr_rules = [r for r in rules if isinstance(r, dict) and r.get("type") == CONTRACT_RULE_TYPE]
    if not pr_rules:
        found.append(
            f"لا قاعدة `{CONTRACT_RULE_TYPE}` نافذة على الفرع — "
            "فلا شيء يشترط حلّ المحادثات. والغياب يعني «لم يُقرأ»، لا «مُفعَّل»."
        )
        return found

    observed = [
        rule.get("parameters", {}).get(CONTRACT_PARAMETER)
        for rule in pr_rules
        if isinstance(rule.get("parameters"), dict)
    ]
    if not observed:
        found.append(
            f"قاعدة `{CONTRACT_RULE_TYPE}` نافذة بلا كتلة `parameters` مفهومة — "
            "الشرط لم يُرَ، والغياب ليس تفعيلاً."
        )
        return found

    if not any(value is True for value in observed):
        found.append(
            f"`{CONTRACT_PARAMETER}` = {observed!r} — القفل غير مُفعَّل. "
            "زرُّ الدمج يعمل وخيوط المراجعة مفتوحة."
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--protection-file",
        type=Path,
        required=True,
        help="استجابة `gh api repos/<owner>/<repo>/rules/branches/main` مُجسَّدةً في ملفّ",
    )
    args = parser.parse_args(argv)

    problems = violations(_load(args.protection_file))
    if problems:
        print("branch_protection_contract_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(f"\n{REMEDY}")
        return 1

    print(f"branch_protection_contract_guard: PASS ({CONTRACT_PARAMETER} نافذ على الفرع)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
