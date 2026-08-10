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
merging`` على حماية ``main`` يُعطّل زرّ الدمج نفسه. وهذا المستودع **لا يُدير الحماية
كأكواد**: لا ``CODEOWNERS`` ولا ``.github/settings.yml`` ولا ruleset — مقيس.

**فما يفعله هذا الحارس بالضبط:** لا يمنع دمجاً ولا يرى خيطاً. يمنع أن **يُطفَأ القفل
صامتاً** بعد تفعيله: يُحوِّل إعداداً غير مرئيّ في واجهةٍ إلى **قياسٍ أحمر** في CI.

وله سابقةٌ عاملة في هذا المستودع تُنسَخ بنيتُها لا فكرتها:
``.github/workflows/runtime-verification-promotion.yml`` يجلب بيئة الموافقة بـ``gh api``
ثمّ يؤكّد أنّ ``protection_rules`` تحمل ``required_reviewers`` غير فارغة.

**ولماذا الحكم هنا والشبكة هناك:** ``scripts/ci/**`` لا يستدعي GitHub في هذا المستودع
إطلاقاً (مقيس)، والوظيفة وحدها تجلب. وهذا يُرضي درسين متعارضين معاً — منطقٌ مدفون في
``run: |`` لا يُقاس إلّا بتشغيل الوظيفة كاملةً (درس ``resilient_docker_pull.sh``)، وحالةُ
GitHub لا تدخل أداةً محلّيّة (عقد ``test_local_preflight_contract``). فالوظيفة تُجسّد
الاستجابة في ملفّ، والحارس يحكم عليه — تماماً كما يفعل
``pr_capability_impact_gate.py --pr-body-file``.

    gh api "repos/${REPO}/branches/main/protection" > protection.json
    python scripts/ci/branch_protection_contract_guard.py --protection-file protection.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: البند الوحيد المفروض. **ولا يُوسَّع إلى جردٍ عامّ للحماية عمداً:** جردٌ يَبيت مع كلّ
#: تغيير إعدادٍ مشروع يُدرَّب قارئه على تجاهله فيُبطِل الحارس بدل أن يُشدّده — وهو الخطأ
#: الموصوف حرفيّاً في عقد `live_pg_schema_contract`. الفجوة المفتوحة واحدة، فالمفروض واحد.
CONTRACT_KEY = "required_conversation_resolution"

#: نصّ العلاج — يُطبَع مع الفشل لأنّ من يقرأ الأحمر يجب أن يعرف أين يذهب.
REMEDY = (
    "العلاج في إعدادات GitHub لا في هذا المستودع:\n"
    "  Settings → Branches → main → Require conversation resolution before merging\n"
    "  ولا يُغني عنه انضباطٌ يدويّ: خيطٌ يُفتَح بين القراءة والدمج لا يراه من قرأ قبله."
)


def _load(path: Path) -> dict:
    """الفشل المغلق يبدأ من القراءة.

    ملفٌّ غائب أو غير قابل للتحليل يعني أنّ **الاستجابة لم تُقرأ** — لا أنّ الحماية
    مضبوطة. ورمزٌ بلا صلاحية قراءة الحماية يُعيد استجابة خطأ لا عقداً، فتقع هنا.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"✗ لا ملفّ حماية في {path} — لم تُجلَب الاستجابة أصلاً.\n"
            "  للصلاحية خياران: منح `permissions: administration: read` للوظيفة، أو "
            "استخدام سرٍّ بصلاحية قراءة الحماية كما في `RUNTIME_VERIFICATION_ENV_AUDITOR_TOKEN`."
        ) from None
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ تعذّرت قراءة {path}: {exc} — «لم يُقرأ» ليس «مضبوط».") from None
    if not isinstance(document, dict):
        raise SystemExit(f"✗ {path} ليس كائن JSON — استجابةٌ لا تُفهَم فشلٌ لا قبول.")
    return document


def violations(document: dict) -> list[str]:
    """المخالفات — والغياب مخالفةٌ لا سكوت.

    **ولا يُقرأ المفتاح الغائب قبولاً:** استجابةٌ لا تحمل `required_conversation_resolution`
    تعني أنّ الحقل لم يُرَ، وقراءتُه «مُفعَّل» هي بعينها «نتيجةٌ عن سؤالٍ لم يُطرَح» —
    الصنف الذي عولج ستّ مرّات في الشريحة التي أنشأت هذه الفجوة.
    """
    found: list[str] = []

    block = document.get(CONTRACT_KEY)
    if not isinstance(block, dict):
        found.append(
            f"`{CONTRACT_KEY}` غائب عن استجابة الحماية أو ليس كائناً — "
            "والغياب يعني «لم يُقرأ»، لا «مُفعَّل»."
        )
        return found

    enabled = block.get("enabled")
    if enabled is not True:
        found.append(
            f"`{CONTRACT_KEY}.enabled` = {enabled!r} — القفل غير مُفعَّل. "
            "زرُّ الدمج يعمل وخيوط المراجعة مفتوحة."
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--protection-file",
        type=Path,
        required=True,
        help="استجابة `gh api repos/<owner>/<repo>/branches/main/protection` مُجسَّدةً في ملفّ",
    )
    args = parser.parse_args(argv)

    problems = violations(_load(args.protection_file))
    if problems:
        print("branch_protection_contract_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(f"\n{REMEDY}")
        return 1

    print(f"branch_protection_contract_guard: PASS ({CONTRACT_KEY} مُفعَّل على الفرع المحميّ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
