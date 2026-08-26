#!/usr/bin/env python3
"""محارف الاتّجاه الخفيّة — BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01.

**الحادثة المقيسة:** محرف `U+200F` (RLM) في docstring عربيّ أسقط *Security Scan* في CI
بـ**B613 trojansource** (HIGH ⇒ حاجب)، على رأسٍ أُعلِن أخضر. وفاتَ لأنّ `preflight.sh`
بالملفّ الافتراضيّ **لا يُشغّل bandit** — هو في `--full` وحده، والدفعُ كان على الافتراضيّ.

**وصنفان لا صنف — والخلط بينهما هو ما يجعل الحارس إمّا أعمى أو مُزعِجاً:**

* **قلبُ الاتّجاه (`override`/`isolate`)** — `RLE`·`LRE`·`RLO`·`LRO`·`PDF`·`LRI`·`RLI`
  ·`FSI`·`PDI`. هذه **تُعيد ترتيب الرموز بصريّاً**: سطرٌ يقرؤه المراجع `if (admin)`
  ويُنفَّذ غيرَه. هي هجوم *trojan source* (CVE-2021-42574) بعينه، ولا استعمال مشروع
  لها في مصدرٍ أو وثيقة هنا. **تُحجَب مطلقاً، بلا أساس ولا استثناء.** والمقيس اليوم: صفر.
* **العلاماتُ والخفايا** — `RLM`·`LRM`·`ALM`·`ZWNJ`·`BOM`. لا تقلب ترتيباً؛ تضبط اتّجاه
  محرفٍ محايد (قوسٌ في نصّ عربيّ مثلاً)، وهو **استعمال مشروع كتبتُه بنفسي**. لكنّها خفيّة،
  و`bandit` يحجب `RLM` ولا يحجب `LRM` — فـ«استبدال RLM بـLRM» يُمرِّر البوّابة **ويُبقي
  المحرف الخفيّ**. فتُحكَم بأساسٍ مُعلَن **يتقلّص ولا ينمو**، لا بحظرٍ يُكذَّب أوّل مرّة.

**ولماذا لم يكفِ `bandit`:** نطاقه `services/ bots/ agents/` وحدها، وهذه المحارف مقيسة في
**٩٣ ملفّاً** عبر الشجرة — `json`·`md`·`yml`·`sql`·`tsx`·`ps1`. أي أنّ البوّابة القائمة
كانت تحرس عُشر السطح وتُقرأ حراسةً له كلّه.

**وهذا رخيصٌ عمداً:** Python صرف بلا `bandit`، فيعمل في الملفّ **الافتراضيّ** — والحادثة
كلّها كانت «اختيارُ ملفٍّ أرخص ثمّ قراءةُ أخضره أخضرَ CI».

    python scripts/ci/bidi_control_char_guard.py            # بوّابة
    python scripts/ci/bidi_control_char_guard.py --generate # أعِد توليد الأساس
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجٌ عربيّ يُرمَّز بلغة الآلة.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "architecture" / "bidi_control_char_baseline.json"

# قلبُ الاتّجاه — يُعيد ترتيب الرموز بصريّاً. محظورٌ مطلقاً.
OVERRIDES = {
    0x202A: "LRE",
    0x202B: "RLE",
    0x202C: "PDF",
    0x202D: "LRO",
    0x202E: "RLO",
    0x2066: "LRI",
    0x2067: "RLI",
    0x2068: "FSI",
    0x2069: "PDI",
}

# علاماتٌ وخفايا — لا تقلب ترتيباً، ومحكومة بأساسٍ يتقلّص.
MARKS = {
    0x200E: "LRM",
    0x200F: "RLM",
    0x061C: "ALM",
    0x200B: "ZWSP",
    0x200C: "ZWNJ",
    0x200D: "ZWJ",
    0xFEFF: "BOM",
}


def strip_added(base: str = "origin/main", root: Path = ROOT) -> dict[str, int]:
    """يحذف علاماتِ `MARKS` من **الأسطر المضافة وحدها** مقابل ``base``.

    ``BIDI-MARKS-ARE-REINTRODUCED-FASTER-THAN-DISCIPLINE-REMOVES-THEM-01``

    **العطل المقيس مرّتين في ساعة، لا مرّة:** شريحةُ دماغٍ حُجِبت بسبع علامات `RLM`
    أدخلها نصٌّ عربيٌّ مخلوط — كلُّها بنمطٍ واحد: بعد قوسٍ مفتوحٍ يليه رقمٌ أو
    لاتينيّ. أُزيلت، وأُعلِن أنّ النمط صار متجنَّباً — ثمّ عاد **في أوّل نصٍّ جديد**
    بثلاث علامات. فالمحرفُ لا يُرى بالعين ولا ينفع فيه انضباط.

    ورسالةُ الحارس كانت تقول «احذف الزائد» وتترك **كيف** للقارئ؛ والحذفُ اليدويّ
    على محرفٍ غير مرئيّ إمّا أن يُخطئ الموضع أو يمسّ سطراً سابقاً — وهو ما ينقض
    إلحاقيّةَ ملفّات الدماغ.

    **ولماذا الأسطرُ المضافة وحدها:** الأساسُ يتقلّص ولا ينمو، فالمطلوبُ إزالةُ ما
    **أُدخِل** لا تنظيفُ الشجرة. وتنظيفٌ شامل يمسّ سطوراً ملتزَمةً سابقاً ويُخفي
    انحرافاً لم يقع في هذه الشريحة.

    **ولا يُستدعى من `preflight` تلقائيّاً بقرارٍ صريح:** أداةُ القياس لا تُعدّل
    الشجرة أثناء قياسها — ذاك صنفُ التلوّث نفسُه (`LESSON-CONCURRENT-PREFLIGHT-…-01`).
    فالرسالةُ تُسمّي الأمر، والتشغيلُ فعلٌ مقصود.

    **حدٌّ مُعلَن — لا يُميّز العيّنةَ من السهو.** الحارسُ يُميّز بأساسٍ لكلّ ملفّ؛
    وهذا الوضعُ يحذف **كلّ** علامةٍ في سطرٍ مضاف. فملفٌّ يحتاج المحرفَ **عمداً** —
    كاختبارٍ يزرعه عيّنةً — يُتلَف بصمت: تصير الثابتةُ فارغةً وتمرّ اختباراتُه بلا
    أن تختبر شيئاً.

    **ووقع هذا على أوّل استعمالٍ حقيقيّ:** `tests_v9/test_bidi_strip_added.py` —
    شهادةُ هذا الوضع نفسِه — كُتِبت بمحرفَين حرفيَّين فحجبها الحارس، **ورسالتُه
    أرشدت إلى الوضع الذي كان سيُفرِغ عيّنتَيها**. فالأداةُ كانت ستُعطّل شهادتَها
    على نفسها.

    **فالقاعدة:** العيّنةُ لمحرفٍ غير مرئيّ تُكتَب **هروباً** (``"\\u200f"``) لا
    حرفاً. والأداةُ لا تستطيع فرضَ ذلك — **تُعلِنه ولا تحرسه**.

    **وهذا يجعل العلاجَ أضيقَ ممّا يبدو:** يُزيل نمطَ السهو في الكتابة العربيّة
    المخلوطة (مقيسٌ مرّتين في ساعة) ويترك نمطَ «العيّنة المقصودة» بلا حارس.
    """
    marks = "".join(chr(cp) for cp in MARKS)
    table = str.maketrans("", "", marks)
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--unified=0", base],
        capture_output=True,
        encoding="utf-8",
        check=False,
    ).stdout
    added: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current:
            body = line[1:]
            if any(ch in marks for ch in body):
                added.setdefault(current, []).append(body)
    cleaned: dict[str, int] = {}
    for name, lines in added.items():
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        removed = 0
        for old in lines:
            new = old.translate(table)
            if new != old and old in text:
                text = text.replace(old, new)
                removed += len(old) - len(new)
        if removed:
            path.write_text(text, encoding="utf-8")
            cleaned[name] = removed
    return cleaned


def tracked_files(root: Path = ROOT) -> list[str]:
    """ملفّات git المتتبَّعة — لا مسحُ قرصٍ يبتلع `node_modules` وبيئات افتراضيّة."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def scan_text(text: str) -> tuple[Counter, Counter]:
    """(القالبات، العلامات) في نصٍّ واحد، معدودةً باسم المحرف."""
    overrides: Counter = Counter()
    marks: Counter = Counter()
    for ch in text:
        code = ord(ch)
        if code in OVERRIDES:
            overrides[OVERRIDES[code]] += 1
        elif code in MARKS:
            marks[MARKS[code]] += 1
    return overrides, marks


