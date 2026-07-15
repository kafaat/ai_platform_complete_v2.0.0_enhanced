#!/usr/bin/env python3
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
required = [
    root / "services/sahool-platform/api/irrigation_engineering_workspace.py",
    root / "services/sahool-platform/api/routers/irrigation_engineering.py",
    root / "migrations/v185_vendor_neutral_irrigation_engineering_workspace.sql",
    root / "services/sahool-platform/tests/test_irrigation_engineering_workspace.py",
]
missing = [str(p.relative_to(root)) for p in required if not p.exists()]
if missing:
    print("IRR-X1 guard failed; missing:", *missing, sep="\n- ")
    sys.exit(1)
text = required[0].read_text()
for token in (
    "IrrigationSystemSpecification",
    "capability_graph",
    "manual_operation",
    "manufacturer",
):
    if token not in text:
        print(f"IRR-X1 guard failed; token missing: {token}")
        sys.exit(1)
if "Valley" in text or "Zimmatic" in text:
    print("IRR-X1 guard failed; vendor-specific domain coupling detected")
    sys.exit(1)
print("IRR-X1 vendor-neutral irrigation engineering guard: PASS")
