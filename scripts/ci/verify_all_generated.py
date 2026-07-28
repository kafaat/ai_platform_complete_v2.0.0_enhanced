#!/usr/bin/env python3
"""يشغّل **كلّ** خطوات ``--check`` المولَّدة بأمر واحد — وبالترتيب الذي تتطلّبه التبعيّات.

``GENERATED-ARTIFACT-SWEEP-01``. «ضريبة التسجيل» موصوفة في `hot.md` بثلاث قفزات
(جرد ⇒ كتالوج ⇒ حزمة)، ومداها الحقيقيّ **٤٧ خطوة موزّعة على ١٨ workflow**. الفارق ليس
تفصيلاً: شريحتان متتاليتان في 2026-07-28 كلّفتا جولة CI كاملة كلّ واحدة لأنّ الفحص
المحلّيّ كان انتقائيّاً — أُصلِح ما سمّاه CI، فظهر التالي في الجولة التي بعدها.

**القائمة تُكتشَف من الـworkflows لا تُكتب هنا.** قائمة مكتوبة يدويّاً تبيت بصمت عند
إضافة مولّد جديد، فتُعيد إنتاج العيب نفسه في الأداة التي تعالجه. المصدر الوحيد للحقيقة
هو ما ينفّذه CI فعلاً.

الترتيب مُصرَّح لأنّه حقيقة تبعيّة لا تفضيلاً:
  ١) المولّدات المستقلّة — كلٌّ يقرأ الشجرة ويكتب مصنوعه.
  ٢) ``static_governance_closure`` — يبصم مخرجات (١)، فينحرف مرّتين لو سبقها.
  ٣) حزمة الإصدار — تبصم كلّ ما سبق، فهي آخِراً دائماً.

و``--fix`` يُكرّر حتّى الثبات (حدّ ٣ دورات): مولّد يجزّئ ملفّات غيّرها مولّد آخر يحتاج
دورة ثانية — رُصِد فعليّاً على ``execution_dependency_audit``.

**fail-closed على المجهول:** خطوة ``--check`` بلا علم بكيفيّة إعادة توليدها تُبلَّغ
كـ«يدويّة» ولا تُتخطّى صامتةً — فلا يُقرأ نجاح الأداة كتغطية لا تملكها.

    git add -A                                          # ← لازم أوّلاً، انظر أدناه
    python scripts/ci/verify_all_generated.py           # افحص فقط
    python scripts/ci/verify_all_generated.py --fix     # أعد التوليد ثمّ افحص

**‏`git add` قبل التشغيل ضرورة لا عادة:** المولّدات تمسح `git ls-files` (مُتعقَّب فقط —
قرار #660 لمنع التقاط ملفّات محلّيّة غائبة عن checkout الـCI). فملفّ جديد غير مُدرَج في
الفهرس **لا يراه أيّ مولّد**، وتمرّ المكنسة خضراء بينما CI سيرصد الانحراف بعد الالتزام.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

# خطوة فحص في workflow: `python scripts/<dir>/<name>.py … --check[-suffix]`
# مقصور على **سطر واحد**: `\s` يبتلع الأسطر الجديدة فيلتهم كتلة YAML كاملة ويُنتج
# «خطوة» وهميّة تمرّ خضراء بلا تنفيذ شيء — رُصِد على أوّل تشغيل.
_STEP = re.compile(
    r"python[ \t]+(scripts/(?:ci|architecture|release)/[a-z_0-9]+\.py)"
    r"((?:[ \t]+(?!\||&)[^\s|&]+)*?[ \t]+--check[a-z-]*)"
)

# علم إعادة التوليد لكلّ سكربت يملكه. الغياب = فحص فقط (يُبلَّغ، لا يُتخطّى).
_GENERATE_FLAG = {
    "generate_service_inventory.py": "--write-registry",
    "capability_mapping_engine.py": "--generate",
    "capability_evidence_maturity_engine.py": "--generate",
    "capability_parity_investment_engine.py": "--generate",
    "capability_release_history.py": "--generate",
    "capability_runtime_evidence.py": "--generate",
    "execution_dependency_audit.py": "--generate",
    "decision_lineage_graph.py": "--generate",
    "database_contract_graph.py": "--generate",
    "event_contract_graph.py": "--generate",
    "architecture_graph.py": "--generate",
    "route_conflict_guard.py": "--generate",
    "router_reachability_guard.py": "--generate",
    "runtime_contract_generator.py": "--generate",
    "generate_indicator_artifacts.py": "--write",
    "generate_indicators_frontend_manifest.py": "--write",
    "pr_capability_impact_gate.py": "--generate-index",
    "build_platform_catalog.py": "",  # بلا علم — التشغيل العاري يكتب
    "build_service_dependency_bundle.py": "--generate",
    "static_governance_closure.py": "--generate",
}

# يبصم مخرجات المولّدات ⇒ بعدها دائماً.
_LATE = ("static_governance_closure.py",)

# تبصم كلّ ما سبق ⇒ آخر شيء على الإطلاق.
_RELEASE_BUILD = "scripts/release/build_release_bundle.py"
_RELEASE_VALIDATE = "scripts/release/validate_release_package.py"

MAX_PASSES = 3


def discover() -> list[tuple[str, list[str]]]:
    """(مسار السكربت، وسائطه) لكلّ خطوة ``--check`` في الـworkflows — مُزالة التكرار."""
    seen: dict[tuple[str, tuple[str, ...]], None] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for script, args in _STEP.findall(text):
            argv = tuple(a for a in args.split() if a)
            seen.setdefault((script, argv), None)
    return [(s, list(a)) for (s, a) in seen]


def _run(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 — أوامر من الـworkflows لا من مُدخَل مستخدم
        [sys.executable, *argv], cwd=ROOT, capture_output=True, text=True
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _sort_key(step: tuple[str, list[str]]) -> tuple[int, str]:
    name = Path(step[0]).name
    return (1 if name in _LATE else 0, step[0])


def tree_state() -> str:
    """حالة الملفّات المتتبَّعة — الإشارة الوحيدة التي لا يملك الحارس تزييفها."""
    out = subprocess.run(  # noqa: S603 — أمر ثابت
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    return "\n".join(sorted(out.splitlines()))


def unreferenced_generators() -> list[str]:
    """مولِّدات في الشجرة **لا يذكرها أيّ workflow** — عمياء عن الاكتشاف.

    الاكتشاف من الـworkflows يرى ما يُشغّله CI بدقّة، ويعمى بالتعريف عمّا **نسيه**.
    والقياس يقول إنّ هذه ليست حالة نظريّة: أربعة مولِّدات خارج كلّ workflow، وثلاثة
    منها منحرفة على `main` — وفيها `path3_runtime_readiness_closure` الذي يُعلن
    جاهزيّةً لا تسندها الشجرة (`PATH3-READINESS-CLAIM-UNBACKED-01`).

    تُذكر ولا تُشغَّل: تشغيلها هنا يوسّع العقد بلا قرار، وكتمانها يجعل الأداة تدّعي
    شمولاً لا تملكه.
    """
    writes = re.compile(r'"(--(?:generate|write)[a-z-]*)"')
    referenced: set[str] = set()
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        referenced.update(
            re.findall(r"(scripts/(?:ci|release)/[a-z0-9_]+\.py)", wf.read_text(encoding="utf-8"))
        )
    found: set[str] = set()
    for folder in ("scripts/ci", "scripts/release"):
        for script in sorted((ROOT / folder).glob("*.py")):
            if writes.search(script.read_text(encoding="utf-8", errors="ignore")):
                found.add(f"{folder}/{script.name}")
    return sorted(found - referenced)


def check_all(steps) -> list[tuple[str, str]]:
    """يُعيد قائمة (الخطوة، آخر سطر) لكلّ فحص فاشل."""
    failures: list[tuple[str, str]] = []
    for script, args in sorted(steps, key=_sort_key):
        code, out = _run([script, *args])
        label = f"{script} {' '.join(args)}".strip()
        if code != 0:
            tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
            failures.append((label, tail))
            print(f"  ✗ {label}\n      {tail}")
        else:
            print(f"  ✓ {label}")
    return failures


def regenerate(steps) -> list[str]:
    """يُعيد توليد ما يُعرَف توليده؛ يُعيد أسماء الخطوات **غير** القابلة للتوليد آليّاً."""
    manual: list[str] = []
    for script, _args in sorted(steps, key=_sort_key):
        name = Path(script).name
        if name not in _GENERATE_FLAG:
            manual.append(script)
            continue
        flag = _GENERATE_FLAG[name]
        code, out = _run([script, flag] if flag else [script])
        if code != 0:
            tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
            print(f"  ! تعذّر توليد {script}: {tail}")
    # حزمة الإصدار آخِراً — تبصم كلّ ما سبق. لكن **بشرط الحاجة**: البناء يكتب
    # ``generated_at`` جديداً في كلّ مرّة، فبناؤه بلا داعٍ يُوسّخ الشجرة بفرق طابع زمنيّ
    # لا يقابله تغيير محتوى (``file_count`` ثابت) — ضجيج يُخفي الفرق الحقيقيّ في المراجعة.
    if _run([_RELEASE_VALIDATE])[0] != 0:
        _run([_RELEASE_BUILD])
    return manual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="أعد التوليد حتّى الثبات ثمّ افحص")
    args = parser.parse_args()

    steps = discover()
    print(f"اكتُشفت {len(steps)} خطوة --check من {len(list(WORKFLOWS.glob('*.yml')))} workflow\n")

    manual: list[str] = []
    if args.fix:
        for attempt in range(1, MAX_PASSES + 1):
            print(f"— دورة توليد {attempt}/{MAX_PASSES}")
            manual = regenerate(steps)
            if not check_all(steps):
                break
            print()
        else:
            print("\nلم تثبت المصنوعات بعد الحدّ الأقصى للدورات.")
            return 1
    else:
        # CHECK-STEPS-MUTATE-THE-TREE-01: ستّة حرّاس يكتبون في وضع «فحص فقط»، فيُصلحون
        # الانحراف صامتاً ويُعيدون صفراً. مُثبَت: إفساد `service_inventory.csv` ثمّ
        # الفحص ⇒ يختفي الإفساد وتُعلَن السلامة. فرمز الخروج وحده **أخضر كاذب**،
        # والحدّ الصادق أنّ حالة الشجرة قبل الفحص = حالتها بعده.
        before = tree_state()
        failed = bool(check_all(steps))
        after = tree_state()
        if before != after:
            print("\n  ✗ حارس كتب أثناء الفحص — الشجرة تغيّرت بين بدايته ونهايته:")
            for line in sorted(set(after.splitlines()) ^ set(before.splitlines())):
                print(f"      {line}")
            print("      انحراف أُصلِح صامتاً وضاع دليله قبل أن يُقرأ في git diff.")
            failed = True
        if failed:
            print("\nانحراف في المصنوعات المولَّدة — شغّل --fix ثمّ راجع الفرق قبل الالتزام.")
            return 1

    code, out = _run([_RELEASE_VALIDATE])
    print(f"\n{out.splitlines()[-1] if out.splitlines() else ''}")
    if code != 0:
        return 1

    if manual:
        # صدق: الأداة لا تدّعي تغطية لا تملكها.
        print("\nفُحِصت ولا تُولَّد آليّاً (تحتاج يداً إن انحرفت):")
        for script in manual:
            print(f"  · {script}")

    blind = unreferenced_generators()
    if blind:
        # صدق: الأداة لا تدّعي تغطية لا تملكها — وهذا حدّ **الاكتشاف** لا حدّ التنفيذ.
        print("\nمولِّدات لا يذكرها أيّ workflow ⇒ خارج الاكتشاف (لم تُفحَص هنا):")
        for script in blind:
            print(f"  · {script}")
        print("  انظر PATH3-READINESS-CLAIM-UNBACKED-01 — ثلاثة منها منحرفة على main.")

    print("\n✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
