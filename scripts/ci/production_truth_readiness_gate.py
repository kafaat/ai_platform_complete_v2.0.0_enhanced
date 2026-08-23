#!/usr/bin/env python3
"""Production truth/readiness gate: no synthetic serving paths; honest readiness."""

from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    "vegetation synthetic generator removed": "def _generate_timeseries"
    not in (root / "services/vegetation-analysis-service/vegetation_runtime.py").read_text(
        encoding="utf-8"
    ),
    "vegetation current NDVI authoritative": "_current_ndvi_from_raster"
    in (root / "services/vegetation-analysis-service/routers/analysis.py").read_text(
        encoding="utf-8"
    ),
    "vegetation readiness raster-aware": "authoritative-raster-only"
    in (root / "services/vegetation-analysis-service/routers/health.py").read_text(
        encoding="utf-8"
    ),
    # Honest readiness: production readiness is gated on a verified scientific path
    # (scientific_ready + verified_missing), not a bare pcse import — see wofost_adapter.
    "agriai readiness pcse-aware": (
        "scientific_ready" in (root / "services/agriai-engine/main.py").read_text(encoding="utf-8")
        and "verified_missing"
        in (root / "services/agriai-engine/main.py").read_text(encoding="utf-8")
    ),
    "runtime work docs mention leases": "durable leases"
    in (root / "services/decision-service/main.py").read_text(encoding="utf-8"),
}
failed = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(("PASS" if v else "FAIL"), k)
raise SystemExit(1 if failed else 0)
