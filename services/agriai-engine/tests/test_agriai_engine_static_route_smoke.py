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


def test_runtime_identity_endpoint_is_exposed():
    """Live certification binds evidence to the image via /runtime-identity; agriai-engine
    was measured 404 on the live environment. Structural check: a real FastAPI GET route
    wired to the immutable build identity of THIS service."""
    tree = ast.parse((SERVICE / "main.py").read_text(encoding="utf-8"))
    src = (SERVICE / "main.py").read_text(encoding="utf-8")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "get"
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
                and dec.args[0].value == "/runtime-identity"
            ):
                seg = ast.get_source_segment(src, node)
                assert seg and 'load_build_identity("agriai-engine")' in seg
                return
    raise AssertionError("agriai-engine must expose GET /runtime-identity")


def test_build_identity_is_baked_into_the_image():
    """A runtime env var can relabel an old image; only a build-time file cannot."""
    dockerfile = (SERVICE / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG SAHOOL_GIT_SHA" in dockerfile
    assert "ARG SAHOOL_BUILD_ID" in dockerfile
    assert ".sahool-build-metadata.json" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
