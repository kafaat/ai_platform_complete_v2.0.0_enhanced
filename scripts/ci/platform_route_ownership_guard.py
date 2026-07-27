#!/usr/bin/env python3
"""Verify the platform extraction map against the current AST route surface."""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from scripts.ci.platform_route_classification import (  # noqa: E402
    collect_platform_routes,
    normalize_route_path,
)

PLATFORM_ROOT = REPO / "services/sahool-platform"
MAP_PATH = REPO / "docs/architecture/platform_extraction_map.json"
METHOD_ORDER = ("DELETE", "GET", "PATCH", "POST", "PUT")


@dataclass(frozen=True, order=True)
class Surface:
    method: str
    path: str
    file: str
    function: str
    line: int

    @property
    def identity(self):
        return (self.method, self.path, self.function)


def _literal_methods(call: ast.Call, source: Path) -> str:
    value = next((k.value for k in call.keywords if k.arg == "methods"), None)
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        raise AssertionError(
            f"api_route methods must be a literal collection in {source}:{call.lineno}"
        )
    methods = []
    for item in value.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            raise AssertionError(f"api_route method must be literal in {source}:{call.lineno}")
        methods.append(item.value.strip().upper())
    if not methods:
        raise AssertionError(f"api_route methods empty in {source}:{call.lineno}")
    return ",".join(
        sorted(set(methods), key=lambda m: METHOD_ORDER.index(m) if m in METHOD_ORDER else 99)
    )


def collect_api_routes(root: Path = PLATFORM_ROOT) -> list[Surface]:
    out = []
    for source in sorted(root.rglob("*.py")):
        rel = source.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (
                    not isinstance(dec, ast.Call)
                    or not isinstance(dec.func, ast.Attribute)
                    or dec.func.attr != "api_route"
                ):
                    continue
                raw = (
                    dec.args[0]
                    if dec.args
                    else next((k.value for k in dec.keywords if k.arg == "path"), None)
                )
                if not isinstance(raw, ast.Constant) or not isinstance(raw.value, str):
                    raise AssertionError(f"api_route path must be literal in {source}:{dec.lineno}")
                out.append(
                    Surface(
                        _literal_methods(dec, source),
                        normalize_route_path(raw.value),
                        rel,
                        node.name,
                        dec.lineno,
                    )
                )
    return sorted(out)


def collect_surface() -> list[Surface]:
    direct = [
        Surface(r.method, r.path, r.source, r.function, r.line)
        for r in collect_platform_routes(PLATFORM_ROOT)
    ]
    return sorted(direct + collect_api_routes())


def load_map():
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def validate() -> dict:
    surface = collect_surface()
    doc = load_map()
    rows = doc.get("routes")
    if not isinstance(rows, list):
        raise AssertionError("platform extraction map routes must be a list")
    mapped = []
    for r in rows:
        mapped.append(
            Surface(
                str(r.get("method")),
                str(r.get("path")),
                str(r.get("file")),
                str(r.get("function")),
                int(r.get("line", 0)),
            )
        )
    s_by = {x.identity: x for x in surface}
    m_by = {x.identity: x for x in mapped}
    missing = sorted(set(s_by) - set(m_by))
    stale = sorted(set(m_by) - set(s_by))
    if missing or stale:
        raise AssertionError(
            f"platform extraction map identity drift: missing={missing[:10]} stale={stale[:10]}"
        )
    location = []
    for key, current in s_by.items():
        documented = m_by[key]
        if (current.file, current.line) != (documented.file, documented.line):
            location.append(
                {
                    "method": key[0],
                    "path": key[1],
                    "function": key[2],
                    "documented": f"{documented.file}:{documented.line}",
                    "current": f"{current.file}:{current.line}",
                }
            )
    if location:
        raise AssertionError(f"platform extraction map source drift: {location[:10]}")
    return {
        "surface_routes": len(surface),
        "direct_routes": len(surface) - len(collect_api_routes()),
        "api_route_declarations": len(collect_api_routes()),
        "mapped_routes": len(mapped),
    }


def main():
    result = validate()
    print("platform route ownership: PASS")
    [print(f"  {k}: {v}") for k, v in result.items()]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
