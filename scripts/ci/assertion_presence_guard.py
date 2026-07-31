#!/usr/bin/env python3
"""حارس «الخضرة الزائفة»: دالّة اختبار بلا تأكيد **وتُرجِع قيمة** لا يمكن أن تفشل.

العلّة المقيسة (2026-07-31): ملفّات في هذا المستودع تُعرّف دوالّ ``test_*`` تُرجِع
``[("✓"|"✗", msg), …]`` بدل أن تؤكّد. pytest **يُهمِل القيمة الراجعة** (ويكتفي
بتحذير ``PytestReturnNotNoneWarning``)، فالدالّة تُحسَب «ناجحة» مهما كان محتوى ما
أعادته — بما فيه علامات ``✗`` صريحة. قياس مباشر على ``test_roadmap_phase23.py``:
pytest يجمع ١٤٣ اختباراً، **واحد** فقط يحوي ``assert``؛ وتشغيل الدوالّ وقراءة
حمولاتها كشف علامتَي ``✗`` حقيقيّتين تحت خضرة تامّة (فجوة تبعيّات + ١١ معالِج
استثناء صامت). فالخضرة هنا لا تُثبت أنّ العقد صحيح؛ قد لا تُثبت أنّ ثمّة تأكيداً
أصلاً.

النمط المرصود **قاطع لا استدلاليّ**: بلا ``assert`` وبلا ``pytest.raises`` **و**
تُرجِع قيمة. دالّة بلا تأكيد لكنّها لا تُرجِع شيئاً قد تكون اختبار دخان مشروعاً
(«لا ينهار») فلا تُرصَد هنا — نُفضّل صفر إيجابيّة كاذبة على شمول أوسع.

الراتشِت يفرض **مجموعة مُجمَّدة لا عدداً**: أيّ دالّة جديدة تحمل النمط تُسقِط CI
حتى لو انخفض العدد الكلّي — وإلّا أمكن إصلاح دالّة وإدخال أخرى بلا أثر. التقلّص
مسموح ومطلوب (وتحديث الأساس جزء من الإصلاح).

الاستعمال:
    python3 scripts/ci/assertion_presence_guard.py            # يكتب الأساس
    python3 scripts/ci/assertion_presence_guard.py --check    # بوّابة CI
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "architecture" / "assertion_presence_baseline.json"
SCAN_ROOTS = ("tests_v9", "tests", "services")


def _is_assertionless_returning_test(node: ast.AST) -> bool:
    """هل الدالّة ``test_*`` بلا تأكيد **وتُرجِع قيمة**؟ (النمط القاطع وحده)."""
    if not (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ):
        return False
    body = list(ast.walk(node))
    has_assert = any(isinstance(x, ast.Assert) for x in body)
    # pytest.raises(...) تأكيد صحيح وإن لم يكن `assert` نصّاً.
    has_raises = any(isinstance(x, ast.Attribute) and x.attr == "raises" for x in body)
    if has_assert or has_raises:
        return False
    return any(isinstance(x, ast.Return) and x.value is not None for x in body)


def collect() -> list[str]:
    """``{path}::{func}`` لكلّ دالّة تحمل النمط، مرتّبة (قابلة لإعادة التوليد حتميّاً)."""
    found: list[str] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("test_*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            rel = py.relative_to(ROOT).as_posix()
            for node in ast.walk(tree):
                if _is_assertionless_returning_test(node):
                    found.append(f"{rel}::{node.name}")
    return sorted(set(found))


def _write(entries: list[str]) -> None:
    BASELINE.write_text(
        json.dumps(
            {
                "$comment": (
                    "أساس مُجمَّد لدوالّ الاختبار التي لا يمكن أن تفشل (بلا assert/raises "
                    "وتُرجِع قيمة — pytest يُهمِل القيمة الراجعة). المجموعة تتقلّص ولا تنمو: "
                    "أيّ إدخال جديد يُسقِط CI حتى لو انخفض العدد الكلّي (منع استبدال دَين "
                    "بدَين). إصلاح دالّة = تحويلها إلى assert حقيقيّ ثمّ حذف سطرها هنا."
                ),
                "gap": "TESTS-PASS-WITHOUT-ASSERTING-01",
                "count": len(entries),
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    entries = collect()
    if "--check" not in sys.argv:
        _write(entries)
        print(f"assertion_presence_baseline_written count={len(entries)}")
        return 0

    if not BASELINE.is_file():
        raise SystemExit(f"الأساس مفقود: {BASELINE.relative_to(ROOT)} — شغّل السكربت بلا --check.")
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    frozen_set = set(frozen.get("entries") or [])
    current_set = set(entries)

    new = sorted(current_set - frozen_set)
    if new:
        raise SystemExit(
            "دالّة/دوالّ اختبار جديدة لا يمكن أن تفشل (بلا assert/raises وتُرجِع قيمة) — "
            "pytest سيعدّها ناجحة مهما كان ما أعادته:\n  "
            + "\n  ".join(new)
            + "\n\nالعلاج: استبدل الإرجاع بـassert حقيقيّ. "
            f"(الأساس {BASELINE.relative_to(ROOT)} يتقلّص ولا ينمو.)"
        )

    fixed = sorted(frozen_set - current_set)
    if fixed:
        print(f"  تقلّصت {len(frozen_set)} ⇒ {len(current_set)} ({len(fixed)} أُصلِحت) — حدّث الأساس.")
    print(f"test_assertion_presence_check_ok frozen={len(frozen_set)} current={len(current_set)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
