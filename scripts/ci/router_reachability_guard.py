#!/usr/bin/env python3
"""Conservative static FastAPI router reachability inventory and drift guard.

The analysis resolves literal Python imports and ``include_router`` calls. Routers that
cannot be proven reachable are review candidates, not deletion candidates, because
application factories, plugin loading, monkey-patching, or runtime imports may connect
them dynamically.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "execution-audit/generated/router_reachability.json"
SCAN_ROOTS = (ROOT / "services", ROOT / "sahool-platform", ROOT / "shared")
ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "api_route",
    "route",
    "websocket",
}


@dataclass(frozen=True)
class RouterDef:
    node_id: str
    module: str
    symbol: str
    kind: str
    line: int
    route_count: int


@dataclass(frozen=True)
class IncludeEdge:
    source: str
    target: str | None
    module: str
    line: int
    expression: str
    prefix: str | None
    resolved: bool


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def literal_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def resolve_from(current: str, level: int, imported: str | None) -> str:
    base = current.split(".")[:-1]
    if level:
        base = base[: max(0, len(base) - level + 1)]
    if imported:
        base.extend(imported.split("."))
    return ".".join(base)


def scan() -> tuple[list[RouterDef], list[IncludeEdge], list[dict]]:
    trees: dict[str, tuple[Path, ast.Module]] = {}
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(
                    path.read_text(encoding="utf-8", errors="ignore"), filename=str(path)
                )
            except SyntaxError:
                continue
            trees[module_name(path)] = (path, tree)

    defs: dict[str, RouterDef] = {}
    aliases_by_module: dict[str, dict[str, str]] = {}
    unresolved: list[dict] = []

    for mod, (_path, tree) in trees.items():
        aliases: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                source = resolve_from(mod, node.level, node.module)
                for alias in node.names:
                    local = alias.asname or alias.name
                    aliases[local] = f"{source}.{alias.name}" if source else alias.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        aliases_by_module[mod] = aliases

        route_counts: dict[str, int] = defaultdict(int)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if (
                        isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr.lower() in ROUTE_METHODS
                    ):
                        recv = dotted(deco.func.value)
                        if recv and "." not in recv:
                            route_counts[recv] += 1

        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            constructor = dotted(value.func)
            if not constructor or constructor.split(".")[-1] not in {
                "FastAPI",
                "APIRouter",
                "Router",
            }:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    kind = "app" if constructor.split(".")[-1] == "FastAPI" else "router"
                    nid = f"{mod}:{target.id}"
                    defs[nid] = RouterDef(
                        nid, mod, target.id, kind, node.lineno, route_counts.get(target.id, 0)
                    )

    def resolve_expr(mod: str, expr: ast.AST) -> str | None:
        name = dotted(expr)
        if not name:
            return None
        if "." not in name:
            local = f"{mod}:{name}"
            if local in defs:
                return local
            imported = aliases_by_module.get(mod, {}).get(name)
            if imported and "." in imported:
                imod, symbol = imported.rsplit(".", 1)
                candidate = f"{imod}:{symbol}"
                if candidate in defs:
                    return candidate
            return None
        first, rest = name.split(".", 1)
        imported = aliases_by_module.get(mod, {}).get(first)
        if imported:
            candidate = f"{imported}:{rest}"
            if candidate in defs:
                return candidate
            if "." in imported:
                imod, imported_symbol = imported.rsplit(".", 1)
                candidate = f"{imod}:{imported_symbol}.{rest}"
                if candidate in defs:
                    return candidate
        candidate = f"{mod}:{name}"
        return candidate if candidate in defs else None

    edges: list[IncludeEdge] = []
    for mod, (path, tree) in trees.items():
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr != "include_router"
            ):
                continue
            source = resolve_expr(mod, node.func.value)
            target = resolve_expr(mod, node.args[0]) if node.args else None
            prefix = None
            for kw in node.keywords:
                if kw.arg == "prefix":
                    prefix = literal_str(kw.value)
            expr = ast.unparse(node.args[0]) if node.args else "<missing>"
            resolved = source is not None and target is not None
            edges.append(
                IncludeEdge(
                    source or f"{mod}:<dynamic-source>",
                    target,
                    path.relative_to(ROOT).as_posix(),
                    node.lineno,
                    expr,
                    prefix,
                    resolved,
                )
            )
            if not resolved:
                unresolved.append(
                    {
                        "module": mod,
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": node.lineno,
                        "source": source,
                        "target_expression": expr,
                        "classification": "review_only_dynamic_or_unresolved_include",
                    }
                )

    return (
        sorted(defs.values(), key=lambda x: x.node_id),
        sorted(edges, key=lambda x: (x.module, x.line, x.expression)),
        sorted(unresolved, key=lambda x: (x["file"], x["line"])),
    )


def build_payload() -> dict:
    defs, edges, unresolved = scan()
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.resolved and edge.target:
            graph[edge.source].add(edge.target)

    roots = sorted(x.node_id for x in defs if x.kind == "app")
    reachable: set[str] = set(roots)
    queue = deque(roots)
    while queue:
        current = queue.popleft()
        for target in sorted(graph.get(current, ())):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    routed = [x for x in defs if x.kind == "router" and x.route_count > 0]
    orphan_candidates = [
        {
            **asdict(x),
            "classification": "review_only_not_statically_reachable",
            "safe_to_delete": False,
        }
        for x in routed
        if x.node_id not in reachable
    ]
    digest_lines = [f"D|{x.node_id}|{x.kind}|{x.line}|{x.route_count}" for x in defs]
    digest_lines += [
        f"E|{x.source}|{x.target}|{x.module}|{x.line}|{x.prefix}|{x.resolved}" for x in edges
    ]
    return {
        "schema_version": 1,
        "analysis_kind": "static_repository_evidence",
        "runtime_verified": False,
        "production_certified": False,
        "safe_automatic_deletions": 0,
        "definition_count": len(defs),
        "application_root_count": len(roots),
        "router_with_routes_count": len(routed),
        "include_edge_count": len(edges),
        "resolved_include_edge_count": sum(1 for x in edges if x.resolved),
        "unresolved_include_count": len(unresolved),
        "reachable_node_count": len(reachable),
        "orphan_candidate_count": len(orphan_candidates),
        "inventory_sha256": hashlib.sha256("\n".join(sorted(digest_lines)).encode()).hexdigest(),
        "application_roots": roots,
        "definitions": [asdict(x) | {"statically_reachable": x.node_id in reachable} for x in defs],
        "include_edges": [asdict(x) for x in edges],
        "unresolved_includes": unresolved,
        "orphan_candidates": orphan_candidates,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    text = render(payload)
    if args.generate:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
    elif not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        print("router reachability artifact drift; run --generate")
        return 2
    print(
        "router reachability PASS: "
        f"{payload['application_root_count']} apps, "
        f"{payload['router_with_routes_count']} routed routers, "
        f"{payload['orphan_candidate_count']} review candidates, "
        f"{payload['unresolved_include_count']} unresolved includes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
