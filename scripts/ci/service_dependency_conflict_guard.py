#!/usr/bin/env python3
"""Generate an auditable cross-service dependency conflict report.

This is not a resolver. It answers a governance question: do different services pin
incompatible direct versions of the same package? That matters before attempting a
single transitive lock, and it explains why Sahool uses service-local images instead
of one shared Python environment.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
REQ_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==(?P<version>.+)$")


@dataclass
class ConflictRow:
    package: str
    version_count: int
    versions: str
    services: str
    files: str


def meaningful(line: str) -> str:
    return line.split("#", 1)[0].strip()


def normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def iter_req_files() -> list[Path]:
    return sorted(SERVICES.glob("*/requirements*.txt")) + sorted(
        SERVICES.glob("*/*/requirements*.txt")
    )


def discover() -> list[ConflictRow]:
    seen: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    files: dict[str, set[str]] = defaultdict(set)
    for req_file in iter_req_files():
        service = req_file.relative_to(SERVICES).parts[0]
        for line_no, raw in enumerate(
            req_file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            req = meaningful(raw)
            if not req or req.startswith("-") or req.startswith("--"):
                continue
            m = REQ_RE.match(req)
            if not m:
                continue
            package = normalize(m.group("name"))
            version = m.group("version").strip()
            seen[package][version].append(service)
            files[package].add(f"{req_file.relative_to(ROOT)}:{line_no}")
    rows: list[ConflictRow] = []
    for package, by_version in sorted(seen.items()):
        if len(by_version) <= 1:
            continue
        service_bits = []
        for version, services in sorted(by_version.items()):
            service_bits.append(f"{version}=>{','.join(sorted(set(services)))}")
        rows.append(
            ConflictRow(
                package=package,
                version_count=len(by_version),
                versions=", ".join(sorted(by_version)),
                services="; ".join(service_bits),
                files="; ".join(sorted(files[package])),
            )
        )
    return rows


def write(rows: list[ConflictRow], output_root: Path = ROOT) -> None:
    payload = [asdict(r) for r in rows]
    (output_root / "dependency_conflicts.generated.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (output_root / "dependency_conflicts.csv").open("w", encoding="utf-8", newline="") as f:
        fields = (
            list(asdict(rows[0]).keys())
            if rows
            else ["package", "version_count", "versions", "services", "files"]
        )
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(payload)


def check() -> None:
    import tempfile

    names = ["dependency_conflicts.generated.json", "dependency_conflicts.csv"]
    rows = discover()
    with tempfile.TemporaryDirectory(prefix="sahool-dependency-conflict-check-") as tmp:
        candidate_root = Path(tmp)
        write(rows, candidate_root)
        drift = [
            name
            for name in names
            if not (ROOT / name).exists()
            or (ROOT / name).read_bytes() != (candidate_root / name).read_bytes()
        ]
    if drift:
        raise SystemExit(
            "Dependency conflict inventory drift detected: "
            + ", ".join(drift)
            + "; run scripts/ci/service_dependency_conflict_guard.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        print("dependency_conflict_inventory_check_ok")
        return
    rows = discover()
    write(rows)
    print(
        f"generated dependency conflict report: {len(rows)} packages with cross-service version divergence"
    )


if __name__ == "__main__":
    main()
