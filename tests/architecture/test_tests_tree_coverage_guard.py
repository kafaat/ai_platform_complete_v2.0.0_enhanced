"""حارس ``ARCH-TESTS-UNLISTED-IN-CI-01``: الاستثناء يُشتقّ ولا يُكتب.

هذا الملفّ نفسه هو البرهان الأصغر على الشكل الجديد: **لا يذكره أيّ workflow**، ويعمل
مع ذلك — لأنّ وظيفة *Repository Tests* تشغّل شجرة ``tests/`` كاملةً ناقص أساس مُبرَّر.
تحت الشكل القديم (قائمة مسارات مكتوبة) كان سيولد خامداً كما ولد ١٧ حارساً قبله.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "ci" / "tests_tree_coverage_guard.py"
_BASELINE = ROOT / "docs" / "testing" / "tests_tree_baseline.json"

# سقف راتشِت: يُخفَض بإغلاق سبب، ولا يُرفَع لتمرير بوّابة.
_MAX_EXCLUDED = 10


def _load():
    spec = importlib.util.spec_from_file_location("tests_tree_coverage_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["excluded"]


def test_the_baseline_is_consistent_with_the_tree_and_the_workflow():
    assert MOD.check() == 0


def test_the_baseline_never_silently_grows():
    assert len(_baseline()) <= _MAX_EXCLUDED, f"نما الأساس: {sorted(_baseline())}"


def test_every_exclusion_carries_a_reason_evidence_and_a_closing_condition():
    """استثناء بلا شرط إغلاق ليس تأجيلاً بل حذفاً مؤجّلاً إلى الأبد."""
    for path, entry in _baseline().items():
        assert (ROOT / path).is_file(), f"{path}: مدخل لملفّ غير موجود"
        for field in ("reason", "evidence", "to_close"):
            assert len(entry.get(field, "").strip()) >= 20, f"{path}: {field} أقصر من تفسير"


def test_the_ignore_arguments_are_derived_from_the_baseline():
    """لو كُتبت في الـYAML لأمكن استثناء ملفّ بلا مدخل — وهي العلّة نفسها بشكل جديد."""
    derived = MOD.pytest_ignores()
    assert derived == [f"--ignore={p}" for p in sorted(_baseline())]
    assert len(derived) == len(_baseline())


def test_no_workflow_hardcodes_an_ignore_under_tests():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        assert "--ignore=tests/" not in wf.read_text(encoding="utf-8"), (
            f"{wf.name}: استثناء مكتوب يدويّاً يلتفّ على الأساس"
        )


def test_the_tree_is_discovered_not_enumerated():
    """أرضيّة تمنع كشفاً منهاراً: العدّ من `git ls-files` لا من قائمة مكتوبة."""
    tracked = MOD.tracked_tests()
    assert len(tracked) >= 100, f"كشف مُنهار: {len(tracked)}"
    assert any(p.count("/") == 1 for p in tracked), "ملفّات جذر tests/ غائبة عن الكشف"


def test_this_very_file_is_covered_without_being_listed_anywhere():
    """البرهان الذاتيّ: الحارس الجديد يعمل بلا أن يسمّيه أحد.

    لو عاد الشكل إلى قائمة مسارات مكتوبة لسقط هذا التأكيد — وهو التمييز الوحيد بين
    «مُغطّى» و«مُغطّى لأنّ أحدهم تذكّر».
    """
    me = Path(__file__).relative_to(ROOT).as_posix()
    assert me in MOD.tracked_tests()
    assert me not in _baseline()
    listed = any(
        Path(__file__).name in wf.read_text(encoding="utf-8")
        for wf in (ROOT / ".github" / "workflows").glob("*.yml")
    )
    assert not listed, "أُدرِج هذا الملفّ يدويّاً — البرهان الذاتيّ فقد معناه"
