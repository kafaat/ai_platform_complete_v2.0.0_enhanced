#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "vegetation v2 contract": (
        ROOT / "services/vegetation-analysis-service/vegetation_contracts.py",
        "vegetation-snapshot.v2",
    ),
    "full provenance gate": (
        ROOT / "services/vegetation-analysis-service/vegetation_contracts.py",
        "provenance_{key}_missing",
    ),
    "real-only raw-band suppression": (
        ROOT / "services/vegetation-analysis-service/vegetation_runtime.py",
        "None if VEGETATION_REAL_ONLY else bands",
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
