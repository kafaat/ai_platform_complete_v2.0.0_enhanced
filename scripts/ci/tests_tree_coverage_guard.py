#!/usr/bin/env python3
"""شجرة ``tests/`` تُشغَّل كاملةً ناقص أساس مُبرَّر — لا بقائمة سماح مكتوبة يدويّاً.

``ARCH-TESTS-UNLISTED-IN-CI-01``. ``pytest.ini`` يحصر ``testpaths`` في ``tests_v9``،
فكلّ ما تحت ``tests/`` كان يُشغَّل بقائمة مسارات صريحة في الـworkflows — ٣٥ ملفّاً
اسماً اسماً. أيّ ملفّ **جديد** يقع خارج القائمة صامتاً، ولا شيء يقارن محتوى الشجرة
بالقائمة. مقيس على ``bb53981e``: **٦٦ من ١١٢** ملفّاً لا يذكره أيّ workflow، بينها
الخمسة عشر في جذر ``tests/`` كلّها.

إطالة القائمة تُعيد إنتاج العلّة. الشكل المعتمَد: وظيفة تشغّل ``pytest tests`` كاملةً،
والاستثناءات **تُشتقّ من هذا الأساس** عبر ``--pytest-ignores`` بدل أن تُكتب في الـYAML —
فلا يُستثنى ملفّ بلا مدخل يحمل سببه ودليله وشرط إغلاقه، والملفّ الجديد مُغطّى تلقائيّاً
بلا أن يتذكّره أحد.

    python scripts/ci/tests_tree_coverage_guard.py --check
    python scripts/ci/tests_tree_coverage_guard.py --pytest-ignores   # لخطوة CI
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
BASELINE = ROOT / "docs" / "testing" / "tests_tree_baseline.json"
WORKFLOWS = ROOT / ".github" / "workflows"

# خطوة CI يجب أن تسأل السكربت عن الاستثناءات؛ استثناء مكتوب في الـYAML يلتفّ على الأساس.
_DERIVED_CALL = "tests_tree_coverage_guard.py --pytest-ignores"


def tracked_tests() -> list[str]:
    """كلّ ملفّ اختبار مُتعقَّب تحت ``tests/`` — ``git ls-files`` كما يرى CI (قرار #660)."""
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "tests/test_*.py", "tests/**/test_*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(set(out.stdout.split()))


def excluded() -> dict[str, dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["excluded"]


def pytest_ignores() -> list[str]:
    return [f"--ignore={path}" for path in sorted(excluded())]


def check() -> int:
    entries = excluded()
    tracked = set(tracked_tests())
    problems: list[str] = []

    for path in sorted(entries):
        if path not in tracked:
            problems.append(f"مدخل لملفّ غير موجود (أو غير مُتعقَّب): {path} — احذف المدخل.")
        entry = entries[path]
        for field in ("reason", "evidence", "to_close"):
            if len(str(entry.get(field, "")).strip()) < 20:
                problems.append(f"{path}: {field} أقصر من أن يكون تفسيراً")

    # الاستثناء يجب أن يُشتقّ من الأساس لا يُكتب في الـYAML — وإلّا التفّ عليه بصمت.
    hardcoded = [
        wf.name
        for wf in sorted(WORKFLOWS.glob("*.yml"))
        if "--ignore=tests/" in wf.read_text(encoding="utf-8")
    ]
    if hardcoded:
        problems.append(
            f"استثناء مكتوب يدويّاً في workflow (يلتفّ على الأساس): {', '.join(hardcoded)}"
        )

    if not any(_DERIVED_CALL in wf.read_text(encoding="utf-8") for wf in WORKFLOWS.glob("*.yml")):
        problems.append(
            "لا workflow يشتقّ الاستثناءات من الأساس — الوظيفة إمّا غائبة أو تتجاوز الحارس."
        )

    if problems:
        print("tests tree coverage guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        return 1

    print(
        f"tests tree coverage guard: PASS "
        f"({len(tracked)} ملفّ تحت tests/ · {len(entries)} مستثنى بأساس مُبرَّر · "
        f"{len(tracked) - len(entries)} يُشغَّل)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="افحص اتّساق الأساس")
    parser.add_argument(
        "--pytest-ignores",
        action="store_true",
        help="اطبع وسائط --ignore المُشتقّة من الأساس (لخطوة CI)",
    )
    args = parser.parse_args()
    if args.pytest_ignores:
        print(" ".join(pytest_ignores()))
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
