#!/usr/bin/env python3
"""Bind platform-route governance state to source releases and final archives."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
GOVERNANCE_ATTESTATION = (
    REPO / "docs/architecture/generated/platform_route_governance_attestation.json"
)
BUDGET_INVENTORY = REPO / "docs/architecture/generated/platform_route_budget_inventory.json"
OWNERSHIP_INVENTORY = REPO / "docs/architecture/generated/platform_route_ownership_inventory.json"
SOURCE_BINDING = REPO / "release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json"
SOURCE_SCHEMA = "sahool.platform-route-release-binding.v1"
ARCHIVE_SCHEMA = "sahool.platform-route-archive-binding.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AssertionError(f"required route-governance input missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def build_source_binding() -> dict[str, Any]:
    governance = _load_json(GOVERNANCE_ATTESTATION)
    budget = _load_json(BUDGET_INVENTORY)
    ownership = _load_json(OWNERSHIP_INVENTORY)
    statement_sha = governance.get("statement_sha256")
    if not isinstance(statement_sha, str) or len(statement_sha) != 64:
        raise AssertionError("route-governance attestation has no valid statement_sha256")
    return {
        "schema_version": SOURCE_SCHEMA,
        "route_governance_statement_sha256": statement_sha,
        "inputs": [
            {
                "path": GOVERNANCE_ATTESTATION.relative_to(REPO).as_posix(),
                "sha256": sha256_file(GOVERNANCE_ATTESTATION),
            },
            {
                "path": BUDGET_INVENTORY.relative_to(REPO).as_posix(),
                "sha256": sha256_file(BUDGET_INVENTORY),
            },
            {
                "path": OWNERSHIP_INVENTORY.relative_to(REPO).as_posix(),
                "sha256": sha256_file(OWNERSHIP_INVENTORY),
            },
        ],
        "route_counts": {
            "raw_routes": budget["counts"]["raw_routes"],
            "infrastructure_routes": budget["counts"]["infrastructure_routes"],
            "domain_budget_routes": budget["counts"]["domain_budget_routes"],
            "domain_route_budget": budget["counts"]["domain_route_budget"],
            "full_ownership_surface": ownership["counts"]["surface_routes"],
        },
    }


def write_source_binding(path: Path = SOURCE_BINDING) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(build_source_binding()), encoding="utf-8")


def check_source_binding(path: Path = SOURCE_BINDING) -> None:
    expected = canonical_json(build_source_binding())
    if not path.is_file():
        raise AssertionError(f"source route-governance binding missing: {path}")
    if path.read_text(encoding="utf-8") != expected:
        raise AssertionError(
            "source route-governance binding is stale; run "
            "python scripts/release/platform_route_release_binding.py --write-source"
        )


def build_archive_binding(archive: Path, source_binding: Path = SOURCE_BINDING) -> dict[str, Any]:
    check_source_binding(source_binding)
    if not archive.is_file():
        raise AssertionError(f"release archive missing: {archive}")
    source = _load_json(source_binding)
    return {
        "schema_version": ARCHIVE_SCHEMA,
        "artifact": {
            "name": archive.name,
            "sha256": sha256_file(archive),
            "size_bytes": archive.stat().st_size,
        },
        "source_binding": {
            "path": source_binding.relative_to(REPO).as_posix()
            if source_binding.is_relative_to(REPO)
            else str(source_binding),
            "sha256": sha256_file(source_binding),
        },
        "route_governance_statement_sha256": source["route_governance_statement_sha256"],
        "route_counts": source["route_counts"],
    }


def check_archive_binding(archive: Path, binding: Path) -> None:
    expected = canonical_json(build_archive_binding(archive))
    if not binding.is_file():
        raise AssertionError(f"archive route-governance binding missing: {binding}")
    if binding.read_text(encoding="utf-8") != expected:
        raise AssertionError("archive route-governance binding does not match the release archive")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-source", action="store_true")
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-archive-binding", type=Path)
    args = parser.parse_args()

    if args.write_source:
        write_source_binding()
    if args.check_source:
        check_source_binding()
    if args.check_archive_binding:
        if not args.archive:
            parser.error("--check-archive-binding requires --archive")
        # Check mode is deliberately side-effect free.  In particular, do not rewrite the
        # default sidecar before validating it; that would make a tampered binding pass.
        check_archive_binding(args.archive.resolve(), args.check_archive_binding.resolve())
    elif args.archive:
        document = build_archive_binding(args.archive.resolve())
        output = args.output or args.archive.with_suffix(
            args.archive.suffix + ".route-governance.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(canonical_json(document), encoding="utf-8")
        print(f"archive route-governance binding written: {output}")
    if not any((args.write_source, args.check_source, args.archive, args.check_archive_binding)):
        parser.error("select a source or archive operation")
    print("platform route release binding: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
