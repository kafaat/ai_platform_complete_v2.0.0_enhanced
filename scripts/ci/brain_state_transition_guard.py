#!/usr/bin/env python3
"""Prevent sahool-brain-only edits from claiming executable/certification closure."""

from __future__ import annotations

import argparse
import re
import subprocess

CLOSED_RE = re.compile(
    r"^\+[^+].*\b(CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)\b", re.I
)
SUBSTANTIVE = (
    "services/",
    "scripts/ci/",
    "tests/",
    "tests_v9/",
    ".github/workflows/",
    "migrations/",
    "runtime-verification/",
    "certification/evidence/",
)


def check(paths: list[str], diff: str) -> None:
    claims = [line for line in diff.splitlines() if CLOSED_RE.search(line)]
    brain_changed = any(p.startswith("sahool-brain/") for p in paths)
    outside = [
        p
        for p in paths
        if any(p.startswith(x) for x in SUBSTANTIVE) and not p.startswith("sahool-brain/")
    ]
    if brain_changed and claims and not outside:
        raise SystemExit(
            "sahool-brain-only closure/verification transition rejected; include executable code/test/evidence outside the brain knowledge base"
        )
    print("brain_state_transition_guard_ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    a = p.parse_args()
    names = subprocess.run(
        ["git", "diff", "--name-only", f"{a.base}...{a.head}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{a.base}...{a.head}", "--", "sahool-brain/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    check(names, diff)


if __name__ == "__main__":
    main()
