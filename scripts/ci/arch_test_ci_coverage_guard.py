#!/usr/bin/env python3
"""كلّ اختبار في ``tests/architecture/`` يجب أن يُشغّله workflow — أو يُعفى بسببه.

``ARCH-TESTS-UNLISTED-IN-CI-01``. ``pytest.ini`` يحصر ``testpaths`` في ``tests_v9``،
فكلّ ما تحت ``tests/`` يُشغَّل في CI **بقائمة مسارات صريحة يدويّة**. القائمة اليدويّة
تبيت بصمت: ملفّ جديد يقع خارجها ولا شيء يقول ذلك.

الأدلّة الثلاثة التي أوجبت هذا الحارس، كلّها من يوم واحد (2026-07-28):

1. **١٧ من ٥٤** اختباراً خارج القائمة — منها حرّاس بُنيت في الجلسة نفسها.
2. ``sahool-brain/hot.md:1`` كان يقول إنّ ثلاثيّة عدّ المسارات «**يفرضها**»
   ``test_brain_state_consistency.py`` — وهو خارج القائمة، أي أنّ الادّعاء وصف
   اختباراً لا يعمل. صُحِّح النصّ إلى «يفحصه يدويّاً».
3. مكنسة المصنوعات (#691) نفسها — سكربتها واختبارها — لم تكن موصولة بأيّ workflow:
   أداة بُنيت لتحرس، ولا تعمل إلّا إن تذكّر أحدهم تشغيلها.

القاعدة المفروضة: ملفّ اختبار في ``tests/architecture/`` غير مذكور في أيّ workflow
يُسقِط هذا الحارس، ما لم يكن في أساس مُجمَّد **يتقلّص ولا ينمو**، وكلّ مدخل فيه
يحمل سببه وشرط إغلاقه.

يعمل بلا pytest — نفس نمط ``platform_route_placement_guard``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests" / "architecture"
WORKFLOWS = ROOT / ".github" / "workflows"
BASELINE = ROOT / "docs" / "architecture" / "arch_test_ci_coverage_baseline.json"

_REF = re.compile(r"tests/architecture/(test_[a-z0-9_]+\.py)")


def present() -> set[str]:
    return {p.name for p in sorted(TESTS.glob("test_*.py"))}


def referenced() -> set[str]:
    found: set[str] = set()
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        found.update(_REF.findall(wf.read_text(encoding="utf-8")))
    return found


def exempt() -> dict[str, dict]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))["exempt"]


def check() -> int:
    here, wired, waived = present(), referenced(), exempt()

    unlisted = sorted(here - wired - set(waived))
    # اسم بائت في workflow يُعطي طمأنينة كاذبة: الخطوة تُشير إلى ملفّ غير موجود.
    ghosts = sorted(wired - here)
    # إعفاء لملفّ لم يعد موجوداً = أساس بائت يُخفي نموّه.
    stale_waivers = sorted(set(waived) - here)

    problems = False
    if unlisted:
        problems = True
        print("arch test CI coverage guard: FAIL")
        for name in unlisted:
            print(f"  ✗ tests/architecture/{name} — لا يُشغّله أيّ workflow")
    for name in ghosts:
        problems = True
        print(f"  ✗ workflow يذكر tests/architecture/{name} — وهو غير موجود")
    for name in stale_waivers:
        problems = True
        print(f"  ✗ إعفاء بائت لـ{name} — الملفّ غير موجود، احذف المدخل")

    if problems:
        print(
            "\nأضِف الملفّ إلى قائمة pytest في أحد الـworkflows (capability-governance.yml\n"
            "غالباً). لا تُضِفه إلى الأساس إلّا إن كان **يفشل لسبب مُسجَّل** — والأساس\n"
            f"يتقلّص ولا ينمو، ويفرض ذلك اختبار في {BASELINE.name}."
        )
        return 1

    print(f"arch test CI coverage guard: PASS ({len(here & wired)}/{len(here)} موصول)")
    if waived:
        print(f"  {len(waived)} معفى بسبب مُسجَّل — الأساس يتقلّص ولا ينمو:")
        for name, entry in sorted(waived.items()):
            print(f"    · {name} — {entry['gap']}")
    else:
        print("  لا إعفاء: كلّ اختبار معماريّ يُشغّله workflow.")
    return 0


if __name__ == "__main__":
    sys.exit(check())
