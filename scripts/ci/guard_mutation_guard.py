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
#: سطحُ الحجب المُجمَّد — كلُّ ثلاثيّة (حارس، workflow، وظيفة) قائمةٍ يومَ التجميد.
BLOCKING_SURFACE_BASELINE = ROOT / "docs" / "architecture" / "blocking_surface_baseline.json"
#: إقراراتُ ما زِيد بعد التجميد — أربعُ خصائصَ لكلّ زيادة.
BLOCKING_SURFACE_ADDITIONS = ROOT / "docs" / "architecture" / "blocking_surface_additions.json"
#: مواضعُ الحجب المشروعة. `advisory` ليست موضعاً بل إعلانُ أنّ الفحص **لا يحجب**.
_IMPACT_PLACEMENTS = ("merge", "release", "publish", "advisory")
_REQUIRED_ADDITION_FIELDS = ("counterexample", "mutation", "positive_witness", "impact")

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


def _mutated_source(label: str, *, ci: Path = CI, root: Path = ROOT) -> Path:
    """Resolve a guard mutation source without broadening the mandatory guard inventory.

    Bare keys remain the canonical ``scripts/ci`` guard inventory.  A path-like key is
    an explicitly registered guard outside that directory (for example an architecture
    admission guard); it is plantable and validated, but does not implicitly pull every
    ``*_guard.py`` in the repository into the debt ratchet.
    """
    if "/" not in label and "\\" not in label:
        return ci / label
    rel = Path(label)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"invalid mutated guard path: {label}")
    return root / rel


def _unknown_mutation_sections(registry: dict) -> list[str]:
    """Return top-level keys that look like mutation specs but are outside legal sections."""
    legal = {"mutated", "behavioural"}
    out: list[str] = []
    for key, value in registry.items():
        if key in legal or key.startswith("$"):
            continue
        if isinstance(value, dict) and ("mutations" in value or "test" in value):
            out.append(key)
    return sorted(out)


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

    unknown_sections = _unknown_mutation_sections(registry)
    if unknown_sections:
        failures.append(
            "مواصفات طفرة خارج القسمين القانونيّين `mutated`/`behavioural`: "
            f"{unknown_sections}. إعلانٌ لا يقرأه runner ليس قياساً."
        )

    bare_mutated = {name for name in mutated if "/" not in name and "\\" not in name}
    both = bare_mutated & debt
    if both:
        failures.append(f"حارس مُواصَف ومُعلَن ديناً معاً: {sorted(both)}")

    missing = present - bare_mutated - debt
    if missing:
        failures.append(
            f"حارس بلا مواصفة طفرة: {sorted(missing)}\n"
            "  أضِف إليه في guard_mutation_registry.json طفرةً تزرع العطل الذي\n"
            "  وُجِد ليمسكه، واختباراً يجب أن يحمرّ عندها. «له اختبار» ليس دليلاً:\n"
            "  اختبار الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة، وهي خاصّيّة\n"
            "  يُحقّقها حارسٌ لا يفعل شيئاً."
        )

    ghost = (bare_mutated | debt) - present
    if ghost:
        failures.append(f"مدخل لحارس غير موجود: {sorted(ghost)}")

    external_mutated = sorted(set(mutated) - bare_mutated)
    for label in external_mutated:
        try:
            src = _mutated_source(label, ci=ci, root=root)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not src.exists():
            failures.append(f"مدخل لحارس خارجي غير موجود: {label}")
        elif not any(src.name.endswith(suffix.replace("*", "")) for suffix in GUARD_GLOBS):
            failures.append(f"مدخل `mutated` خارجي ليس حارساً `*_guard.py|sh`: {label}")

    if len(debt) > ceiling:
        failures.append(
            f"unmutated_debt: {len(debt)} والسقف {ceiling}. الدَّين يتقلّص ولا ينمو —"
            "\n  وحارسٌ يُكتَب اليوم لا عذر له: من عرف العطل عرف كيف يزرعه."
        )

    for name, spec in sorted(mutated.items()):
        try:
            src = _mutated_source(name, ci=ci, root=root)
        except ValueError:
            continue
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


