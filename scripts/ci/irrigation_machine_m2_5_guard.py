#!/usr/bin/env python3
"""M2.5 end-state guard: persisted machine capability remains; dead platform compute does not."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
migration = ROOT / "migrations/v172_irrigation_machine_capability.sql"
text = migration.read_text(encoding="utf-8")
for token in ("canonical_irrigation_machine_capabilities", "irrigation_machine_spans", "FORCE ROW LEVEL SECURITY"):
    assert token in text, ("migrations/v172_irrigation_machine_capability.sql", token)

legacy = ROOT / "services/sahool-platform/api/canonical_irrigation_machine_capability.py"
assert not legacy.exists(), "retired duplicate machine capability compute returned"
print("irrigation machine M2.5 guard: PASS (persisted capability retained; dead compute retired)")
