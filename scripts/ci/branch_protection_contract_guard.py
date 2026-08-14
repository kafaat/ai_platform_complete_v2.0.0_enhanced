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

**والدليل يُربَط بمصدره وإلّا لم يكن دليلاً:** الصياغة الأولى قبلت **مصفوفة قواعد عارية**،
فكانت خضرتها تقول «قواعدُ ما، من مكانٍ ما، في وقتٍ ما» — وملفٌّ لفرعٍ آخر أو لمستودعٍ آخر
أو من تشغيلٍ سابق يمرّ منها بلا أثر. فصار المقروء **ظرفَ دليل** يحمل: النقطة المُستدعاة
حرفيّاً · رمز HTTP الذي أعادته · المستودع · الفرع · و`commit_sha` المقيس عنده. ويُطابَق
كلٌّ منها بما يتوقّعه الحارس: الفرع **مثبَّتٌ في الكود** (`main`) فلا يُعاد توجيهه بمعامل،
والمستودع والـSHA يأتيان من سياق GitHub، والحالة يجب أن تكون `200` **بعينها**.

**ولماذا رمز HTTP بندٌ في العقد لا تفصيلاً في الصدفة:** `401/403` تعني رمزاً بلا صلاحية،
و`404` مستودعاً أو فرعاً غير المقصود، و`429` خنقاً، و`5xx` عطلاً عند GitHub — وكلّها
تُنتِج **جسماً صالح البنية** لا مصفوفة قواعد. فلو تُرك الحكم لـ`set -e` في الصدفة لصار
منطقاً مدفوناً لا يُقاس إلّا بتشغيل الوظيفة كاملةً؛ وهو الدرس نفسه الذي أخرج الحكم من
`run: |` أصلاً. فالوظيفة تُسجّل الحالة كما هي، والحارس يحكم — و«لم يُقرأ» يبقى فشلاً.

**وحدّ صدقٍ يُقال صراحةً:** هذا يربط الدليل بـ**ما أعلنه المُشغِّل** عن نداءٍ جرى، لا
يشهد بأنّ المُشغِّل صدق. الشاهدُ على ذلك هو حدود الثقة في CI نفسها (سرٌّ لا يُقرأ من
الخارج، وسجلّ تشغيل قابل للتدقيق) — لا هذا الملفّ. وما يمنعه فعليّاً: دليلٌ من SHA سابق،
ودليلٌ لفرعٍ أو مستودعٍ آخر، ودليلٌ عن استجابة ليست `200`.

