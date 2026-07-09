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
    "release/DEPLOYMENT_READINESS_CHECKLIST.md",
    "RELEASE_NOTES_20260626.md",
    "scripts/release/build_release_bundle.py",
    "scripts/release/validate_release_package.py",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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

    checksum_file = root / "release/FILE_CHECKSUMS.sha256"
    checked = 0
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
    if checked <= 0:
        print("no checksum rows validated")
        return 1
    print(f"release package validation passed: {checked} checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
