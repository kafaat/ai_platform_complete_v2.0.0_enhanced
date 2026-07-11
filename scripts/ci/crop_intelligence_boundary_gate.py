#!/usr/bin/env python3
"""Keep Crop Intelligence as an interpretation layer, not a weather calculator."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "services/sahool-platform/core/crop_intelligence"
FORBIDDEN = (
    "0.6108 *",
    "penman",
    "hargreaves",
    "def gdd_day",
    "def compute_et0",
    "def compute_vpd",
)

violations = []
for path in PKG.rglob("*.py"):
    text = path.read_text(encoding="utf-8").lower()
    for token in FORBIDDEN:
        if token.lower() in text:
            violations.append(f"{path.relative_to(ROOT)}: forbidden weather kernel token {token!r}")

if violations:
    print("crop_intelligence_boundary_gate_failed")
    print("\n".join(violations))
    sys.exit(1)
print("crop_intelligence_boundary_gate_ok")
