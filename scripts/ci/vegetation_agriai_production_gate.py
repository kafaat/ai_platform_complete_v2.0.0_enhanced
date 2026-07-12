#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "vegetation v2 contract": (
        ROOT / "services/vegetation-analysis-service/vegetation_contracts.py",
        "vegetation-snapshot.v2",
    ),
    # the authority check moved to the canonical registry (validate_observation);
    # the gate asserts the contracts module delegates to it.
    "full provenance gate": (
        ROOT / "services/vegetation-analysis-service/vegetation_contracts.py",
        "validate_observation",
    ),
    # RIV consolidation (20260712) made raw-band suppression unconditional: the
    # strict raster-consumer never returns raw bands at all (stronger than the old
    # `None if VEGETATION_REAL_ONLY else bands`). Assert the absolute form.
    "real-only raw-band suppression": (
        ROOT / "services/vegetation-analysis-service/vegetation_runtime.py",
        '"raw_bands": None',
    ),
    "agronomic v2 contract": (
        ROOT / "services/agriai-engine/agronomic_context.py",
        "agronomic-context.v2",
    ),
    "feature manifest required": (
        ROOT / "services/agriai-engine/agronomic_context.py",
        "feature_manifest",
    ),
    "future-data guard": (ROOT / "services/agriai-engine/agronomic_context.py", "future_data"),
}
failed = []
for name, (path, needle) in checks.items():
    if not path.exists() or needle not in path.read_text():
        failed.append(name)
if failed:
    raise SystemExit("FAIL: " + ", ".join(failed))
print("vegetation/agriai production gate: PASS")
