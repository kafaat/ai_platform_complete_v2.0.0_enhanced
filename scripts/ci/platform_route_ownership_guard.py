#!/usr/bin/env python3
"""Verify and materialize the complete sahool-platform route ownership surface."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ci.platform_route_classification import (  # noqa: E402
    collect_platform_routes,
    normalize_route_path,
)

PLATFORM_ROOT = REPO / "services/sahool-platform"
MAP_PATH = REPO / "docs/architecture/platform_extraction_map.json"
GENERATED_PATH = REPO / "docs/architecture/generated/platform_route_ownership_inventory.json"
SCHEMA_VERSION = "sahool.platform-route-ownership-inventory.v1"
METHOD_ORDER = ("DELETE", "GET", "PATCH", "POST", "PUT")


@dataclass(frozen=True, order=True)
class Surface:
    method: str
    path: str
    file: str
    function: str
    line: int
    declaration_kind: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.method, self.path, self.function


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _literal_methods(call: ast.Call, source: Path) -> str:
    value = next((keyword.value for keyword in call.keywords if keyword.arg == "methods"), None)
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        raise AssertionError(
            f"api_route methods must be a literal collection in {source}:{call.lineno}"
        )
    methods: list[str] = []
    for item in value.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            raise AssertionError(f"api_route method must be literal in {source}:{call.lineno}")
        methods.append(item.value.strip().upper())
    if not methods:
        raise AssertionError(f"api_route methods empty in {source}:{call.lineno}")
    unknown = sorted(set(methods) - set(METHOD_ORDER))
    if unknown:
        raise AssertionError(f"unsupported api_route methods in {source}:{call.lineno}: {unknown}")
    return ",".join(sorted(set(methods), key=METHOD_ORDER.index))


def collect_api_routes(root: Path = PLATFORM_ROOT) -> list[Surface]:
    routes: list[Surface] = []
    for source in sorted(root.rglob("*.py")):
        relative = source.relative_to(root).as_posix()
        if relative.startswith("tests/"):
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    not isinstance(decorator, ast.Call)
                    or not isinstance(decorator.func, ast.Attribute)
                    or decorator.func.attr != "api_route"
                ):
                    continue
                raw_path = (
                    decorator.args[0]
                    if decorator.args
                    else next(
                        (keyword.value for keyword in decorator.keywords if keyword.arg == "path"),
                        None,
                    )
                )
                if not isinstance(raw_path, ast.Constant) or not isinstance(raw_path.value, str):
                    raise AssertionError(
                        f"api_route path must be literal in {source}:{decorator.lineno}"
                    )
                routes.append(
                    Surface(
                        method=_literal_methods(decorator, source),
                        path=normalize_route_path(raw_path.value),
                        file=relative,
                        function=node.name,
                        line=decorator.lineno,
                        declaration_kind="api_route",
                    )
                )
    return sorted(routes)


def collect_surface(root: Path = PLATFORM_ROOT) -> list[Surface]:
    direct = [
        Surface(
            method=route.method,
            path=route.path,
            file=route.source,
            function=route.function,
            line=route.line,
            declaration_kind="direct",
        )
        for route in collect_platform_routes(root)
    ]
    return sorted(direct + collect_api_routes(root))


def load_map(path: Path = MAP_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapped_surface(row: dict[str, Any]) -> Surface:
    return Surface(
        method=str(row.get("method")),
        path=str(row.get("path")),
        file=str(row.get("file")),
        function=str(row.get("function")),
        line=int(row.get("line", 0)),
        declaration_kind="api_route" if "," in str(row.get("method")) else "direct",
    )


def build_inventory(
    *, platform_root: Path = PLATFORM_ROOT, map_path: Path = MAP_PATH
) -> dict[str, Any]:
    surface = collect_surface(platform_root)
    document = load_map(map_path)
    rows = document.get("routes")
    if not isinstance(rows, list):
        raise AssertionError("platform extraction map routes must be a list")

    mapped_rows = [_mapped_surface(row) for row in rows]
    surface_by_identity = {item.identity: item for item in surface}
    mapped_by_identity = {item.identity: item for item in mapped_rows}
    if len(surface_by_identity) != len(surface):
        raise AssertionError("duplicate route identity in live platform surface")
    if len(mapped_by_identity) != len(mapped_rows):
        raise AssertionError("duplicate route identity in platform extraction map")

    missing = sorted(set(surface_by_identity) - set(mapped_by_identity))
    stale = sorted(set(mapped_by_identity) - set(surface_by_identity))
    if missing or stale:
        raise AssertionError(
            f"platform extraction map identity drift: missing={missing[:10]} stale={stale[:10]}"
        )

    location_drift: list[dict[str, str]] = []
    inventory_rows: list[dict[str, Any]] = []
    raw_map_by_identity = {
        (str(row.get("method")), str(row.get("path")), str(row.get("function"))): row
        for row in rows
    }
    for identity, current in sorted(surface_by_identity.items()):
        documented = mapped_by_identity[identity]
        if (current.file, current.line) != (documented.file, documented.line):
            location_drift.append(
                {
                    "method": identity[0],
                    "path": identity[1],
                    "function": identity[2],
                    "documented": f"{documented.file}:{documented.line}",
                    "current": f"{current.file}:{current.line}",
                }
            )
        raw = raw_map_by_identity[identity]
        inventory_rows.append(
            {
                "method": current.method,
                "path": current.path,
                "function": current.function,
                "file": current.file,
                "line": current.line,
                "declaration_kind": current.declaration_kind,
                "owner": raw.get("target_owner", raw.get("owner")),
                "owner_type": raw.get("owner_type"),
                "classification": raw.get("classification"),
                "subclassification": raw.get("subclassification"),
                "domain_budget_counted": raw.get("domain_budget_counted"),
                "route_key": raw.get("route_key"),
            }
        )
    if location_drift:
        raise AssertionError(f"platform extraction map source drift: {location_drift[:10]}")

    direct_count = sum(row.declaration_kind == "direct" for row in surface)
    api_route_count = len(surface) - direct_count
    canonical_rows = json.dumps(inventory_rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": SCHEMA_VERSION,
        "map_file": map_path.relative_to(REPO).as_posix(),
        "map_sha256": _sha256(map_path.read_bytes()),
        "counts": {
            "surface_routes": len(surface),
            "direct_routes": direct_count,
            "api_route_declarations": api_route_count,
            "mapped_routes": len(mapped_rows),
        },
        "inventory_sha256": _sha256(canonical_rows),
        "routes": inventory_rows,
    }


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(document), encoding="utf-8")


def check_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    if not path.exists():
        raise AssertionError(f"generated route-ownership inventory is missing: {path}")
    if path.read_text(encoding="utf-8") != canonical_json(document):
        raise AssertionError(
            "generated platform route-ownership inventory is stale; run "
            "python scripts/ci/platform_route_ownership_guard.py --write-generated"
        )


def validate() -> dict[str, int]:
    return build_inventory()["counts"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-generated", action="store_true")
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    inventory = build_inventory()
    if args.write_generated:
        write_generated(inventory)
    if args.check_generated:
        check_generated(inventory)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(canonical_json(inventory), encoding="utf-8")

    print("platform route ownership: PASS")
    for key, value in inventory["counts"].items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
