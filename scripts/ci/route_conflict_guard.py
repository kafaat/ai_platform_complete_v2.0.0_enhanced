#!/usr/bin/env python3
"""Static FastAPI/Starlette route collision guard.

The fail-closed rule is intentionally narrow: the same HTTP method and literal path
registered more than once on the same router/app symbol in the same module is a hard
conflict. Cross-module matches are emitted as review candidates because include_router
prefixes and distinct process boundaries cannot be proven from decorators alone.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "execution-audit/generated/route_conflicts.json"
SCAN_ROOTS = (ROOT / "services", ROOT / "sahool-platform")
HTTP = {"get", "post", "put", "patch", "delete", "options", "head", "api_route", "route"}


@dataclass(frozen=True)
class Route:
    module: str
    receiver: str
    method: str
    path: str
    function: str
    line: int


def literal_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def receiver_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{receiver_name(node.value)}.{node.attr}"
    return "<dynamic>"


def methods_for(call: ast.Call, attr: str) -> list[str]:
    if attr not in {"api_route", "route"}:
        return [attr.upper()]
    for kw in call.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            values = [literal_str(x) for x in kw.value.elts]
            return sorted({x.upper() for x in values if x}) or ["ANY"]
    return ["ANY"]


def scan() -> list[Route]:
    result: list[Route] = []
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
            rel = path.relative_to(ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for deco in node.decorator_list:
                    if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                        continue
                    attr = deco.func.attr.lower()
                    if attr not in HTTP or not deco.args:
                        continue
                    route_path = literal_str(deco.args[0])
                    if route_path is None:
                        continue
                    recv = receiver_name(deco.func.value)
                    for method in methods_for(deco, attr):
                        result.append(Route(rel, recv, method, route_path, node.name, node.lineno))
    return sorted(result, key=lambda r: (r.module, r.receiver, r.method, r.path, r.line))


def build_payload() -> dict:
    routes = scan()
    exact: dict[tuple[str, str, str, str], list[Route]] = defaultdict(list)
    broad: dict[tuple[str, str], list[Route]] = defaultdict(list)
    for route in routes:
        exact[(route.module, route.receiver, route.method, route.path)].append(route)
        broad[(route.method, route.path)].append(route)
    hard = []
    for key, items in sorted(exact.items()):
        if len(items) > 1:
            hard.append(
                {
                    "module": key[0],
                    "receiver": key[1],
                    "method": key[2],
                    "path": key[3],
                    "definitions": [asdict(x) for x in items],
                }
            )
    candidates = []
    for (method, path), items in sorted(broad.items()):
        modules = {(x.module, x.receiver) for x in items}
        if len(modules) > 1:
            candidates.append(
                {
                    "method": method,
                    "path": path,
                    "registrations": [asdict(x) for x in items],
                    "classification": "review_only_distinct_module_or_router",
                }
            )
    digest = hashlib.sha256(
        "\n".join(
            f"{r.module}|{r.receiver}|{r.method}|{r.path}|{r.function}|{r.line}" for r in routes
        ).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "analysis_kind": "static_repository_evidence",
        "runtime_verified": False,
        "production_certified": False,
        "route_count": len(routes),
        "hard_conflict_count": len(hard),
        "cross_scope_candidate_count": len(candidates),
        "route_inventory_sha256": digest,
        "hard_conflicts": hard,
        "cross_scope_candidates": candidates,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    payload = build_payload()
    text = render(payload)
    if args.generate:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
    else:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("route conflict artifact drift; run --generate")
            return 2
    if payload["hard_conflict_count"]:
        print(f"hard route conflicts: {payload['hard_conflict_count']}")
        return 1
    print(
        f"route conflict guard PASS: {payload['route_count']} routes, 0 hard conflicts, {payload['cross_scope_candidate_count']} review candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
