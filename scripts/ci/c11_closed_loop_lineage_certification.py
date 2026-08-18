#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run(rel: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(ROOT / rel), *map(str, args)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, (p.stdout or "").strip()


def emit(stage: str, status: str, findings=(), **extra) -> int:
    out = {
        "schema": f"sahool.{stage.lower()}-certification/v2",
        "stage": stage,
        "status": status,
        "authority_changed": False,
        "findings": list(findings),
        **extra,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if status in {"PASS", "EVIDENCE_REQUIRED", "LIVE_EVIDENCE_VERIFIED"} else 1


def _git_head() -> tuple[int, str]:
    p = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, (p.stdout or "").strip().lower()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--subject-sha")
    args = ap.parse_args(argv)

    # CI contract mode is deliberately non-invasive even if DATABASE_URL happens to be present.
    if not args.live:
        return emit(
            "C11",
            "EVIDENCE_REQUIRED",
            ["explicit_live_execution_required"],
            live_execution=False,
        )

    if not os.getenv("DATABASE_URL", "").strip():
        return emit(
            "C11", "FAILED", ["DATABASE_URL_required_for_live_lineage"], live_execution=True
        )
    subject = (args.subject_sha or "").lower()
    if not _SHA_RE.fullmatch(subject):
        return emit("C11", "FAILED", ["full_40_char_subject_sha_required"], live_execution=True)
    rc, head = _git_head()
    if rc != 0:
        return emit(
            "C11",
            "FAILED",
            ["real_git_checkout_required_for_live_lineage"],
            subject_sha=subject,
            live_execution=True,
        )
    if head != subject:
        return emit(
            "C11",
            "FAILED",
            ["local_checkout_subject_sha_mismatch"],
            subject_sha=subject,
            local_subject_sha=head,
            live_execution=True,
        )

    rc, output = run("scripts/certification/certify_agronomic_lineage.py")
    return emit(
        "C11",
        "LIVE_EVIDENCE_VERIFIED" if rc == 0 else "FAILED",
        [] if rc == 0 else ["canonical_agronomic_lineage_certification_failed", output[-1000:]],
        subject_sha=subject,
        local_subject_sha=head,
        subject_match=True,
        live_execution=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
