"""بوّابة CI لماسح بصمات العيوب (scripts/defect_signature_scan).

يُفعِّل منهجيّة كشف العيوب بالأنماط كبوّابة دائمة: الكود الحاليّ نظيف، وأيّ بصمة جديدة
(except عريض/عارٍ صامت بلا تبرير، أو assert تافه) تُفشِل CI. يتضمّن سلامة ذاتيّة للماسح.
"""

from __future__ import annotations

import importlib.util
import os
import textwrap

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load_scanner():
    path = os.path.join(ROOT, "scripts", "defect_signature_scan.py")
    spec = importlib.util.spec_from_file_location("defect_scan", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_codebase_has_no_dangerous_signatures():
    """الكود الحاليّ خالٍ من البصمات الخطيرة — أيّ بصمة جديدة تُفشِل البوّابة."""
    findings = _load_scanner().scan()
    assert not findings, "بصمات عيوب مكتشَفة:\n  " + "\n  ".join(findings)


def test_scanner_detects_broad_swallow(tmp_path):
    """سلامة الماسح: يرصد except عريضاً صامتاً بلا تبرير."""
    m = _load_scanner()
    d = tmp_path / "services"
    d.mkdir()
    (d / "leak.py").write_text(
        textwrap.dedent("""
        def f():
            try:
                risky()
            except Exception:
                return None
        """),
        encoding="utf-8",
    )
    m.ROOT = tmp_path
    findings = m.scan()
    assert any("broad-except-swallow" in f for f in findings)


def test_scanner_ignores_justified_swallow(tmp_path):
    """except موثَّق بـnoqa أو ضيّق النوع ⇒ لا يُبلَّغ (لا إيجابيّة كاذبة)."""
    m = _load_scanner()
    d = tmp_path / "services"
    d.mkdir()
    (d / "ok.py").write_text(
        textwrap.dedent("""
        def f():
            try:
                risky()
            except Exception:  # noqa: BLE001 — مبرَّر
                return None
        def g():
            try:
                risky()
            except ValueError:
                return None
        """),
        encoding="utf-8",
    )
    m.ROOT = tmp_path
    assert m.scan() == []


def test_scanner_detects_trivial_assert(tmp_path):
    """سلامة الماسح: يرصد assert التافه (وهم التغطية) في الاختبارات."""
    m = _load_scanner()
    d = tmp_path / "services"
    d.mkdir()
    (d / "test_fake.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    m.ROOT = tmp_path
    assert any("وهم تغطية" in f for f in m.scan())
