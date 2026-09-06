"""Date-parser extraction preserves router aliases, error codes and timezone behavior."""

from __future__ import annotations

import ast
import importlib.util
from datetime import UTC, date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "sahool-platform" / "api"
_SPEC = importlib.util.spec_from_file_location(
    "platform_request_dates_test", API / "request_dates.py"
)
assert _SPEC is not None and _SPEC.loader is not None
PARSERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(PARSERS)


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


def test_main_reexports_one_implementation_to_existing_consumers(monkeypatch):
    """Execute the real import statement, without booting the database-bearing app."""
    import sys
    import types

    tree = ast.parse((API / "main.py").read_text(encoding="utf-8"))
    names = {"_parse_date", "_parse_iso_utc"}
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        for node in tree.body
    )
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "api.request_dates"
    ]
    assert len(imports) == 1
    assert {alias.name for alias in imports[0].names} == names
    package = types.ModuleType("api")
    package.__path__ = [str(API)]
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.request_dates", PARSERS)
    bound = {}
    exec(compile(ast.Module(body=imports, type_ignores=[]), "main_parser_import", "exec"), bound)
    assert bound["_parse_date"] is PARSERS._parse_date
    assert bound["_parse_iso_utc"] is PARSERS._parse_iso_utc
    assert bound["_parse_date"]("2026-09-06", "sowing_date") == date(2026, 9, 6)
