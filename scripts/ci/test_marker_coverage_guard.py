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

**ثقبان أُغلِقا بعد أن أسقطا ملفّين حقيقيّين.** كلاهما من صنف واحد: الحارس يثبّت
*تنفيذاً* حيث كانت *الخاصّيّة* مطلوبة.

  ① **النطاق كان مسطّحاً.** ``git ls-files 'tests_v9/test_*.py'`` لا يرى
     ``tests_v9/<دليل>/test_*.py``. فملفّا ``tests_v9/runtime_activation/`` — ثمانية
     اختبارات تؤكّد التركيبة القانونيّة ومسارات البوّابة — كانا ميّتين في **كلّ** وظيفة،
     و**غير قابلين للظهور في الأساس أصلاً**: الحارس المبنيّ لالتقاط هذا الصنف بالذات
     لا يستطيع تسميتهما. الآن التعداد بالخاصّيّة: كلّ متعقَّب تحت ``tests_v9`` اسمه
     ``test_*.py``، مهما عَمُق.

  ② **والقياس كان نصّيّاً.** ``_MARKED`` القديم كان يطابق ``pytestmark`` **مجرّداً**،
     فـ``pytestmark = pytest.mark.asyncio`` يُقرأ «موسوم» بينما ``asyncio`` ليس علامة
     انتقاء فيُستبعَد الملفّ من كلّ وظيفة — موسومٌ ظاهراً، ميّتٌ فعلاً. وكان يطابق داخل
     تعليق أو نصّ. والأدهى: ``registered_markers()`` موصوفةٌ بأنّها «مصدر الحقيقة
     الوحيد لأسماء العلامات» وهي **زينة** — تُستعمل في سطر النجاح فقط بينما الأسماء
     مُصلَّبة في التعبير النمطيّ. الآن القراءة بـAST والأسماء تُشتقّ من ``pytest.ini``،
     فإضافة علامة هناك تتبعها البوّابة بلا تعديل هنا.

**مقيسٌ لا مُقدَّر:** التمييز بين النصّ والبنية أعطى ١١ بدل ٩ على الشجرة ذاتها —
الفارق هو الملفّان المحجوبان بالثقب ①. والقياس مُصدَّق بـ``pytest`` نفسه: اختبار
``test_the_guard_agrees_with_pytests_own_selection`` يقارن جواب الحارس بجمع pytest
الحقيقيّ تحت ``-m``، فلا يبقى القياس الرخيص صادقاً بالادّعاء.

يعمل بلا pytest (``ast`` من المكتبة القياسيّة) — نفس نمط ``platform_route_placement_guard``.

    python scripts/ci/test_marker_coverage_guard.py --check
"""

from __future__ import annotations

import argparse
import ast
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
BASELINE = ROOT / "docs" / "testing" / "unmarked_tests_baseline.json"
PYTEST_INI = ROOT / "pytest.ini"
TESTS_DIR = "tests_v9"


def registered_markers() -> set[str]:
    """العلامات المُعلَنة في ``pytest.ini`` — مصدر الحقيقة الوحيد لأسماء العلامات.

    وهي **حاملة** الآن لا زينة: ``marker_names_in`` تُقارَن بها، فحذف علامة من
    ``pytest.ini`` يجعل الملفّات الموسومة بها بلا علامة انتقاء — وهو الصدق نفسه،
    لأنّ pytest سيستبعدها فعلاً.
    """
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
    """`git ls-files` لا مسح القرص — نفس قرار #660: مُتعقَّب فقط، كما يرى CI.

    والتصفية **بالخاصّيّة** (اسم الملفّ) لا بنمط مسار: نمط ``tests_v9/test_*.py``
    مسطّح، ودليلٌ فرعيّ واحد يكفي ليختفي ملفّ عن حارسٍ بُني لرؤيته.
    """
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z", "--", TESTS_DIR],
        cwd=ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout
    return sorted(
        rel
        for rel in out.split("\0")
        if rel and rel.endswith(".py") and Path(rel).name.startswith("test_")
    )


def marker_names_in(path: Path) -> set[str]:
    """أسماء العلامات المُطبَّقة فعلاً في الملفّ — بالبنية لا بالنصّ.

    المواضع الثلاثة التي يقرأها pytest: ``pytestmark`` على مستوى الوحدة، ومُزخرِفات
    الدوالّ، ومُزخرِفات الأصناف. **الثالث ليس تفصيلاً:** ثمانية ملفّات في هذه الشجرة
    تَسِم على مستوى الصنف وحده، وأوّل صياغة عندي أغفلَته فأعلنتها بلا علامة — أمسكه
    التصديق بـpytest، لا قراءتي.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return set()

    def names(node: ast.AST) -> set[str]:
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute):
                owner = sub.value
                if (
                    isinstance(owner, ast.Attribute)
                    and owner.attr == "mark"
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "pytest"
                ):
                    found.add(sub.attr)
        return found

    applied: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            value = node.value  # type: ignore[union-attr]
            if value is not None:
                applied |= names(value)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                applied |= names(decorator)
    return applied


def unmarked() -> list[str]:
    """ملفّات لا تحمل **علامة انتقاء مُسجَّلة** — أي لا تُنتقى بأيّ ``-m`` في CI."""
    known = registered_markers()
    return [path for path in tracked_test_files() if not (marker_names_in(ROOT / path) & known)]


def check() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["unmarked"]
    in_tree = set(unmarked())
    in_baseline = set(baseline)

    problems: list[str] = []
    for path in sorted(in_tree - in_baseline):
        problems.append(
            f"اختبار بلا علامة وخارج الأساس: {path} — أضف "
            f"`pytestmark = pytest.mark.<علامة>`؛ بلا علامة **مُسجَّلة في pytest.ini** "
            f"لا يعمل في أيّ وظيفة CI (`pytest.mark.asyncio` وحدها لا تكفي)."
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
