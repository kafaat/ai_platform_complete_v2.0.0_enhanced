#!/usr/bin/env python3
"""Activate a compose stack and collect fail-closed runtime evidence for PATH-3."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
TARGETS = ROOT / "runtime-verification/generated/compose_runtime_targets.json"
TARGET_ENV = ROOT / "runtime-verification/generated/compose_runtime_targets.env"
RESOLVER = ROOT / "scripts/ci/compose_runtime_target_resolver.py"
OVERLAY = ROOT / "docker-compose.runtime-verification.yml"


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT, check=False, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", action="append", dest="compose_files")
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--image-manifest")
    parser.add_argument("--service", action="append", dest="services")
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--keep-stack", action="store_true")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Probe only compose-resolved services and retain unresolved services as explicit blockers.",
    )
    args = parser.parse_args()

    if not shutil.which("docker"):
        print("BLOCKED_ENVIRONMENT: docker CLI missing", file=sys.stderr)
        return 2
    if run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        print("BLOCKED_ENVIRONMENT: docker daemon unreachable", file=sys.stderr)
        return 2

    compose_files = args.compose_files or ["docker-compose.v9.yml"]
    composes = [ROOT / f for f in compose_files]
    for compose in composes:
        if not compose.exists():
            print(f"compose file missing: {compose}", file=sys.stderr)
            return 2
    compose = composes[0]
    if not OVERLAY.exists():
        print(f"runtime verification overlay missing: {OVERLAY}", file=sys.stderr)
        return 2

    resolver_cmd = [sys.executable, str(RESOLVER), "--compose-file", str(compose), "--generate"]
    if run(resolver_cmd).returncode:
        return 1

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
    target_by_service = {row["service"]: row for row in targets}
    planned = {row["service"] for row in plan["services"] if row.get("probes")}
    selected = set(args.services or planned)
    unknown = sorted(selected - planned)
    if unknown:
        print("Unknown or non-probe services: " + ", ".join(unknown), file=sys.stderr)
        return 2

    unresolved = sorted(
        service for service in selected if not target_by_service.get(service, {}).get("resolved")
    )
    if unresolved and not args.allow_partial:
        print("PATH-3 target resolution blockers: " + ", ".join(unresolved), file=sys.stderr)
        print("Use --allow-partial only for explicitly partial runtime evidence.", file=sys.stderr)
        return 2
    selected -= set(unresolved)
    if not selected:
        print("No resolved services selected for probing", file=sys.stderr)
        return 2

    required_profiles = sorted(
        {
            profile
            for service in selected
            for profile in target_by_service.get(service, {}).get("profiles", [])
        }
    )
    compose_args = ["docker", "compose"]
    for item in composes:
        compose_args += ["-f", str(item)]
    compose_args += ["-f", str(OVERLAY)]
    profile_args = [arg for profile in required_profiles for arg in ("--profile", profile)]
    try:
        if run(compose_args + profile_args + ["config"]).returncode:
            return 1
        if run(
            compose_args
            + profile_args
            + ["up", "-d", "--wait", "--wait-timeout", str(args.startup_timeout)]
        ).returncode:
            return 1

        batch = (
            compose_args
            + profile_args
            + [
                "--profile",
                "runtime-verification",
                "run",
                "--rm",
                "--env-file",
                str(TARGET_ENV),
                "-e",
                f"TESTED_SHA={os.getenv('TESTED_SHA', '')}",
                "runtime-verifier",
                "--environment-id",
                args.environment_id,
            ]
        )
        for service in sorted(selected):
            batch.extend(["--service", service])
        probe_rc = run(batch).returncode

        # Runtime Evidence Trust Hardening: bind functional receipts to the exact
        # running image IDs and immutable OCI labels before executing live probes.
        manifest_cmd = [
            sys.executable,
            "scripts/ci/runtime_deployment_manifest.py",
            "--tested-sha",
            os.getenv("TESTED_SHA", ""),
        ]
        for item in composes:
            manifest_cmd += ["--compose-file", str(item)]
        manifest_cmd += ["--compose-file", str(OVERLAY)]
        if args.image_manifest:
            manifest_cmd += ["--image-manifest", args.image_manifest]
        manifest_rc = run(manifest_cmd).returncode
        functional_rc = 0
        functional_targets = {
            "weather-service": "http://sahool-weather-service:8000",
            "soil-service": "http://sahool-soil-service:8000",
            "sahool-platform": "http://sahool-platform:8000",
        }
        if manifest_rc == 0:
            for service, base_url in functional_targets.items():
                cmd = (
                    compose_args
                    + profile_args
                    + [
                        "--profile",
                        "runtime-verification",
                        "run",
                        "--rm",
                        "-e",
                        "SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY",
                        "-e",
                        "GITHUB_RUN_ID",
                        "-e",
                        "SAHOOL_AGENT_TOKEN",
                        "-e",
                        "SAHOOL_PLATFORM_PROBE_JWT",
                        "functional-runtime-verifier",
                        "--run",
                        "--service",
                        service,
                        "--base-url",
                        base_url,
                        "--environment-id",
                        args.environment_id,
                        "--tested-sha",
                        os.getenv("TESTED_SHA", ""),
                        "--deployment-manifest",
                        "/workspace/runtime-verification/generated/functional_deployment_manifest.json",
                    ]
                )
                functional_rc |= run(cmd).returncode
        else:
            functional_rc = 1

        ingestion_rc = run(
            [sys.executable, "scripts/ci/runtime_evidence_ingestion.py", "--generate"]
        ).returncode
        certification_rc = run(
            [sys.executable, "scripts/ci/runtime_certification_gate.py", "--generate"]
        ).returncode
        if unresolved:
            print("Partial PATH-3 blockers retained: " + ", ".join(unresolved), file=sys.stderr)
        return (
            1 if probe_rc or manifest_rc or functional_rc or ingestion_rc or certification_rc else 0
        )
    finally:
        if not args.keep_stack:
            run(compose_args + ["down", "--remove-orphans"])


if __name__ == "__main__":
    raise SystemExit(main())