def scan(root: Path = ROOT) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """يمسح الشجرة ويُعيد (قالباتٌ لكلّ ملفّ، عددُ العلامات لكلّ ملفّ).

    الملفّات الثنائيّة تُتخطّى بصمت — لا نصّ فيها يُقرأ، وإدانتُها كانت ستُنتِج ضجيجاً.
    """
    overrides: dict[str, dict[str, int]] = {}
    marks: dict[str, int] = {}
    for name in tracked_files(root):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found_overrides, found_marks = scan_text(text)
        if found_overrides:
            overrides[name] = dict(found_overrides)
        if found_marks:
            marks[name] = sum(found_marks.values())
    return overrides, marks


def _head_sha(root: Path = ROOT) -> str:
    """بصمةُ الرأس التي قِيس عندها الأساس — يكتبها المولّد لا اليد."""
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    ).stdout.strip()


def load_baseline(path: Path = BASELINE) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("marks_per_file", {}).items() if not k.startswith("$")}


def violations(
    overrides: dict[str, dict[str, int]], marks: dict[str, int], baseline: dict[str, int]
) -> list[str]:
    """أسبابُ الحجب. الفارغة تعني مروراً."""
    failures: list[str] = []
    for name, counts in sorted(overrides.items()):
        detail = " · ".join(f"{k}×{v}" for k, v in sorted(counts.items()))
        failures.append(
            f"{name}: محرفُ قلبِ اتّجاه ({detail}) — يُعيد ترتيب الرموز بصريّاً، "
            "فيقرأ المراجع سطراً ويُنفَّذ غيرُه. لا أساس له ولا استثناء: احذفه."
        )
    for name, count in sorted(marks.items()):
        allowed = baseline.get(name, 0)
        if count > allowed:
            failures.append(
                f"{name}: {count} محرفاً خفيّاً والمُعلَن {allowed} — الأساس يتقلّص ولا ينمو. "
                "احذف الزائد (لا تستبدله بـLRM: يُمرِّر bandit ويُبقي المحرف). "
                "وللحذف من أسطرك المضافة وحدها: "
                "`python3 scripts/ci/bidi_control_char_guard.py --strip-added`."
            )
    return failures


