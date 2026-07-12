#!/usr/bin/env python3
"""Production truth/readiness gate: no synthetic serving paths; honest readiness."""

from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    "vegetation synthetic generator removed": "def _generate_timeseries"
    not in (root / "services/vegetation-analysis-service/vegetation_runtime.py").read_text(),
    "vegetation current NDVI authoritative": "_current_ndvi_from_raster"
    in (root / "services/vegetation-analysis-service/routers/analysis.py").read_text(),
    "vegetation readiness raster-aware": "authoritative-raster-only"
    in (root / "services/vegetation-analysis-service/routers/health.py").read_text(),
    "agriai readiness pcse-aware": "required_missing"
    in (root / "services/agriai-engine/main.py").read_text(),
    "runtime work docs mention leases": "durable leases"
    in (root / "services/decision-service/main.py").read_text(),
}
failed = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(("PASS" if v else "FAIL"), k)
raise SystemExit(1 if failed else 0)
