#!/usr/bin/env python3
"""Artifact-based closure gate for Path 1 static governance.

Each expensive scanner runs as its own CI step. This final gate validates the
committed outputs and formal closure invariants without rescanning the tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "governance" / "generated"
SUMMARY_PATH = OUT_DIR / "STATIC_GOVERNANCE_CLOSURE.json"
REPORT_PATH = OUT_DIR / "STATIC_GOVERNANCE_CLOSURE.md"
MANIFEST_PATH = OUT_DIR / "STATIC_GOVERNANCE_ARTIFACTS.sha256"

ARTIFACT_ROOTS = [
    ROOT / "capabilities/generated",
    ROOT / "architecture/generated",
    ROOT / "runtime-contracts/generated",
    ROOT / "decision-lineage/generated",
    ROOT / "execution-audit/generated",
]

REQUIRED = {
    "capability": ROOT / "capabilities/generated/capability_summary.json",
    "traceability": ROOT / "capabilities/generated/capability_traceability_summary.json",
    "certification": ROOT / "capabilities/generated/capability_certification_summary.json",
    "runtime_evidence": ROOT / "capabilities/generated/capability_runtime_evidence_summary.json",
    "architecture": ROOT / "architecture/generated/architecture_graph.json",
    "runtime_contracts": ROOT / "runtime-contracts/generated/runtime_contracts_summary.json",
    "lineage": ROOT / "decision-lineage/generated/decision_lineage_summary.json",
    "execution": ROOT / "execution-audit/generated/execution_audit_summary.json",
    "duplicates": ROOT / "execution-audit/generated/duplicate_definitions.json",
    "routes": ROOT / "execution-audit/generated/route_conflicts.json",
    "reachability": ROOT / "execution-audit/generated/router_reachability.json",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _manifest_files() -> set[str]:
    """Return the signed release-manifest paths as an offline allowlist.

    Extracted release archives do not contain ``.git``.  In that environment we
    must not fall back to scanning the raw filesystem, because editor caches,
    partial generated files, or other untracked content would make the closure
    manifest non-reproducible.  The release checksum manifest is the only
    accepted offline source of repository membership.
    """
    manifest = ROOT / "release" / "FILE_CHECKSUMS.sha256"
    if not manifest.exists():
        return set()

    paths: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1]:
            paths.add(parts[1])
    return paths


def _tracked_files() -> set[str]:
    """Return repository paths without ever scanning arbitrary untracked files.

    A git worktree is authoritative in CI and development.  For an extracted,
    signed release archive, use ``release/FILE_CHECKSUMS.sha256`` as a fail-closed
    allowlist.  If neither source is available, abort instead of silently
    widening the artifact set.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        tracked = {rel for rel in out.split("\0") if rel}
        if tracked:
            return tracked
    except (OSError, subprocess.CalledProcessError):
        pass

    manifest_files = _manifest_files()
    if manifest_files:
        return manifest_files
    raise RuntimeError(
        "no git worktree and no signed release manifest "
        "(release/FILE_CHECKSUMS.sha256); refusing to scan the raw filesystem "
        "(fail-closed)"
    )


def artifact_files() -> list[Path]:
    tracked = _tracked_files()
    files: list[Path] = []
    for root in ARTIFACT_ROOTS:
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.relative_to(ROOT).as_posix() in tracked
            )
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def manifest_text() -> str:
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}\n"
        for path in artifact_files()
    )


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def evaluate() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = {name: load_json(path) for name, path in REQUIRED.items()}
    checks = [
        check(f"artifact:{name}", bool(payload), path.relative_to(ROOT).as_posix())
        for (name, path), payload in zip(REQUIRED.items(), data.values(), strict=True)
    ]
    if not all(item["passed"] for item in checks):
        return checks, data

    arch = data["architecture"]
    lineage = data["lineage"]
    duplicate = data["duplicates"]
    routes = data["routes"]
    reach = data["reachability"]
    runtime = data["runtime_contracts"]
    execution = data["execution"]
    certification = data["certification"]

    checks.extend(
        [
            check(
                "architecture:no_cycles",
                len(arch.get("cycles", [])) == 0,
                f"cycles={len(arch.get('cycles', []))}",
            ),
            check(
                "lineage:complete_static_chain",
                lineage.get("complete_static_chain") is True,
                f"complete={lineage.get('complete_static_chain')}",
            ),
            check(
                "lineage:no_runtime_claim",
                lineage.get("runtime_verified") is False
                and lineage.get("production_certified") is False,
                "runtime=false, production=false",
            ),
            check(
                "runtime_contracts:no_live_claim",
                runtime.get("live_runtime_verified") in (0, False),
                f"live={runtime.get('live_runtime_verified')}",
            ),
            check(
                "execution:no_automatic_deletion",
                execution.get("automatic_deletions", 0) == 0,
                f"automatic_deletions={execution.get('automatic_deletions')}",
            ),
            check(
                "definitions:no_duplicates",
                duplicate.get("finding_count") == 0,
                f"findings={duplicate.get('finding_count')}",
            ),
            check(
                "routes:no_hard_conflicts",
                routes.get("hard_conflict_count") == 0,
                f"hard_conflicts={routes.get('hard_conflict_count')}",
            ),
            check(
                "reachability:no_automatic_deletion",
                reach.get("safe_automatic_deletions", []) in ([], 0, None),
                "review-only candidates",
            ),
            check(
                "certification:no_production_claim",
                certification.get(
                    "production_certified_capabilities",
                    certification.get("production_certified", 0),
                )
                in (0, False, None, []),
                "production certification remains zero",
            ),
        ]
    )
    return checks, data


