"""Canonical-state modules must be reachable from a mounted route, not merely imported.

The distinction this guard exists for: "has a consumer" and "is reachable" are not the
same claim. A module imported only by another module that nothing imports is still dead
code — the import makes the gap *harder* to see, because every naive check ("does anything
import it?") now passes.

Measured on the wave package that motivated this file: twenty-three modules each had an
importer, and only five had a path from a router that ``router_registry`` actually mounts.
The other eighteen were imported by four consumer modules that nothing imported.

Routers under ``api/routers/`` are auto-registered by ``pkgutil.iter_modules`` in
``api/router_registry.py``, so the mounted set is "every module in that package" minus the
explicit exclusions — dropping a file in is enough to mount it, and dropping a file in
without a caller is enough to look wired while being unreachable.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[1]

# The chain landed as the first genuinely-reachable slice of the v217-v231 wave.
# A module joins this tuple only in the change that makes it reachable.
REACHABLE_CANONICAL_MODULES = (
    "api/agronomic_state_consumers.py",
    "api/canonical_nutrient_ledger.py",
    "api/canonical_phenology_state.py",
    "api/canonical_salinity_state.py",
    "api/persisted_canonical_repositories.py",
)


def _module_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        if rel.startswith(("tests/", "examples/")) or "/tests/" in rel or "__pycache__" in rel:
            continue
        out[rel] = path
    return out


def _import_graph(files: dict[str, Path]) -> dict[str, set[str]]:
    by_name = {rel[:-3].replace("/", "."): rel for rel in files}
    edges: dict[str, set[str]] = defaultdict(set)
    for rel, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - a broken file fails its own gate
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in by_name:
                        edges[rel].add(by_name[alias.name])
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module in by_name:
                    edges[rel].add(by_name[node.module])
                # `from api.pkg import mod` — the imported name may itself be a module.
                for alias in node.names:
                    candidate = f"{node.module}.{alias.name}"
                    if candidate in by_name:
                        edges[rel].add(by_name[candidate])
    return edges


def _reachable_from_mounted_routers() -> set[str]:
    files = _module_files()
    edges = _import_graph(files)
    roots = [
        rel for rel in files if rel.startswith("api/routers/") and not rel.endswith("__init__.py")
    ]
    assert roots, "no routers found — the reachability root set must not be empty"
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edges[current] - seen)
    return seen


def test_every_declared_canonical_module_is_reachable_from_a_mounted_route():
    reachable = _reachable_from_mounted_routers()
    unreachable = [m for m in REACHABLE_CANONICAL_MODULES if m not in reachable]
    assert not unreachable, (
        "declared reachable but no import path from any mounted router: "
        f"{unreachable}. Being imported is not being reachable — an importer that is "
        "itself unreachable does not wire anything."
    )


def test_the_persisted_chain_runs_through_a_real_route_not_a_helper():
    """The entry point must be a router, so the chain is reachable by a request."""
    files = _module_files()
    edges = _import_graph(files)
    routers = {r for r in files if r.startswith("api/routers/")}
    importers = {
        rel for rel, targets in edges.items() if "api/agronomic_state_consumers.py" in targets
    }
    assert importers & routers, (
        "api/agronomic_state_consumers.py must be imported by a router; a chain whose "
        "head is a plain module is not reachable by any request"
    )


def test_the_repository_layer_reads_persisted_state_rather_than_trusting_the_client():
    """The canonical objects come from the database, not from the request body."""
    source = (PLATFORM / "api" / "persisted_canonical_repositories.py").read_text(encoding="utf-8")
    for table in (
        "canonical_phenology_states",
        "canonical_salinity_states",
        "canonical_nutrient_ledgers",
    ):
        assert table in source, f"the repository must read {table}"


def test_the_route_accepts_identifiers_only_and_never_a_canonical_object():
    """A client-supplied canonical object or digest would forge the source of truth."""
    router = (PLATFORM / "api" / "routers" / "recommendations.py").read_text(encoding="utf-8")
    tree = ast.parse(router)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""
    executable = ast.unparse(tree)
    assert "load_agronomic_context" in executable, "the route must load persisted state"
    for forged in ("req.canonical_state", "req.state_digest", "req.source_state_digest"):
        assert forged not in executable, (
            f"{forged!r} would let the client supply canonical truth it does not own"
        )
