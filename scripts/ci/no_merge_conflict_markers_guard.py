#!/usr/bin/env python3
"""حارس CI: يمنع تسرّب علامات تعارض دمج git إلى أيّ ملفّ مُتتبَّع.

سياق الحادثة (2026-07-13): حاوية المنصّة سقطت بـ502 على كلّ نقطة لأنّ نسخة نشر محلّيّة
حملت `<<<<<<< HEAD` غير محلولة في `api/routers/soil_sampling.py:64` — SyntaxError يُسقِط
`import api.main` كاملاً (router_registry يستورد كلّ الموجِّهات تلقائيّاً). المستودع نظيف،
لكن لا حارس يمنع لو التُزِم تعارض. هذا الحارس يُغلق تلك الفجوة على مستوى المستودع.

يفحص علامتَي git القاطعتَين اللتَين لا تظهران شرعيّاً في كود سليم:
  `<<<<<<< <label>`  و  `>>>>>>> <label>`
(علامة `=======` وحدها تُتجاهَل — تظهر شرعيّاً في مساطر docstring/Markdown؛ ووجود إحدى
علامتَي السهم كافٍ للكشف عن أيّ تعارض، فالثلاث تظهر معاً دائماً.)

يعدّ الملفّات عبر `git ls-files` (المُتتبَّعة فقط)، ويتخطّى الثنائيّة، ويستثني نفسه
واختبارَه (يحتويان العلامات كنصّ). الفشل يطبع كلّ موقع (path:line).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# علامتا السهم القاطعتان (7 محارف + مسافة + تسمية) — لا تظهران في كود سليم.
_MARKER = re.compile(r"^(<{7}|>{7}) ")

# ملفّات تحتوي العلامات كنصّ مشروع (الحارس نفسه + اختباره) — تُستثنى.
_SELF = {
    "scripts/ci/no_merge_conflict_markers_guard.py",
    "tests_v9/test_no_merge_conflict_markers_guard.py",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ln for ln in out.stdout.splitlines() if ln]


def scan() -> list[str]:
    hits: list[str] = []
    for rel in _tracked_files():
        if rel in _SELF:
            continue
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # ثنائيّ/غير نصّيّ — تخطّى
        for i, line in enumerate(text.splitlines(), 1):
            if _MARKER.match(line):
                hits.append(f"{rel}:{i}: {line[:60]}")
    return hits


def main() -> int:
    hits = scan()
    if hits:
        print("no_merge_conflict_markers_guard FAILED — unresolved git conflict markers:")
        for h in hits:
            print(f"  - {h}")
        return 1
    print("no_merge_conflict_markers_guard_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
