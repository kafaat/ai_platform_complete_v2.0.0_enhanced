"""A certification switch is read before any module-level ``pytest.importorskip``.

Live tests read a ``*_CERTIFICATION_REQUIRED`` switch so that, on a certifying runner, a skip
becomes a failure. A module-level ``pytest.importorskip(...)`` that runs before the switch is read
skips the whole module when the dependency is missing, and the certification is silently void:
the run reports "skipped, exit 0" and measured nothing. The lab reproduced this by shadowing
``asyncpg`` with a module that raises ``ModuleNotFoundError``.

The fix (pattern of ``test_d1_raster_queue_rls_live_pg.py``) reads the switch first and only falls
back to ``importorskip`` when it is off. This guard parses every ``tests_v9`` module that names
such a switch and fails if a module-level ``importorskip`` call comes before the first
module-level statement that reads it. Calls inside functions or classes do not count: they run
at test time, after collection has read the switch.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TESTS_DIR = Path(__file__).resolve().parent
SWITCH = re.compile(r"^[A-Z0-9_]*_CERTIFICATION_REQUIRED$")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _walk_module_level(node: ast.AST):
    """Yield the nodes of ``node`` that execute at import time (skip function/class bodies)."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPES):
            continue
        yield from _walk_module_level(child)


def _switch_read_lines(node: ast.AST) -> list[int]:
    """Line of each import-time call or subscript that names a certification switch."""
    lines = []
    for sub in _walk_module_level(node):
        if not isinstance(sub, ast.Call | ast.Subscript):
            continue
        if any(
            isinstance(leaf, ast.Constant)
            and isinstance(leaf.value, str)
            and SWITCH.match(leaf.value)
            for leaf in ast.walk(sub)
        ):
            lines.append(sub.lineno)
    return lines


def _importorskip_lines(node: ast.AST) -> list[int]:
    return [
        sub.lineno
        for sub in _walk_module_level(node)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Attribute)
        and sub.func.attr == "importorskip"
    ]


def _names_a_switch(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and SWITCH.match(n.value)
        for n in ast.walk(tree)
    )


def violations(path: Path, root: Path) -> list[str]:
    """One message per module-level importorskip that runs before the switch is read."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if not _names_a_switch(tree):
        return []
    switch_line = None
    skips: list[int] = []
    for stmt in tree.body:
        if isinstance(stmt, _SCOPES):
            continue
        skips += _importorskip_lines(stmt)
        reads = _switch_read_lines(stmt)
        if reads:
            switch_line = min(reads)
            break
    early = [ln for ln in skips if switch_line is None or ln < switch_line]
    where = f"switch read at line {switch_line}" if switch_line else "switch never read at import"
    return [
        f"{path.relative_to(root)}:{ln}: module-level pytest.importorskip runs before the "
        f"certification switch is read ({where}); a missing dependency would skip a certifying "
        "run green"
        for ln in early
    ]


def _modules() -> list[Path]:
    return sorted(TESTS_DIR.glob("*.py"))


def test_scan_sees_the_known_switch_modules():
    scanned = [
        p.name
        for p in _modules()
        if _names_a_switch(ast.parse(p.read_text(encoding="utf-8"), filename=str(p)))
    ]
    assert "test_notification_delivery_transitions_live_pg.py" in scanned, (
        f"the scan no longer recognises a known switch module; scanned={scanned}"
    )
    assert len(scanned) >= 20, f"expected at least 20 switch modules, found {len(scanned)}"


def test_certification_switch_is_read_before_module_level_importorskip():
    found = [msg for p in _modules() for msg in violations(p, TESTS_DIR.parent)]
    assert not found, (
        "read the *_CERTIFICATION_REQUIRED switch before importing, and fall back to "
        "pytest.importorskip only when it is off (see test_d1_raster_queue_rls_live_pg.py):\n"
        + "\n".join(found)
    )


def test_detector_flags_importorskip_before_switch(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import os\nimport pytest\n"
        'asyncpg = pytest.importorskip("asyncpg")\n'
        '_R = os.getenv("X_CERTIFICATION_REQUIRED") == "1"\n',
        encoding="utf-8",
    )
    good = tmp_path / "good.py"
    good.write_text(
        "import os\nimport pytest\n"
        '_R = os.getenv("X_CERTIFICATION_REQUIRED") == "1"\n'
        "try:\n    import asyncpg\nexcept ImportError:\n    if _R:\n        raise\n"
        '    asyncpg = pytest.importorskip("asyncpg")\n'
        "def later():\n"
        '    pytest.importorskip("fastapi")\n',
        encoding="utf-8",
    )
    bad_found = violations(bad, tmp_path)
    good_found = violations(good, tmp_path)
    assert len(bad_found) == 1, f"the detector missed an early importorskip: {bad_found}"
    assert "bad.py:3" in bad_found[0], f"the message must name the line: {bad_found[0]}"
    assert "line 4" in bad_found[0], f"the message must name the switch line: {bad_found[0]}"
    assert good_found == [], f"the detector flagged the fixed pattern: {good_found}"
