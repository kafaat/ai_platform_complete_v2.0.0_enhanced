#!/usr/bin/env python3
"""لا حارس بلا عطلٍ مزروع يُثبِت أنّه يُطلِق — GUARDS-WITHOUT-A-PLANTED-DEFECT-01.

الحارس الأخضر يقول شيئاً واحداً بيقين: **لم يُطلِق**. وهذا يحتمل معنيين لا يفرّق
بينهما شيء في هذا المستودع اليوم — «لم يجد عطلاً» و«لا يرى العطل أصلاً». وثلاثة
حرّاس في جلسة واحدة كانوا في المعنى الثاني وهم خُضر:

* ``runtime_contract_generator`` — نمطه يلتقط الاسم الحرفيّ داخل النداء فقط، فثلاثة
  عشر متغيّراً غير مباشر لم يكن يراها. البوّابة تمرّ، والصمت يُقرأ «لا متغيّر هنا»
  وهو يعني «لم أنظر».
* تصنيف الأسرار فيه — اللاحقة `_KEY` وحدها لا تطابق أيّ علامة سرّ، فعشرة مفاتيح
  توقيع نُشِرت تهيئةً عاديّة.
* ``brain_state_transition_guard`` — نمطه كان خاطئاً في الاتّجاهين معاً: يطابق داخل
  `fail-closed` (٤٧٧ ملفّاً) ولا يطابق `CLOSED_IN_CODE` (مفردة الإغلاق الفعليّة).

**والاختبار الموجود لا يكفي دليلاً:** أكثر من ثلثي هؤلاء له ملفّ اختبار، والاختبارات
كانت خضراء طوال الوقت. الفرق أنّ اختبار الحارس يقيس عادةً أنّه **يمرّ على شجرة
سليمة** — وهي خاصّيّة يُحقّقها حارسٌ لا يفعل شيئاً على الإطلاق.

فالدليل الوحيد أن **يُزرَع العطل في الحارس نفسه ويُثبَت أنّ اختباره يحمرّ**. وقد
اخترع هذا المستودع الفكرة مرّتين مستقلّتين (نمط «التكذيب» في `sahool-brain/`) ولم
يُفرَض قطّ، فبقيت عادةً تُنسى تحت الضغط — وهي تُنسى بالضبط حين تلزم.

**ما يُحجَب (رخيص، ثابت):** حارس جديد بلا مواصفة طفرة · مواصفة سلسلتها لم تعد في
المصدر أو تتكرّر فيه (مواصفة بائتة تُبلِّغ تغطيةً لا تملكها) · نموّ الدَّين فوق سقفه
· مدخل دَين لحارس غير موجود · ملفّ اختبار مُعلَن غير موجود.

**وما يُنفَّذ فعلاً:** ``--run`` يزرع كلّ طفرة في مصدر حارسها ويُشغّل اختباره ويؤكّد
أنّه حمرّ **وأنّ الاختبار المُسمّى بعينه** هو الذي سقط. لأنّ «سقط شيء ما» يمرّ على
طفرة كسرت الاستيراد لا القاعدة.

    python scripts/ci/guard_mutation_guard.py           # الفحص الثابت (بوّابة)
    python scripts/ci/guard_mutation_guard.py --run     # زرعٌ وتشغيل فعليّ
    python scripts/ci/guard_mutation_guard.py --run --only claim_base_guard.py
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "scripts" / "ci"
REGISTRY = ROOT / "docs" / "architecture" / "guard_mutation_registry.json"

# هذا الحارس نفسه ليس استثناءً — يظهر في السجلّ كغيره، ومواصفته تحت الاختبار.
GUARD_GLOBS = ("*_guard.py", "*_guard.sh")

# In-place mutation is unavoidable because the real tests resolve canonical paths.
# Keep an explicit restoration ledger so SIGTERM (for example GNU timeout) cannot
# leave the checkout carrying a planted defect. SIGKILL is not recoverable; CI must
# use a TERM grace period before KILL.
_ACTIVE_RESTORES: dict[Path, str] = {}


def _restore_active_sources() -> None:
    for path, original in list(_ACTIVE_RESTORES.items()):
        try:
            path.write_text(original, encoding="utf-8")
        finally:
            _ACTIVE_RESTORES.pop(path, None)


def _termination_handler(signum, _frame) -> None:
    _restore_active_sources()
    raise SystemExit(128 + int(signum))


atexit.register(_restore_active_sources)
for _signal in (signal.SIGTERM, signal.SIGINT):
    signal.signal(_signal, _termination_handler)


def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guard_inventory(ci: Path = CI) -> set[str]:
    return {p.name for glob in GUARD_GLOBS for p in ci.glob(glob)}


def check(registry: dict, ci: Path = CI, root: Path = ROOT) -> list[str]:
    """أسباب الحجب. الفارغة تعني مروراً."""
    failures: list[str] = []
    mutated = registry["mutated"]
    debt = {k for k in registry["unmutated_debt"] if not k.startswith("$")}
    ceiling = registry["unmutated_debt_ceiling"]
    present = guard_inventory(ci)

    both = set(mutated) & debt
    if both:
        failures.append(f"حارس مُواصَف ومُعلَن ديناً معاً: {sorted(both)}")

    missing = present - set(mutated) - debt
    if missing:
        failures.append(
            f"حارس بلا مواصفة طفرة: {sorted(missing)}\n"
            "  أضِف إليه في guard_mutation_registry.json طفرةً تزرع العطل الذي\n"
            "  وُجِد ليمسكه، واختباراً يجب أن يحمرّ عندها. «له اختبار» ليس دليلاً:\n"
            "  اختبار الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة، وهي خاصّيّة\n"
            "  يُحقّقها حارسٌ لا يفعل شيئاً."
        )

    ghost = (set(mutated) | debt) - present
    if ghost:
        failures.append(f"مدخل لحارس غير موجود: {sorted(ghost)}")

    if len(debt) > ceiling:
        failures.append(
            f"unmutated_debt: {len(debt)} والسقف {ceiling}. الدَّين يتقلّص ولا ينمو —"
            "\n  وحارسٌ يُكتَب اليوم لا عذر له: من عرف العطل عرف كيف يزرعه."
        )

    for name, spec in sorted(mutated.items()):
        src = ci / name
        if not src.exists():
            continue
        content = src.read_text(encoding="utf-8")
        test_file = root / spec["test"]
        test_src = ""
        if not test_file.exists():
            failures.append(f"{name}: ملفّ الاختبار المُعلَن غير موجود — {spec['test']}")
        else:
            test_src = test_file.read_text(encoding="utf-8")
        if not spec.get("mutations"):
            failures.append(f"{name}: مُدرَج في `mutated` بلا طفرة واحدة")
        for i, m in enumerate(spec.get("mutations", [])):
            occurrences = content.count(m["find"])
            if occurrences == 0:
                failures.append(
                    f"{name}[{i}]: سلسلة الطفرة لم تعد في المصدر — مواصفة بائتة"
                    f"\n  تُبلِّغ تغطيةً لا تملكها: {m['find'][:60]!r}"
                )
            elif occurrences > 1:
                failures.append(
                    f"{name}[{i}]: سلسلة الطفرة تتكرّر {occurrences} مرّات — الزرع"
                    f"\n  غير محدَّد الموضع: {m['find'][:60]!r}"
                )
            # `expect` لا بدّ أن يكون **اسم اختبار موجوداً** لا بادئةً. و`"test_"`
            # وحدها تطابق أيّ سقوط، فتُحوّل شرط «الاختبار المُسمّى» إلى «شيء ما
            # سقط» — وهو الشرط الذي وُجِد `expect` ليمنعه. (وقعتُ فيها هنا أوّلاً.)
            expect = m.get("expect", "")
            if not expect:
                failures.append(f"{name}[{i}]: بلا `expect` يسمّي الاختبار الذي يسقط")
            elif test_src and f"def {expect}(" not in test_src:
                failures.append(
                    f"{name}[{i}]: `expect` لا يسمّي اختباراً في {spec['test']} —"
                    f"\n  {expect!r}. بادئةٌ عامّة تطابق أيّ سقوط وتُعيد الشرط إلى"
                    "\n  «سقط شيء ما»، وهو ما يمرّ على طفرةٍ كسرت الاستيراد."
                )

    return failures


def ran_at_all(out: str) -> bool:
    """هل شغّل pytest اختباراً أصلاً؟

    خرجٌ بغير صفر يحتمل معنيين: «سقطت اختبارات» و«لم يُشغَّل شيء». الثاني ليس
    دليلاً في أيّ اتّجاه — والخلط بينهما وقع فعلاً: وُضِعت `--run` أوّلاً في وظيفة
    lint لا تُثبِّت pytest، فانهار المُشغِّل قبل جمع اختبار واحد وأُبلِغ عن ١٨
    «حمرّ بغير الاختبار المُتوقَّع». صحيحٌ حرفيّاً ويُرسِل قارئه إلى المكان الخطأ.
    """
    return any(m in out for m in (" passed", " failed", " error", "no tests ran"))


_FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+\S+::(\w+)", re.M)


def failing_tests(out: str) -> list[str]:
    """أسماء الاختبارات الساقطة كما طبعها pytest، بلا تكرار وبترتيب ثابت.

    يُقرأ من سطور `-q` الختاميّة (`FAILED path::name` و`ERROR path::name`). وحين لا
    يطبع pytest أيّ اسم — انهيار جمع مثلاً — تعود القائمة فارغة، وذلك **بذاته خبر**:
    يفصل «سقط اختبار آخر» عن «لم يُسمِّ المُشغِّل شيئاً».
    """
    return sorted(set(_FAILED_RE.findall(out)))


def _run_tests(test_file: str, root: Path) -> tuple[int, str]:
    """Run one mutation test in a deterministic, isolated process environment.

    ``PYTHONDONTWRITEBYTECODE`` ليس تشدّداً — هو **علاج الرقيعة المُسجَّلة** التي أخفقت
    ثلاث مرّات على ``claim_base_guard.py[4]`` (``MUTATION-VERDICT-CONTRADICTS-ITS-OWN-
    DIAGNOSIS-01``). المقيس: بايثون يُبطِل ``.pyc`` بـ**(mtime, size)** لا بالمحتوى.
    والطفرتان ``[3]`` و``[4]`` على ذلك الحارس هما **الزوج الوحيد المتساوي الطول** بين
    ثمانٍ (٧١٨٨ حرفاً لكلٍّ، ``+9`` عن الأصل — قِيس، لا افتُرِض). فحين تقع كتابتاهما في
    نفس دقّة الطابع الزمنيّ، تُحمَّل بايتكود ``[3]`` أثناء تشغيل ``[4]`` ⇒ يسقط
    **اختبار ``[3]``** وحده والمُشغَّلة ``[4]`` — وهو حرفيّاً ما سجّله الـCI:
    ``1 failed, 27 passed`` مع «الساقط فعلاً: test_a_measured_stamp_does_not_satisfy_a_decision».

    وهذا يفسّر لماذا لم تُصِب الرقيعةُ طفرةً أخرى قطّ، ولماذا تخضرّ الإعادات: بينها زمنٌ
    يكفي لاختلاف ``mtime``. بلا ``.pyc`` لا ذاكرة تبيت أصلاً.
    """
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "TZ": "UTC",
        }
    )
    with tempfile.TemporaryDirectory(prefix="sahool-guard-mutation-") as tmp:
        env["TMPDIR"] = tmp
        env["TEMP"] = tmp
        env["TMP"] = tmp
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                test_file,
                "-q",
                "--no-cov",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root,
            env=env,
        )
    return res.returncode, res.stdout + res.stderr


def _outcome(code: int, out: str, expected: str) -> tuple[str, tuple[str, ...]]:
    if not ran_at_all(out):
        return "runner_did_not_run", tuple()
    if code == 0:
        return "unexpected_green", tuple()
    observed = tuple(failing_tests(out))
    if expected not in out:
        return "wrong_test", observed
    return "expected_red", observed


def _diagnose_repeat(
    src: Path,
    original: str,
    mutation: dict,
    test_file: str,
    root: Path,
    repeats: int = 3,
) -> list[tuple[str, tuple[str, ...]]]:
    """Repeat only an anomalous plant; inconsistency remains a blocking result."""
    outcomes: list[tuple[str, tuple[str, ...]]] = []
    for _ in range(repeats):
        try:
            _ACTIVE_RESTORES[src] = original
            src.write_text(
                original.replace(mutation["find"], mutation["replace"], 1),
                encoding="utf-8",
            )
            code, out = _run_tests(test_file, root)
            outcomes.append(_outcome(code, out, mutation["expect"]))
        finally:
            src.write_text(original, encoding="utf-8")
            _ACTIVE_RESTORES.pop(src, None)
    return outcomes


def run_mutations(
    registry: dict, only: str | None = None, ci: Path = CI, root: Path = ROOT
) -> list[str]:
    """يزرع كلّ طفرة فعليّاً ويؤكّد أنّ الاختبار المُسمّى سقط. يُرجِع الإخفاقات."""
    failures: list[str] = []
    for name, spec in sorted(registry["mutated"].items()):
        if only and name != only:
            continue
        src = ci / name
        original = src.read_text(encoding="utf-8")
        for i, m in enumerate(spec["mutations"]):
            label = f"{name}[{i}] {m.get('why', '')}"
            try:
                _ACTIVE_RESTORES[src] = original
                src.write_text(original.replace(m["find"], m["replace"], 1), encoding="utf-8")
                code, out = _run_tests(spec["test"], root)
            finally:
                src.write_text(original, encoding="utf-8")
                _ACTIVE_RESTORES.pop(src, None)
            # الحارس الذي يزرع ويستعيد يحتاج أن **يُثبت** استعادته. بلا هذا، أيّ تسرّب
            # بين طفرتين متتاليتين يظهر «رقيعةً» لا عطلاً — وهو ما كلّف ثلاث ملاحظات
            # قبل أن يُعزَل السبب. المقارنة بالمحتوى لا بالحجم: طفرتان متساويتا الطول
            # هما بالضبط الحالة التي أخفت العطل.
            if src.read_text(encoding="utf-8") != original:
                failures.append(
                    f"✗ {label}: **الاستعادة لم تُعِد المصدر إلى أصله** — كلّ طفرة تالية"
                    "\n    تعمل على شجرة ملوَّثة، وأحكامها لا تخصّ ما زُرِع فيها."
                )
            if not ran_at_all(out):
                failures.append(
                    f"✗ {label}: **المُشغِّل لم يُشغّل اختباراً** — لا انهيار الحارس"
                    "\n    ولا سلامته مُثبَتان هنا. الأرجح بيئة بلا pytest أو بلا"
                    f"\n    تبعيّات الجناح. آخر ما طُبِع:\n    {out.strip()[-300:]}"
                )
            elif code == 0:
                failures.append(
                    f"✗ {label}: العطل مزروع والاختبار **أخضر**. هذا الحارس لا"
                    "\n    يحرس هذه القاعدة — أو الاختبار يقرأ مصنوعةً مُولَّدة سلفاً"
                    "\n    بدل أن يمرّ بالقاعدة نفسها."
                )
            elif m["expect"] not in out:
                repeats = _diagnose_repeat(src, original, m, spec["test"], root)
                stable = len(set(repeats)) == 1
                repeat_detail = " · ".join(
                    f"{kind}:{','.join(names) or '-'}" for kind, names in repeats
                )
                # **يُسمّي ما سقط فعلاً، لا ما لم يسقط — وهذا فرقٌ كلّفني تشخيصاً.**
                # أخفق هذا الفرع مرّةً على `claim_base_guard.py[4]` ولم يتكرّر في ثلاثة
                # تشغيلات تالية على الشجرة نفسها، فلم يبقَ منه إلّا نفيُ المتوقَّع — ولا
                # يُشخَّص منه شيء. والحارس **بوّابة حاجبة**، وفحصٌ يخضرّ بإعادة التشغيل
                # يُدرّب قارئه على إعادة التشغيل بدل القراءة، فيُطفَأ بلا تعديل سطر.
                # فالحادثة التالية تُقرأ من سجلّها بدل انتظار إعادة إنتاج قد لا تحدث.
                observed = failing_tests(out)
                detail = " · ".join(observed) if observed else "لا اسم اختبار في المخرَج"
                # `stable` تقيس اتّفاق الإعادات **مع بعضها**، لا مع الملاحظة الأولى.
                # فحين تُعطي الإعادات الثلاث `expected_red` — أي الطفرة تعمل والاختبار
                # المُسمّى يسقط — كان يُطبَع «STABLE_WRONG_TEST»، وهو **وصفٌ خاطئ لِما
                # حدث**: لا شيء «مستقرّ» ولا «الاختبار خاطئ». الشذوذ في الملاحظة الأولى
                # وحدها. مقيس على `claim_base_guard.py[4]` مرّتين (#792 حيث كانت الإعادات
                # `wrong_test` فعلاً، و#795 حيث كانت `expected_red` ثلاثاً).
                # **يبقى حاجباً** — فحصٌ يخضرّ بإعادة التشغيل يُدرّب قارئه على إعادة
                # التشغيل بدل القراءة — لكنّ الاسم يصف الواقعة بدل أن يقلبها.
                repeat_kinds = {kind for kind, _ in repeats}
                if repeat_kinds == {"expected_red"}:
                    classification = "FLAKY_FIRST_OBSERVATION"
                elif stable:
                    classification = "STABLE_WRONG_TEST"
                else:
                    classification = "NON_DETERMINISTIC"
                failures.append(
                    f"✗ {label}: حمرّ بغير الاختبار المُتوقَّع {m['expect']!r} —"
                    "\n    وهذا يمرّ على طفرة كسرت الاستيراد لا القاعدة."
                    f"\n    التصنيف: {classification}"
                    f"\n    إعادة التشخيص: {repeat_detail}"
                    f"\n    الساقط فعلاً: {detail}"
                    f"\n    آخر ما طُبِع:\n    {out.strip()[-300:]}"
                )
            else:
                print(f"  ✓ {label} ⇒ {m['expect']}")
    return failures


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true", help="ازرع الطفرات وشغّل اختباراتها")
    p.add_argument("--only")
    args = p.parse_args()

    registry = load_registry()
    failures = check(registry)
    n_mut = sum(len(s["mutations"]) for s in registry["mutated"].values())
    debt = len([k for k in registry["unmutated_debt"] if not k.startswith("$")])
    print(
        f"guard_mutation_guard: {len(registry['mutated'])} حارساً مُواصَفاً "
        f"({n_mut} طفرة) · {debt} ديناً مُعلَناً"
    )

    if args.run and not failures:
        print("\nزرعٌ وتشغيل فعليّ:")
        failures += run_mutations(registry, args.only)

    if failures:
        print("\nguard_mutation_guard: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print("\nguard_mutation_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
