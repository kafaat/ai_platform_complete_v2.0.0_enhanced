#!/usr/bin/env python3
"""Full-plan closure gate for the Vegetation + AgriAI increment.

Asserts the delivered closure surface stays present on the landed shape:
the canonical indicator registry, the governed agronomic adapters + PIT
field-history composer, the production-safe legacy-field-registry default,
the AGRIAI_PRODUCTION_MODE fail-closed simulation guard, and the AC-1
context store (the delivered bundle's duplicate `018_agronomic_context_
snapshots.sql` was reconciled into the already-landed
`018_ac1_agronomic_context.sql` — see docs/audits/VEGETATION_AGRIAI_FULL_
PLAN_CLOSURE_20260712.md).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

required = [
    "services/vegetation-analysis-service/indicator_registry.py",
    "services/agriai-engine/agronomic_adapters.py",
    "services/agriai-engine/field_history.py",
    "services/decision-service/migrations/018_ac1_agronomic_context.sql",
]
missing = [p for p in required if not (ROOT / p).exists()]
assert not missing, missing

rt = (ROOT / "services/vegetation-analysis-service/vegetation_runtime.py").read_text()
assert 'default=os.getenv("SAHOOL_ENV", "development").lower() != "production"' in rt, (
    "legacy field registry must default OFF in production"
)

wo = (ROOT / "services/agriai-engine/wofost_adapter.py").read_text()
assert "agriai_production_simulation_unavailable" in wo, (
    "production mode must fail closed when PCSE/inputs are unavailable"
)

ac = (ROOT / "services/agriai-engine/agronomic_context.py").read_text()
assert "import agronomic_adapters as adapters" in ac, (
    "context normalization must go through the governed adapters"
)

print("vegetation/agriai full closure gate: PASS")
