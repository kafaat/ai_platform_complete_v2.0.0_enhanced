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

**والاكتشاف من الـworkflows يترك ثقباً بحدّ تعريفه:** مولّد يدعم ``--check`` ولا يذكره
أيّ workflow خارج المدى تماماً — لا يراه CI ولا تراه هذه المكنسة. تُغلَق الزاوية بتصنيف
صريح: كلّ سكربت في ``scripts/{ci,architecture,release}`` يُعلن علم ``--check`` ولا اسم له
في أيّ workflow **يجب** أن يكون مُدرَجاً في ``docs/architecture/generated_chain_known_drift.json``
بحارسه وسبب صمته ودليله وشرط إغلاقه. مولّد جديد يدخل بلا تصنيف ⇒ فشل.

التصنيف غير المُغطّى لا يُنفَّذ افتراضياً لأنّه خارج عقد workflows المكتشَف، لا لأن
``--check`` مسموح له بالكتابة. أُغلقت ``CHECK-STEPS-MUTATE-THE-TREE-01``: أوضاع الفحص
للحرّاس الستّة أصبحت قراءة فقط، مع بقاء مقارنة حالة الشجرة دفاعاً إضافياً.

    git add -A                                          # ← لازم أوّلاً، انظر أدناه
    python scripts/ci/verify_all_generated.py           # افحص فقط
    python scripts/ci/verify_all_generated.py --fix     # أعد التوليد ثمّ افحص
    python scripts/ci/verify_all_generated.py --uncovered  # شغّل غير المُغطّى (يكتب!)

**`git add` قبل التشغيل ضرورة لا عادة:** المولّدات تمسح `git ls-files` (مُتعقَّب فقط —
قرار #660 لمنع التقاط ملفّات محلّيّة غائبة عن checkout الـCI). فملفّ جديد غير مُدرَج في
الفهرس **لا يراه أيّ مولّد**، وتمرّ المكنسة خضراء بينما CI سيرصد الانحراف بعد الالتزام.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
KNOWN_DRIFT = ROOT / "docs" / "architecture" / "generated_chain_known_drift.json"

# أدلّة السكربتات التي قد تحمل مولّدات — نفسها التي يطابقها `_STEP` في الـworkflows.
_SCRIPT_DIRS = ("scripts/ci", "scripts/architecture", "scripts/release")

# «يدعم --check» = يُعلن العلم كسلسلة نصّيّة في مصدره (argparse)، لا مجرّد ذكره في شرح.
# التمييز ليس شكليّاً: `verify_all_generated` نفسه يذكر `--check` في docstring ولا يملكه.
_DECLARES_CHECK = re.compile(r"""["']--check[a-z-]*["']""")

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
    "capability_runtime_evidence.py": "--apply",
    "execution_dependency_audit.py": "--generate",
    "decision_lineage_graph.py": "--generate",
    "database_contract_graph.py": "--generate",
    "event_contract_graph.py": "--generate",
    "architecture_graph.py": "--generate",
    "route_conflict_guard.py": "--generate",
    "router_reachability_guard.py": "--generate",
    "runtime_contract_generator.py": "--generate",
    "generate_indicator_artifacts.py": "",
    "generate_indicators_frontend_manifest.py": "",
    "pr_capability_impact_gate.py": "--generate-index",
    "build_platform_catalog.py": "",  # بلا علم — التشغيل العاري يكتب
    "build_service_dependency_bundle.py": "",
    "static_governance_closure.py": "--generate",
}

# يبصم مخرجات المولّدات ⇒ بعدها دائماً.
_LATE = ("static_governance_closure.py",)

# تبصم كلّ ما سبق ⇒ آخر شيء على الإطلاق.
_RELEASE_BUILD = "scripts/release/build_release_bundle.py"
_RELEASE_VALIDATE = "scripts/release/validate_release_package.py"

MAX_PASSES = 3
STEP_TIMEOUT_SECONDS = 180


def discover() -> list[tuple[str, list[str]]]:
    """(مسار السكربت، وسائطه) لكلّ خطوة ``--check`` في الـworkflows — مُزالة التكرار."""
    seen: dict[tuple[str, tuple[str, ...]], None] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for script, args in _STEP.findall(text):
            argv = tuple(a for a in args.split() if a)
            seen.setdefault((script, argv), None)
    return [(s, list(a)) for (s, a) in seen]


def uncovered() -> list[str]:
    """السكربتات التي تُعلن ``--check`` ولا يذكرها أيّ workflow — خارج مدى CI والمكنسة."""
    named = "\n".join(wf.read_text(encoding="utf-8") for wf in WORKFLOWS.glob("*.yml"))
    found: list[str] = []
    for directory in _SCRIPT_DIRS:
        for path in sorted((ROOT / directory).glob("*.py")):
            if not _DECLARES_CHECK.search(path.read_text(encoding="utf-8")):
                continue
            if path.name in named:
                continue
            found.append(f"{directory}/{path.name}")
    return found


def load_known_drift() -> dict[str, dict]:
    """أساس التصنيف. غيابه ليس «لا شيء معروف» بل عطب — لا يُقرأ كخضرة."""
    if not KNOWN_DRIFT.exists():
        raise FileNotFoundError(f"أساس التصنيف مفقود: {KNOWN_DRIFT.relative_to(ROOT)}")
    return json.loads(KNOWN_DRIFT.read_text(encoding="utf-8"))["uncovered"]