**ولماذا الحكم هنا والشبكة هناك:** ``scripts/ci/**`` لا يستدعي GitHub في هذا المستودع
إطلاقاً (مقيس)، والوظيفة وحدها تجلب. وهذا يُرضي درسين متعارضين معاً — منطقٌ مدفون في
``run: |`` لا يُقاس إلّا بتشغيل الوظيفة كاملةً (درس ``resilient_docker_pull.sh``)، وحالةُ
GitHub لا تدخل أداةً محلّيّة (عقد ``test_local_preflight_contract``). فالوظيفة تُجسّد
الاستجابة في ملفّ، والحارس يحكم عليه — تماماً كما يفعل
``pr_capability_impact_gate.py --pr-body-file``.

    # الوظيفة تجلب وتُسجّل الحالة كما هي (لا تحكم):
    status=$(curl -sS -o rules.json -w '%{http_code}' -H "Authorization: Bearer $GH_TOKEN" \\
             "https://api.github.com/repos/${REPO}/rules/branches/main")
    jq -n --arg repo "$REPO" --arg sha "$SHA" --argjson code "$status" \\
       --slurpfile rules rules.json '{…}' > protection.json
    python scripts/ci/branch_protection_contract_guard.py --protection-file protection.json \\
      --expect-repository "$REPO" --expect-sha "$SHA"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: نسخة ظرف الدليل. تغييرُ شكل الظرف يُبطِل الأدلّة القديمة صراحةً بدل أن يُقرأ نقصُها قبولاً.
EVIDENCE_SCHEMA = "sahool.branch-protection-evidence.v1"

#: الفرع المُتعاقَد عليه — **مثبَّتٌ في الكود عمداً**. لو صار معاملاً لأمكن توجيه الحارس
#: إلى فرعٍ محميّ آخر فيخضرّ عن سؤالٍ ليس هو السؤال؛ والعقد بندُه «الفرع الافتراضيّ».
CONTRACT_BRANCH = "main"

#: الحالة الوحيدة التي تعني «قُرِئت القواعد». كلّ ما عداها استجابةٌ عن شيء آخر.
CONTRACT_HTTP_STATUS = 200

#: تفسير أصناف الفشل الشبكيّ — من يقرأ الأحمر يجب أن يعرف أيّ علاجٍ يخصّه.
HTTP_MEANING = {
    401: "رمزٌ غائب أو منتهٍ",
    403: "رمزٌ بلا صلاحية قراءة قواعد المستودع (أو مُقيَّد بـSSO)",
    404: "مستودعٌ أو فرعٌ غير موجود — أو النقطة خاطئة",
    429: "خنقٌ من GitHub (rate limit) — أعِد المحاولة، ولا تقرأه قبولاً",
}

#: بصمة الالتزام: أربعون خانة سِتّ-عشريّة. أيّ شكلٍ آخر يعني حقلاً لم يُملأ صحيحاً.
_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")

#: نوع القاعدة التي تحمل شروط الـPR في استجابة القواعد النافذة.
CONTRACT_RULE_TYPE = "pull_request"

#: البند الوحيد المفروض — اسمه في الـRulesets مقابل `required_conversation_resolution`
#: في الحماية الكلاسيكيّة. **ولا يُوسَّع إلى جردٍ عامّ للحماية عمداً:** جردٌ يَبيت مع كلّ
#: تغيير إعدادٍ مشروع يُدرَّب قارئه على تجاهله فيُبطِل الحارس بدل أن يُشدّده — وهو الخطأ
#: الموصوف حرفيّاً في عقد `live_pg_schema_contract`. الفجوة المفتوحة واحدة، فالمفروض واحد.
CONTRACT_PARAMETER = "required_review_thread_resolution"

#: البند **المشروط** — يُفرَض حين تمسّ الـPR مسارَ التفويضات وحدها.
#: `GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01`: طبقة AUTHORIZATION في GATE-01 تقرأ
#: `approved_by: owner` من ملفٍّ **في نفس الـPR**، فمن يحتاج التفويض يستطيع إصداره.
#: والفرق عن البند أعلاه أنّ هذا **مشروط بالمسّ** لا دائم: بندٌ دائم يحجب كلّ دمجٍ في
#: المستودع حتّى يُفعَّل إعدادٌ لا يملكه وكيل، وذلك ثمنٌ لا تُبرّره فجوةٌ نطاقُها ملفّان.
#: فالحجب يقع **على الفعل الذي يحتاج الحماية**: إصدارُ تفويضٍ لا يمرّ إلّا ومراجعةُ
#: مالكي الكود مفروضة فعليّاً على الفرع.
CODE_OWNER_PARAMETER = "require_code_owner_review"

#: المسار المحميّ — وهو نفسه ما يقرؤه `gate01_frozen_path_guard` تفويضاً.
AUTHORIZATION_PATH = "docs/architecture/gates/adjudications/"

#: نصّ العلاج — يُطبَع مع الفشل لأنّ من يقرأ الأحمر يجب أن يعرف أين يذهب.
REMEDY = (
    "العلاج في إعدادات GitHub لا في هذا المستودع:\n"
    "  Rulesets → قاعدة على main → Require a pull request before merging\n"
    "            → Require conversation resolution before merging\n"
    "  (أو Branch protection rules الكلاسيكيّة — كلتاهما تظهران في القواعد النافذة)\n"
    "  وتأكّد أنّ Enforcement status = Active: قاعدةٌ Disabled تُعرَض مضبوطةً ولا تفرض شيئاً.\n"
    "  ولا يُغني عنه انضباطٌ يدويّ: خيطٌ يُفتَح بين القراءة والدمج لا يراه من قرأ قبله.\n"
    "\n"
    "وإن كان الفشل على البند المشروط (مسّ مسار التفويضات):\n"
    "  Rulesets → قاعدة على main → Require review from Code Owners\n"
    "  و`.github/CODEOWNERS` يُسمّي مالك `docs/architecture/gates/adjudications/**`.\n"
    "  الملفّ وحده **خامل**: بلا الإعداد يبقى مظهرَ حمايةٍ بلا حماية — ولذلك يُقاس\n"
    "  الإعدادُ نفسه هنا، ولا يُقرأ وجودُ الملفّ تفعيلاً."
)


def _load(path: Path) -> dict:
    """الفشل المغلق يبدأ من القراءة.

    ملفٌّ غائب أو غير قابل للتحليل يعني أنّ **الاستجابة لم تُقرأ** — لا أنّ الحماية
    مضبوطة. ورمزٌ بلا صلاحية قراءة القواعد يُعيد استجابة خطأ لا عقداً، فتقع هنا.

    **ومصفوفةٌ عارية تُرفض صراحةً:** هي شكل الدليل القديم، وقبولُها اليوم يعني قبولَ
    دليلٍ بلا مصدر — لفرعٍ آخر أو من تشغيلٍ سابق. الرفض يُسمّي الترقية بدل أن يُلمِّح.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"✗ لا ملفّ دليلٍ في {path} — لم تُجلَب الاستجابة أصلاً.\n"
            "  تحقّق من أنّ خطوة جلب `repos/<owner>/<repo>/rules/branches/main` نُفِّذت "
            "برمزٍ له صلاحية قراءة قواعد المستودع."
        ) from None
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ تعذّرت قراءة {path}: {exc} — «لم يُقرأ» ليس «مضبوط».") from None
    if isinstance(document, list):
        raise SystemExit(
            f"✗ {path} مصفوفةُ قواعد عارية — شكلُ الدليل القديم بلا مصدر.\n"
            f"  الدليل اليوم ظرفٌ `{EVIDENCE_SCHEMA}` يحمل endpoint وhttp_status "
            "وrepository وbranch وcommit_sha ثمّ rules. ومصفوفةٌ بلا مصدر تمرّ من "
            "فرعٍ آخر أو من تشغيلٍ سابق بلا أثر."
        )
    if not isinstance(document, dict):
        raise SystemExit(f"✗ {path} ليس كائن JSON — استجابةٌ لا تُفهَم فشلٌ لا قبول.")
    if document.get("schema_version") != EVIDENCE_SCHEMA:
        raise SystemExit(
            f"✗ {path}: `schema_version` = {document.get('schema_version')!r} "
            f"والمنتظَر {EVIDENCE_SCHEMA!r} — ظرفٌ لا يُعرَف شكلُه لا يُقرأ دليلاً."
        )
    return document


def evidence_violations(envelope: dict, *, expect_repository: str, expect_sha: str) -> list[str]:
    """مخالفات **المصدر** — قبل أيّ نظرٍ في القواعد نفسها.

    ترتيبُها مقصود: القواعد لا تُقرأ إطلاقاً ما لم يُثبَت أنّها قواعد **هذا** المستودع
    على **`main`** من **هذا** الـSHA وباستجابة `200`. فالسؤال «هل القفل مُفعَّل؟» لا
    معنى له قبل «قفلُ ماذا، قِيس متى؟».
    """
    found: list[str] = []

    status = envelope.get("http_status")
    if status != CONTRACT_HTTP_STATUS:
        meaning = HTTP_MEANING.get(status if isinstance(status, int) else 0)
        if meaning is None and isinstance(status, int) and 500 <= status < 600:
            meaning = "عطلٌ عند GitHub — استجابةٌ ليست قراءةً"
        tail = f" ({meaning})" if meaning else ""
        found.append(
            f"`http_status` = {status!r} والمنتظَر {CONTRACT_HTTP_STATUS}{tail} — "
            "استجابةٌ غير ناجحة تحمل جسماً صالح البنية ولا تحمل قواعد. «لم يُقرأ» ليس «مضبوط»."
        )

    repository = envelope.get("repository")
    if repository != expect_repository:
        found.append(
            f"`repository` = {repository!r} والمقصود {expect_repository!r} — "
            "دليلٌ عن مستودعٍ آخر ليس دليلاً عن هذا."
        )

    branch = envelope.get("branch")
    if branch != CONTRACT_BRANCH:
        found.append(
            f"`branch` = {branch!r} والعقد على {CONTRACT_BRANCH!r} — "
            "فرعٌ محميّ آخر يُخضِر الحارس عن سؤالٍ ليس هو السؤال."
        )

    expected_endpoint = f"repos/{expect_repository}/rules/branches/{CONTRACT_BRANCH}"
    endpoint = envelope.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.endswith(expected_endpoint):
        found.append(
            f"`endpoint` = {endpoint!r} ولا ينتهي بـ{expected_endpoint!r} — "
            "النقطة المُستدعاة هي ما قِيس فعلاً؛ حقلا repository/branch إعلانٌ، وهي القياس."
        )

    sha = envelope.get("commit_sha")
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        found.append(
            f"`commit_sha` = {sha!r} ليس بصمةً من أربعين خانة سِتّ-عشريّة صغيرة — "
            "حقلٌ لم يُملأ صحيحاً لا يربط الدليل بشيء."
        )
    elif sha != expect_sha:
        found.append(
            f"`commit_sha` = {sha} والمُختبَر {expect_sha} — "
            "دليلٌ من التزامٍ آخر (مصنوعٌ مُعاد استعماله أو تشغيلٌ سابق). "
            "الدليل يُقاس عند الـSHA الذي يُحكَم عليه."
        )

    if not isinstance(envelope.get("rules"), list):
        found.append(
            f"`rules` = {type(envelope.get('rules')).__name__} لا مصفوفة — "
            "القواعد النافذة تُعاد مصفوفةً؛ جسمُ خطأٍ في موضعها لا يُقرأ قواعد."
        )

    return found


def touches_authorization(changed: list[str]) -> bool:
    """هل تمسّ هذه الـPR مسارَ التفويضات؟ — الشرط الذي يُشغّل البند المشروط."""
    return any(name.startswith(AUTHORIZATION_PATH) for name in changed)


def code_owner_violations(rules: list) -> list[str]:
    """مخالفاتُ البند المشروط — تُقرأ فقط حين مُسّ مسارُ التفويضات.

    نفس منطق البند الدائم: **الاتّحاد لا التقاطع** (تكفي قاعدةٌ واحدة تُفعّله)، و**الغياب
    مخالفة لا سكوت** — قاعدةٌ بلا الشرط تعني أنّه لم يُرَ.
    """
    pr_rules = [r for r in rules if isinstance(r, dict) and r.get("type") == CONTRACT_RULE_TYPE]
    observed = [
        rule.get("parameters", {}).get(CODE_OWNER_PARAMETER)
        for rule in pr_rules
        if isinstance(rule.get("parameters"), dict)
    ]
    if any(value is True for value in observed):
        return []
    return [
        f"هذه الـPR تمسّ `{AUTHORIZATION_PATH}` و`{CODE_OWNER_PARAMETER}` = "
        f"{observed!r} — فالتفويض يُصدره من يحتاجه. طبقةُ AUTHORIZATION تقرأ "
        "`approved_by: owner` من ملفٍّ في نفس الـPR ولا تُثبِت منشأه؛ ومراجعةُ مالكي "
        "الكود هي ما يجعل المنشأ **هويّةً مستقلّة** لا حقلاً نصّيّاً."
    ]


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
        # جردُ ما رآه الرمز فعلاً يفصل سببين يتشابه أثرهما ويختلف علاجهما:
        # قائمةٌ فارغة ⇒ لا قاعدة نافذة أصلاً (أو الرمز لا يرى الـRulesets)، بينما
        # قواعدُ أخرى حاضرة ⇒ القاعدة نافذة ومرئيّة و«Require a pull request» غير مؤشَّر.
        seen = sorted({r.get("type") for r in rules if isinstance(r, dict) and r.get("type")})
        inventory = "، ".join(seen) if seen else "لا شيء — القائمة فارغة"
        found.append(
            f"لا قاعدة `{CONTRACT_RULE_TYPE}` نافذة على الفرع — "
            f"فلا شيء يشترط حلّ المحادثات. المرئيّ ({len(rules)}): {inventory}. "
            "والغياب يعني «لم يُقرأ»، لا «مُفعَّل»."
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
        help=f"ظرف الدليل ({EVIDENCE_SCHEMA}) الذي كتبته خطوة الجلب",
    )
    parser.add_argument(
        "--expect-repository",
        required=True,
        help="`owner/repo` المقصود — من سياق GitHub، ويُطابَق بالنقطة المُستدعاة فعلاً",
    )
    parser.add_argument(
        "--expect-sha",
        required=True,
        help="الالتزام المُختبَر — دليلٌ من SHA آخر يُرفَض",
    )
    parser.add_argument(
        "--changed-files",
        type=Path,
        help=(
            "ملفٌّ يحمل المسارات المُغيَّرة (سطرٌ لكلٍّ). حين تمسّ "
            f"`{AUTHORIZATION_PATH}` يُفرَض `{CODE_OWNER_PARAMETER}` أيضاً."
        ),
    )
    args = parser.parse_args(argv)

    changed: list[str] = []
    if args.changed_files:
        # الغياب فشلٌ لا تخطٍّ: راية مُمرَّرة لملفٍّ غير موجود تعني أنّ خطوة الاشتقاق
        # لم تعمل، وقراءةُ ذلك «لم تُمَسّ التفويضات» تُطفِئ البند بصمت.
        try:
            text = args.changed_files.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(
                f"✗ تعذّرت قراءة {args.changed_files}: {exc} — قائمةُ المسارات لم تُشتقّ، "
                "و«لم تُقرأ» ليست «لم تُمَسّ»."
            ) from None
        changed = [line.strip() for line in text.splitlines() if line.strip()]

    envelope = _load(args.protection_file)
    problems = evidence_violations(
        envelope,
        expect_repository=args.expect_repository,
        expect_sha=args.expect_sha,
    )
    # القواعد لا تُقرأ ما لم يُثبَت مصدرها — وإلّا صار الحكم على قواعدَ لا يُعرَف لِمَن هي.
    rules = envelope.get("rules")
    if not problems:
        problems = violations(rules)
        if touches_authorization(changed):
            problems += code_owner_violations(rules)

    if problems:
        print("branch_protection_contract_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(f"\n{REMEDY}")
        return 1

    # **الخضرة تُصرِّح بما فُحِص، لا تكتفي بأنّها خضراء:** خضرةٌ بلا عدّ لا يفرّق فيها
    # قارئُها بين «فُحِصت قاعدة فمرّت» و«لم يُفحَص شيء». والصفر يقع أعلاه فشلاً.
    pr_rules = [r for r in rules if isinstance(r, dict) and r.get("type") == CONTRACT_RULE_TYPE]
    print(
        f"branch_protection_contract_guard: PASS ({CONTRACT_PARAMETER} نافذ على "
        f"{args.expect_repository}@{CONTRACT_BRANCH} عند {args.expect_sha[:8]} — "
        f"فُحِصت {len(rules)} قاعدة نافذة، منها {len(pr_rules)} من نوع {CONTRACT_RULE_TYPE})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
