#!/usr/bin/env python3
"""Guard against report-only certification/progress changes in CI.

Usage in CI:
  git diff --name-only origin/main...HEAD | python scripts/ci/no_report_only_change_guard.py --stdin

Local static check only verifies the policy file itself. The guard allows docs-only
changes, but blocks changes that are exclusively generated reports/csv/json under
release-report patterns unless a code, test, guard, inventory, workflow, or runbook
change accompanies them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPORT_SUFFIXES = (".md", ".csv", ".json")
REPORT_NAME_HINTS = (
    "REPORT",
    "INVENTORY",
    "CHECKLIST",
    "SUMMARY",
    "MATRIX",
    "REGISTRY",
)
SUBSTANTIVE_PREFIXES = (
    "services/",
    "bots/",
    "scripts/ci/",
    "tests_v9/",
    ".github/workflows/",
    "docs/runbooks/",
    "certification/evidence/",
    # SQL migrations are schema/data code — a migration-only fix (e.g. making a
    # DDL statement idempotent) is substantive, not a report. Without this, any
    # PR that only touches migrations/ + regenerates the release bundle would be
    # wrongly blocked as "report-only".
    "migrations/",
)
SUBSTANTIVE_EXACT = {"requirements.services.direct.lock", "REPORT_INDEX.md"}


def is_report_like(path: str) -> bool:
    p = Path(path)
    if p.suffix not in REPORT_SUFFIXES:
        return False
    upper = p.name.upper()
    if any(hint in upper for hint in REPORT_NAME_HINTS):
        return True
    if path.startswith("certification/evidence/") or path.startswith("docs/runbooks/"):
        return False
    return p.suffix in {".csv", ".json"} and "generated" in p.name


def is_substantive(path: str) -> bool:
    if path in SUBSTANTIVE_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in SUBSTANTIVE_PREFIXES):
        return True
    return False


def check_changed_files(paths: list[str]) -> None:
    clean = [p.strip() for p in paths if p.strip()]
    if not clean:
        print("no_report_only_change_guard_no_changes")
        return
    substantive = [p for p in clean if is_substantive(p) and not is_report_like(p)]
    report_like = [p for p in clean if is_report_like(p)]
    if report_like and not substantive:
        raise SystemExit(
            "report-only change detected; include code/test/guard/workflow/runbook/evidence changes or mark as docs-only outside certification path"
        )
    print("no_report_only_change_guard_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdin", action="store_true", help="read changed paths from stdin")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    if args.stdin:
        paths = sys.stdin.read().splitlines()
    else:
        paths = args.paths
    check_changed_files(paths)


if __name__ == "__main__":
    main()
