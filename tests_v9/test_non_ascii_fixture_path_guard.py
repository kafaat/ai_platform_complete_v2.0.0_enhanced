"""مسارُ ملفٍّ غير ASCII في تجهيزة اختبار يُسقِطها تحت لغة الآلة — لا الحارسَ الذي تقيسه.

``NON-ASCII-TEST-FIXTURE-PATH-BREAKS-C-LOCALE-01``. §٣.١٠ من بروتوكول ما قبل الدفع
تُشغّل ``pytest -m unit`` تحت ``LC_ALL=C PYTHONUTF8=0`` عمداً — «المتّجه الذي يخفيه
Linux». وتحت هذه اللغة يصير ترميز نظام الملفّات ASCII، فإنشاءُ مسارٍ عربيّ أو قراءتُه
يرفع ``UnicodeEncodeError`` **قبل** أن يبلغ الاستدعاءُ الحارسَ المقصود.

**المقيس — ثلاث مرّات، وكلّها على `main` النقيّ لا على فرعٍ:**

    #820  tests_v9/test_branch_protection_contract_guard.py   "لا-وجود-له.json"
    #824  tests_v9/test_frontend_lint_debt_guard.py            "لا-وجود-له.json"
                                                    (والثالثة هي هذا الحارس نفسه)

في الحالتين كان التأكيد عن **ملفّ غائب**، والعربيّة في الاسم زينةٌ لا خاصّيّة — بينما
المحتوى العربيّ في ``write_text(..., encoding="utf-8")`` سليمٌ تماماً لأنّ الترميز
مُثبَّت صراحةً. فالعطل في **المسار** وحده.

**ولماذا حارسٌ لا تصحيحٌ ثالث:** التصحيح يُصلح ما وقع، والنمط يتكرّر لأنّ كاتب الاختبار
لا يرى خطوة ١٠ وهو يكتب. وكلّ تكرارٍ يُحمِّر ``preflight --full`` **للجميع** على `main`،
فتصير البوّابة الموضوعة لقياس متّجه الترميز ساقطةً على تجهيزةٍ من الصنف نفسه.

**والنطاق مسارات الملفّات وحدها.** لا يُمنَع النصّ العربيّ في الشيفرة ولا في الرسائل ولا
في المحتوى المكتوب بترميزٍ مُثبَّت — وهي أعمدة هذا المستودع. يُمنَع أن يُبنى **مسار** من
حرفٍ خارج ASCII.

يفشل مغلقاً: ملفّ اختبارٍ لا يُقرأ يُبلَّغ فشلاً، لا يُتخطّى.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TEST_DIRS = ("tests_v9", "tests")

# استدعاءات تبني مساراً: `tmp_path / "…"` و`Path("…")` و`os.path.join("…")`.
_PATH_CTX = re.compile(r"(tmp_path\s*/|Path\(|os\.path\.join\()")
_NON_ASCII = re.compile(r"[^\x00-\x7f]")


def _string_literals_used_as_paths(source: str) -> list[tuple[int, str]]:
    """يُرجِع (سطر، نصّ) لكلّ سلسلة تُستعمل في بناء مسار وتحوي حرفاً غير ASCII.

    التحليل بـ``ast`` لا بـregex على السطر: سلسلةٌ عربيّة في رسالة تأكيد ليست مساراً،
    والتمييز بنيويّ. نبحث عن ``BinOp`` بقسمة يمينها سلسلة (نمط ``tmp_path / "…"``)
    وعن ``Call`` لـ``Path``/``os.path.join`` بوسائط سلسلة.
    """
    found: list[tuple[int, str]] = []

    def note(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _NON_ASCII.search(node.value):
                found.append((node.lineno, node.value))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            note(node.right)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in {"Path", "join"}:
                for arg in node.args:
                    note(arg)
    return found


def _test_files() -> list[Path]:
    files: list[Path] = []
    for d in TEST_DIRS:
        base = ROOT / d
        if base.is_dir():
            files.extend(sorted(base.rglob("test_*.py")))
    return files


def test_no_test_builds_a_file_path_from_non_ascii_characters():
    """المسار الذي لا يحتمل لغة الآلة يُسقِط تجهيزته قبل أن تقيس شيئاً."""
    files = _test_files()
    assert files, "لم يُعثَر على ملفّات اختبار — الحارس لا يقيس شيئاً"

    offenders: list[str] = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # فشلٌ مغلق: لا تخطٍّ صامت
            offenders.append(f"{path.relative_to(ROOT)}: تعذّرت قراءته — {exc}")
            continue
        if not _PATH_CTX.search(source):
            continue
        try:
            hits = _string_literals_used_as_paths(source)
        except SyntaxError as exc:
            offenders.append(f"{path.relative_to(ROOT)}: تعذّر تحليله — {exc}")
            continue
        for line, text in hits:
            offenders.append(f"{path.relative_to(ROOT)}:{line}: {text!r}")

    assert not offenders, (
        "مسارُ ملفٍّ مبنيٌّ من حرفٍ غير ASCII داخل اختبار. تحت "
        "`LC_ALL=C PYTHONUTF8=0` (خطوة ١٠) يصير ترميز نظام الملفّات ASCII، فيرتفع "
        "`UnicodeEncodeError` **قبل** أن يبلغ الاستدعاءُ الحارسَ — فيسقط الاختبار على "
        "تجهيزته لا على ما يقيسه، ويُحمِّر `preflight --full` للجميع.\n"
        "استعمل اسماً ASCII؛ المحتوى العربيّ يبقى مسموحاً بترميزٍ مُثبَّت "
        '(`write_text(..., encoding="utf-8")`).\n'
        "المواضع:\n  " + "\n  ".join(offenders)
    )


def test_the_detector_sees_a_planted_path_and_ignores_arabic_that_is_not_a_path():
    """تكذيبٌ للكاشف نفسه: يُمسِك المسار، ولا يُمسِك النصّ العربيّ المشروع.

    الشقّ الثاني هو المهمّ: كاشفٌ يُنذِر على كلّ عربيّة كان سيُحمِّر آلاف الأسطر
    المشروعة في هذا المستودع، فيُبطَّل بعد أوّل استعمال — إنذارٌ يُدرَّب قارئُه على
    تجاوزه ليس حارساً.
    """
    planted = 'p = tmp_path / "لا-وجود-له.json"\n'
    assert _string_literals_used_as_paths(planted), "الكاشف لم يُمسِك مساراً مزروعاً"

    legitimate = (
        'assert x, "الرسالة عربيّة ولا تُبنى منها مسارات"\n'
        'broken.write_text("{ليس JSON", encoding="utf-8")\n'
        'D = {"سبب": "قيمة"}\n'
    )
    assert not _string_literals_used_as_paths(legitimate), (
        "الكاشف أنذر على نصّ عربيّ ليس مساراً — إيجابيّة كاذبة تُبطِله"
    )
