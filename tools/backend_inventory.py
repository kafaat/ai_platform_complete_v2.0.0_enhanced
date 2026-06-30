#!/usr/bin/env python3
"""Generate a deterministic backend service inventory for SAHOOL.

The script intentionally reads source files only; it does not import services or
require network/database dependencies.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT / "services"
ROUTE_RE = re.compile(r"@(app|router)\.(get|post|put|patch|delete)\(([^\n]+)")
EXPOSE_RE = re.compile(r"(?:EXPOSE\s+|PORT\s*=\s*|--port\s+)(\d{3,5})")

DOMAIN_RULES = [
    ("weather", "Weather Intelligence"),
    ("raster", "Imagery & Raster"),
    ("vegetation", "Vegetation Analytics"),
    ("indicator", "Vegetation Analytics"),
    ("soil", "Soil Intelligence"),
    ("field-segmentation", "Field Boundary AI"),
    ("sam2", "Field Boundary AI"),
    ("edge", "Edge Inference"),
    ("ai_agronomist", "AI Advisor"),
    ("agriai", "AI Advisor"),
    ("rag", "Knowledge Retrieval"),
    ("knowledge", "Knowledge Graph"),
    ("guardrails", "AI Safety & Governance"),
    ("auth", "Identity & Access"),
    ("odoo", "ERP Integration"),
    ("mcp", "Agent Tools"),
    ("supervisor", "Agent Orchestration"),
    ("tts", "Voice & Notifications"),
    ("video", "Video Processing"),
    ("actuator", "IoT Actuation"),
    ("platform", "Core Field Platform"),
]


@dataclass(frozen=True)
class ServiceInventory:
    service: str
    path: str
    domain: str
    python_files: int
    python_loc: int
    route_count: int
    main: str | None
    dockerfile: bool
    ports: list[str]
    risk: str
    suggested_owner: str


def classify_domain(name: str) -> str:
    key = name.lower()
    for token, domain in DOMAIN_RULES:
        if token in key:
            return domain
    return "Unclassified / Support"


def iter_py(path: Path) -> Iterable[Path]:
    yield from path.rglob("*.py")


def count_loc(files: Iterable[Path]) -> int:
    total = 0
    for file in files:
        try:
            total += len(file.read_text(errors="ignore").splitlines())
        except OSError:
            continue
    return total


def count_routes(files: Iterable[Path]) -> int:
    routes = 0
    for file in files:
        try:
            routes += len(ROUTE_RE.findall(file.read_text(errors="ignore")))
        except OSError:
            continue
    return routes


def find_main(path: Path) -> str | None:
    for candidate in (path / "main.py", path / "api" / "main.py", path / "src" / "main.py"):
        if candidate.exists():
            return candidate.relative_to(ROOT).as_posix()
    return None


def find_ports(path: Path) -> list[str]:
    ports: set[str] = set()
    for candidate in (path / "Dockerfile", path / "README.md"):
        if not candidate.exists():
            continue
        try:
            for match in EXPOSE_RE.finditer(candidate.read_text(errors="ignore")):
                ports.add(match.group(1))
        except OSError:
            continue
    return sorted(ports)


def risk_for(loc: int, routes: int, dockerfile: bool, main: str | None) -> str:
    if loc > 100_000 or routes > 300:
        return "critical-core-concentration"
    if routes > 40 or loc > 10_000:
        return "high-boundary-pressure"
    if not dockerfile or not main:
        return "medium-runtime-contract-gap"
    return "normal"


def inventory() -> list[ServiceInventory]:
    services: list[ServiceInventory] = []
    for service_dir in sorted(SERVICES_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        py_files = list(iter_py(service_dir))
        loc = count_loc(py_files)
        routes = count_routes(py_files)
        main = find_main(service_dir)
        dockerfile = (service_dir / "Dockerfile").exists()
        domain = classify_domain(service_dir.name)
        services.append(
            ServiceInventory(
                service=service_dir.name,
                path=service_dir.relative_to(ROOT).as_posix(),
                domain=domain,
                python_files=len(py_files),
                python_loc=loc,
                route_count=routes,
                main=main,
                dockerfile=dockerfile,
                ports=find_ports(service_dir),
                risk=risk_for(loc, routes, dockerfile, main),
                suggested_owner=domain.replace(" & ", "/"),
            )
        )
    return services


def write_outputs(services: list[ServiceInventory]) -> None:
    out_json = ROOT / "docs" / "backend" / "service_inventory.generated.json"
    out_json.write_text(
        json.dumps([asdict(s) for s in services], ensure_ascii=False, indent=2) + "\n"
    )

    rows = [
        "| Service | Domain | LOC | Routes | Main | Docker | Ports | Risk |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for s in services:
        rows.append(
            f"| `{s.service}` | {s.domain} | {s.python_loc} | {s.route_count} | "
            f"`{s.main or '-'}` | {'yes' if s.dockerfile else 'no'} | {', '.join(s.ports) or '-'} | `{s.risk}` |"
        )
    (ROOT / "docs" / "backend" / "service_inventory.generated.md").write_text(
        "\n".join(rows) + "\n"
    )


if __name__ == "__main__":
    data = inventory()
    write_outputs(data)
    print(
        json.dumps(
            {
                "services": len(data),
                "routes": sum(s.route_count for s in data),
                "loc": sum(s.python_loc for s in data),
            },
            ensure_ascii=False,
        )
    )
