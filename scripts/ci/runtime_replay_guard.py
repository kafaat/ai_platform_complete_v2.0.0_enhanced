#!/usr/bin/env python3
"""Fail closed when an attested evidence bundle was already consumed."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HEX = re.compile(r"^[0-9a-f]{64}$")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle-sha256", required=True)
    p.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    a = p.parse_args()
    if not HEX.fullmatch(a.bundle_sha256):
        print("invalid bundle digest", file=sys.stderr)
        return 2
    if not a.repository:
        print("repository required", file=sys.stderr)
        return 2
    name = "path3-consumed-" + a.bundle_sha256
    cp = subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "GET",
            f"repos/{a.repository}/actions/artifacts",
            "-f",
            f"name={name}",
            "-f",
            "per_page=100",
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode:
        print("replay ledger query failed: " + cp.stderr, file=sys.stderr)
        return 2
    try:
        rows = json.loads(cp.stdout).get("artifacts", [])
    except Exception:
        print("replay ledger response invalid", file=sys.stderr)
        return 2
    if any(not x.get("expired", False) for x in rows):
        print(f"replay_detected:{name}", file=sys.stderr)
        return 1
    print(f"replay_guard_clear marker={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
