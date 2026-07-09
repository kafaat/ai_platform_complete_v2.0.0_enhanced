#!/usr/bin/env python3
"""Generate Sahool service and route inventory from source code.

Outputs:
- service_inventory.generated.json
- service_inventory.csv
- route_inventory.generated.json
- route_inventory.csv
- SERVICE_REGISTRY.md (when --write-registry is passed)

This script is intentionally static and dependency-light. It parses Python AST
for FastAPI decorators and walks service folders, so CI can detect drift without
starting the whole platform.
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
SERVICES = ROOT / "services"
HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "api_route",
    "websocket",
}
DOMAIN_MAP = {
    "weather": "Weather Intelligence",
    "raster": "Imagery & Raster",
    "vegetation": "Vegetation Analytics",
    "indicator": "Vegetation Analytics",
    "soil": "Soil Intelligence",
    "edge": "Edge Inference",
    "sam2": "Field Boundary AI",
    "segmentation": "Field Boundary AI",
    "auth": "Identity & Access",
    "rag": "Knowledge Retrieval",
    "knowledge": "Knowledge Retrieval",
    "mcp": "Agent Tools",
    "ai_agronomist": "AI Advisor",
    "agriai": "AI Advisor",
    "guardrails": "AI Safety & Governance",
    "supervisor": "Agent Orchestration",
    "decision": "Decision SoR",
    "odoo": "ERP Integration",
    "actuator": "IoT Actuation",
    "tts": "Voice & Notifications",
    "video": "Video Processing",
    "platform": "Core Field Platform",
}


@dataclass
class RouteRow:
    service: str
    file: str
    line: int
    method: str
    path: str
    function: str


@dataclass
class ServiceRow:
    service: str
    domain: str
    python_files: int
    python_loc: int
    tests: int
    routes: int
    main: str
    dockerfile: str
    requirements: str
    risk: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def python_loc(files: Iterable[Path]) -> int:
    total = 0
    for p in files:
        try:
            total += sum(
                1
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
        except Exception:
            pass
    return total


def decorator_route(dec: ast.AST) -> tuple[str, str] | None:
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    method = None
    if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
        method = func.attr.upper().replace("API_ROUTE", "ANY")
    if method is None:
        return None
    path = None
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        path = dec.args[0].value
    for kw in dec.keywords:
        if (
            kw.arg == "path"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            path = kw.value.value
    if not path:
        path = "<dynamic>"
    return method, path


def registration_call_route(node: ast.AST) -> tuple[str, str, str] | None:
    """Return (method, path, handler_name) for app.get("/x")(handler) registrations."""
    if not isinstance(node, ast.Call):
        return None
    inner = node.func
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)):
        return None
    if inner.func.attr not in HTTP_METHODS:
        return None
    path = None
    if (
        inner.args
        and isinstance(inner.args[0], ast.Constant)
        and isinstance(inner.args[0].value, str)
    ):
        path = inner.args[0].value
    for kw in inner.keywords:
        if (
            kw.arg == "path"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            path = kw.value.value
    if not path:
        return None
    handler = "<registered>"
    if node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Attribute):
            handler = arg.attr
        elif isinstance(arg, ast.Name):
            handler = arg.id
    return inner.func.attr.upper().replace("API_ROUTE", "ANY"), path, handler


def routes_for_file(service: str, path: Path) -> list[RouteRow]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    rows: list[RouteRow] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                route = decorator_route(dec)
                if route:
                    method, route_path = route
                    rows.append(
                        RouteRow(
                            service,
                            rel(path),
                            getattr(node, "lineno", 0),
                            method,
                            route_path,
                            node.name,
                        )
                    )
    for node in ast.walk(tree):
        route = registration_call_route(node)
        if route:
            method, route_path, handler = route
            rows.append(
                RouteRow(
                    service, rel(path), getattr(node, "lineno", 0), method, route_path, handler
                )
            )
    return rows


def domain_for(service: str) -> str:
    for key, domain in DOMAIN_MAP.items():
        if key in service:
            return domain
    return "Unclassified / Support"


def risk_for(service: str, routes: int, tests: int, loc: int) -> str:
    if service == "sahool-platform" or loc > 50000 or routes > 250:
        return "critical-core-concentration"
    if routes and tests == 0:
        return "high-zero-test-routes"
    if routes == 0:
        return "medium-runtime-contract-gap"
    return "normal"


def discover() -> tuple[list[ServiceRow], list[RouteRow]]:
    service_rows: list[ServiceRow] = []
    route_rows: list[RouteRow] = []
    for svc_dir in sorted(p for p in SERVICES.iterdir() if p.is_dir()):
        py_files = [p for p in svc_dir.rglob("*.py") if "__pycache__" not in p.parts]
        test_files = [p for p in py_files if p.name.startswith("test_") or "/tests/" in str(p)]
        svc_routes: list[RouteRow] = []
        for py in py_files:
            svc_routes.extend(routes_for_file(svc_dir.name, py))
        route_rows.extend(svc_routes)
        main = "-"
        for candidate in [
            svc_dir / "main.py",
            svc_dir / "api" / "main.py",
            svc_dir / "src" / "main.py",
        ]:
            if candidate.exists():
                main = rel(candidate)
                break
        docker = "-"
        for candidate in [svc_dir / "Dockerfile", svc_dir / "Dockerfile.arm64"]:
            if candidate.exists():
                docker = rel(candidate)
                break
        req = "-"
        for candidate in [svc_dir / "requirements.txt", svc_dir / "pyproject.toml"]:
            if candidate.exists():
                req = rel(candidate)
                break
        loc_count = python_loc(py_files)
        service_rows.append(
            ServiceRow(
                service=svc_dir.name,
                domain=domain_for(svc_dir.name),
                python_files=len(py_files),
                python_loc=loc_count,
                tests=len(test_files),
                routes=len(svc_routes),
                main=main,
                dockerfile=docker,
                requirements=req,
                risk=risk_for(svc_dir.name, len(svc_routes), len(test_files), loc_count),
            )
        )
    return service_rows, route_rows


def write_outputs(services: list[ServiceRow], routes: list[RouteRow], write_registry: bool) -> None:
    service_json = [asdict(r) for r in services]
    route_json = [asdict(r) for r in routes]
    (ROOT / "service_inventory.generated.json").write_text(
        json.dumps(service_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / "route_inventory.generated.json").write_text(
        json.dumps(route_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (ROOT / "service_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(services[0]).keys()))
        writer.writeheader()
        writer.writerows(service_json)
    with (ROOT / "route_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(asdict(routes[0]).keys())
            if routes
            else ["service", "file", "line", "method", "path", "function"],
        )
        writer.writeheader()
        writer.writerows(route_json)
    if write_registry:
        write_service_registry(services, routes)


def write_service_registry(services: list[ServiceRow], routes: list[RouteRow]) -> None:
    by_domain: dict[str, list[str]] = {}
    for svc in services:
        by_domain.setdefault(svc.domain, []).append(svc.service)
    total_loc = sum(s.python_loc for s in services)
    lines = [
        "# SAHOOL Backend Service Registry",
        "",
        "> Generated automatically from source code by `scripts/ci/generate_service_inventory.py`.",
        "> Do not hand-edit counts; run the generator and commit the generated inventory files.",
        "",
        "## Inventory summary",
        "",
        f"- Services discovered: **{len(services)}**",
        f"- Python LOC discovered: **{total_loc:,}**",
        f"- Routes discovered: **{len(routes)}**",
        f"- Largest service concentration: **{max(services, key=lambda s: s.routes).service if services else '-'}**",
        "- Protected product decision: **MapHub default must be raw field satellite image / truecolor, not weather and not NDVI-only.**",
        "",
        "## Service registry",
        "",
        "| Service | Domain | Python files | LOC | Tests | Routes | Main | Docker | Requirements | Risk |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for s in services:
        lines.append(
            f"| `{s.service}` | {s.domain} | {s.python_files} | {s.python_loc} | {s.tests} | {s.routes} | `{s.main}` | `{s.dockerfile}` | `{s.requirements}` | `{s.risk}` |"
        )
    lines += [
        "",
        "## Domain ownership matrix",
        "",
        "| Domain | Services | Recommended ownership rule |",
        "|---|---:|---|",
    ]
    for domain, names in sorted(by_domain.items()):
        lines.append(
            f"| {domain} | {', '.join(f'`{n}`' for n in sorted(names))} | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |"
        )
    lines += [
        "",
        "## Governance rules",
        "",
        "1. `SERVICE_REGISTRY.md`, `service_inventory.generated.json`, and `route_inventory.generated.json` are generated from code.",
        "2. CI must fail when generated inventory differs from committed inventory.",
        "3. Services with routes and zero tests are `high-zero-test-routes` until a smoke/contract test exists.",
        "4. `docker-compose.v9.yml` is the production-reference local runtime; `docker-compose.fixed.yml`/`docker-compose.unified.yml` remain at the repository root (guarded by SEC-1 compose tests).",
        "5. `sahool-platform` hosts the Field Intelligence Backbone (see `docs/backend/ADR_V50_BACKEND_OWNERSHIP_AND_RAW_IMAGERY_DEFAULT.md`).",
        "",
    ]
    (ROOT / "SERVICE_REGISTRY.md").write_text("\n".join(lines), encoding="utf-8")


def check_drift() -> None:
    before = {
        "service_inventory.generated.json": (ROOT / "service_inventory.generated.json").read_text(
            encoding="utf-8"
        )
        if (ROOT / "service_inventory.generated.json").exists()
        else None,
        "route_inventory.generated.json": (ROOT / "route_inventory.generated.json").read_text(
            encoding="utf-8"
        )
        if (ROOT / "route_inventory.generated.json").exists()
        else None,
        "SERVICE_REGISTRY.md": (ROOT / "SERVICE_REGISTRY.md").read_text(encoding="utf-8")
        if (ROOT / "SERVICE_REGISTRY.md").exists()
        else None,
    }
    services, routes = discover()
    write_outputs(services, routes, True)
    drifted = [
        name for name, text in before.items() if (ROOT / name).read_text(encoding="utf-8") != text
    ]
    if drifted:
        raise SystemExit(
            "Inventory drift detected: "
            + ", ".join(drifted)
            + "; run scripts/ci/generate_service_inventory.py --write-registry"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-registry", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check_drift()
        return
    services, routes = discover()
    write_outputs(services, routes, args.write_registry)
    print(f"generated inventory: {len(services)} services, {len(routes)} routes")


if __name__ == "__main__":
    main()
