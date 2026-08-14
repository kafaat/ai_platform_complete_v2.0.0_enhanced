#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
errors = []
required = [
    "migrations/v157_soil_projection_jobs_reconciliation.sql",
    "services/soil-service/projection_jobs.py",
    "scripts/soil/reconcile_historical.py",
    "services/soil-service/test_soil_projection_jobs.py",
]
for rel in required:
    if not (ROOT / rel).is_file():
        errors.append(f"missing {rel}")

migration = (
    (ROOT / required[0]).read_text(encoding="utf-8") if (ROOT / required[0]).is_file() else ""
)
for token in (
    "soil_profile_projection_jobs",
    "soil_reconciliation_checkpoints",
    "FORCE ROW LEVEL SECURITY",
    "sahool_claim_soil_projection_job",
    "SECURITY DEFINER",
):
    if token not in migration:
        errors.append(f"v157 missing {token}")

store = (ROOT / "services/soil-service/soil_store.py").read_text(encoding="utf-8")
if "projection_jobs.enqueue" not in store:
    errors.append("canonical observation persistence does not enqueue projection")

field_context = (ROOT / "services/sahool-platform/api/field_context.py").read_text(encoding="utf-8")
moisture_body = field_context.split("async def _latest_soil_moisture", 1)[-1].split(
    "async def _field_season_context", 1
)[0]
if "FROM device_telemetry" in moisture_body:
    errors.append("platform still reads soil moisture directly from device_telemetry")
if "FROM soil_observations" not in moisture_body:
    errors.append("platform soil moisture is not sourced from soil_observations")

manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
if "v157_soil_projection_jobs_reconciliation.sql" not in manifest:
    errors.append("v157 absent from migration manifest")

if errors:
    raise SystemExit("soil_projection_reconciliation_guard failed:\n- " + "\n- ".join(errors))
print("soil_projection_reconciliation_guard_ok")
