#!/usr/bin/env python3
"""Prevent sahool-brain-only edits from claiming executable/certification closure."""

from __future__ import annotations

import argparse
import re
import subprocess

# BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01. `\b(CLOSED)\b` was wrong in both
# directions at once, and the two errors hid each other:
#
#   false positive — `fail-closed` and `open-closed` are DESIGN descriptions, not state
#     transitions, and the hyphen is a word boundary. The term appears 273 times in the
#     brain alone and in 477 files repo-wide, so any brain-only note explaining a
#     fail-closed rule was rejected with a message about "closure/verification
#     transition" -- a true block for a false reason, which is worse than no block,
#     because the message sends the reader to look for a claim that was never made.
#
#   false negative — `CLOSED_IN_CODE` and `CLOSED_IN_CODE_AND_PG_PROVEN` are THIS
#     repository's actual closure vocabulary, and `\b` fails on the trailing `_`, so the
#     real claims the guard exists to catch walked straight past it.
#
# The lookbehind rejects a preceding hyphen or word character (kills `fail-closed`), the
# optional `_UPPER` tail admits the real status tokens, and the trailing lookahead keeps
# `closedness` out. Verified against twelve cases, positive and negative, in
# tests_v9/test_brain_transition_guard_vocabulary.py.
CLOSED_RE = re.compile(
    r"^\+[^+].*(?<![\w-])(CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)"
    r"(?:_[A-Z][A-Z_]*)?(?![\w-])",
    re.I,
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
