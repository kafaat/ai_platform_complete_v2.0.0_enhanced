"""كلّ اختبار ``security`` تجمعه وظيفةٌ حاجبة — لا علامةٌ تُقرأ تغطيةً وهي لا تعمل.

تدقيق 2026-11-01 (Q2): ١٣ اختباراً مُعلَّمةً ``security`` وحدها لم تُشغّلها أيُّ وظيفة CI
(منها عزل المستأجر في سجلّ القرار): *Unit Tests* تختار ``-m unit``، و*Integration Tests*
``-m integration``، وخطوة ``pytest -m security`` في *Security Scan* تسمّي ملفّين بعينهما.
فعلامة ``security`` وحدها **لا تُوصل اختباراً إلى بوّابة**.

الفحص بـ``ast`` (علامة الوحدة ``pytestmark`` + مُزخرِفات الصنف + مُزخرِفات الدالّة)، لا
بتشغيل ``pytest --collect-only`` (عشرات الثواني على ١٢ ألف حالة).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SUITE = Path(__file__).resolve().parent
# العلامات التي تختارها وظيفةٌ حاجبة تجمع ``tests_v9`` كلّه (ci.yml: unit-tests · integration-tests).
GATED = {"unit", "integration"}


def _marks(node: ast.AST) -> set[str]:
    """أسماء ``pytest.mark.X`` في تعبير (مُزخرِف، أو قيمة ``pytestmark`` مفردة أو قائمة)."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Attribute)
            and sub.value.attr == "mark"
            and isinstance(sub.value.value, ast.Name)
            and sub.value.value.id == "pytest"
        ):
            out.add(sub.attr)
    return out


def _module_marks(tree: ast.Module) -> set[str]:
    marks: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
        ):
            marks |= _marks(stmt.value)
    return marks


def _ungated_security_tests(source: str, name: str) -> list[str]:
    tree = ast.parse(source)
    module = _module_marks(tree)
    found: list[str] = []

    def visit(body, inherited: set[str], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                cls = inherited | {m for d in node.decorator_list for m in _marks(d)}
                # `pytestmark = ...` في جسم الصنف يُورَّث لدوالّه كمُزخرِف الصنف.
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
                    ):
                        cls |= _marks(stmt.value)
                visit(node.body, cls, f"{prefix}{node.name}::")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                marks = inherited | {m for d in node.decorator_list for m in _marks(d)}
                if "security" in marks and not marks & GATED:
                    found.append(f"{name}::{prefix}{node.name}")

    visit(tree.body, module, "")
    return found


def test_the_scanner_sees_all_three_marker_sites():
    """تكذيبٌ للماسح نفسِه: علامةُ وحدة ومُزخرِفُ صنف ومُزخرِفُ دالّة كلّها تُرى."""
    src = (
        "import pytest\n"
        "pytestmark = [pytest.mark.security]\n"
        "def test_a(): pass\n"
        "@pytest.mark.unit\n"
        "class TestB:\n"
        "    def test_b(self): pass\n"
        "class TestC:\n"
        "    @pytest.mark.integration\n"
        "    async def test_c(self): pass\n"
        "    def test_d(self): pass\n"
        "class TestE:\n"
        "    pytestmark = pytest.mark.unit\n"
        "    def test_e(self): pass\n"
    )
    assert _module_marks(ast.parse(src)) == {"security"}
    assert _ungated_security_tests(src, "probe.py") == [
        "probe.py::test_a",
        "probe.py::TestC::test_d",
    ]
    # صنفٌ يُعلِن `pytestmark = security` في جسمه ودالّتُه بلا علامة بوّابة ⇒ يُرى.
    body_src = (
        "import pytest\n"
        "class TestAuth:\n"
        "    pytestmark = pytest.mark.security\n"
        "    def test_x(self): pass\n"
    )
    assert _ungated_security_tests(body_src, "body.py") == ["body.py::TestAuth::test_x"]


def test_every_security_test_is_selected_by_a_gating_job():
    ungated = sorted(
        t
        for p in sorted(SUITE.glob("test_*.py"))
        for t in _ungated_security_tests(p.read_text(encoding="utf-8"), p.name)
    )
    assert not ungated, (
        "اختبارات ``security`` لا تختارها أيُّ وظيفة حاجبة (لا ``unit`` ولا ``integration``) — "
        f"تُقرأ تغطيةً أمنيّة وهي لا تُشغَّل: {ungated}. أضف ``unit`` إن كانت نقيّة "
        "(بلا خدمات حيّة)، أو ``integration`` إن احتاجت Postgres/Redis."
    )
