"""Regression guard: a masked raster read is cast to float **before** NaN is filled in.

``src.read(..., masked=True)`` returns an integer masked array for SoilGrids (Int16) and
most DEMs. ``.filled(np.nan)`` on that array raises (NaN has no integer value), the caller
catches it and the field silently comes back as "outside source". The fix at every call
site is ``.astype(<float>).filled(np.nan)``. This test scans the service source so a new
call site written the old way fails here, not in production.
"""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _is_nan(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "nan"


def _chain_has_masked_read(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "read"
            and any(
                k.arg == "masked" and isinstance(k.value, ast.Constant) and k.value.value is True
                for k in sub.keywords
            )
        ):
            return True
    return False


def _chain_has_float_cast(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "astype"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and str(sub.args[0].value).startswith("float")
        ):
            return True
    return False


def offenders(source: str, name: str = "<src>") -> list[str]:
    """``file:line`` of every NaN fill applied to a masked read without a float cast first."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = None
        if node.func.attr == "filled" and node.args and _is_nan(node.args[0]):
            # <expr>.filled(np.nan) — but not np.ma.filled(...), handled below.
            if not (isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "ma"):
                receiver = node.func.value
        if node.func.attr == "filled" and (
            isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "ma"
        ):
            nan_given = (len(node.args) > 1 and _is_nan(node.args[1])) or any(
                k.arg == "fill_value" and _is_nan(k.value) for k in node.keywords
            )
            if nan_given and node.args:
                receiver = node.args[0]
        if (
            receiver is not None
            and _chain_has_masked_read(receiver)
            and not _chain_has_float_cast(receiver)
        ):
            out.append(f"{name}:{node.lineno}")
    return out


def test_no_masked_read_is_nan_filled_before_a_float_cast():
    found = []
    for path in sorted(HERE.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        found += offenders(path.read_text(encoding="utf-8"), path.name)
    assert not found, (
        "masked read filled with NaN before a float cast (raises on Int16/Int32 rasters): "
        f"{found} — write .astype('float32').filled(np.nan)"
    )


def test_the_guard_catches_the_old_pattern_and_accepts_the_fix():
    bad = "arr = src.read(1, masked=True).filled(np.nan).astype('float32')\n"
    bad_ma = "arr = np.ma.filled(src.read(1, masked=True), np.nan)\n"
    good = "arr = src.read(1, masked=True).astype('float32').filled(np.nan)\n"
    good_ma = "arr = np.ma.filled(src.read(1, masked=True).astype('float32'), fill_value=np.nan)\n"
    assert offenders(bad) == ["<src>:1"]
    assert offenders(bad_ma) == ["<src>:1"]
    assert offenders(good) == []
    assert offenders(good_ma) == []
