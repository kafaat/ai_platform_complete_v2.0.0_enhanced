#!/usr/bin/env python3
"""Enforce machine-readable source placement for governed platform routes."""

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
    normalize_route_method,
    normalize_route_path,
)
from scripts.ci.platform_route_ownership_guard import collect_surface  # noqa: E402

CONTRACT_PATH = REPO / "docs/architecture/platform_route_placement_contract.json"
SCHEMA_VERSION = "sahool.platform-route-placement-evidence.v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise AssertionError(f"platform route placement contract missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "sahool.platform-route-placement-contract.v1":
        raise AssertionError("unsupported platform route placement contract schema")
    routes = value.get("routes")
    if not isinstance(routes, list) or not routes:
        raise AssertionError("platform route placement contract routes must be non-empty")
    return value


def verify_placement(*, repo: Path = REPO, contract_path: Path | None = None) -> dict[str, Any]:
    contract_path = (
        contract_path or repo / "docs/architecture/platform_route_placement_contract.json"
    )
    contract = load_contract(contract_path)
    platform_root = repo / "services/sahool-platform"
    surface = collect_surface(platform_root)
    evidence: list[dict[str, Any]] = []

    placement_pairs: list[tuple[str, str]] = []
    for index, rule in enumerate(contract["routes"]):
        if not isinstance(rule, dict):
            raise AssertionError(f"placement contract route #{index} must be an object")
        try:
            method = normalize_route_method(str(rule["method"]))
            path = normalize_route_path(str(rule["path"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AssertionError(f"invalid placement contract route #{index}: {exc}") from exc
        placement_pairs.append((method, path))

    duplicate_pairs = sorted(
        pair for pair in set(placement_pairs) if placement_pairs.count(pair) > 1
    )
    if duplicate_pairs:
        raise AssertionError(
            "Platform route placement contract contains duplicate method/path entries: "
            f"{duplicate_pairs}"
        )

    placement_pair_set = frozenset(placement_pairs)
    if placement_pair_set != INFRASTRUCTURE_ROUTES:
        missing_rules = sorted(INFRASTRUCTURE_ROUTES - placement_pair_set)
        stale_rules = sorted(placement_pair_set - INFRASTRUCTURE_ROUTES)
        raise AssertionError(
            "Platform route placement contract must exactly cover the infrastructure "
            "allowlist:\n"
            f"  missing placement rules: {missing_rules}\n"
            f"  non-infrastructure placement rules: {stale_rules}"
        )

    for rule, (method, path) in zip(contract["routes"], placement_pairs, strict=True):
        required_source = str(rule["required_source"])
        required_relative = Path(required_source).relative_to("services/sahool-platform").as_posix()
        required_function = str(rule.get("required_function") or "")
        forbidden = {str(item) for item in rule.get("forbidden_sources", [])}
        matches = [route for route in surface if route.method == method and route.path == path]
        if len(matches) != 1:
            locations = [f"services/sahool-platform/{r.file}:{r.line}" for r in matches]
            raise AssertionError(
                "Platform route placement violation:\n"
                f"  route:            {method} {path}\n"
                f"  declarations:     {len(matches)} {locations}\n"
                f"  required source:  {required_source}\n"
                "The route must have exactly one declaration."
            )
        route = matches[0]
        actual_source = f"services/sahool-platform/{route.file}"
        if actual_source in forbidden or route.file != required_relative:
            raise AssertionError(
                "Platform route placement violation:\n"
                f"  route:            {method} {path}\n"
                f"  declared in:      {actual_source}\n"
                f"  required source:  {required_source}\n\n"
                f"Move the endpoint declaration to {required_source}.\n"
                "Do not suppress this failure by changing the route budget, "
                "ownership inventory, or governance attestation."
            )
        if required_function and route.function != required_function:
            raise AssertionError(
                f"Platform route placement violation: {method} {path} must use function "
                f"{required_function}, found {route.function}"
            )
        evidence.append(
            {
                "method": method,
                "path": path,
                "required_source": required_source,
                "actual_source": actual_source,
                "required_function": required_function,
                "actual_function": route.function,
                "line": route.line,
                "contract_satisfied": True,
            }
        )

    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": {
            "path": contract_path.relative_to(repo).as_posix(),
            "sha256": _sha256(contract_path.read_bytes()),
        },
        "routes": evidence,
        "evidence_sha256": _sha256(canonical),
    }


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    document = verify_placement()
    if args.json_output:
        args.json_output.write_text(canonical_json(document), encoding="utf-8")
    print("platform route placement guard: PASS")
    for row in document["routes"]:
        print(f"  {row['method']} {row['path']} -> {row['actual_source']}:{row['line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
