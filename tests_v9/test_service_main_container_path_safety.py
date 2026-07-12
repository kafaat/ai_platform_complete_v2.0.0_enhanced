"""Guard: service main.py entrypoints must not hardcode repo-tree parent indexes.

Container startup regression (20260712): several services build paths to shared/ or
data files via ``Path(__file__).resolve().parents[N]`` (N>=1). That is valid in the
repo layout (main.py nested under services/<svc>/) but the Dockerfiles flatten the
service to ``/app`` — so ``/app/main.py`` has no ``parents[2]`` and the process dies
with ``IndexError`` before serving (whole container unhealthy).

main.py is ALWAYS copied to the image root (``COPY ... /app/`` or
``COPY .../main.py /app/main.py``), so any ``.parents[N]`` with N>=1 in a service
main.py is layout-fragile. Resolve such paths by walking up from ``Path(__file__)``
until the target exists (works in both the repo and the flattened container), as
indicators-service/main.py::_resolve_manifest does.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _parents_index_calls(path: Path) -> list[int]:
    """Return the line numbers of `Path(__file__)....parents[N]` (N is an int constant)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[int] = []
    for node in ast.walk(tree):
        # match Subscript whose value is an Attribute ending in `.parents`
        if not isinstance(node, ast.Subscript):
            continue
        val = node.value
        if isinstance(val, ast.Attribute) and val.attr == "parents":
            idx = node.slice
            if isinstance(idx, ast.Constant) and isinstance(idx.value, int) and idx.value >= 1:
                hits.append(node.lineno)
    return hits


def test_service_main_files_have_no_fragile_parent_index():
    offenders: list[str] = []
    for main_py in sorted(ROOT.glob("services/*/main.py")):
        lines = _parents_index_calls(main_py)
        if lines:
            rel = main_py.relative_to(ROOT)
            offenders.append(f"{rel}: Path(...).parents[N] at line(s) {lines}")
    assert not offenders, (
        "service main.py uses a hardcoded repo-tree parent index that breaks in the flat "
        "/app container (resolve by walking up from __file__ instead):\n" + "\n".join(offenders)
    )
