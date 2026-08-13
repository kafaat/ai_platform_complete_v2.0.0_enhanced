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

**وقسمٌ ثانٍ — ``behavioural``:** الحرّاس الساكنة تقيس **وقوع** الشيء لا **أثره**.
حارسُ تغطية مفتاح الطوارئ مثلاً يُثبِت أنّ كلّ موضع إطلاق **يستشير** المفتاح، ويمرّ
أخضر على مسارٍ يستشيره ثمّ يتجاهل نتيجته، أو يستشيره **بنطاقٍ أضيق** فلا يُطابِق،
أو يستشيره **بعد** النشر. فمفاتيح هذا القسم **مسارات مصادر** لا أسماء حرّاس، وطفراته
تُزرع في منطق الإنتاج نفسه ويجب أن تحمرّ اختباراتُ سلوكه المُسمّاة. ونفس الصرامة
تحكمه: سلسلةٌ فريدة في المصدر، و``expect`` يسمّي اختباراً موجوداً.

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
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "scripts" / "ci"
REGISTRY = ROOT / "docs" / "architecture" / "guard_mutation_registry.json"

# هذا الحارس نفسه ليس استثناءً — يظهر في السجلّ كغيره، ومواصفته تحت الاختبار.
GUARD_GLOBS = ("*_guard.py", "*_guard.sh")

# الطفرات تُزرع داخل نسخة مؤقتة من checkout عند تشغيل الأداة الفعلية. يبقى دفتر
# الاستعادة دفاعاً داخل تلك النسخة، وكذلك للمستودعات الصناعية الصغيرة التي تستدعي
# ``run_mutations`` مباشرةً في اختبارات الوحدة. وبذلك لا يستطيع SIGKILL أو timeout
# تلويث شجرة العمل القانونية؛ أسوأ ما يتركه نسخةً مؤقتة خارجها.
_ACTIVE_RESTORES: dict[Path, str] = {}

_COPY_IGNORE = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
}


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


def behavioural_specs(registry: dict, root: Path = ROOT) -> list[tuple[str, Path, dict]]:
    """المواصفات السلوكيّة: ``(المعرِّف، مسار المصدر، المواصفة)`` — مفاتيحها **مسارات**.

    قسمٌ منفصل عن ``mutated`` عمداً: ذاك يُكذِّب **حارساً** (هل يُطلِق على عطلٍ مزروع
    في نفسه؟)، وهذا يُكذِّب **سلوكاً** (هل يمنع الأثر الفيزيائيّ فعلاً؟). ودمجُهما
    كان سيخلط جردَ الحرّاس بجرد المصادر ويُفسِد حساب الدَّين — والقاعدتان تُقاسان
    بنفس الصرامة: سلسلةٌ فريدة في المصدر، و`expect` يسمّي اختباراً موجوداً.

    وُجِد لأنّ الحرّاس الساكنة تقيس **وقوع** الاستشارة لا **أثرها**: مسارٌ يستشير
    مفتاح الطوارئ ثمّ يتجاهل نتيجته يمرّ عليها كلّها أخضر.
    """
    # مفاتيح `$` تعليقاتٌ محلّيّة كعُرف بقيّة هذا السجلّ (`unmutated_debt`)، لا مواصفات.
    return [
        (path, root / path, spec)
        for path, spec in sorted(registry.get("behavioural", {}).items())
        if not path.startswith("$")
    ]


def mutation_test(spec: dict, mutation: dict) -> str:
    """جناحُ هذه الطفرة: ``mutation["test"]`` إن وُجِد، وإلّا جناحُ المواصفة.

    وحدةُ إنتاجٍ واحدة تُقاس بأكثر من جناح سلوكيّ — التعويض في جناحه والتصريح في
    جناحه. وإلزامُ جناحٍ واحد لكلّ ملفّ كان يدفع اختباراً إلى ملفٍّ لا يخصّه أو
    يُسقِط الطفرة أصلاً؛ وكلاهما يُنقِص القياس لأجل شكل السجلّ.
    """
    return mutation.get("test") or spec["test"]