def _run_tests_for_mutation(test_file: str, expected: str, root: Path) -> tuple[int, str]:
    """«ضيّق ثم تراجَع» — `MUT-SWEEP-RUNS-THE-WHOLE-FILE-PER-PLANT-01`.

    المقيس قبل هذا: كلّ زرعة كانت تشغّل **ملفّ الاختبار كاملاً** (~9.7ث لملفّ
    يبني مستودعات git) بينما الاختبار المتوقَّع وحده ~0.5ث — ومع مئات الزرعات
    صارت المكنسة ~50 دقيقة في CI.

    المسار السريع يحسم حكماً واحداً فقط: **مقتولة** (خرجٌ أحمر والمُتوقَّع مُسمًّى
    بين الساقطين) — وهو نفس معيار `_outcome` حرفيّاً، على معرّف عقدة صريح
    `file::name` لا `-k` (المطابقة الجزئيّة تجرّ اختباراتٍ لم تُقصَد). وكلّ ما عداه
    — مرّ المُتوقَّع، أو سقط غيرُه، أو لم يُجمَع الاسم أصلاً (`no tests ran` لعقدةٍ
    غير موجودة أو دالّةٍ داخل صنف)، أو انهار المُشغِّل — **يتراجع إلى الملفّ الكامل**
    فتُحسَم التصنيفات (`unexpected_green` · `wrong_test` · `runner_did_not_run`)
    من نفس المشهد الذي كانت تُحسَم منه دائماً. لا حكم يتغيّر؛ فقط الطريق إلى
    «مقتولة» يقصر — وهي الحالة الغالبة قطعاً في شجرة خضراء (كلّ الطفرات مقتولة).
    """
    code, out = _run_tests(f"{test_file}::{expected}", root)
    if ran_at_all(out) and code != 0 and expected in failing_tests(out):
        return code, out
    return _run_tests(test_file, root)


def _outcome(code: int, out: str, expected: str) -> tuple[str, tuple[str, ...]]:
    if not ran_at_all(out):
        return "runner_did_not_run", tuple()
    if code == 0:
        return "unexpected_green", tuple()
    observed = tuple(failing_tests(out))
    # **العضويّة في قائمة الساقطين، لا الوجود في المخرَج.** `expected in out` يمرّ على
    # حالةٍ يظهر فيها الاسم المُتوقَّع في **نصٍّ آخر** — رسالة تأكيد، أو تتبُّع مكدّس،
    # أو معامل `parametrize`، أو سطر تجميع — بينما الساقط اختبارٌ ثانٍ. عندها يُقرأ
    # الحكم `expected_red` والقاعدة **غير محروسة**، وهو العطل نفسه الذي وُجِد `expect`
    # ليمنعه: «سقط شيء ما» بدل «سقط المُسمّى». و`failing_tests` كانت موجودة وتستخرج
    # `FAILED/ERROR` فعلاً — فالفجوة كانت في **مصدر القرار** لا في القدرة على القياس.
    if expected not in observed:
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
            code, out = _run_tests_for_mutation(test_file, mutation["expect"], root)
            outcomes.append(_outcome(code, out, mutation["expect"]))
        finally:
            src.write_text(original, encoding="utf-8")
            _ACTIVE_RESTORES.pop(src, None)
    return outcomes