def closure_payload(
    checks: list[dict[str, Any]],
    tests: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tests_passed = True if tests is None else bool(tests.get("passed"))
    all_passed = all(item.get("passed", False) for item in checks) and tests_passed
    payload = {
        "schema_version": "1.1.0",
        "scope": "path-1-static-architecture-governance",
        "status": "CLOSED" if all_passed else "OPEN",
        "static_governance_verified": all_passed,
        "runtime_verified": False,
        "production_certified": False,
        "checks": checks,
        "tracked_non_blocking_remainders": [
            "static orphan-service candidates",
            "cross-scope route review candidates",
            "routers not provably reachable through static resolution",
            "capabilities without full UI/mobile/runtime traceability",
        ],
        "boundary": "Repository-static evidence only; live stack, telemetry, database, queue, and production execution belong to a separate path.",
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# SAHOOL PATH-1 Closure — Static Architecture Governance",
        "",
        f"**Final status: `{payload['status']}`**",
        "",
        "## Closure gates",
        "",
        "| Gate | Result | Detail |",
        "|---|---|---|",
    ]
    for item in payload["checks"]:
        lines.append(
            f"| `{item['name']}` | **{'PASS' if item['passed'] else 'FAIL'}** | {str(item['detail']).replace('|', '/')} |"
        )
    lines.extend(
        [
            "",
            "## Formal boundary",
            "",
            payload["boundary"],
            "",
            "## Tracked non-blocking remainders",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["tracked_non_blocking_remainders"])
    lines.extend(["", f"Content SHA-256: `{payload['content_sha256']}`", ""])
    return "\n".join(lines)


def write_closure(payload: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8")
    MANIFEST_PATH.write_text(manifest_text(), encoding="utf-8")


def validate_closure(payload: dict[str, Any]) -> bool:
    return (
        SUMMARY_PATH.exists()
        and SUMMARY_PATH.read_text(encoding="utf-8")
        == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        and REPORT_PATH.exists()
        and REPORT_PATH.read_text(encoding="utf-8") == render_report(payload)
        and MANIFEST_PATH.exists()
        and MANIFEST_PATH.read_text(encoding="utf-8") == manifest_text()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    checks, _ = evaluate()
    payload = closure_payload(checks)
    if args.generate:
        write_closure(payload)
    elif not validate_closure(payload):
        print("FAIL: static governance closure drift; run --generate")
        # Name the exact drifted artifact so a CI-only drift is diagnosable rather
        # than opaque (mirrors the capability-mapping drift diagnostic).
        expected_summary = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if (
            not SUMMARY_PATH.exists()
            or SUMMARY_PATH.read_text(encoding="utf-8") != expected_summary
        ):
            print(" - drift: STATIC_GOVERNANCE_CLOSURE.json (payload/content_sha256)")
        if not REPORT_PATH.exists() or REPORT_PATH.read_text(encoding="utf-8") != render_report(
            payload
        ):
            print(" - drift: STATIC_GOVERNANCE_CLOSURE.md")
        fresh_manifest = manifest_text()
        if (
            not MANIFEST_PATH.exists()
            or MANIFEST_PATH.read_text(encoding="utf-8") != fresh_manifest
        ):
            committed_lines = (
                MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
                if MANIFEST_PATH.exists()
                else []
            )
            fresh_lines = fresh_manifest.splitlines()
            committed_set = set(committed_lines)
            fresh_set = set(fresh_lines)
            only_committed = sorted(x.split("  ", 1)[-1] for x in committed_set - fresh_set)
            only_fresh = sorted(x.split("  ", 1)[-1] for x in fresh_set - committed_set)
            print(
                " - drift: STATIC_GOVERNANCE_ARTIFACTS.sha256"
                f" only-committed={only_committed[:8]} only-fresh={only_fresh[:8]}"
            )
        return 1
    print(
        f"PATH-1 {payload['status']}: {sum(item['passed'] for item in checks)}/{len(checks)} closure checks passed"
    )
    return 0 if payload["status"] == "CLOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
