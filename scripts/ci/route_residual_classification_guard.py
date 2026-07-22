#!/usr/bin/env python3
"""Classify route decorators that remain directly in main.py files.

The goal is to make the residual route surface explicit. Business endpoints may
remain only if listed in the generated allowlist; otherwise new business routes
must move to routers/runtime modules.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "route_residual_classification.generated.json"
CSV_PATH = ROOT / "route_residual_classification.csv"
ALLOWLIST_PATH = ROOT / "route_residual_business_allowlist.generated.json"
METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _route_decorators(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            method = None
            if isinstance(fn, ast.Attribute) and fn.attr in METHODS:
                method = fn.attr.upper()
            if not method or not dec.args:
                continue
            arg0 = dec.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                route_path = arg0.value
            else:
                continue
            rows.append(
                {
                    "service": _service_name(path),
                    "file": str(path.relative_to(ROOT)),
                    "line": node.lineno,
                    "method": method,
                    "path": route_path,
                    "function": node.name,
                    "classification": classify_route(route_path, node.name),
                }
            )
    return rows


def _service_name(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if parts[0] == "services" and len(parts) > 1:
        if parts[1] == "sahool-platform" and len(parts) > 2 and parts[2] == "api":
            return "sahool-platform/api"
        return parts[1]
    if parts[0] == "bots" and len(parts) > 1:
        return f"bots/{parts[1]}"
    return parts[0]


def classify_route(path: str, func: str) -> str:
    p = path.rstrip("/") or "/"
    f = func.lower()
    if p in {"/health", "/healthz", "/livez"} or "health" in f:
        return "health"
    if p in {"/ready", "/readyz"} or "ready" in f:
        return "readiness"
    if p == "/metrics" or "metric" in f:
        return "metrics"
    if p.startswith("/internal"):
        return "internal_endpoint"
    if "contract" in p or "contract" in f:
        return "contract"
    if "capabilities" in p or "capabilities" in f:
        return "capabilities"
    if p.startswith("/v1"):
        return "business_endpoint"
    if p in {"/", "/status", "/ping"}:
        return "legacy_alias"
    # Unversioned non-health routes are treated as business until explicitly proven otherwise.
    return "business_endpoint"


def collect() -> list[dict]:
    rows = []
    for base in [ROOT / "services", ROOT / "bots"]:
        if base.exists():
            for path in base.rglob("main.py"):
                rows.extend(_route_decorators(path))
    rows.sort(key=lambda r: (r["service"], r["file"], r["line"], r["method"], r["path"]))
    return rows


def payload() -> dict:
    rows = collect()
    counts = {}
    for r in rows:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    business = [r for r in rows if r["classification"] == "business_endpoint"]
    return {
        "schema_version": 1,
        "policy": "Residual routes in main.py must be classified. New business endpoints should be moved to routers unless explicitly allowlisted.",
        "total_residual_main_routes": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "business_endpoint_count": len(business),
        "rows": rows,
    }


def write_files() -> None:
    data = payload()
    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["service", "file", "line", "method", "path", "function", "classification"],
        )
        writer.writeheader()
        writer.writerows(data["rows"])
    allow = {
        "schema_version": 1,
        "policy": "Existing business endpoints in main.py are frozen residual compatibility surface. New entries require review.",
        "business_endpoints": [
            {k: r[k] for k in ["service", "file", "line", "method", "path", "function"]}
            for r in data["rows"]
            if r["classification"] == "business_endpoint"
        ],
    }
    ALLOWLIST_PATH.write_text(
        json.dumps(allow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def check_files() -> None:
    expected = json.dumps(payload(), indent=2, ensure_ascii=False) + "\n"
    if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != expected:
        raise SystemExit("route residual classification drift; run with --write")
    if not CSV_PATH.exists() or not ALLOWLIST_PATH.exists():
        raise SystemExit("route residual CSV or business allowlist missing; run with --write")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    current_business = [
        {k: r[k] for k in ["service", "file", "line", "method", "path", "function"]}
        for r in data["rows"]
        if r["classification"] == "business_endpoint"
    ]
    if allow.get("business_endpoints") != current_business:
        raise SystemExit("business residual route allowlist drift; run with --write after review")
    print("route_residual_classification_check_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_files()
    if args.check or not args.write:
        check_files()


if __name__ == "__main__":
    main()