def parse_shard(raw: str | None) -> tuple[int, int] | None:
    """`i/N` — الفهرس صفريّ والمقام موجب، وأيّ شكلٍ آخر فشلٌ يُسمّي نفسه.

    فاشل-مغلق عمداً: `--shard` مشوّهةٌ تُقرأ «بلا تقسيم» تعني حزمةً تزرع **كلّ**
    الطفرات بينما أخواتها تزرع أنصبتها — فتُقرأ خضرتُها تغطيةً وهي تكرار.
    """
    if raw is None:
        return None
    if raw.count("/") != 1:
        raise SystemExit(f"✗ --shard {raw!r}: الشكل `i/N` (مثال `0/5`).")
    head, _, tail = raw.partition("/")
    try:
        index, total = int(head), int(tail)
    except ValueError:
        raise SystemExit(f"✗ --shard {raw!r}: الفهرس والمقام عددان صحيحان.") from None
    if total < 1:
        raise SystemExit(f"✗ --shard {raw!r}: المقام يجب أن يكون ≥ 1.")
    if not 0 <= index < total:
        raise SystemExit(f"✗ --shard {raw!r}: الفهرس خارج [0, {total - 1}].")
    return index, total


def _shard_assignment(weights: list[tuple[str, int]], total: int) -> dict[str, int]:
    """توزيعٌ **حتميّ موزون** بالطفرات — لا بتجزئة الاسم.

    الحتميّة شرطُ صحّةٍ لا تفضيل: حزمتان تحسبان القسمة بطريقتين مختلفتين تتركان
    طفراتٍ لا تزرعها أيٌّ منهما، ولا شيء يُظهِر ذلك. ولذلك: ترتيبٌ ثابت (الأثقل
    أوّلاً، وعند التساوي بالاسم) ثمّ إسنادٌ إلى أخفّ حزمة — بلا `hash()` الذي
    يُبذَّر عشوائيّاً بين العمليّات فيُنتِج توزيعين مختلفين لنفس المدخل.

    **والوزن طفراتٌ لا أسماء — مقيسٌ لا مفترَض:** تجزئةُ الاسم أعطت على السجلّ
    الحاليّ توزيعاً من ٣٣ إلى ١٥٢ طفرة (٤٫٦×)، والزمن الحائطيّ يحكمه الأثقل —
    فكان نصفُ مكسب التقسيم يضيع في حزمةٍ واحدة. والموزون يُقارِبها إلى ~٩٣.
    """
    order = sorted(weights, key=lambda item: (-item[1], item[0]))
    loads = [0] * total
    assignment: dict[str, int] = {}
    for name, weight in order:
        index = min(range(total), key=lambda i: (loads[i], i))
        assignment[name] = index
        loads[index] += weight
    return assignment


def _plantable_weights(registry: dict, root: Path = ROOT) -> list[tuple[str, int]]:
    """(اسم، عدد طفراته) لكلّ ما يُزرَع — القسمان معاً بنفس القاعدة."""
    weights = [(name, len(spec["mutations"])) for name, spec in registry["mutated"].items()]
    weights += [
        (name, len(spec["mutations"])) for name, _src, spec in behavioural_specs(registry, root)
    ]
    return weights


def shard_of(name: str, total: int, registry: dict | None = None, root: Path = ROOT) -> int:
    """حزمةُ حارسٍ بعينه وفق التوزيع الموزون الحتميّ."""
    reg = registry if registry is not None else load_registry()
    return _shard_assignment(_plantable_weights(reg, root), total)[name]


