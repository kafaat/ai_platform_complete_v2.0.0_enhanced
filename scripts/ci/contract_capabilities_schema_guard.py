#!/usr/bin/env python3
"""Guard stable schemas for /contract and /capabilities endpoints.

These endpoints are consumed by operators and service-discovery tooling. They are
allowed to be service-specific, but every implementation must expose a minimal
common envelope so clients can reason about ownership, runtime implementation,
and capability status without special-casing every service.
"""
from __future__ import annotations

import ast
import csv
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_JSON = ROOT / "contract_capabilities_inventory.generated.json"
INVENTORY_CSV = ROOT / "contract_capabilities_inventory.csv"

CONTRACT_REQUIRED_KEYS = {"service", "contract_version", "implemented_runtime"}
CAPABILITIES_REQUIRED_KEYS = {"service", "schema_version", "capabilities"}

# Endpoint handlers that return a helper call rather than an inline dict.
HELPER_REQUIRED_KEYS = {
    "services/edge-inference/main.py": {
        "capabilities_payload": CAPABILITIES_REQUIRED_KEYS,
    }
}


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorator_path(deco: ast.AST) -> str | None:
    if not isinstance(deco, ast.Call) or not deco.args:
        return None
    func = deco.func
    if not isinstance(func, ast.Attribute) or func.attr not in {"get", "post", "put", "patch", "delete"}:
        return None
    return _string_value(deco.args[0])


def _dict_keys(node: ast.Dict) -> set[str]:
    keys: set[str] = set()
    for key in node.keys:
        val = _string_value(key) if key is not None else None
        if val:
            keys.add(val)
    return keys


def _first_return_keys(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[set[str], str]:
    for node in ast.walk(fn):
        if isinstance(node, ast.Return):
            if isinstance(node.value, ast.Dict):
                return _dict_keys(node.value), "inline-dict"
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                return {f"helper:{node.value.func.id}"}, "helper-call"
            return set(), "non-dict-return"
    return set(), "no-return"


def _function_keys(tree: ast.Module, name: str) -> set[str]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                    return _dict_keys(child.value)
    return set()


def _iter_main_files() -> Iterable[Path]:
    for base in (ROOT / "services", ROOT / "bots"):
        if base.exists():
            yield from base.rglob("main.py")


def build_inventory() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(_iter_main_files()):
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            records.append({"file": rel, "endpoint": "<parse-error>", "handler": "", "keys": [], "status": "parse_error", "detail": str(exc)})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                endpoint = _decorator_path(deco)
                if endpoint not in {"/contract", "/capabilities"}:
                    continue
                keys, mode = _first_return_keys(node)
                required = CONTRACT_REQUIRED_KEYS if endpoint == "/contract" else CAPABILITIES_REQUIRED_KEYS
                if mode == "helper-call":
                    helper_names = [k.split(":", 1)[1] for k in keys if k.startswith("helper:")]
                    helper_keys = set()
                    for helper in helper_names:
                        helper_keys |= _function_keys(tree, helper)
                    keys = helper_keys
                    mode = "helper-inline-dict" if helper_keys else "helper-unresolved"
                missing = sorted(required - keys)
                status = "ok" if not missing else "missing_keys"
                records.append({
                    "file": rel,
                    "endpoint": endpoint,
                    "handler": node.name,
                    "mode": mode,
                    "keys": sorted(keys),
                    "required_keys": sorted(required),
                    "missing_keys": missing,
                    "status": status,
                })
    return records


def write_inventory(records: list[dict[str, object]]) -> None:
    INVENTORY_JSON.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with INVENTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "endpoint", "handler", "mode", "status", "missing_keys", "keys"])
        writer.writeheader()
        for r in records:
            writer.writerow({
                "file": r.get("file", ""),
                "endpoint": r.get("endpoint", ""),
                "handler": r.get("handler", ""),
                "mode": r.get("mode", ""),
                "status": r.get("status", ""),
                "missing_keys": ",".join(r.get("missing_keys", [])),
                "keys": ",".join(r.get("keys", [])),
            })


def main(argv: list[str]) -> int:
    check = "--check" in argv
    records = build_inventory()
    failures = [r for r in records if r.get("status") != "ok"]
    if not check:
        write_inventory(records)
    if check:
        expected = json.loads(INVENTORY_JSON.read_text(encoding="utf-8")) if INVENTORY_JSON.exists() else None
        if expected != records:
            print("contract/capabilities inventory drift; run scripts/ci/contract_capabilities_schema_guard.py", file=sys.stderr)
            return 1
    if failures:
        for r in failures:
            print(f"{r['file']} {r['endpoint']} missing {r.get('missing_keys')}", file=sys.stderr)
        return 1
    print("contract_capabilities_schema_check_ok" if check else "contract_capabilities_schema_inventory_written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
