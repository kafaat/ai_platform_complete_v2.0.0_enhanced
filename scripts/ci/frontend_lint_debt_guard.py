#!/usr/bin/env python3
"""تحذيرُ الواجهة دَينٌ — والدَّينُ يُحرَس أو ينمو صامتاً.

``FRONTEND-LINT-DEBT-UNGUARDED-01``

**العطل الذي يحرسه:** ``eslint`` في هذا المستودع يُبلِّغ **تحذيراً** لا خطأً على
``no-explicit-any`` و``no-unused-vars``. فوظيفة *Frontend Typecheck* تخرج **خضراء**
وفيها مئةُ تحذير — وGitHub يعرض عشرةً منها فقط في التعليقات، فيقرأ المالك «عشرة»
والواقع مئة. أي أنّ العدّاد **غير مرئيّ** وغير محجوب معاً.

**ولا يُرفَع إلى خطأ دفعةً واحدة:** ٨٢ خطأً تُوقِف كلّ عمل الواجهة، والإصلاح الصحيح
لـ``any`` تصميمُ نوعٍ لا استبدالُ كلمة. فالمُختار راتشِت: العدد المقيس سقفٌ **ينزل ولا
يصعد**، والفائض يُحمِر برسالةٍ تسمّي القاعدة والملفّات الجديدة.

**وثلاثة بنود لا واحد:**

1. **لا يزيد الإجماليّ عن السقف** — تحذيرٌ جديد يُحجَب عند إدخاله لا بعد شهور.
2. **لا يقلّ عنه بلا خفض السقف** — سقفٌ مُرتخٍ يبتلع عودة الدَّين صامتاً، وهو درسُ
   ``visual_fixme_baseline_guard`` نفسه بعد أن قِيس هناك.
3. **لا تظهر قاعدةٌ جديدة** — سقفٌ إجماليّ وحده يسمح باستبدال ``any`` بصنفٍ أسوأ ما دام
   المجموع ثابتاً. فالسقف **لكلّ قاعدة**.

**حدّ الصدق:** هذا يحرس **تراكم** الدَّين لا يُصلحه. الـ٨٢ الباقية دَينٌ مفتوح:
٤٦ ``any`` تحتاج تصميم أنواع، و٣٦ متغيّراً غير مستعمَل يحتاج كلٌّ منها قراءةً
(المُهمَل قد يكون خطأً حقيقيّاً: حالةٌ تُضبَط ولا تُقرأ).
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

#: السقف المقيس لكلّ قاعدة — **راتشِت**: يُخفَّض عند سداد دَين، ولا يُرفَع إلّا
#: بمُحاكَمة مكتوبة. القيم من تشغيلٍ نظيف على `71d019fc` بعد إزالة عشرة توجيهات
#: تعطيلٍ لا تُخمِد شيئاً وثلاثة استيرادات ميّتة خلّفها تفكيك `api.ts`.
BASELINE: dict[str, int] = {
    "@typescript-eslint/no-explicit-any": 46,
    "@typescript-eslint/no-unused-vars": 36,
}

#: سببُ بقاء كلٍّ منها — عددٌ بلا سبب يُنقَل بين الأجيال بلا معنى.
WHY: dict[str, str] = {
    "@typescript-eslint/no-explicit-any": (
        "إصلاحُها تصميمُ نوعٍ لا استبدالُ كلمة: أكثرها على حدود استجابات API "
        "وأحداث MapLibre. تُسدَّد بنطاقٍ نطاقاً مع تفكيك `api.ts`."
    ),
    "@typescript-eslint/no-unused-vars": (
        "كلٌّ منها يحتاج قراءةً لا حذفاً آليّاً: مُهمَلٌ قد يكون خطأً حقيقيّاً "
        "(حالةٌ تُضبَط ولا تُقرأ) لا مجرّد استيرادٍ زائد."
    ),
}


def counts_from_report(report: list) -> dict[str, int]:
    """يعدّ التحذيرات بالقاعدة من مخرَج `eslint -f json`."""
    tally: collections.Counter[str] = collections.Counter()
    for entry in report:
        if not isinstance(entry, dict):
            continue
        for message in entry.get("messages", []):
            rule = message.get("ruleId")
            if rule:
                tally[rule] += 1
    return dict(tally)


def files_for_rule(report: list, rule: str) -> list[str]:
    """الملفّات التي تحمل قاعدةً بعينها — تُطبَع مع الفشل ليُعرَف أين يُنظر."""
    found = []
    for entry in report:
        if not isinstance(entry, dict):
            continue
        hits = sum(1 for m in entry.get("messages", []) if m.get("ruleId") == rule)
        if hits:
            path = str(entry.get("filePath", "?")).split("/frontend/")[-1]
            found.append(f"{path} ({hits})")
    return sorted(found)


def violations(report: list) -> list[str]:
    """المخالفات — والنقصان مخالفةٌ كالزيادة، والقاعدة الجديدة مخالفةٌ ثالثة."""
    found: list[str] = []
    observed = counts_from_report(report)

    for rule, limit in sorted(BASELINE.items()):
        actual = observed.get(rule, 0)
        if actual > limit:
            found.append(
                f"{rule}: {actual} تحذيراً والسقف {limit} — دَينٌ جديد بلا مُحاكَمة.\n"
                f"الملفّات: {', '.join(files_for_rule(report, rule)[:8])}"
            )
        elif actual < limit:
            found.append(
                f"{rule}: {actual} تحذيراً والسقف {limit} — سُدِّد دَينٌ ولم يُخفَّض السقف. "
                f"اخفِض BASELINE['{rule}'] إلى {actual} وإلّا ابتلع السقفُ عودتَه صامتاً."
            )

    for rule in sorted(set(observed) - set(BASELINE)):
        found.append(
            f"{rule}: قاعدةٌ خارج الأساس ({observed[rule]} تحذيراً) — "
            "سقفٌ إجماليّ وحده يسمح باستبدال دَينٍ بأسوأ منه ما دام المجموع ثابتاً. "
            "أضِفها إلى BASELINE بسببٍ مكتوب، أو أصلِحها."
        )

    return found


def run_eslint() -> list:
    """يُشغّل eslint ويُعيد تقريره — وتعذّرُ التشغيل فشلٌ لا تخطٍّ."""
    try:
        proc = subprocess.run(
            ["npx", "eslint", "src", "e2e", "-f", "json"],
            capture_output=True,
            # `text=True` وحده يفكّ الترميز بلغة الآلة، وأسماء الملفّات ورسائل
            # القواعد تحمل حروفاً غير ASCII — فيتغيّر ما يُقرأ بتغيّر لغة الرَّانر،
            # ونتيجةٌ تتبع البيئة ليست قياساً. (يفرضه `test_text_encoding_locale`.)
            text=True,
            encoding="utf-8",
            cwd=FRONTEND,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit("✗ `npx` غير متاح — لا يُقاس الدَّين، و«لم يُقَس» ليس «لم ينمُ».") from None
    if not proc.stdout.strip():
        raise SystemExit(f"✗ eslint لم يُنتِج تقريراً: {proc.stderr.strip()[:400]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ تقرير eslint غير قابل للتحليل: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--report-file",
        type=Path,
        help="تقرير `eslint -f json` مُجسَّداً (للاختبار؛ بدونه يُشغَّل eslint)",
    )
    args = parser.parse_args(argv)

    if args.report_file is not None:
        try:
            report = json.loads(args.report_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"✗ تعذّرت قراءة {args.report_file}: {exc}") from None
    else:
        report = run_eslint()

    if not isinstance(report, list):
        raise SystemExit("✗ تقرير eslint ليس قائمة — استجابةٌ لا تُفهَم فشلٌ لا قبول.")

    problems = violations(report)
    if problems:
        print("frontend_lint_debt_guard: FAIL")
        # **كلّ سطرٍ يحمل بادئته — والمخالفة قد تكون متعدّدة الأسطر.**
        # طباعةُ الرسالة كتلةً واحدة تُخرِج سطرها الثاني بلا `✗` ولا إزاحة، فيبدو
        # في سجلّ CI سطراً غريباً لا تتمّةً — ويكسر أيّ قراءةٍ سطريّة للسجلّ.
        for problem in problems:
            head, *rest = problem.splitlines()
            print(f"  ✗ {head}")
            for continuation in rest:
                print(f"      {continuation.strip()}")
        print(
            "\nالدَّين يُحرَس ولا يُخفى: `eslint` هنا يُبلِّغ **تحذيراً** لا خطأً، "
            "فالوظيفة تخرج خضراء ومعها مئة تحذير، وGitHub يعرض عشرةً منها فقط."
        )
        return 1

    total = sum(BASELINE.values())
    print(
        f"frontend_lint_debt_guard: PASS ({len(BASELINE)} قاعدة مُراقَبة · "
        f"{total} تحذيراً عند السقف، لكلٍّ سببٌ مكتوب)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
