#!/usr/bin/env python3
"""Guard canonical health/readiness response envelopes.

This is intentionally static: it does not import service apps or require their
runtime dependencies. It verifies that HTTP entrypoints exposing `/healthz` and
`/readyz` keep a minimum machine-readable envelope so probes, dashboards and
operators can reason about liveness/readiness uniformly.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATED_JSON = ROOT / "health_readiness_inventory.generated.json"
GENERATED_CSV = ROOT / "health_readiness_inventory.csv"
ENTRYPOINT_GLOBS = ("services/**/main.py", "bots/**/main.py")


@dataclass(frozen=True)
class EndpointRecord:
    file: str
    function: str
    path: str
    line: int
    has_status: bool
    has_service: bool
    has_ready_or_implemented: bool
    verdict: str


def _route_path(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in {"get", "post"}:
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    path = decorator.args[0].value
    return path if isinstance(path, str) else None


def _function_source(path: Path, node: ast.AST) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", getattr(node, "lineno", 1))
    return "\n".join(lines[start:end])


def collect() -> list[EndpointRecord]:
    records: list[EndpointRecord] = []
    files: list[Path] = []
    for pattern in ENTRYPOINT_GLOBS:
        files.extend(ROOT.glob(pattern))
    for path in sorted(set(files)):
        if "/.venv/" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_paths = [_route_path(d) for d in node.decorator_list]
            for route in [r for r in route_paths if r in {"/healthz", "/readyz"}]:
                src = _function_source(path, node)
                has_status = (
                    '"status"' in src
                    or "'status'" in src
                    or "status=" in src
                    or "handle_healthz" in src
                    or "handle_readyz" in src
                )
                has_service = (
                    '"service"' in src
                    or "'service'" in src
                    or "service=" in src
                    or "handle_healthz" in src
                    or "handle_readyz" in src
                )
                if route == "/healthz":
                    has_ready = True
                    verdict = "ok" if has_status and has_service else "missing_health_envelope"
                else:
                    has_ready = (
                        '"implemented_runtime"' in src
                        or "'implemented_runtime'" in src
                        or '"ready"' in src
                        or "'ready'" in src
                        or "handle_readyz" in src
                    )
                    verdict = (
                        "ok"
                        if has_status and has_service and has_ready
                        else "missing_readiness_envelope"
                    )
                records.append(
                    EndpointRecord(
                        file=str(path.relative_to(ROOT)),
                        function=node.name,
                        path=route,
                        line=getattr(node, "lineno", 0),
                        has_status=has_status,
                        has_service=has_service,
                        has_ready_or_implemented=has_ready,
                        verdict=verdict,
                    )
                )
    return records


def write(records: Iterable[EndpointRecord]) -> None:
    rows = [asdict(r) for r in records]
    GENERATED_JSON.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with GENERATED_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["file"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = collect()
    failures = [r for r in records if r.verdict != "ok"]
    if args.write:
        write(records)
    if args.check:
        expected = (
            json.loads(GENERATED_JSON.read_text(encoding="utf-8"))
            if GENERATED_JSON.exists()
            else None
        )
        current = [asdict(r) for r in records]
        if expected != current:
            print("health_readiness_inventory_drift")
            return 1
    if failures:
        for r in failures:
            print(f"{r.verdict}: {r.file}:{r.line} {r.path} {r.function}")
        return 1
    print("health_readiness_schema_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
