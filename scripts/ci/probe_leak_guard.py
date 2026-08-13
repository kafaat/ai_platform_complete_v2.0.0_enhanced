#!/usr/bin/env python3
"""يُسمّي مِسبار اختبار تسرّب إلى الشجرة، بدل تركه يُشخَّص خطأً — `TEST-PROBE-LEAKS-INTO-THE-TREE-01`.

**الحادثة التي أوجبته، لا فرضيّة.** تقرير اعتماد خارجيّ (SAHOOL v22) أصدر **NO-GO**
وعزا **١٩ إخفاقاً** في CI إلى «تغيير غير محكوم أضاف `GET /api/probe-newservice/readyz`
في `compat_gateway.py:145` بلا مصادقة ولا تصنيف». وطالب بحذف المسار أو تقنينه.

**المسار لم يدخل هذا المستودع قطّ.** هو مِسبار اصطناعيّ يحقنه
`tests_v9/test_api_versioning_policy_guard.py` ليُثبِت أنّ حارس الإصدارات يرفض مساراً
غير مُصنَّف، ثمّ يستعيده في `finally`. و`finally` لا ينجو من SIGKILL ولا من إلغاء
وظيفة CI ولا من إغلاق طرفيّة — فبقي المِسبار في شجرتهم.

فالتسريب لم يُوسِّخ شجرةً فحسب: **أنتج تشخيصاً خاطئاً كلّف جولة اعتماد كاملة**، ووجّه
الإصلاح إلى مسار لا وجود له. وهذا أسوأ من فشل صاخب، لأنّ الفشل الصاخب يُقرأ.

**العلاج على شطرين، وهذا هو الثاني:**
  ① المِسبار صار يعيش في ملفّ **غير متعقَّب** فلا يُعدَّل مصدر حقيقيّ أبداً. مُقاس:
     `timeout -s KILL` أثناء الاختبار ⇒ **صفر** ملفّ مصدر متعقَّب متأثّر (كان ١).
  ② لكنّ الاختبار **يُعيد التوليد عمداً** ليُثبِت أنّ إعادة التوليد لا تُبيّض مساراً
     جديداً — فالمقاطعة تترك الجرود المولَّدة منحرفة. هذا الحارس يُسمّي ذلك بسطر
     واحد وعلاجه، بدل تسعة عشر إخفاقاً لا يقول أيّها السبب.

**النطاق مقصود وضيّق:** المصادر تحت `services/` والجرود المولَّدة في الجذر. رموز
المِسبار تظهر **شرعيّاً** في ثلاثة مواضع تُستثنى صراحةً: الاختبار نفسه (يُعرّفها)،
و`capability_mapping.json` (يفهرس الاختبار)، و`sahool-brain/` (يشرح الحادثة). حارسٌ
يُطلِق على توثيق ما يمنعه يُعطَّل في أوّل يوم — وهو عطل تكرّر في هذا المستودع.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

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

# رموز المسارات الاصطناعيّة التي تحقنها اختبارات الحرّاس. أيّ إضافة هناك تُضاف هنا.
PROBE_MARKERS = (
    "probe-newservice",
    "probe-swapped-in",
    "ghost-probe",
    "decoy-already-adjudicated",
)

# ملفّ المِسبار غير المتعقَّب — وجوده وحده دليل مقاطعة.
PROBE_MODULE = (
    ROOT / "services" / "sahool-platform" / "api" / "routers" / "_probe_unadjudicated_route.py"
)

# النطاق: **كلّ ملفّ متعقَّب**، لا `services/` وحدها.
#
# أوّل صياغة مسحت `services/**/*.py` والجرود الخمسة في الجذر — فكانت قائمة
# الاستثناءات أدناه **شيفرة ميتة**: لا موضع شرعيّ يقع داخل ذلك النطاق أصلاً. كشفَته
# طفرة مزروعة (نزع الاستثناء) بقيت خضراء، فلو تسرّب المِسبار إلى مصنوعة خارج القائمة
# الخمسة لَما رآه أحد. النطاق الكامل يجعل الاستثناء حاملاً ويجعل الطفرة تُسقِط اختباراً.
#
# الملفّ غير المتعقَّب يُفحَص منفصلاً (`PROBE_MODULE`) لأنّ `ls-files` لا يراه.

# مواضع الذكر الشرعيّ — تُستثنى بالمسار لا بالتخمين.
#
# `docs/runbooks/` أُضيف بعد وقوع العطل الذي يحذّر منه docstring هذا الملفّ حرفيّاً:
# #802 أضاف درس «عودة مسار probe-newservice المحظور» إلى كتالوج الدروس، فأطلق
# الحارس على **توثيق ما يمنعه** وصار `main` أحمر على بوّابته الحاجبة نفسها
# (`ci.yml:489`) وعلى `test_the_tree_is_clean_right_now`. والاستثناء لا يُفقِد
# كشفاً: ما يبقى بعد المقاطعة هو ملفّ المِسبار غير المتعقَّب والجرود المولَّدة في
# الجذر — ولا يكتب أيّ اختبار في `docs/runbooks/`، وسردٌ في Markdown لا يُعلن مساراً.
ALLOWED = (
    "tests_v9/",
    "tests/",
    "docs/capability-registry/",
    "docs/runbooks/",
    "sahool-brain/",
    "scripts/ci/probe_leak_guard.py",
    # جردٌ **مشتقّ** من ملفّات الاختبار: يسجّل نصوص التأكيدات حرفيّاً، فرمزُ المِسبار
    # يصله من `tests_v9/test_certification_regression_fixes.py` وهو موضع ذِكرٍ شرعيّ
    # أصلاً. بالمسار التامّ لا بالدليل — `docs/architecture/` كاملاً يُعمي الحارس عن
    # مصنوعات لا علاقة لها بالاختبارات. وهذه ثالث مرّة في يومٍ واحد يُطلِق فيها حارسٌ
    # على توثيق ما يمنعه؛ والمرّة الثالثة كانت مصنوعتي أنا.
    "docs/architecture/source_text_assertion_inventory.json",
)


def _is_allowed(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in ALLOWED)


def leaks(root: Path | None = None) -> list[str]:
    """مواضع التسريب. `root` لأجل الاختبار: مستودع مؤقّت بدل الشجرة الحيّة.

    بدونه كان الاختبار يكتب رمز مِسبار في جرد **متعقَّب** ثمّ «يستعيده» بـ
    `write_text` — و`read_text` يُترجم `\r\n` إلى `\n` فالاستعادة **مُفقِدة**:
    الملفّ يعود بمحتوى مطابق ونهايات أسطر مختلفة، فتفشل جزئته. أي أنّ اختبار الحارس
    وقع في الصنف الذي بُني الحارس لمنعه. الآن لا يُمَسّ ملفّ متعقَّب أصلاً.
    """
    base = root or ROOT
    found: list[str] = []

    if (base / PROBE_MODULE.relative_to(ROOT)).exists():
        found.append(
            f"{PROBE_MODULE.relative_to(ROOT).as_posix()} — ملفّ مِسبار مؤقّت باقٍ (اختبار قُوطِع)"
        )

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=base,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    candidates = [base / rel for rel in tracked.split("\0") if rel]

    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if _is_allowed(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marker in PROBE_MARKERS:
            if marker in text:
                found.append(f"{rel} — يحوي رمز مِسبار {marker!r}")
                break
    return found


def main() -> int:
    problems = leaks()
    if problems:
        print("مِسبار اختبار تسرّب إلى الشجرة — ليس تغييراً من مطوّر:")
        for line in problems:
            print(f"  ✗ {line}")
        print(
            "\nالسبب: اختبار حارس يحقن مساراً اصطناعيّاً ويستعيده في finally، وقد قُوطِع\n"
            "(SIGKILL / إلغاء وظيفة / إغلاق طرفيّة) فلم يُنفَّذ الاستعادة.\n"
            "\nالعلاج — لا تُصنّف المسار ولا تُضِفه إلى أيّ allowlist:\n"
            "  rm -f services/sahool-platform/api/routers/_probe_unadjudicated_route.py\n"
            "  git checkout -- api_versioning_inventory.* api_versioning_legacy_allowlist.generated.json\n"
            "  python scripts/ci/api_versioning_policy_guard.py --check\n"
        )
        return 1

    print("probe_leak_guard: PASS (لا مِسبار اختبار في المصادر ولا في الجرود)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
