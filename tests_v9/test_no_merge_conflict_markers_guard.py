"""اختبار حارس علامات تعارض الدمج — يبقى المستودع نظيفاً، والحارس يكشف التسرّب."""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = pytest.mark.unit

_GUARD = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "ci", "no_merge_conflict_markers_guard.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc_guard", _GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_repo_has_no_conflict_markers():
    """المستودع الحاليّ نظيف — لا علامة تعارض في أيّ ملفّ مُتتبَّع."""
    mod = _load()
    assert mod.scan() == [], "علامات تعارض دمج غير محلولة في ملفّات مُتتبَّعة"


def test_guard_detects_arrow_markers(tmp_path, monkeypatch):
    """يكشف علامتَي السهم القاطعتَين ويتجاهل مساطر docstring (====)."""
    mod = _load()
    marker = "<" * 7 + " HEAD"
    end = ">" * 7 + " branch"
    assert mod._MARKER.match(marker)
    assert mod._MARKER.match(end)
    # مسطرة docstring (سبع علامات = أو أكثر) ليست تعارضاً.
    assert not mod._MARKER.match("=" * 7)
    assert not mod._MARKER.match("=" * 40)
    # نصّ عاديّ لا يُطابَق.
    assert not mod._MARKER.match("<<< not a marker")