def _run_mutations_in_place(
    registry: dict,
    only: str | None,
    ci: Path,
    root: Path,
    shard: tuple[int, int] | None = None,
) -> list[str]:
    """ازرع داخل workspace غير قانونيّ (نسخة مؤقتة أو fixture اختبار فقط)."""
    failures: list[str] = []
    plantable = [
        (name, _mutated_source(name, ci=ci, root=root), spec)
        for name, spec in sorted(registry["mutated"].items())
    ]
    plantable += behavioural_specs(registry, root)
    if shard is not None:
        index, total = shard
        assignment = _shard_assignment(_plantable_weights(registry, root), total)
        plantable = [entry for entry in plantable if assignment.get(entry[0]) == index]
    # **مرشِّحٌ لا يُطابِق شيئاً كان يطبع `ok`.** المطابقة بالاسم **كاملاً**، ومفاتيح
    # القسم السلوكيّ مساراتٌ (`.github/workflows/certify-run.yml`) لا أسماءَ مختصرة —
    # فـ`--only certify-run` كان يزرع **صفر** طفرة ويخرج ناجحاً. ووقع ذلك عليّ مرّتين
    # في جلسةٍ واحدة: قرأتُ أخضرَه إثباتاً بينما لم يُقَس شيء. وهو الصنف نفسه الذي
    # يلاحقه هذا الحارس، في أداته هو. فصار «لم أجد ما أزرعه» فشلاً يُسمّي البدائل.
    if only and not any(name == only for name, _, _ in plantable):
        return [
            f"--only {only!r} لا يُطابِق أيّ مواصفة ⇒ صفر طفرة مزروعة. "
            "المطابقة بالاسم كاملاً، ومفاتيحُ القسم السلوكيّ مسارات. "
            f"المتاح: {', '.join(sorted(n for n, _, _ in plantable))}"
        ]
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
                code, out = _run_tests_for_mutation(test_file, m["expect"], root)
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
            elif m["expect"] not in failing_tests(out):
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
    shard: tuple[int, int] | None = None,
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
        return _run_mutations_in_place(registry, only, ci, root, shard)

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
        return _run_mutations_in_place(registry, only, mirror / ci_relative, mirror, shard)


def shard_inventory(registry: dict, total: int, root: Path = ROOT) -> dict:
    """جردُ الأنصبة — **حارسُ اتّحادٍ فاشل-مغلق للتقسيم**.

    حزمةٌ تسقط صامتةً (وظيفةٌ أُلغيت، أو مقامٌ اختلف بين حزمتين، أو تجزئةٌ تغيّرت)
    تترك طفراتٍ لا يزرعها أحد — وكلُّ الحزم الباقية خضراء. فالمجموع يُقاس صراحةً:
    ``sum(نصيب كلّ حزمة) == الكون``، وأيّ نقصٍ فشلٌ يُسمّي الحزمة الفارغة.

    ولا يكفي عدُّ الحرّاس: الكلفة طفراتٌ لا أسماء، فيُعَدّ الاثنان معاً — ويُطبَع
    التوزيع كي يُرى الميل قبل أن يصير حزمةً تُهيمن على الزمن الحائطيّ.
    """
    plantable = [(name, spec) for name, spec in sorted(registry["mutated"].items())]
    plantable += [(name, spec) for name, _src, spec in behavioural_specs(registry, root)]
    universe_guards = len(plantable)
    universe_mutations = sum(len(spec["mutations"]) for _name, spec in plantable)

    assignment = _shard_assignment(_plantable_weights(registry, root), total)
    shards = []
    for index in range(total):
        members = [(n, s) for n, s in plantable if assignment.get(n) == index]
        shards.append(
            {
                "shard": f"{index}/{total}",
                "guards": len(members),
                "mutations": sum(len(s["mutations"]) for _n, s in members),
            }
        )
    covered_guards = sum(s["guards"] for s in shards)
    covered_mutations = sum(s["mutations"] for s in shards)
    empty = [s["shard"] for s in shards if s["guards"] == 0]
    return {
        "total": total,
        "universe": {"guards": universe_guards, "mutations": universe_mutations},
        "covered": {"guards": covered_guards, "mutations": covered_mutations},
        "shards": shards,
        "empty_shards": empty,
        "union_complete": covered_guards == universe_guards
        and covered_mutations == universe_mutations,
    }


def shard_inventory_failures(inventory: dict) -> list[str]:
    """أسبابُ حجب الجرد — الاتّحاد الناقص والحزمةُ الفارغة عطلان مختلفان."""
    failures: list[str] = []
    if not inventory["union_complete"]:
        failures.append(
            "اتّحادُ الحزم لا يساوي الكون: "
            f"حرّاس {inventory['covered']['guards']}/{inventory['universe']['guards']} · "
            f"طفرات {inventory['covered']['mutations']}/{inventory['universe']['mutations']} — "
            "طفراتٌ لا تزرعها أيّ حزمة، وكلُّ الحزم خضراء."
        )
    if inventory["empty_shards"]:
        failures.append(
            f"حزمٌ فارغة: {inventory['empty_shards']} — وظيفةٌ تُشغَّل ولا تقيس شيئاً "
            "تُقرأ خضرتُها تغطيةً. اخفض المقام أو أعِد النظر في التجزئة."
        )
    return failures


