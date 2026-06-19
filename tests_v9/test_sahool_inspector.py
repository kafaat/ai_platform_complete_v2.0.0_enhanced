"""اختبارات أداة Sahool Inspector (الفحص الساكن للجاهزية) — تثبت أنّها تعمل وتُصنّف بدقّة.

ليست اختبارات «يجب أن يمرّ كلّ شيء» (الأداة تكشف فجوات حقيقيّة في المنصّة الآن)، بل
تثبت أنّ كلّ فحص يُرجِع نتيجة مُهيكَلة بحالة صالحة، وأنّ الفحوصات التي تطابق حُرّاس CI
الخضراء (RLS، توصيل الراوترات، MANIFEST) تُصنَّف PASS — أي لا إنذارات كاذبة.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "sahool_inspector.py"
_spec = importlib.util.spec_from_file_location("sahool_inspector", _TOOL)
inspector = importlib.util.module_from_spec(_spec)
# تسجيل الوحدة قبل exec_module ضروريّ لـ@dataclass (يحلّ النوع عبر sys.modules).
sys.modules["sahool_inspector"] = inspector
_spec.loader.exec_module(inspector)

_VALID = {inspector.PASS, inspector.WARN, inspector.FAIL, inspector.SKIP}


def test_run_returns_structured_results():
    results, overall = inspector.run()
    assert len(results) == 5
    assert overall in _VALID
    for r in results:
        assert r.status in _VALID
        assert isinstance(r.summary, str) and r.summary
        assert isinstance(r.findings, list)


def test_no_false_positives_vs_green_ci_guards():
    # هذه الفحوصات تطابق حُرّاس CI الخضراء — يجب أن تكون PASS (لا إنذار كاذب).
    by_name = {r.name: r for r in inspector.run()[0]}
    assert by_name["RLS coverage"].status == inspector.PASS, by_name["RLS coverage"].summary
    assert by_name["router wiring"].status == inspector.PASS, by_name["router wiring"].findings
    assert by_name["migration manifest"].status == inspector.PASS, by_name[
        "migration manifest"
    ].findings


def test_overall_fail_when_any_check_fails():
    results, overall = inspector.run()
    if any(r.status == inspector.FAIL for r in results):
        assert overall == inspector.FAIL


def test_main_json_mode_exit_code():
    # FAIL ⇒ رمز خروج 1 (صالح لـCI)؛ JSON يُطبَع دون استثناء.
    code = inspector.main(["--json"])
    assert code in (0, 1)
