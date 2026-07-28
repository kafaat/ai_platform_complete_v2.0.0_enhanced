#!/usr/bin/env python3
"""Cross-attest platform route classification, budget, ownership, and map state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ci.platform_route_budget_guard import (  # noqa: E402
    build_inventory as build_budget_inventory,
)
from scripts.ci.platform_route_ownership_guard import (  # noqa: E402
    build_inventory as build_ownership_inventory,
)

CLASSIFICATION_PATH = REPO / "scripts/ci/platform_route_classification.py"
MAP_PATH = REPO / "docs/architecture/platform_extraction_map.json"
BUDGET_GENERATED_PATH = REPO / "docs/architecture/generated/platform_route_budget_inventory.json"
OWNERSHIP_GENERATED_PATH = (
    REPO / "docs/architecture/generated/platform_route_ownership_inventory.json"
)
GENERATED_PATH = REPO / "docs/architecture/generated/platform_route_governance_attestation.json"
SCHEMA_VERSION = "sahool.platform-route-governance-attestation.v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_record(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(REPO).as_posix(),
        "sha256": _sha256(path.read_bytes()),
    }


def build_attestation() -> dict[str, Any]:
    budget = build_budget_inventory()
    ownership = build_ownership_inventory()
    if budget["counts"]["raw_routes"] != ownership["counts"]["direct_routes"]:
        raise AssertionError("budget raw route count differs from ownership direct route count")
    if ownership["counts"]["surface_routes"] != (
        ownership["counts"]["direct_routes"] + ownership["counts"]["api_route_declarations"]
    ):
        raise AssertionError("ownership surface count is not exhaustive")

    for path in (BUDGET_GENERATED_PATH, OWNERSHIP_GENERATED_PATH):
        if not path.exists():
            raise AssertionError(f"required generated inventory missing: {path}")

    inputs = [
        _file_record(CLASSIFICATION_PATH),
        _file_record(MAP_PATH),
        _file_record(BUDGET_GENERATED_PATH),
        _file_record(OWNERSHIP_GENERATED_PATH),
    ]
    statement = {
        "classification_sha256": inputs[0]["sha256"],
        "map_sha256": inputs[1]["sha256"],
        "budget_inventory_sha256": budget["inventory_sha256"],
        "ownership_inventory_sha256": ownership["inventory_sha256"],
        "raw_routes": budget["counts"]["raw_routes"],
        "infrastructure_routes": budget["counts"]["infrastructure_routes"],
        "domain_budget_routes": budget["counts"]["domain_budget_routes"],
        "domain_route_budget": budget["counts"]["domain_route_budget"],
        "full_ownership_surface": ownership["counts"]["surface_routes"],
        "api_route_declarations": ownership["counts"]["api_route_declarations"],
    }
    statement_sha256 = _sha256(
        json.dumps(statement, sort_keys=True, separators=(",", ":")).encode()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "statement_sha256": statement_sha256,
        "statement": statement,
        "inputs": inputs,
    }


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(document), encoding="utf-8")


def check_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    if not path.exists():
        raise AssertionError(f"generated route-governance attestation is missing: {path}")
    if path.read_text(encoding="utf-8") != canonical_json(document):
        raise AssertionError(
            "generated platform route-governance attestation is stale; run "
            "python scripts/ci/platform_route_governance_attestation.py --write-generated"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-generated", action="store_true")
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    document = build_attestation()
    if args.write_generated:
        write_generated(document)
    if args.check_generated:
        check_generated(document)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(canonical_json(document), encoding="utf-8")
    print("platform route governance attestation: PASS")
    for key, value in document["statement"].items():
        if key.endswith("routes") or key in {
            "domain_route_budget",
            "full_ownership_surface",
            "api_route_declarations",
        }:
            print(f"  {key}: {value}")
    print(f"  statement_sha256: {document['statement_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
