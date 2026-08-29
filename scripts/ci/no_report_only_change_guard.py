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
    # Frontend/mobile application code IS code — the guard's own message invites
    # "code/test/guard" changes, but the first implementation only recognised
    # backend trees. A real UI fix (TSX/Dart) + regenerated release checksums was
    # wrongly blocked as "report-only" (measured on PR #857). Any runtime tree
    # added later needs a prefix here AND a regression test below.
    "frontend/",
    "mobile/",
    "scripts/ci/",
    "tests_v9/",
    # Architecture/guard tests live under tests/ (not tests_v9/). A test is exactly
    # the "test" category this guard's own message invites; without this prefix a PR
    # that adds real tests here + regenerates the bundle is wrongly blocked.
    "tests/",
    ".github/workflows/",
    "docs/runbooks/",
    "certification/evidence/",
    # runtime-verification/ holds functional probe PLANS and the identity-bridge map —
    # behavioural governance specs (what gets verified, how evidence propagates), not
    # reports. Changing them is substantive. (Live evidence under
    # runtime-verification/functional_evidence/ is gitignored and never committed.)
    "runtime-verification/",
    # SQL migrations are schema/data code — a migration-only fix (e.g. making a
    # DDL statement idempotent) is substantive, not a report. Without this, any
    # PR that only touches migrations/ + regenerates the release bundle would be
    # wrongly blocked as "report-only".
    "migrations/",
    # GATE-01 adjudications and policy are AUTHORIZATION INSTRUMENTS, not progress
    # reports: `gate01_frozen_path_guard` reads them to decide PASS/BLOCK on
    # physical-actuation code, so editing one changes what CI permits. This is the
    # same category as runtime-verification/ above — behavioural governance, not a
    # report — and the same reasoning the sahool-brain/ exemption already applies:
    # a MANDATED step must be landable without contriving an unrelated code change.
    #
    # Measured on #959: sealing a spent one-time grant `CONSUMED` after its merge is
    # a step the adjudication file itself calls "لازمة لا تحسينيّة", yet it touches
    # only that JSON + the brain + regenerated artifacts — so every seal was
    # report-only by classification and therefore unlandable. An unlandable mandated
    # step is how `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01` stays open forever.
    #
    # This does NOT weaken the control that matters: `branch_protection_contract_guard`
    # still demands code-owner review on this exact path, and it is a separate gate.
    "docs/architecture/gates/",
)
SUBSTANTIVE_EXACT = {"requirements.services.direct.lock", "REPORT_INDEX.md"}


def is_report_like(path: str) -> bool:
    p = Path(path)
    if p.suffix not in REPORT_SUFFIXES:
        return False
    # The sahool-brain/ knowledge base is mandated documentation (CLAUDE.md contributor
    # protocol, strict per-fact sourcing), NOT a certification/progress report — even when
    # a file name matches a report hint (e.g. the brain's own gaps/registry.md). Treating
    # it as docs lets the required end-of-session brain maintenance land without contriving
    # an unrelated code change; the guard still blocks the capabilities/ certification
    # registry and generated release reports.
    if path.startswith("sahool-brain/"):
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
