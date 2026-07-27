#!/usr/bin/env python3
"""Fail-closed SAHOOL platform domain-route budget guard.

This command is intentionally dependency-free. It inventories every literal
FastAPI route declaration under sahool-platform, validates the central
infrastructure allowlist, preserves the raw inventory, and applies the ratchet
only to domain-budget routes.
"""

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

from scripts.ci.platform_route_classification import (  # noqa: E402
    INFRASTRUCTURE_ROUTES,
    RouteDeclaration,
    assert_infrastructure_allowlist_is_used,
    collect_platform_routes,
    partition_routes,
)

PLATFORM_ROOT = REPO / "services/sahool-platform"
POLICY_PATH = REPO / "docs/architecture/platform_extraction_map.json"
GENERATED_PATH = REPO / "docs/architecture/generated/platform_route_budget_inventory.json"
SCHEMA_VERSION = "sahool.platform-route-budget-inventory.v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _route_dict(route: RouteDeclaration, classification: str) -> dict[str, Any]:
    return {
        "method": route.method,
        "path": route.path,
        "classification": classification,
        "source": route.source,
        "line": route.line,
        "function": route.function,
    }


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    policy = document.get("p2_6_route_budget_reduction")
    if not isinstance(policy, dict):
        raise AssertionError("missing p2_6_route_budget_reduction policy")
    return policy


def build_inventory(
    *, platform_root: Path = PLATFORM_ROOT, policy_path: Path = POLICY_PATH
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    budget = policy.get("domain_route_budget")
    legacy_budget = policy.get("new_max_platform_routes")
    if not isinstance(budget, int) or budget < 0:
        raise AssertionError("domain_route_budget must be a non-negative integer")
    if legacy_budget != budget:
        raise AssertionError(
            "new_max_platform_routes must remain an exact compatibility alias for "
            "domain_route_budget"
        )

    documented = {
        (entry.get("method"), entry.get("path"))
        for entry in policy.get("infrastructure_route_allowlist", [])
        if isinstance(entry, dict)
    }
    if documented != set(INFRASTRUCTURE_ROUTES):
        raise AssertionError(
            "documented infrastructure allowlist differs from canonical policy: "
            f"documented={sorted(documented)} canonical={sorted(INFRASTRUCTURE_ROUTES)}"
        )

    raw = collect_platform_routes(platform_root)
    assert_infrastructure_allowlist_is_used(raw)
    infrastructure, domain = partition_routes(raw)
    if len(raw) != len(infrastructure) + len(domain):
        raise AssertionError("route partition is not exhaustive")
    if len(domain) > budget:
        raise AssertionError(
            "Platform domain-route budget exceeded:\n"
            f"  raw routes:            {len(raw)}\n"
            f"  infrastructure routes: {len(infrastructure)}\n"
            f"  domain routes:         {len(domain)}\n"
            f"  domain maximum:        {budget}\n"
        )

    raw_rows = [
        _route_dict(route, "infrastructure" if route.infrastructure else "domain") for route in raw
    ]
    route_payload = json.dumps(raw_rows, sort_keys=True, separators=(",", ":")).encode()
    policy_payload = policy_path.read_bytes()
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": {
            "domain_route_budget": budget,
            "canonical_infrastructure_allowlist": [
                {"method": method, "path": path} for method, path in sorted(INFRASTRUCTURE_ROUTES)
            ],
            "policy_file": policy_path.relative_to(REPO).as_posix(),
            "policy_sha256": _sha256_bytes(policy_payload),
        },
        "counts": {
            "raw_routes": len(raw),
            "infrastructure_routes": len(infrastructure),
            "domain_budget_routes": len(domain),
            "domain_route_budget": budget,
            "domain_budget_headroom": budget - len(domain),
        },
        "inventory_sha256": _sha256_bytes(route_payload),
        "routes": raw_rows,
    }


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(document), encoding="utf-8")


def check_generated(document: dict[str, Any], path: Path = GENERATED_PATH) -> None:
    expected = canonical_json(document)
    if not path.exists():
        raise AssertionError(f"generated route-budget inventory is missing: {path}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(
            "generated platform route-budget inventory is stale; run "
            "python scripts/ci/platform_route_budget_guard.py --write-generated"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-generated", action="store_true")
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    inventory = build_inventory()
    if args.write_generated:
        write_generated(inventory)
    if args.check_generated:
        check_generated(inventory)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(canonical_json(inventory), encoding="utf-8")

    counts = inventory["counts"]
    print(
        "platform route budget: PASS\n"
        f"  raw routes:            {counts['raw_routes']}\n"
        f"  infrastructure routes: {counts['infrastructure_routes']}\n"
        f"  domain routes:         {counts['domain_budget_routes']}\n"
        f"  domain maximum:        {counts['domain_route_budget']}\n"
        f"  domain headroom:       {counts['domain_budget_headroom']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
