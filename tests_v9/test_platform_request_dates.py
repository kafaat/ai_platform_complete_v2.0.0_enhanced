"""Request date contracts stay intact without growing either platform budget."""

from __future__ import annotations

import ast
import types
from datetime import UTC, date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "sahool-platform" / "api"
# Execute the real parser definitions and their real datetime import from main.
# This narrow unit harness does not boot the application or stand in for an HTTP test.
_MAIN_TREE = ast.parse((API / "main.py").read_text(encoding="utf-8"))
_NAMES = {"_parse_date", "_parse_iso_utc"}
_FUNCTIONS = [
    node for node in _MAIN_TREE.body if isinstance(node, ast.FunctionDef) and node.name in _NAMES
]
assert len(_FUNCTIONS) == 2
assert {node.name for node in _FUNCTIONS} == _NAMES
_DATETIME_IMPORTS = [
    node
    for node in _MAIN_TREE.body
    if isinstance(node, ast.ImportFrom) and node.module == "datetime"
]
assert len(_DATETIME_IMPORTS) == 1
PARSERS = types.ModuleType("platform_main_dates_under_test")
PARSERS.HTTPException = HTTPException
exec(
    compile(
        ast.Module(body=[*_DATETIME_IMPORTS, *_FUNCTIONS], type_ignores=[]),
        str(API / "main.py"),
        "exec",
    ),
    vars(PARSERS),
)


@pytest.mark.parametrize("value", [None, ""])
def test_optional_date_remains_absent(value):
    assert PARSERS._parse_date(value, "sowing_date") is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-09-06", date(2026, 9, 6)),
        (" 2024-02-29 ", date(2024, 2, 29)),
    ],
)
def test_valid_dates_preserve_strip_and_leap_day(value, expected):
    assert PARSERS._parse_date(value, "sowing_date") == expected


@pytest.mark.parametrize("value", [" ", "2026-02-29", "tomorrow", 123, object()])
def test_bad_date_preserves_400_and_field_name(value):
    with pytest.raises(HTTPException) as exc:
        PARSERS._parse_date(value, "sowing_date")
    assert exc.value.status_code == 400
    assert "sowing_date" in exc.value.detail
    assert "YYYY-MM-DD" in exc.value.detail


@pytest.mark.parametrize(
    "value, expected_offset",
    [
        ("2026-09-06T15:15:00", timedelta(0)),
        ("2026-09-06T15:15:00Z", timedelta(0)),
        ("2026-09-06T15:15:00+03:00", timedelta(hours=3)),
        ("2026-09-06T15:15:00-04:00", timedelta(hours=-4)),
    ],
)
def test_iso_parser_preserves_aware_offset_and_only_defaults_naive_to_utc(value, expected_offset):
    parsed = PARSERS._parse_iso_utc(value)
    assert parsed.utcoffset() == expected_offset
    assert parsed.hour == 15
    assert parsed.minute == 15
    if expected_offset == timedelta(0):
        assert parsed.tzinfo == UTC


@pytest.mark.parametrize("value", [None, "", "not-iso", "2026-13-01T00:00:00", 123])
def test_bad_iso_preserves_422(value):
    with pytest.raises(HTTPException) as exc:
        PARSERS._parse_iso_utc(value)
    assert exc.value.status_code == 422
    assert repr(value) in exc.value.detail


def test_main_keeps_one_parser_for_existing_router_consumers(monkeypatch):
    """Execute each router's existing parser import without booting the application."""
    import sys

    assert not (API / "request_dates.py").exists()
    assert all(not function.decorator_list for function in _FUNCTIONS)
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "api.request_dates"
        for node in _MAIN_TREE.body
    )
    package = types.ModuleType("api")
    package.__path__ = [str(API)]
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.main", PARSERS)
    consumers = set()
    for path in sorted((API / "routers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.module != "api.main":
                continue
            aliases = [alias for alias in node.names if alias.name in _NAMES]
            if not aliases:
                continue
            selected = ast.ImportFrom(module=node.module, names=aliases, level=node.level)
            code = ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))
            bound = {}
            exec(compile(code, str(path), "exec"), bound)
            for alias in aliases:
                assert bound[alias.asname or alias.name] is getattr(PARSERS, alias.name)
                consumers.add(alias.name)
    assert consumers == _NAMES


def test_main_line_budget_is_preserved():
    assert len((API / "main.py").read_text(encoding="utf-8").splitlines()) <= 2553
