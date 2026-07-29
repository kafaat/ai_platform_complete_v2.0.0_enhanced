#!/usr/bin/env python3
"""يمنع وُلود اختبار خامد: ملفّ في ``tests_v9`` بلا علامة لا يعمل في أيّ وظيفة CI.

``TESTS-UNMARKED-DESELECTED-01``. كلّ وظائف الاختبار تنتقي بـ``-m`` (``unit`` ·
``integration`` · ``security``)، وpytest يستبعد ما **لا علامة له** من كلّ واحدة منها.
والملفّ يبقى داخل ``testpaths`` فيُجمَع محلّيّاً ويبدو حيّاً — وهذا أخبث من الاستبعاد
بالمسار، لأنّ الاستبعاد هناك ظاهر في قائمة الـworkflow بينما هنا لا شيء يُعلنه: لا خطأ
ولا تحذير، فقط عدد مجموع أصغر لا يقارنه شيء.

الكلفة مقيسة لا مُقدَّرة: عند الاكتشاف كان **٦٥ ملفّاً** لا يعمل في أيّ مكان، و**سبعة**
من تسعة إخفاقات فيها كانت تأكيدات على **نصّ مصدر** انتقل بتفكيك لاحق. أي أنّ الاختبار
الخامد لا يفوّت الانحدار فحسب — بل يتعفّن إلى إنذار كاذب، فيبدو إيقاظه لاحقاً كسراً.

الأساس في ``docs/testing/unmarked_tests_baseline.json`` **يتقلّص ولا ينمو**: ملفّ جديد
بلا علامة ⇒ فشل؛ ومدخل بائت (وُسِم أو حُذِف) ⇒ فشل يطالب بحذفه.

    python scripts/ci/test_marker_coverage_guard.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "testing" / "unmarked_tests_baseline.json"
PYTEST_INI = ROOT / "pytest.ini"

# علامة مُعلَنة على مستوى الوحدة أو على دالّة. القبول واسع عمداً: الغرض «هل يُنتقى
# هذا الملفّ بـ-m؟» لا فرض أسلوب واحد.
_MARKED = re.compile(r"pytestmark|pytest\.mark\.(unit|integration|security|slow|mcp)")


def registered_markers() -> set[str]:
    """العلامات المُعلَنة في ``pytest.ini`` — مصدر الحقيقة الوحيد لأسماء العلامات."""
    text = PYTEST_INI.read_text(encoding="utf-8")
    block = text.split("markers =", 1)[1] if "markers =" in text else ""
    names = set()
    for line in block.splitlines()[1:]:
        if not line.startswith((" ", "\t")):
            break
        name = line.strip().split(":", 1)[0].strip()
        if name:
            names.add(name)
    return names


def tracked_test_files() -> list[str]:
    """`git ls-files` لا مسح القرص — نفس قرار #660: مُتعقَّب فقط، كما يرى CI."""
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "tests_v9/test_*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(out.stdout.split())


def unmarked() -> list[str]:
    return [
        path
        for path in tracked_test_files()
        if not _MARKED.search((ROOT / path).read_text(encoding="utf-8"))
    ]


def check() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["unmarked"]
    in_tree = set(unmarked())
    in_baseline = set(baseline)

    problems: list[str] = []
    for path in sorted(in_tree - in_baseline):
        problems.append(
            f"اختبار بلا علامة وخارج الأساس: {path} — أضف "
            f"`pytestmark = pytest.mark.<علامة>`؛ بلا علامة لا يعمل في أيّ وظيفة CI."
        )
    for path in sorted(in_baseline - in_tree):
        problems.append(f"مدخل بائت في الأساس: {path} — وُسِم أو حُذِف. احذف المدخل (الأساس يتقلّص).")

    # صدق الأساس نفسه: مدخل بلا سبب ودليل ليس معرفةً بل قائمة تجاهُل.
    for path, entry in sorted(baseline.items()):
        for field in ("reason", "evidence"):
            if not str(entry.get(field, "")).strip():
                problems.append(f"مدخل بلا {field}: {path}")

    if problems:
        print("test marker coverage guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        return 1

    known = registered_markers()
    print(
        f"test marker coverage guard: PASS "
        f"({len(tracked_test_files())} ملفّ · {len(in_baseline)} في الأساس المُجمَّد · "
        f"علامات مُعلَنة: {', '.join(sorted(known))})"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="افحص (الوضع الوحيد)")
    parser.parse_args()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
