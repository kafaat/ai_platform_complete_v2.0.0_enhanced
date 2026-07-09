#!/usr/bin/env python3
"""Generate and optionally enforce Python service dependency inventory.

This guard has two modes:
- default: writes dependency_inventory.generated.json/csv and prints the number of unpinned lines.
- --check: fails when generated inventory is stale or when any service contains unpinned deps.

It does not pretend to resolve transitive dependency versions offline. It records the direct
requirements declared by each service and marks whether each line is exact-pinned.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
EXACT_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^=].+$")
RANGE_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(?:>=|~=|>|<|!=|===).*$")
STRICT_SERVICES = {
    "weather-service",
    "edge-inference",
    "mcp_servers",
    "agriai-engine",
    "knowledge-graph",
    "rag-retrieval",
    "indicators-service",
}


@dataclass
class DependencyRow:
    service: str
    file: str
    line: int
    requirement: str
    package: str
    exact_pinned: bool
    strict_service: bool
    issue: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def meaningful(raw: str) -> str:
    return raw.split("#", 1)[0].strip()


def package_name(req: str) -> str:
    base = re.split(r"==|>=|<=|~=|!=|>|<|===", req, maxsplit=1)[0].strip()
    return base.split("[", 1)[0].strip()


def classify(req: str) -> tuple[bool, str]:
    if EXACT_PIN_RE.match(req):
        return True, ""
    if RANGE_RE.match(req):
        return False, "range_or_minimum_pin"
    return False, "unpinned_or_nonstandard_direct_requirement"


def discover() -> list[DependencyRow]:
    rows: list[DependencyRow] = []
    for req_file in sorted(SERVICES.glob("*/requirements*.txt")) + sorted(SERVICES.glob("*/*/requirements*.txt")):
        parts = req_file.relative_to(SERVICES).parts
        service = parts[0]
        for line_no, raw in enumerate(req_file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            req = meaningful(raw)
            if not req or req.startswith("-") or req.startswith("--"):
                continue
            exact, issue = classify(req)
            rows.append(DependencyRow(
                service=service,
                file=rel(req_file),
                line=line_no,
                requirement=req,
                package=package_name(req),
                exact_pinned=exact,
                strict_service=service in STRICT_SERVICES,
                issue=issue,
            ))
    return rows


def write(rows: list[DependencyRow]) -> None:
    payload = [asdict(r) for r in rows]
    (ROOT / "dependency_inventory.generated.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (ROOT / "dependency_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(asdict(rows[0]).keys()) if rows else ["service", "file", "line", "requirement", "package", "exact_pinned", "strict_service", "issue"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(payload)


def check() -> None:
    before = {
        "dependency_inventory.generated.json": (ROOT / "dependency_inventory.generated.json").read_text(encoding="utf-8") if (ROOT / "dependency_inventory.generated.json").exists() else None,
        "dependency_inventory.csv": (ROOT / "dependency_inventory.csv").read_text(encoding="utf-8") if (ROOT / "dependency_inventory.csv").exists() else None,
    }
    rows = discover(); write(rows)
    drifted = [name for name, text in before.items() if (ROOT / name).read_text(encoding="utf-8") != text]
    unpinned = [r for r in rows if not r.exact_pinned]
    if drifted:
        raise SystemExit("Dependency inventory drift detected: " + ", ".join(drifted) + "; run scripts/ci/dependency_inventory_guard.py")
    if unpinned:
        formatted = "\n".join(f"{r.file}:{r.line}: {r.requirement} [{r.issue}]" for r in unpinned)
        raise SystemExit("Unpinned dependencies in service requirements:\n" + formatted)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check(); print("dependency_inventory_check_ok"); return
    rows = discover(); write(rows)
    total = len(rows)
    unpinned = sum(1 for r in rows if not r.exact_pinned)
    strict_unpinned = sum(1 for r in rows if r.strict_service and not r.exact_pinned)
    print(f"generated dependency inventory: {total} direct deps, {unpinned} unpinned/ranged, {strict_unpinned} strict-service violations")


if __name__ == "__main__":
    main()
