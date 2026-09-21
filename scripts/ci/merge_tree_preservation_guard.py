#!/usr/bin/env python3
"""Prevent a merge/squash candidate from erasing already-recorded evidence identities.

This guard compares the *candidate tree* (normally pull_request HEAD, i.e. GitHub's
synthetic merge tree) with the current base ref. It intentionally does not reason
only about the branch's commit history: #1061 showed that a history can look valid
while the tree that would enter main silently drops operational evidence.

The operational evidence log is append-only in substance: it may grow, but it may
not shrink and every existing E-YYYY-MM-DD-NN identity must survive. The gap
registry is stateful, so byte-prefix preservation would be wrong; only identities
already present in the base are required to survive.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = "docs/evidence/operational_evidence_log.md"
REGISTRY_PATH = "sahool-brain/gaps/registry.md"
EVIDENCE_ID = re.compile(r"(?m)^###\\s+(E-\\d{4}-\\d{2}-\\d{2}-\\d{2})\\b")


def _load_gap_parser():
    path = ROOT / "scripts/ci/gap_registry_measure.py"
    spec = importlib.util.spec_from_file_location("gap_registry_measure", path)
    if not spec or not spec.loader:
        raise RuntimeError("canonical gap parser unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GAP = _load_gap_parser()


def gap_identities(text: str) -> set[str]:
    """Use the canonical registry grammar, not an independent generic ID regex."""
    found: set[str] = set()
    fence: str | None = None
    for line in text.splitlines():
        fm = GAP.FENCE.match(line)
        if fence is not None:
            if fm and fm.group("marker")[0] == fence[0] and len(fm.group("marker")) >= len(fence) and not fm.group("tail").strip():
                fence = None
            continue
        if fm:
            fence = fm.group("marker")
            continue
        hm = GAP.HEADING.match(line)
        if hm:
            found.add(hm.group("id"))
            continue
        dm = GAP.DEEP_HEADING.match(line)
        if dm:
            found.add(dm.group("id"))
            continue
        if line.startswith("|"):
            cells = GAP.table_cells(line)
            if cells:
                lm = GAP.LABEL.fullmatch(cells[0])
                if lm:
                    found.add(lm.group("id"))
    return found


def judge(base_evidence: str, candidate_evidence: str, base_registry: str, candidate_registry: str) -> list[str]:
    problems: list[str] = []
    if len(candidate_evidence.encode("utf-8")) < len(base_evidence.encode("utf-8")):
        problems.append(
            f"EVIDENCE_LOG_SHRANK:{len(base_evidence.encode('utf-8'))}->{len(candidate_evidence.encode('utf-8'))}"
        )
    missing_e = sorted(set(EVIDENCE_ID.findall(base_evidence)) - set(EVIDENCE_ID.findall(candidate_evidence)))
    if missing_e:
        problems.append("MISSING_EVIDENCE_IDS:" + ",".join(missing_e))
    missing_g = sorted(gap_identities(base_registry) - gap_identities(candidate_registry))
    if missing_g:
        problems.append("MISSING_GAP_IDS:" + ",".join(missing_g))
    return problems


def _git_text(ref: str, path: str) -> str:
    cp = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True, capture_output=True)
    if cp.returncode:
        raise SystemExit(f"merge-tree preservation: cannot read {ref}:{path}: {cp.stderr.strip()}")
    return cp.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args(argv)
    problems = judge(
        _git_text(args.base, EVIDENCE_PATH),
        _git_text(args.head, EVIDENCE_PATH),
        _git_text(args.base, REGISTRY_PATH),
        _git_text(args.head, REGISTRY_PATH),
    )
    if problems:
        print("merge_tree_preservation_guard: FAIL", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("merge_tree_preservation_guard: OK — base evidence/gap identities survive candidate tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
