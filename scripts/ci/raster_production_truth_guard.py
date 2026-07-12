#!/usr/bin/env python3
"""Fail closed if synthetic indicator data can reach production serving paths."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ROOT / "services/raster-service/routers/fields.py"
GRID = ROOT / "services/raster-service/indicator_grid.py"


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                out.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                out.add(fn.attr)
    return out


def main() -> int:
    fields = FIELDS.read_text(encoding="utf-8")
    grid = GRID.read_text(encoding="utf-8")
    calls = _calls(FIELDS)
    if "synthetic_grid" in calls or "synthetic_grid(" in fields:
        raise SystemExit("synthetic_grid reachable from raster production router")
    if "def synthetic_grid" in grid:
        raise SystemExit("synthetic_grid remains in production indicator_grid module")
    required = [
        '"RASTER_INDICATOR_PRODUCT_UNAVAILABLE"',
        '"RASTER_PRODUCT_NOT_DECISION_ELIGIBLE"',
        'product.get("quality_gate_passed") is True',
        'product.get("provenance")',
    ]
    missing = [x for x in required if x not in fields]
    if missing:
        raise SystemExit(f"production truth fail-closed wiring missing: {missing}")
    print("raster_production_truth_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