def _spec_failures(label: str, src: Path, spec: dict, root: Path, section: str) -> list[str]:
    """قواعد المواصفة الواحدة — واحدةٌ للحرّاس وللسلوك، فلا يرث قسمٌ صرامةً أقلّ."""
    failures: list[str] = []
    content = src.read_text(encoding="utf-8")
    if not spec.get("mutations"):
        failures.append(f"{label}: مُدرَج في `{section}` بلا طفرة واحدة")
    for i, m in enumerate(spec.get("mutations", [])):
        declared_test = mutation_test(spec, m)
        test_file = root / declared_test
        test_src = ""
        if not test_file.exists():
            failures.append(f"{label}[{i}]: ملفّ الاختبار المُعلَن غير موجود — {declared_test}")
        else:
            test_src = test_file.read_text(encoding="utf-8")
        occurrences = content.count(m["find"])
        if occurrences == 0:
            failures.append(
                f"{label}[{i}]: سلسلة الطفرة لم تعد في المصدر — مواصفة بائتة"
                f"\n  تُبلِّغ تغطيةً لا تملكها: {m['find'][:60]!r}"
            )
        elif occurrences > 1:
            failures.append(
                f"{label}[{i}]: سلسلة الطفرة تتكرّر {occurrences} مرّات — الزرع"
                f"\n  غير محدَّد الموضع: {m['find'][:60]!r}"
            )
        # `expect` لا بدّ أن يكون **اسم اختبار موجوداً** لا بادئةً. و`"test_"`
        # وحدها تطابق أيّ سقوط، فتُحوّل شرط «الاختبار المُسمّى» إلى «شيء ما
        # سقط» — وهو الشرط الذي وُجِد `expect` ليمنعه. (وقعتُ فيها هنا أوّلاً.)
        expect = m.get("expect", "")
        if not expect:
            failures.append(f"{label}[{i}]: بلا `expect` يسمّي الاختبار الذي يسقط")
        elif test_src and f"def {expect}(" not in test_src:
            failures.append(
                f"{label}[{i}]: `expect` لا يسمّي اختباراً في {declared_test} —"
                f"\n  {expect!r}. بادئةٌ عامّة تطابق أيّ سقوط وتُعيد الشرط إلى"
                "\n  «سقط شيء ما»، وهو ما يمرّ على طفرةٍ كسرت الاستيراد."
            )
    return failures


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
        failures += _spec_failures(name, src, spec, root, "mutated")

    # المواصفات السلوكيّة: مصدرٌ غائب **يُحجَب** ولا يُتخطّى. الحرّاس يُغطّيهم `ghost`
    # أعلاه من الجرد؛ ولا جردَ للمصادر — فتخطّي المفقود هنا يُسقِط المواصفة صامتةً،
    # وهو بالضبط «حارسٌ يُبلِّغ نتيجةً عن سؤال لم يطرحه».
    for label, src, spec in behavioural_specs(registry, root):
        if not src.exists():
            failures.append(
                f"{label}: مصدرٌ سلوكيّ مُواصَف غير موجود — المواصفة تصف ملفّاً"
                "\n  ليس في الشجرة، فلا تُكذِّب شيئاً."
            )
            continue
        failures += _spec_failures(label, src, spec, root, "behavioural")

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


def _run_mutations_in_place(registry: dict, only: str | None, ci: Path, root: Path) -> list[str]:
    """ازرع داخل workspace غير قانونيّ (نسخة مؤقتة أو fixture اختبار فقط)."""
    failures: list[str] = []
    plantable = [(name, ci / name, spec) for name, spec in sorted(registry["mutated"].items())]
    plantable += behavioural_specs(registry, root)
    for name, src, spec in plantable:
        if only and name != only:
            continue
        original = src.read_text(encoding="utf-8")
        for i, m in enumerate(spec["mutations"]):
            label = f"{name}[{i}] {m.get('why', '')}"
            test_file = mutation_test(spec, m)
            try:
                _ACTIVE_RESTORES[src] = original
                src.write_text(original.replace(m["find"], m["replace"], 1), encoding="utf-8")
                code, out = _run_tests(test_file, root)
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
                repeats = _diagnose_repeat(src, original, m, test_file, root)
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


def _ignore_copy_entries(_directory: str, names: list[str]) -> set[str]:
    """استبعد caches قابلة لإعادة البناء، لا أدلة المستودع ولا ``.git``."""
    return {name for name in names if name in _COPY_IGNORE or name.endswith(".pyc")}


def run_mutations(
    registry: dict,
    only: str | None = None,
    ci: Path = CI,
    root: Path = ROOT,
    *,
    isolate: bool | None = None,
) -> list[str]:
    """ازرع الطفرات خارج شجرة العمل القانونية ثم شغّل اختباراتها.

    استدعاءات اختبارات الوحدة تستخدم مستودعاً صناعياً تحت ``tmp_path``، فتعمل
    داخله مباشرةً افتراضياً. أمّا التشغيل على ``ROOT`` الحقيقي فينسخ **الحالة
    الحالية للـworking tree** (ومنها التغييرات غير الملتزم بها) مرةً واحدة إلى
    دليل مؤقت ويزرع كل الطفرات هناك. لا يصلح ``git worktree`` هنا لأنه يعيد HEAD
    ويُسقط بالضبط التغييرات التي نريد تحكيمها قبل الالتزام.
    """
    resolved_root = root.resolve()
    if isolate is None:
        isolate = resolved_root == ROOT.resolve()
    if not isolate:
        return _run_mutations_in_place(registry, only, ci, root)

    try:
        ci_relative = ci.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("ci must be contained by the isolated repository root") from exc

    with tempfile.TemporaryDirectory(prefix="sahool-guard-mutation-workspace-") as tmp:
        mirror = Path(tmp) / "repo"
        shutil.copytree(
            resolved_root,
            mirror,
            symlinks=True,
            ignore=_ignore_copy_entries,
        )
        return _run_mutations_in_place(registry, only, mirror / ci_relative, mirror)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true", help="ازرع الطفرات وشغّل اختباراتها")
    p.add_argument("--only")
    args = p.parse_args()

    registry = load_registry()
    failures = check(registry)
    n_mut = sum(len(s["mutations"]) for s in registry["mutated"].values())
    behavioural = behavioural_specs(registry)
    n_beh = sum(len(spec["mutations"]) for _, _, spec in behavioural)
    debt = len([k for k in registry["unmutated_debt"] if not k.startswith("$")])
    print(
        f"guard_mutation_guard: {len(registry['mutated'])} حارساً مُواصَفاً "
        f"({n_mut} طفرة) · {debt} ديناً مُعلَناً · "
        f"{len(behavioural)} مصدراً سلوكيّاً ({n_beh} طفرة)"
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
