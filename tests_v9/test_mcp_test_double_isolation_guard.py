"""Ratchet: tests must never shadow the production MCP OAuth module."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_no_test_installs_fake_canonical_oauth_module() -> None:
    offenders: list[str] = []
    for base in (ROOT / "tests", ROOT / "tests_v9"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "ModuleType" and node.args:
                        arg = node.args[0]
                        if isinstance(arg, ast.Constant) and arg.value == "shared.oauth_middleware":
                            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "اختبارات تنشئ كعباً بالاسم الإنتاجي shared.oauth_middleware؛ "
        f"هذا يجعل الأمن رهينة ترتيب collection: {offenders}"
    )