def classify_uncovered() -> list[str]:
    """يُطابق ما في الشجرة بما في الأساس. يُعيد أسطر الأخطاء (فارغة = متّسق).

    الاتّجاهان يفشلان: مولّد جديد بلا تصنيف (ثقب يتّسع صامتاً)، ومدخل بائت في الأساس
    (سكربت وُصِل بـworkflow أو حُذِف — «معروف» صار وصفاً لماضٍ). القائمة تتقلّص ولا تنمو.
    """
    in_tree = set(uncovered())
    in_baseline = set(load_known_drift())
    problems: list[str] = []
    for script in sorted(in_tree - in_baseline):
        problems.append(
            f"مولّد يدعم --check ولا يذكره workflow ولا يصنّفه الأساس: {script}"
            f" — صنّفه في {KNOWN_DRIFT.relative_to(ROOT)} أو صِله بـworkflow."
        )
    for script in sorted(in_baseline - in_tree):
        problems.append(f"مدخل بائت في الأساس: {script} — لم يعد غير مُغطّى (أو حُذِف). احذف المدخل.")
    return problems


def run_uncovered(entries: dict[str, dict]) -> list[tuple[str, str]]:
    """يشغّل غير المُغطّى بعلمه المُصرَّح ويقارن النتيجة بالمُعلَن في الأساس.

    يكتب ملفّات متعقَّبة (``CHECK-STEPS-MUTATE-THE-TREE-01``) — ولذلك لا يعمل افتراضيّاً.
    الفشل هنا ليس «انحرف» بل «انحرافه غير ما يقوله الأساس»: سليم صار منحرفاً (انحدار
    جديد)، أو منحرف صار سليماً (شرط إغلاقه تحقّق ⇒ يُحذف مدخله).
    """
    surprises: list[tuple[str, str]] = []
    for script, entry in sorted(entries.items()):
        code, out = _run([script, entry["check_flag"]])
        drifted = code != 0
        tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
        if drifted == bool(entry["drifts"]):
            state = "منحرف كما هو مُعلَن" if drifted else "سليم كما هو مُعلَن"
            print(f"  ✓ {script} — {state}")
            continue
        note = (
            "الأساس يقول سليم وقد انحرف — انحدار جديد"
            if drifted
            else "الأساس يقول منحرف وقد سلُم — تحقّق شرط الإغلاق، احذف المدخل"
        )
        surprises.append((script, f"{note}: {tail}"))
        print(f"  ✗ {script}\n      {note}\n      {tail}")
    return surprises


def _run(argv: list[str]) -> tuple[int, str]:
    """Run one discovered step with a hard, diagnosable deadline.

    A generated-artifact guard must not be able to consume an entire CI job without naming
    the stalled step. Each command runs in its own process group so descendants are also
    terminated on timeout.
    """
    cmd = [sys.executable, *argv]
    proc = subprocess.Popen(  # noqa: S603 — أوامر من الـworkflows لا من مُدخَل مستخدم
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=STEP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        partial = ((stdout or "") + (stderr or "")).strip()
        detail = f"TIMEOUT after {STEP_TIMEOUT_SECONDS}s: {' '.join(argv)}"
        return 124, (partial + "\n" + detail).strip()
    return proc.returncode, ((stdout or "") + (stderr or "")).strip()


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
    parser.add_argument(
        "--uncovered",
        action="store_true",
        help="شغّل المولّدات غير المُغطّاة وقارنها بالأساس (يكتب ملفّات متعقَّبة — شجرة نظيفة)",
    )
    args = parser.parse_args()

    steps = discover()
    print(f"اكتُشفت {len(steps)} خطوة --check من {len(list(WORKFLOWS.glob('*.yml')))} workflow\n")

    # التصنيف أوّلاً: يقيس مدى الأداة نفسها. مولّد خارج كلّ workflow لا يظهر في أيّ فحص
    # أدناه، فالسكوت عنه يُحوّل نجاح المكنسة إلى ادّعاء تغطية لا تملكها.
    unclassified = classify_uncovered()
    if unclassified:
        print("خلل في تصنيف المولّدات غير المُغطّاة:")
        for line in unclassified:
            print(f"  ✗ {line}")
        return 1
    entries = load_known_drift()
    drifting = [s for s, e in entries.items() if e["drifts"]]
    print(
        f"غير مُغطّى بأيّ workflow: {len(entries)} مولّد "
        f"({len(drifting)} منها منحرف بأساس موثَّق) — خارج مدى هذه المكنسة بالتصميم.\n"
    )

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
        # دفاع إضافي بعد إغلاق CHECK-STEPS-MUTATE-THE-TREE-01: الحرّاس المعروفة
        # صارت قراءة فقط، لكن مقارنة حالة الشجرة تمنع أي حارس مستقبلي من إعادة العيب.
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

    # التقاء شريحتين على الزاوية نفسها (#693 و#690): `unreferenced_generators` يُبلِّغ
    # المجموعة، و`classify_uncovered` أعلاه **يفرض** أن يحمل كلّ عضو فيها مدخلاً مُبرَّراً.
    # يبقى الإبلاغ لأنّه يُسمّي الحدّ في المخرَج، والفرض هو ما يمنع اتّساعه صامتاً.
    blind = unreferenced_generators()
    if blind:
        print("\nمولِّدات لا يذكرها أيّ workflow ⇒ خارج الاكتشاف (مُصنَّفة في الأساس، غير مُنفَّذة هنا):")
        for script in blind:
            print(f"  · {script}")
        print(
            "  مُصنَّفة بسببها في docs/architecture/generated_chain_known_drift.json — القائمة تتقلّص ولا تنمو."
        )

    if args.uncovered:
        print("\n— المولّدات غير المُغطّاة (تنفيذ صريح؛ راجع `git status` بعده):")
        if run_uncovered(entries):
            print("\nحالة مولّد غير مُغطّى تخالف الأساس — حدِّث الأساس أو أصلح السبب.")
            return 1

    print("\n✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