def generate(path: Path = BASELINE, root: Path = ROOT) -> dict:
    overrides, marks = scan(root)
    data = {
        "$comment": (
            "أساسٌ مُعلَن لـBIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01 — **علاماتٌ "
            "وخفايا فقط** (RLM·LRM·ALM·ZWNJ·ZWSP·ZWJ·BOM). لا تقلب ترتيب الرموز، وأكثرها "
            "استعمالٌ مشروع لضبط اتّجاه محرفٍ محايد في نصّ عربيّ — لكنّها خفيّة، فتُحكَم "
            "بعددٍ **يتقلّص ولا ينمو**. أمّا محارف قلب الاتّجاه (override/isolate) فمحظورة "
            "مطلقاً ولا أساس لها: هي هجوم trojan source بعينه، والمقيس اليوم صفر."
        ),
        "$why_not_a_ban_ar": (
            "الحظر الشامل كان سيُكذَّب أوّل مرّة: ٣٥٠ محرفاً في ٩٣ ملفّاً، أكثرها كتبتُه "
            "بنفسي لضبط اتّجاه قوسٍ في شرحٍ عربيّ. وأساسٌ يُكذَّب فوراً يُدرَّب قارئه على "
            "تعطيله — وهو أسوأ من غيابه."
        ),
        "$measured_by_ar": "python scripts/ci/bidi_control_char_guard.py --generate",
        # ختمُ الأساس يكتبه **المولّد** لا يدٌ: مصنوعةٌ مقيسة يُكتَب أساسُها بيدٍ تدّعي
        # قياساً لم يجرِ — وهو عقد `claim_base_registry` (مقيس ⇒ `measured_on`).
        "measured_on": _head_sha(root),
        "gap": "BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01",
        "overrides_present": overrides,
        "marks_per_file": dict(sorted(marks.items())),
        "totals": {"files": len(marks), "marks": sum(marks.values())},
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="محارف الاتّجاه الخفيّة")
    parser.add_argument("--generate", action="store_true", help="أعِد توليد الأساس")
    parser.add_argument(
        "--strip-added",
        action="store_true",
        help="احذف العلامات من الأسطر المضافة مقابل الأساس (لا يمسّ سطراً سابقاً)",
    )
    parser.add_argument("--base", default="origin/main", help="أساسُ المقارنة لـ--strip-added")
    args = parser.parse_args(argv)

    if args.strip_added:
        cleaned = strip_added(args.base)
        if not cleaned:
            print("bidi_control_char_guard: لا علامةَ خفيّة في الأسطر المضافة — لا تغيير")
            return 0
        print(f"bidi_control_char_guard: نُظِّف {len(cleaned)} ملفّاً مقابل {args.base}")
        for name, removed in sorted(cleaned.items()):
            print(f"- {name}: {removed} علامةً محذوفة من أسطرٍ مضافة")
        return 0

    if args.generate:
        data = generate()
        print(
            f"bidi_control_char_guard: كُتِب الأساس — {data['totals']['files']} ملفّاً "
            f"· {data['totals']['marks']} محرفاً خفيّاً · "
            f"{len(data['overrides_present'])} ملفّاً فيه قلبُ اتّجاه"
        )
        return 0

    overrides, marks = scan()
    failures = violations(overrides, marks, load_baseline())
    if failures:
        print("bidi_control_char_guard_failed")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        f"bidi_control_char_guard_ok (لا قلبَ اتّجاه · "
        f"{sum(marks.values())} علامةً خفيّة في {len(marks)} ملفّاً، ضمن الأساس)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
