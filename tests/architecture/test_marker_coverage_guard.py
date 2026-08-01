"""حارس ``TESTS-UNMARKED-DESELECTED-01``: الأساس المُجمَّد يتقلّص ولا يُهادَن.

الحارس نفسه يعمل كخطوة صريحة في `ci.yml` (وظيفة *Unit Tests*)، فهذه الاختبارات لا
تُعيد فحص ما يفحصه — تحرس **دلالته**: أنّ القراءة تطابق ما ينتقيه pytest فعلاً، وأنّ
الأساس معرفة لا قائمة تجاهُل، وأنّه لا ينمو صامتاً.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "ci" / "test_marker_coverage_guard.py"
_BASELINE = ROOT / "docs" / "testing" / "unmarked_tests_baseline.json"

# سقف راتشِت لا هدف: يُخفَض بوسم ملفّ أو حذفه، ولا يُرفَع لتمرير بوّابة.
_MAX_UNMARKED = 9


def _load():
    spec = importlib.util.spec_from_file_location("test_marker_coverage_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["unmarked"]


def test_the_tree_matches_the_baseline():
    """الثابت: لا ملفّ بلا علامة خارج الأساس، ولا مدخل بائت فيه."""
    assert MOD.check() == 0


def test_the_baseline_never_silently_grows():
    assert len(_baseline()) <= _MAX_UNMARKED, f"نما الأساس: {sorted(_baseline())}"


def test_every_baseline_entry_carries_a_measured_reason():
    """«خامد معروف» بلا سبب ودليل يتحوّل إلى قائمة تجاهُل دائمة."""
    for path, entry in _baseline().items():
        assert entry.get("reason"), f"{path}: بلا reason"
        assert len(entry.get("evidence", "").strip()) >= 30, f"{path}: دليل أقصر من تفسير"
        assert (ROOT / path).is_file(), f"{path}: مدخل لملفّ غير موجود"


def test_entries_that_are_not_merely_deferred_name_a_closing_condition():
    """المؤجَّل يحتاج شرط إغلاق؛ ما يعمل بمسار صريح أو لا يجمع اختبارات لا يحتاجه."""
    exempt = {"runs_by_explicit_path", "not_a_pytest_module"}
    for path, entry in _baseline().items():
        if entry["reason"] in exempt:
            continue
        assert entry.get("to_close"), f"{path}: مؤجَّل بلا شرط إغلاق"


def test_the_marker_names_come_from_pytest_ini_not_a_hardcoded_list():
    """قائمة علامات مكتوبة في الحارس تنحرف عن `pytest.ini` بصمت — تُقرأ من المصدر."""
    assert MOD.registered_markers() == {"unit", "integration", "security", "slow", "mcp"}


def test_detection_agrees_with_what_pytest_would_select():
    """القراءة النصّيّة ليست غاية بذاتها: ما تعدّه «موسوماً» يجب أن ينتقيه `-m` فعلاً.

    تُقاس على عيّنة من الشجرة بدل الثقة في التعبير النمطيّ: كلّ ملفّ **خارج** الأساس
    يجب أن يحمل علامة، وكلّ ملفّ **في** الأساس يجب ألّا يحملها.
    """
    unmarked = set(MOD.unmarked())
    assert unmarked == set(_baseline()), "القراءة تخالف الأساس"
    marked = [f for f in MOD.tracked_test_files() if f not in unmarked]
    assert len(marked) > 500, "انهيار الكشف: كلّ الملفّات تبدو بلا علامة"
