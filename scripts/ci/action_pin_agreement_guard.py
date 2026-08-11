#!/usr/bin/env python3
"""ترقيةُ تثبيتٍ نصفُها ترقيةٌ ونصفُها كذبة.

``ACTION-PIN-HALF-UPGRADED-01``

**العطل الذي يحرسه، وقد وقع مرّتين مقيستين:** العمل الواحد مثبَّتٌ ببصمته في
مواضع كثيرة، وترقيتُه تعني تبديلها **كلّها**. و``github_actions_policy_guard``
يسأل سؤالاً واحداً — «أمثبَّتٌ ببصمة كاملة؟» — فيبقى أخضر على شجرةٍ نصفُ مواضعها
على البصمة القديمة ونصفُها على الجديدة. أي أنّ البوّابة القائمة **لا ترى** هذا
الصنف أصلاً.

* في ``#823`` حملت ترقية ``actions/attest`` **سبع مراسٍ** لا خمساً، ومرساتان
  منها في حارسٍ واختبار. أمسكها فحصٌ خارجيّ لا بوّابة.
* وفي هذه الشريحة كانت الحزمة المقترَحة تُبدّل ``upload-artifact`` في
  ``ci.yml`` وحده — **ثلاثة من ثلاثة وعشرين** — فتترك عشرين موضعاً على البصمة
  القديمة، وكلّ البوّابات خضراء.

**وبندان لا واحد،** لأنّ البصمة وحدها لا تكفي:

1. **بصمةٌ واحدة لكلّ عمل** — والانحراف القائم اليوم يُدرَج في أساسٍ **بعدده**،
   فلا ينمو ولا يبقى بعد إصلاحه.
2. **وتعليقُ الوسم يوافق البصمة** — ``@<بصمة v7> # v4`` أسوأ من تعليقٍ غائب:
   يقرؤه القارئ التالي وسماً ويبني عليه. فبصمةٌ واحدة لا تحمل وسمين.

**حدّ الصدق:** هذا يقيس **اتّساق** التثبيت لا **صحّته**. أنّ البصمة الواحدة هي
فعلاً الوسم المكتوب بجانبها ادّعاءٌ عن مستودعٍ أعلى، لا يُثبَت من داخل هذه
الشجرة — ولا يدّعي هذا الحارس إثباته.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: `uses:` بعملٍ مثبَّت ببصمة، مع تعليق وسمٍ اختياريّ على السطر نفسه.
_USES = re.compile(
    r"uses:\s*(?P<action>[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+)@(?P<sha>[0-9a-f]{40})"
    r"[ \t]*(?:#[ \t]*(?P<tag>\S+))?"
)

#: أعمالٌ تحمل اليوم أكثر من بصمة — مُدرَجةٌ **بعددها** لا بوجودها، فزيادةٌ
#: واحدة تُحجَب. وكلٌّ بسببٍ مكتوب؛ و«قِيس ولم يُفسَّر» سببٌ صادق، بخلاف سببٍ
#: مُختلَق يُقرأ تبريراً.
DIVERGENCE_BASELINE: dict[str, int] = {
    "actions/checkout": 3,
    "actions/setup-python": 2,
}

WHY: dict[str, str] = {
    "actions/checkout": (
        "ثلاث بصمات قائمة قبل هذا الحارس. **قِيست ولم تُفسَّر** — لا سجلّ يقول "
        "لماذا تباعدت، ولا أخترع لها سبباً. توحيدُها شريحةٌ مستقلّة تُقارن "
        "`inputs`/`outputs` بين الإصدارات."
    ),
    "actions/setup-python": (
        "بصمتان قائمتان قبل هذا الحارس، بلا سجلّ يفسّر التباعد. الأساس يمنع "
        "الثالثة، ولا يزعم أنّ الاثنتين مقصودتان."
    ),
}


def pins(root: Path) -> dict[str, dict[str, set[str]]]:
    """لكلّ عمل: بصماتُه، ولكلّ بصمة أوسمتُها المكتوبة بجانبها."""
    found: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for path in sorted(root.glob("*.yml")) + sorted(root.glob("*.yaml")):
        for m in _USES.finditer(path.read_text(encoding="utf-8")):
            tag = m.group("tag")
            found[m.group("action")][m.group("sha")]
            if tag:
                found[m.group("action")][m.group("sha")].add(tag)
    return {a: dict(s) for a, s in found.items()}


def violations(observed: dict[str, dict[str, set[str]]]) -> list[str]:
    """المخالفات — والأساسُ المُرتخي مخالفةٌ كالانحراف الجديد."""
    found: list[str] = []

    for action in sorted(observed):
        shas = observed[action]
        allowed = DIVERGENCE_BASELINE.get(action, 1)
        if len(shas) > allowed:
            found.append(
                f"{action}: {len(shas)} بصمةً والمسموح {allowed} — ترقيةٌ نصفُها فقط.\n"
                f"البصمات: {', '.join(sorted(shas))}"
            )
        elif action in DIVERGENCE_BASELINE and len(shas) < allowed:
            found.append(
                f"{action}: {len(shas)} بصمةً والأساس {allowed} — وُحِّد ولم يُخفَّض الأساس. "
                f"اخفِض DIVERGENCE_BASELINE['{action}'] إلى {len(shas)} "
                "وإلّا ابتلع الأساسُ عودةَ التباعد صامتاً."
            )

        for sha, tags in sorted(shas.items()):
            if len(tags) > 1:
                found.append(
                    f"{action}@{sha[:12]}…: بصمةٌ واحدة بوسمين {sorted(tags)} — "
                    "أحدهما يكذب على قارئه. وحّد التعليق مع البصمة."
                )

    for action in sorted(set(DIVERGENCE_BASELINE) - set(observed)):
        found.append(
            f"{action}: في الأساس ولا وجود له في الـworkflows — "
            "مدخلٌ بائت يُقرأ ديناً قائماً وقد زال. احذفه."
        )

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workflows",
        type=Path,
        default=WORKFLOWS,
        help="مجلّد الـworkflows (للاختبار؛ افتراضُه مجلّد المستودع)",
    )
    args = parser.parse_args(argv)

    if not args.workflows.is_dir():
        raise SystemExit(f"✗ لا مجلّد workflows في {args.workflows} — «لم يُقَس» ليس «متّسق».")

    observed = pins(args.workflows)
    problems = violations(observed)
    if problems:
        print("action_pin_agreement_guard: FAIL")
        for problem in problems:
            head, *rest = problem.splitlines()
            print(f"  ✗ {head}")
            for continuation in rest:
                print(f"      {continuation.strip()}")
        print(
            "\nالتثبيت يُرقّى كلّه أو لا يُرقّى: `github_actions_policy_guard` يسأل "
            "«أمثبَّتٌ ببصمة؟» فيبقى أخضر على شجرةٍ نصفُها قديم."
        )
        return 1

    refs = sum(len(s) for s in observed.values())
    print(
        f"action_pin_agreement_guard: PASS ({len(observed)} عملاً · {refs} بصمةً متمايزة · "
        f"{len(DIVERGENCE_BASELINE)} في أساس التباعد، لكلٍّ سببٌ مكتوب)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
