#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[2]
required = [
    "services/sahool-platform/api/irrigation_commissioning_runtime.py",
    "services/sahool-platform/api/routers/irrigation_engineering.py",
    "services/sahool-platform/tests/test_irrigation_commissioning_runtime.py",
    "migrations/v186_irrx1_digital_commissioning_runtime.sql",
]
for rel in required:
    if not (root / rel).is_file():
        raise SystemExit(f"IRR-X1.1 guard: missing {rel}")
text = (root / required[0]).read_text(encoding="utf-8")
for token in [
    "No valid commissioning certificate" if False else "VALID_COMMISSIONING_CERTIFICATE_REQUIRED",
    "authorize_execution",
    "CommissioningState",
    "manual_execution_allowed",
    "ADAPTER_NOT_CAPABLE",
    "TELEMETRY_STALE",
]:
    if token not in text:
        raise SystemExit(f"IRR-X1.1 guard: missing invariant {token}")
router = (root / required[1]).read_text(encoding="utf-8")
for route in [
    "/commissioning/certificates",
    "/commissioning/systems/{system_id}/current",
    "/commissioning/authorize",
]:
    if route not in router:
        raise SystemExit(f"IRR-X1.1 guard: missing route {route}")
sql = (root / required[3]).read_text(encoding="utf-8")
for token in [
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "certificate_digest",
    "authorization_digest",
]:
    if token not in sql:
        raise SystemExit(f"IRR-X1.1 guard: SQL missing {token}")
print("IRR-X1.1 digital commissioning runtime guard: PASS")
