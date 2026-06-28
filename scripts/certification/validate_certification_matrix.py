#!/usr/bin/env python3
"""Validate that Sahool certification matrix is honest and staged."""
from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED_COLUMNS = ["Static gates", "Contract tests", "Local runtime", "Staging runtime", "7-day soak", "14-day soak"]
REQUIRED_ROWS = [
    "Security / RLS roles",
    "Migrations manifest",
    "Observability assets",
    "Field / GIS / imagery path",
    "CanonicalFieldState truth path",
    "Runtime workers side effects",
    "Load / chaos / recovery",
    "Long soak certification",
]
FORBIDDEN_CLAIMS = ["Production Certified: PASS", "14-day soak | PASS"]


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for col in REQUIRED_COLUMNS:
        if col not in text:
            errors.append(f"missing column: {col}")
    for row in REQUIRED_ROWS:
        if row not in text:
            errors.append(f"missing row: {row}")
    for claim in FORBIDDEN_CLAIMS:
        if claim in text:
            errors.append(f"premature certification claim: {claim}")
    if "PENDING" not in text:
        errors.append("matrix must preserve PENDING states until live runtime proves them")
    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    args = p.parse_args()
    path = Path(args.root) / "PRODUCTION_CERTIFICATION_MATRIX.md"
    errors = validate(path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("certification matrix validation: passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
