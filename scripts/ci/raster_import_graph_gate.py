#!/usr/bin/env python3
"""Static import-graph gate for services/raster-service.

This is intentionally lightweight and AST-based: it does not import application
modules, so it can run in CI before heavyweight geospatial dependencies are
installed. It enforces the post-decomposition architecture:

* ``main.py`` is the only application/bootstrap facade.
* production modules must not import or use ``main`` as a runtime dependency.
* production local imports must be acyclic.
* core modules must not import HTTP router modules; dependency direction is
  router -> runtime/helper modules, never runtime/helper -> router.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVC = ROOT / "services" / "raster-service"


def _fail(message: str) -> None:
    raise SystemExit(f"raster-import-graph gate failed: {message}")


def _production_files() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in sorted(SVC.rglob("*.py")):
        rel_parts = path.relative_to(SVC).parts
        if "__pycache__" in rel_parts or path.name.startswith("test_"):
            continue
        module = ".".join(path.relative_to(SVC).with_suffix("").parts)
        modules[module] = path
    return modules


def _resolve_local_module(name: str, modules: set[str]) -> str | None:
    if not name:
        return None
    if name in modules:
        return name
    parts = name.split(".")
    for idx in range(len(parts), 0, -1):
        candidate = ".".join(parts[:idx])
        if candidate in modules:
            return candidate
    if parts[0] in modules:
        return parts[0]
    return None


def _local_import_graph(modules: dict[str, Path]) -> dict[str, set[str]]:
    module_names = set(modules)
    graph: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _resolve_local_module(alias.name, module_names)
                    if resolved and resolved != module:
                        graph[module].add(resolved)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                resolved = _resolve_local_module(node.module, module_names)
                if resolved and resolved != module:
                    graph[module].add(resolved)
    return graph


def _main_dependency_offenders(modules: dict[str, Path]) -> list[str]:
    offenders: list[str] = []
    for module, path in sorted(modules.items()):
        if module == "main":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "main" for alias in node.names):
                offenders.append(f"{path.relative_to(SVC)}:{node.lineno}: import main")
            elif isinstance(node, ast.ImportFrom) and node.module == "main":
                offenders.append(f"{path.relative_to(SVC)}:{node.lineno}: from main import ...")
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "main"
            ):
                offenders.append(f"{path.relative_to(SVC)}:{node.lineno}: main.{node.attr}")
    return offenders


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    found: list[list[str]] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in sorted(graph[node]):
            if state.get(dep) == 1:
                start = stack.index(dep)
                found.append(stack[start:] + [dep])
            elif state.get(dep, 0) == 0:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            visit(node)
    return found


def _core_to_router_edges(graph: dict[str, set[str]]) -> list[str]:
    offenders: list[str] = []
    for module, deps in sorted(graph.items()):
        if module.startswith("routers.") or module in {"main", "router_registry"}:
            continue
        for dep in sorted(deps):
            if dep.startswith("routers.") or dep == "routers.__init__":
                offenders.append(f"{module} -> {dep}")
    return offenders


def main() -> None:
    if not SVC.exists():
        _fail("services/raster-service is missing")
    modules = _production_files()
    if not modules:
        _fail("no production raster-service modules found")

    main_offenders = _main_dependency_offenders(modules)
    if main_offenders:
        _fail("production modules depend on main.py: " + "; ".join(main_offenders))

    graph = _local_import_graph(modules)
    cycles = _cycles(graph)
    if cycles:
        rendered = [" -> ".join(cycle) for cycle in cycles[:10]]
        _fail("local import cycles detected: " + "; ".join(rendered))

    core_router_edges = _core_to_router_edges(graph)
    if core_router_edges:
        _fail("core modules must not import routers: " + "; ".join(core_router_edges))

    print(
        "raster-import-graph gate: OK "
        f"(modules={len(modules)}, local_edges={sum(len(v) for v in graph.values())})"
    )


if __name__ == "__main__":
    main()
