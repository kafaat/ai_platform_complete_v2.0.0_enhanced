#!/usr/bin/env python3
"""Protect the fail-closed, full-history secret scanning workflow."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/secret-history-scan.yml"


def main() -> int:
    errors: list[str] = []
    text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""
    required = {
        "permissions:\n  contents: read": "least-privilege permissions",
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803": "immutable Node 24 checkout action",
        "fetch-depth: 0": "complete Git history",
        "gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e": "immutable Gitleaks action",
        'GITLEAKS_VERSION: "8.30.1"': "pinned scanner engine",
        'GITLEAKS_ENABLE_COMMENTS: "false"': "no pull-request write requirement",
        "schedule:": "periodic rescan",
    }
    if not text:
        errors.append(f"missing workflow: {WORKFLOW.relative_to(ROOT)}")
    for token, purpose in required.items():
        if token not in text:
            errors.append(f"missing {purpose}: {token}")
    for token in ("continue-on-error: true", "permissions: write-all", "pull_request_target:"):
        if token in text:
            errors.append(f"unsafe secret-scan workflow token: {token}")
    if errors:
        print("secret history scan guard: FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("secret history scan guard: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
