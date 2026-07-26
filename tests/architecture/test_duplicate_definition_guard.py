from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "duplicate_definition_guard.py"
spec = importlib.util.spec_from_file_location("duplicate_definition_guard", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def findings(source: str):
    return module.scope_findings(ROOT / "services" / "example.py", ast.parse(source))


def test_same_method_name_in_different_classes_is_valid():
    source = """
class A:
    def validate(self):
        return 1
class B:
    def validate(self):
        return 2
"""
    assert findings(source) == []


def test_duplicate_in_same_class_is_rejected():
    source = """
class A:
    def validate(self):
        return 1
    def validate(self):
        return 2
"""
    result = findings(source)
    assert len(result) == 1
    assert result[0].scope == "<module>.A"
    assert result[0].symbol == "validate"


def test_overload_declarations_are_allowed():
    source = """
from typing import overload
@overload
def parse(value: str) -> str: ...
@overload
def parse(value: int) -> int: ...
def parse(value):
    return value
"""
    assert findings(source) == []


def test_auth_password_validators_are_not_false_duplicates():
    tree = ast.parse((ROOT / "services" / "auth" / "main.py").read_text(encoding="utf-8"))
    auth_findings = module.scope_findings(ROOT / "services" / "auth" / "main.py", tree)
    assert not any(f.symbol == "strong_password" for f in auth_findings)
