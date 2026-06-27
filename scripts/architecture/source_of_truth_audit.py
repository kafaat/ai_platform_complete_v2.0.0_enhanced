#!/usr/bin/env python3
"""Audit runtime code for digital-twin truth-source drift.

CanonicalFieldState must remain the authoritative source. FieldTwin/CropTwin/
WaterTwin/DigitalTwin/phase snapshots/feature projections may exist only as
projections, caches, or derived views unless explicitly quarantined.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

RUNTIME_DIRS = ("services", "shared")
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git", "venv", ".venv", "tests", "docs"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sql", ".md"}
TWIN_RE = re.compile(r"\b(FieldTwin|CropTwin|WaterTwin|DigitalTwin|phase snapshot|phase_snapshot|Feature Store projection|feature projection)\b", re.I)
CANON_RE = re.compile(r"CanonicalFieldState|canonical_field_state|compose_field_state|field_state", re.I)
DERIVED_RE = re.compile(r"derived|projection|cache|snapshot|materiali[sz]ed|read[-_ ]model|view|مشتق", re.I)
FORBIDDEN_RE = re.compile(r"source[-_ ]of[-_ ]truth|authoritative|canonical\s*=\s*False|independent truth|truth source", re.I)
QUARANTINE_TOKENS = ("SOURCE_OF_TRUTH_OK", "DERIVED_VIEW", "PROJECTION_ONLY", "DOC_ONLY", "TEST_ONLY")

@dataclass
class Finding:
    path: str
    line: int
    code: str
    text: str


def iter_files(root: Path):
    for base in RUNTIME_DIRS:
        base_path = root / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES and not any(part in SKIP_DIRS for part in path.parts):
                yield path


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        file_text = "\n".join(lines)
        has_canonical = bool(CANON_RE.search(file_text))
        for idx, line in enumerate(lines, start=1):
            if any(token in line for token in QUARANTINE_TOKENS):
                continue
            if not TWIN_RE.search(line):
                continue
            window = "\n".join(lines[max(0, idx-6): min(len(lines), idx+5)])
            if FORBIDDEN_RE.search(line) and not DERIVED_RE.search(window):
                findings.append(Finding(str(path.relative_to(root)), idx, "independent_truth_claim", line.strip()[:240]))
            elif not (has_canonical or CANON_RE.search(window) or DERIVED_RE.search(window)):
                findings.append(Finding(str(path.relative_to(root)), idx, "unlinked_twin_projection", line.strip()[:240]))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    findings = audit(Path(args.root).resolve())
    payload = {"finding_count": len(findings), "findings": [asdict(f) for f in findings]}
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"source_of_truth_audit: findings={len(findings)}")
        for f in findings[:100]:
            print(f"{f.path}:{f.line}: {f.code}: {f.text}")
    return 1 if args.strict and findings else 0

if __name__ == "__main__":
    raise SystemExit(main())
