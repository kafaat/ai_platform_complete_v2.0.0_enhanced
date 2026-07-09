#!/usr/bin/env python3
"""Prevent stacked /healthz + /health decorators on the same handler.

/healthz remains the canonical Kubernetes liveness endpoint. /health may exist as a
legacy alias only as its own hidden route, not as a duplicate decorator on the same
handler.
"""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _route_paths(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    paths: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                paths.append(dec.args[0].value)
    return paths


def main() -> int:
    offenders = []
    for path in sorted(list(ROOT.glob("services/**/main.py")) + list(ROOT.glob("bots/**/main.py"))):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                paths = set(_route_paths(node))
                if "/healthz" in paths and "/health" in paths:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
    if offenders:
        raise SystemExit("duplicate /healthz+/health decorators remain:\n" + "\n".join(offenders))
    print("health_alias_contract_guard_ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