# ═══ تجميدُ سطح الحجب — إرشاديٌّ حتّى يُكذَّب هو نفسُه ═══════════════════════
#
# **العطلُ الذي يُقاس هنا:** يُضاف الحارسُ لأنّه يبدو صواباً، لا لأنّ عطلاً وقع. فينمو
# سطحُ الحجب أسرعَ ممّا يُثبَت، ويصير الأخضرُ ثمناً يُدفَع لا معلومةً تُقرأ. والمقيسُ
# في هذه الشجرة يقول ذلك بلا تأويل: **٢٩٦ ثلاثيّةَ حجبٍ** من **٢٦٧ حارساً**، وأقلُّ
# من خُمسها له مواصفةُ طفرةٍ تُثبِت أنّه يُطلِق حين يوجد العطل.
#
# **ووحدةُ القياس ثلاثيّةٌ لا اسمُ حارس:** `(الحارس، الـworkflow، الوظيفة)`. لأنّ
# استدعاءَ حارسٍ **قائمٍ** في وظيفةٍ ثانيةٍ توسيعٌ لسطح الحجب أيضاً — يصير يحجب حيث
# لم يكن يحجب — وعدُّ الأسماء وحدَها يُخفيه.
#
# **ولا نموذجَ ثانٍ للاشتقاق:** المصدرُ هو `guard_catalogue.discover_invocations`
# نفسُه الذي يولّد الكتالوج. نموذجان لسطحٍ واحد كانا سينحرفان، وهو الصنفُ الذي
# أُغلِق في هذه الشجرة مراراً.
#
# **وحدُّ تغطيةٍ مُعلَنٌ لا مطويّ:** هذا يقيس **سطحَ الاستدعاء** وحدَه. تشديدُ عتبةٍ
# داخل حارسٍ قائم، أو ترقيةُ فحصٍ إرشاديٍّ إلى حاجب، أو إضافةُ سياقٍ مطلوبٍ في
# الـruleset — **لا يقيسها هذا**. الأخيرةُ خارج المستودع أصلاً. فمن قرأ أخضرَه
# «سطحُ الحجب لم يتوسّع» قرأ أكثرَ ممّا قيس.


