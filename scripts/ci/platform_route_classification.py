#!/usr/bin/env python3
"""Canonical SAHOOL platform route classification for the P2.6 ratchet.

The raw route inventory is always retained. Only explicitly listed, actually
present infrastructure/provenance routes are excluded from the domain budget.
Classification is exact on uppercase HTTP method plus conservatively normalized
literal path. Non-literal route declarations fail closed.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete"})

INFRASTRUCTURE_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/metrics"),
        ("GET", "/runtime-identity"),
    }
)


_MULTI_SLASH_RE = re.compile(r"/{2,}")


@dataclass(frozen=True, order=True)
class RouteDeclaration:
    method: str
    path: str
    source: str
    line: int
    function: str

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path

    @property
    def infrastructure(self) -> bool:
        return self.key in INFRASTRUCTURE_ROUTES


def normalize_route_method(method: str) -> str:
    normalized = method.strip().upper()
    if not normalized:
        raise ValueError("HTTP method must not be empty")
    return normalized


def normalize_route_path(path: str) -> str:
    """Normalize only structural slash differences; preserve route semantics."""
    normalized = path.strip()
    if not normalized:
        raise ValueError("route path must not be empty")
    normalized = "/" + normalized.lstrip("/")
    normalized = _MULTI_SLASH_RE.sub("/", normalized)
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized


def normalized_route_key(method: str, path: str) -> tuple[str, str]:
    return normalize_route_method(method), normalize_route_path(path)


def is_infrastructure_route(method: str, path: str) -> bool:
    return normalized_route_key(method, path) in INFRASTRUCTURE_ROUTES


def _literal_route_path(decorator: ast.Call, source: Path) -> str:
    value: ast.AST | None = decorator.args[0] if decorator.args else None
    if value is None:
        for keyword in decorator.keywords:
            if keyword.arg == "path":
                value = keyword.value
                break
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise AssertionError(
            f"Non-literal route path in {source}:{getattr(decorator, 'lineno', '?')}"
        )
    return normalize_route_path(value.value)


def extract_routes(source: Path, *, repository_root: Path | None = None) -> list[RouteDeclaration]:
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source))
    display_source = (
        source.relative_to(repository_root).as_posix()
        if repository_root is not None and source.is_relative_to(repository_root)
        else source.as_posix()
    )
    routes: list[RouteDeclaration] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.lower()
            if method not in HTTP_METHODS:
                continue
            routes.append(
                RouteDeclaration(
                    method=method.upper(),
                    path=_literal_route_path(decorator, source),
                    source=display_source,
                    line=decorator.lineno,
                    function=node.name,
                )
            )
    return routes


def collect_platform_routes(platform_root: Path) -> list[RouteDeclaration]:
    routes: list[RouteDeclaration] = []
    for source in sorted(platform_root.rglob("*.py")):
        relative = source.relative_to(platform_root).as_posix()
        if relative.startswith("tests/"):
            continue
        routes.extend(extract_routes(source, repository_root=platform_root))
    return sorted(routes)


def partition_routes(
    routes: Iterable[RouteDeclaration],
) -> tuple[list[RouteDeclaration], list[RouteDeclaration]]:
    infrastructure: list[RouteDeclaration] = []
    domain: list[RouteDeclaration] = []
    for route in routes:
        (infrastructure if route.infrastructure else domain).append(route)
    return infrastructure, domain


def assert_infrastructure_allowlist_is_used(routes: Iterable[RouteDeclaration]) -> None:
    declared_pairs = {route.key for route in routes}
    unused = INFRASTRUCTURE_ROUTES - declared_pairs
    if unused:
        raise AssertionError(
            "Infrastructure allowlist contains routes not declared by sahool-platform: "
            f"{sorted(unused)}"
        )
