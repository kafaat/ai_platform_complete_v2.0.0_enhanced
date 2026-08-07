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


def test_guard_detects_arrow_markers():
    """يكشف علامتَي السهم القاطعتَين، ولا يُطلِق على نصّ عاديّ."""
    mod = _load()
    assert mod._MARKER.match("<" * 7 + " HEAD")
    assert mod._MARKER.match(">" * 7 + " branch")
    assert not mod._MARKER.match("<<< not a marker")


def test_a_bare_middle_marker_is_caught_because_a_partial_resolve_leaves_it_alone():
    """**الادّعاء الذي كذّبته حادثة، وكان هذا الاختبار يُثبّته.**

    كانت الصيغة السابقة تؤكّد ``assert not _MARKER.match("=" * 7)`` استناداً إلى أنّ
    «الثلاث تظهر معاً دائماً، فالسهم كافٍ». وذلك **يسقط عند الحلّ الجزئيّ**: من يحذف
    السهمين ويُبقي الوسطى يترك ``=======`` وحدها — وهو ما وقع في
    ``sahool-brain/log.md`` فمرّ الحارسان معاً.

    فالاختبار الذي يُثبّت الفجوة يجعلها **عقداً**، لا سهواً.
    """
    mod = _load()
    assert mod._MARKER.match("=" * 7), "الحلّ الجزئيّ يترك هذه وحدها — يجب أن تُدان"


def test_a_docstring_rule_is_not_a_conflict_marker():
    """**الحدّ الذي يُبقي الإضافة صالحة.** حارسٌ يتّهم كلّ مسطرة يُنزَع في أوّل يوم.

    الدقّة على **سبع بالضبط** هي المقياس: صيغة git حرفيّاً. ومقيس على الشجرة قبل
    الإضافة: ``^={7}$`` ⇒ صفر سطر · و**٢٢٩** ملفّاً يحمل مسطرة ``^={20,}$`` — كلّها
    تبقى خارج النطاق.
    """
    mod = _load()
    for width in (8, 20, 40, 79):
        assert not mod._MARKER.match("=" * width), f"مسطرة بعرض {width} ليست تعارضاً"
    # ولا تُطابَق حين لا تكون وحدها على السطر.
    assert not mod._MARKER.match("=" * 7 + " عنوان")


def test_the_middle_marker_is_caught_end_to_end_not_only_by_the_regex(tmp_path, monkeypatch):
    """التكذيب على `scan()` نفسها لا على النمط وحده — الحارس يُشغَّل، لا يُقرأ."""
    mod = _load()
    assert mod.scan() == [], "الشجرة متّسخة قبل الاختبار"

    leaked = os.path.join(os.path.dirname(__file__), "..", "sahool-brain", "log.md")
    original = open(leaked, encoding="utf-8").read()
    try:
        with open(leaked, "w", encoding="utf-8") as fh:
            fh.write(original + "\nعنوان بريء\n" + "=" * 7 + "\nنصّ بعده\n")
        hits = mod.scan()
        assert any("sahool-brain/log.md" in h for h in hits), hits
    finally:
        with open(leaked, "w", encoding="utf-8") as fh:
            fh.write(original)
    assert mod.scan() == [], "الاستعادة يجب أن تُعيد الحارس أخضر"
