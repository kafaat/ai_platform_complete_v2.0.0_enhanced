#!/usr/bin/env python3
"""Export code-declared service routes for the offline R13 explorer.

Consumes generated inventories. Does not probe gateway, DB, authorization or runtime.
Call the existing inventory drift guard before exporting in CI.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY", "WEBSOCKET"})
KEYS = ("service", "method", "path", "file", "line", "function")
SCHEMA = "sahool.explorer.code-routes/v1"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def code_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    sha = result.stdout.strip().lower()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("INVALID_GIT_HEAD")
    return sha


def create_catalog(
    routes: list[dict], services: list[dict], *, source_head: str, source_sha256: str
) -> dict:
    if not routes or not services:
        raise ValueError("SOURCE_INVENTORY_MISSING_OR_EMPTY")
    if len(source_head) != 40 or any(c not in "0123456789abcdef" for c in source_head):
        raise ValueError("SOURCE_COMMIT_UNBOUND")
    expected = {}
    for svc in services:
        service = svc.get("service")
        if not isinstance(service, str) or not service or service in expected:
            raise ValueError("SERVICE_ROW_INVALID_OR_DUPLICATE")
        count = svc.get("routes")
        if type(count) is not int or count < 0:
            raise ValueError("SERVICE_ROUTE_COUNT_INVALID")
        expected[service] = count
    actual = Counter()
    identities = set()
    keys = set()
    groups = defaultdict(list)
    exported = []
    for row in routes:
        if not isinstance(row, dict) or any(k not in row for k in KEYS):
            raise ValueError("INCOMPLETE_ROUTE_ROW")
        service, method, path, file, line, function = (row[k] for k in KEYS)
        if (
            not all(isinstance(v, str) and v for v in (service, method, path, file, function))
            or type(line) is not int or line < 1
        ):
            raise ValueError("MALFORMED_ROUTE_ROW")
        if service not in expected or method not in METHODS:
            raise ValueError("UNKNOWN_SERVICE_OR_METHOD")
        if not (path.startswith("/") or path == "<dynamic>"):
            raise ValueError("ROUTE_PATH_INVALID")
        if not file.startswith(f"services/{service}/") or ".." in Path(file).parts or "\\" in file:
            raise ValueError("ROUTE_SOURCE_INVALID")
        identity = (service, method, path, file, line, function)
        if identity in identities:
            raise ValueError("DUPLICATE_DECLARATION_ROW")
        identities.add(identity)
        key = (service, method, path)
        keys.add(key)
        actual[service] += 1
        groups[key].append({"file": file, "line": line, "function": function})
        exported.append({
            "service": service, "method": method, "path": path, "file": file,
            "line": line, "function": function,
            "evidence": "CODE_DECLARED_STATIC", "runtime": "NOT_RUN",
            "path_resolution": "UNRESOLVED_DYNAMIC" if path == "<dynamic>" else "LITERAL_FROM_AST",
        })
    if actual != Counter(expected):
        raise ValueError("SERVICE_ROUTE_COUNTS_DRIFT")
    exported.sort(
        key=lambda x: (x["service"], x["method"], x["path"], x["file"], x["line"], x["function"])
    )
    collisions = [
        {"service": s, "method": m, "path": p, "declarations": members}
        for (s, m, p), members in sorted(groups.items()) if len(members) > 1
    ]
    return {
        "schema": SCHEMA,
        "repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "source_commit": source_head,
        "source_route_inventory_sha256": source_sha256,
        "evidence_kind": "CODE_DECLARED_STATIC", "runtime_e2e": "NOT_RUN",
        "ci_statement": "Source inventory consistency is CI-checked; deployed gateway and auth NOT_VERIFIED",
        "counts": {
            "services": len(services),
            "services_with_routes": sum(bool(n) for n in expected.values()),
            "route_declarations": len(exported),
            "unique_service_method_path": len(keys),
            "ambiguous_declaration_groups": len(collisions),
            "unresolved_dynamic_paths": sum(
                x["path_resolution"] == "UNRESOLVED_DYNAMIC" for x in exported
            ),
        },
        "service_route_counts": dict(sorted(expected.items())),
        "ambiguous_declarations": collisions,
        "routes": exported,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-inventory", type=Path, required=True)
    parser.add_argument("--service-inventory", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--expected-head", default=None)
    args = parser.parse_args(argv)
    try:
        if not args.route_inventory.is_file() or not args.service_inventory.is_file():
            raise ValueError("SOURCE_INVENTORY_MISSING_OR_EMPTY")
        head = code_head(args.repo_root)
        if args.expected_head and args.expected_head.lower() != head:
            raise ValueError("SOURCE_HEAD_MISMATCH")
        if (
            args.route_inventory.resolve()
            != (args.repo_root / "route_inventory.generated.json").resolve()
            or args.service_inventory.resolve()
            != (args.repo_root / "service_inventory.generated.json").resolve()
        ):
            raise ValueError("SOURCE_INVENTORY_MUST_BE_REPO_ROOT")
        routes = json.loads(args.route_inventory.read_text(encoding="utf-8"))
        services = json.loads(args.service_inventory.read_text(encoding="utf-8"))
        if not isinstance(routes, list) or not isinstance(services, list):
            raise ValueError("SOURCE_INVENTORY_INVALID_SHAPE")
        catalog = create_catalog(
            routes, services, source_head=head, source_sha256=digest(args.route_inventory)
        )
        args.out_dir.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (args.out_dir / "code_routes_catalog.json").write_bytes(raw)
        receipt = {
            "schema": "sahool.explorer.route-ci-receipt/v1",
            "verdict": "CODE_INVENTORY_EXPORTED",
            "source_commit": head,
            "source_route_inventory_sha256": digest(args.route_inventory),
            "source_service_inventory_sha256": digest(args.service_inventory),
            "output_sha256": sha256(raw).hexdigest(),
            "counts": catalog["counts"],
            "runtime_e2e": "NOT_RUN",
            "gateway_routing": "NOT_VERIFIED", "auth_tenant": "NOT_VERIFIED",
        }
        (args.out_dir / "route_ci_receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ROUTE_EXPORT_BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
