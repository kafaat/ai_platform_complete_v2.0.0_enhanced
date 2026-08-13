#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[2]
backend = (root / "services/sahool-platform/api/irrigation_manual_execution.py").read_text(
    encoding="utf-8"
)
api = (root / "frontend/src/services/api/irrigationManualOperations.ts").read_text(encoding="utf-8")
ui = (root / "frontend/src/sections/IrrigationManualOperationsPanel.tsx").read_text(
    encoding="utf-8"
)
tests = (root / "tests_v9/test_irrx1_2_manual_execution_lifecycle.py").read_text(encoding="utf-8")

required = {
    "backend field": "manual_volume_m3: float | None",
    "operator quality": 'quality = "operator_declared"',
    "ledger blocker": "OPERATOR_DECLARED_VOLUME_REQUIRES_INDEPENDENT_MEASUREMENT",
    "frontend API": "manual_volume_m3?: number",
    "frontend form": "manual_volume_m3: form.manual_volume_m3",
    "UI input": "'manual_volume_m3'",
    "test coverage": "test_operator_declared_volume_is_accepted_but_not_ledger_eligible",
}
joined = "\n".join([backend, api, ui, tests])
missing = [name for name, needle in required.items() if needle not in joined]
if missing:
    raise SystemExit("IRR-X1.6 guard failed: " + ", ".join(missing))
print("IRR-X1.6 manual declared volume guard: PASS")
