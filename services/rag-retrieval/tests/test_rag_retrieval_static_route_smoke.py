from __future__ import annotations

import ast
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "api_route", "websocket"}


def test_service_has_declared_fastapi_routes():
    routes = []
    for path in SERVICE.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in HTTP_METHODS
                    ):
                        routes.append((path.name, node.name, dec.func.attr))
    assert routes, f"{SERVICE.name} must expose at least one statically discoverable route"


def test_service_has_runtime_entry_or_dockerfile():
    assert (
        (SERVICE / "main.py").exists()
        or any(SERVICE.glob("*Dockerfile*"))
        or (SERVICE / "Dockerfile").exists()
    )
