#!/usr/bin/env python3
"""Validate Sahool release packaging assets and checksum integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_RELEASE_ASSETS = [
    "VERSION",
    "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
    "release/FILE_CHECKSUMS.sha256",
    "release/SBOM_MINIMAL.json",
    "release/SBOM_DEPENDENCIES.cdx.json",
    "release/DEPLOYMENT_READINESS_CHECKLIST.md",
    "RELEASE_NOTES_20260626.md",
    "scripts/release/build_release_bundle.py",
    "scripts/release/validate_release_package.py",
    "scripts/release/platform_route_release_binding.py",
    "release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json",
    "docs/architecture/generated/platform_route_governance_attestation.json",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def totals_problem(manifest: dict, count: int, size: int) -> str | None:
    """The manifest's file_count and total_size_bytes must describe the checksummed files.

    Hashes alone left a stale total invisible: a merge that took main's manifest kept main's
    total_size_bytes while the checksums covered grown files, and this validator still passed,
    so verify_all_generated --fix (which rebuilds only when this fails) never rebuilt it
    (Devin on #1590: 108,839,607 recorded, 108,842,208 actual).
    """
    if int(manifest.get("file_count", -1)) != count:
        return f"manifest file_count {manifest.get('file_count')} != {count} checksummed files"
    if int(manifest.get("total_size_bytes", -1)) != size:
        return (
            f"manifest total_size_bytes {manifest.get('total_size_bytes')} != {size} bytes "
            "in the checksummed files"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    missing = [asset for asset in REQUIRED_RELEASE_ASSETS if not (root / asset).exists()]
    if missing:
        print("missing release assets:", ", ".join(missing))
        return 1

    manifest = json.loads(
        (root / "release/SAHOOL_RELEASE_MANIFEST_20260626.json").read_text(encoding="utf-8")
    )
    if manifest.get("missing_required_assets"):
        print("manifest reports missing required assets:", manifest["missing_required_assets"])
        return 1
    if int(manifest.get("file_count", 0)) <= 0:
        print("manifest file_count is empty")
        return 1

    # The source binding must exactly match the current generated route-governance state.
    import subprocess

    binding_check = subprocess.run(
        [
            "python3",
            str(root / "scripts/release/platform_route_release_binding.py"),
            "--check-source",
        ],
        cwd=root,
        check=False,
    )
    if binding_check.returncode != 0:
        print("platform route-governance source binding validation failed")
        return 1

    checksum_file = root / "release/FILE_CHECKSUMS.sha256"
    checked = 0
    total_size = 0
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        path = root / rel
        if not path.exists():
            print(f"checksum target missing: {rel}")
            return 1
        actual = sha256_file(path)
        if actual != expected:
            print(f"checksum mismatch: {rel}")
            return 1
        checked += 1
        total_size += path.stat().st_size
    if checked <= 0:
        print("no checksum rows validated")
        return 1
    problem = totals_problem(manifest, checked, total_size)
    if problem:
        print(problem)
        return 1
    print(f"release package validation passed: {checked} checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