def discover_blocking_surface() -> set[tuple[str, str, str]]:
    """ثلاثيّاتُ الحجب الحاليّة — مشتقّةٌ من `guard_catalogue`، لا مكرّرةٌ عنه."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_guard_catalogue_for_surface", CI / "guard_catalogue.py"
    )
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit("cannot load guard_catalogue")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        (guard, workflow, job)
        for guard, places in module.discover_invocations().items()
        for (workflow, job) in places
    }


def _load_surface_json(path: Path, key: str) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in (data.get(key) or {}).items() if not k.startswith("$")}


def surface_key(triple: tuple[str, str, str]) -> str:
    """مفتاحٌ نصّيٌّ للثلاثيّة — الشكلُ واحدٌ في الأساس والإقرارات معاً."""
    return "{}::{}::{}".format(*triple)


def registered_mutation_tests(registry: dict) -> dict[str, set[str]]:
    """الاختباراتُ المُسمّاة في طفرات كلّ حارس — مفتاحُها اسمُ ملفّ الحارس المجرَّد.

    يُقرأ من `guard_mutation_registry.json` نفسِه لا من نسخةٍ عنه، فلا يصير للطفرات
    تعريفان.

    والمقروءُ `expect` — **اسمُ الاختبار الذي يجب أن يحمرّ** — لا `mutation_test`،
    فذاك يُعيد ملفَّ الجناح لا اسمَ الحالة. (خلطتُهما أوّلَ مرّة فأبلغ الفحصُ عن
    طفرةٍ مسجَّلةٍ بأنّها غيرُ مسجَّلة، وكشفه تشغيلٌ لا قراءة.)
    """
    tests: dict[str, set[str]] = {}
    for section in ("mutated", "behavioural"):
        for label, spec in (registry.get(section) or {}).items():
            if label.startswith("$") or not isinstance(spec, dict):
                continue
            named = {
                str(mutation.get("expect") or "").strip()
                for mutation in (spec.get("mutations") or [])
                if isinstance(mutation, dict)
            }
            tests.setdefault(Path(label).name, set()).update(n for n in named if n)
    return tests


def addition_violations(
    key: str,
    declaration: object,
    known_mutation_tests: dict[str, set[str]] | None = None,
) -> list[str]:
    """ما ينقص إقرارَ زيادةٍ ليكون إقراراً — دالّةٌ نقيّةٌ تُختبَر بلا ملفّات.

    و`known_mutation_tests` هو ما يجعل `mutation` حقلاً **مقيساً لا نثراً**: أوّلُ
    إقرارٍ كُتِب في هذا الملفّ حمل جملةً تذكر اسمَ الاختبار داخلها، وكان الحقلُ
    سيقبل «طفرةٌ ما» بالقدر نفسِه — أي شرطاً يُستوفى بالكتابة لا بالتسجيل. فصار
    الحقلُ يُطالَب باسمِ اختبارٍ **مسجَّلٍ لهذا الحارس بعينه**، والنثرُ إلى
    `$mutation_ar`. ويُترك `None` في الاختبارات النقيّة التي لا تملك سجلّاً.
    """
    if not isinstance(declaration, dict):
        return [f"{key}: الإقرار ليس كائناً"]
    problems = [
        f"{key}: ينقصه `{field}`"
        for field in _REQUIRED_ADDITION_FIELDS
        if not str(declaration.get(field) or "").strip()
    ]
    impact = str(declaration.get("impact") or "").strip()
    if impact and impact not in _IMPACT_PLACEMENTS:
        problems.append(
            f"{key}: `impact` = {impact!r} ليس قيمةَ أثرٍ معروفة ({'/'.join(_IMPACT_PLACEMENTS)})"
        )
    mutation = str(declaration.get("mutation") or "").strip()
    if mutation and known_mutation_tests is not None:
        guard = Path(key.split("::")[0]).name
        registered = known_mutation_tests.get(guard, set())
        if mutation not in registered:
            problems.append(
                f"{key}: `mutation` = {mutation!r} ليس اسمَ اختبارٍ مسجَّلاً لـ{guard} "
                "في `guard_mutation_registry.json` — الإقرارُ يسمّي تكذيباً لا وجودَ له"
            )
    return problems


def retirement_violations(key: str, declaration: object) -> list[str]:
    """ما ينقص إقرارَ تقاعدٍ ليكون إقراراً — سببٌ نصّيٌّ وتاريخُ إقرار.

    ولا يُطلَب هنا تكذيبٌ ولا شاهدٌ موجب: التقاعدُ **إزالةُ** حجبٍ لا إضافتُه، فلا
    شيءَ جديدٌ يُقاس. المطلوبُ أن يُقال **لماذا** ومتى، فيبقى القرارُ مقروءاً.
    """
    if not isinstance(declaration, dict):
        return [f"{key}: إقرارُ التقاعد ليس كائناً"]
    return [
        f"{key}: ينقص إقرارَ التقاعد `{field}`"
        for field in ("reason", "retired_on")
        if not str(declaration.get(field) or "").strip()
    ]


def blocking_surface_findings(
    current: set[tuple[str, str, str]],
    baseline: dict,
    additions: dict,
    known_mutation_tests: dict[str, set[str]] | None = None,
    retirements: dict | None = None,
) -> list[str]:
    """أربعةُ اتّجاهات: زيادةٌ بلا إقرار · إقرارٌ ناقص · إقرارٌ لزيادةٍ زالت · **وحاجبٌ
    تقاعد بلا إقرار**.

    **والرابعُ مقيسٌ لا مُتوقَّع** — قِيس على `main @ a3124ccf` بنزع سطرٍ واحد:
    استدعاءُ `vegetation_runtime_truth_guard.py` من `ci.yml`. فهبط السطحُ ٣٠١ ⇒ ٣٠٠،
    واشتكى فحصُ انحراف الكتالوج وحدَه — **وعلاجُه المنصوصُ عليه إعادةُ التوليد**،
    فإذا فُعِل قال الاثنان معاً `guard_catalogue_ok` و`blocking_surface_ok`. أي أنّ
    **العلاجَ الذي يأمر به النظامُ هو ما يمحو الدليل**، ويبقى ملفُّ الحارس في مكانه
    يبدو حمايةً ولا يُشغّله شيء: «حارسٌ يبدو أنّه يحرس ولا يحرس» على مستوى الـworkflow.

    **ولا يُمنَع التقاعد — يُطالَب بأن يُنطَق.** كان السطرُ السابق يقول إنّ التقلّص
    «تضييقٌ مشروعٌ لا انحراف»، وهو صحيحٌ في الحكم وخاطئٌ في النتيجة: مشروعيّةُ الفعل
    لا تُبرّر **صمتَه**. فيكفيه سببٌ وتاريخ، ويبقى الحذفُ بابَ من يعرف ما يحذف.
    """
    findings: list[str] = []
    frozen = set(baseline)
    declared = set(additions)
    retired = set(retirements or {})
    live = {surface_key(t) for t in current}

    for key in sorted(live - frozen - declared):
        findings.append(f"زيادةٌ في سطح الحجب بلا إقرار — {key}")
    for key in sorted(declared & live):
        findings.extend(addition_violations(key, additions[key], known_mutation_tests))
    for key in sorted(declared - live):
        findings.append(f"إقرارُ زيادةٍ لا وجودَ لها في الشجرة — {key}")
    # **الأساسُ وحدَه، لا الإقرارات.** إقرارُ زيادةٍ زالت يغطّيه الاتّجاهُ الثالث
    # أعلاه، وعلاجُه حذفُ الإقرار لا كتابةُ تقاعد. وضمُّ `declared` هنا كان يُنتِج
    # **ملاحظتين لحقيقةٍ واحدة** — وسجلٌّ يقول الشيءَ مرّتين يُدرِّب قارئَه على
    # تخطّيه، وهو الصنفُ نفسُه الذي تُغلقه هذه الآليّة. أمسكه اختبارٌ قائم.
    for key in sorted(frozen - live - retired):
        findings.append(f"حاجبٌ زال من سطح الحجب بلا إقرار تقاعد — {key}")
    for key in sorted(retired & live):
        findings.append(f"إقرارُ تقاعدٍ لحاجبٍ ما زال يعمل — {key}")
    for key in sorted(retired - live):
        findings.extend(retirement_violations(key, (retirements or {})[key]))
    return findings


def report_blocking_surface(*, enforce: bool = False) -> int:
    """يطبع حالةَ السطح. **إرشاديٌّ افتراضيّاً** — يُعيد 0 مهما وجد.

    و`--enforce` **غيرُ موصولٍ بأيّ workflow**: يوجد ليُشغَّل يدويّاً ويُكذَّب، فترقيتُه
    إلى الحجب تصير قراراً يُتَّخذ بقياسٍ لا بالنسيان. وهذا ما تشترطه السياسةُ على
    نفسِها: لا يُرقّى فحصٌ إلى حاجبٍ قبل أن يُكذَّب هو أوّلاً.
    """
    current = discover_blocking_surface()
    baseline = _load_surface_json(BLOCKING_SURFACE_BASELINE, "legacy_blocking")
    additions = _load_surface_json(BLOCKING_SURFACE_ADDITIONS, "additions")
    retirements = _load_surface_json(BLOCKING_SURFACE_BASELINE, "retired")
    findings = blocking_surface_findings(
        current,
        baseline,
        additions,
        registered_mutation_tests(load_registry()),
        retirements,
    )

    print(
        f"blocking_surface: {len(current)} ثلاثيّةً حاليّة · "
        f"{len(baseline)} مُجمَّدةً (legacy_blocking) · {len(additions)} إقراراً · "
        f"{len(retirements)} تقاعداً"
    )
    if findings:
        print(f"\nblocking_surface: {len(findings)} ملاحظة" + ("" if enforce else " (إرشاديّ)"))
        for line in findings:
            print(f"  ⚠ {line}")
        # **الإرشادُ يتبع نوعَ الملاحظة.** كان يُطبَع نصُّ الزيادة مهما كانت الملاحظة،
        # فيُقرأ على تقاعدٍ فيُطالِبه بطفرةٍ وشاهدٍ موجب — وهو مطلبٌ لا معنى له لإزالةِ
        # حجب. ورسالةٌ تصف واجباً غيرَ الواجب تُدرِّب قارئَها على تجاهل الرسائل.
        if any("تقاعد" in line for line in findings):
            print(
                "\nوالتقاعدُ لا يُمنَع بل يُنطَق: أدرِج الثلاثيّة في `retired` داخل "
                "`blocking_surface_baseline.json` بـ`reason` و`retired_on`."
            )
        if any("زيادة" in line for line in findings):
            print(
                "\nوكلُّ زيادةٍ تحتاج قبل تفعيلها: مثالاً مضادّاً مقيساً (أو التزامَ سلامة) · "
                "طفرةً يقتلها اختبارٌ مُسمًّى · شاهداً موجباً أنّ العلاج المشروع يمرّ · "
                "وتصنيفَ أثرٍ يقول أين يحجب."
            )
        if enforce:
            return 1
    else:
        print("blocking_surface_ok — لا زيادةَ بلا إقرار ولا تقاعدَ بلا نطق")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true", help="ازرع الطفرات وشغّل اختباراتها")
    p.add_argument("--only")
    p.add_argument(
        "--shard",
        help="`i/N` — حزمةٌ حتميّة بتجزئة اسم الحارس. الاتّحاد مقيسٌ لا مفترَض: "
        "شغّل `--shard-inventory N` لتقرأ الأنصبة، ومجموعُها يجب أن يساوي الكون.",
    )
    p.add_argument("--shard-inventory", type=int, metavar="N")
    p.add_argument(
        "--blocking-surface",
        action="store_true",
        help="قِس سطحَ الحجب مقابل الأساس المُجمَّد — **إرشاديّ**، يُعيد 0 مهما وجد",
    )
    p.add_argument(
        "--enforce",
        action="store_true",
        help="مع `--blocking-surface`: اجعلها حاجبة. غيرُ موصولٍ بأيّ workflow عمداً — "
        "الترقيةُ إلى الحجب قرارٌ يُتَّخذ بقياسٍ لا بالنسيان.",
    )
    args = p.parse_args()

    if args.blocking_surface:
        return report_blocking_surface(enforce=args.enforce)

    registry = load_registry()

    if args.shard_inventory is not None:
        inventory = shard_inventory(registry, args.shard_inventory)
        for entry in inventory["shards"]:
            print(f"  {entry['shard']}: {entry['guards']} حارساً · {entry['mutations']} طفرة")
        problems = shard_inventory_failures(inventory)
        if problems:
            print("\nshard_inventory: FAIL", file=sys.stderr)
            for line in problems:
                print(f"  ✗ {line}", file=sys.stderr)
            return 1
        print(
            f"\nshard_inventory_ok (الاتّحاد كامل: {inventory['universe']['guards']} حارساً · "
            f"{inventory['universe']['mutations']} طفرة على {inventory['total']} حزم)"
        )
        return 0

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
        failures += run_mutations(registry, args.only, shard=parse_shard(args.shard))

    if failures:
        print("\nguard_mutation_guard: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print("\nguard_mutation_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
