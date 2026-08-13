#!/usr/bin/env python3
"""Fail closed if durable lab workflow or canonical projection wiring regresses."""

from pathlib import Path

checks = {
    "migrations/v156_durable_soil_lab_workflow.sql": [
        "CREATE TABLE IF NOT EXISTS lab_samples",
        "CREATE TABLE IF NOT EXISTS soil_lab_results",
        "CREATE TABLE IF NOT EXISTS lab_sample_custody_events",
        "FORCE ROW LEVEL SECURITY",
        "WITH CHECK",
    ],
    "services/sahool-platform/api/routers/soil_sampling.py": [
        "tenant_connection",
        "lab_store",
        "transition_lab_sample",
        "publish_soil_lab_evidence",
    ],
    "services/sahool-platform/api/lab_store.py": ["insert_soil_results", "latest_soil_analysis"],
    "services/soil-service/soil_store.py": [
        "rebuild_snapshot_locked",
        "pg_advisory_xact_lock",
        "canonical_sensor_readings",
    ],
    "services/soil-service/routers/readings.py": [
        "canonical_sensor_readings",
        "rebuild_snapshot_locked",
    ],
}
for filename, needles in checks.items():
    text = Path(filename).read_text(encoding="utf-8")
    missing = [n for n in needles if n not in text]
    if missing:
        raise SystemExit(f"{filename}: missing {missing}")
router = Path("services/sahool-platform/api/routers/soil_sampling.py").read_text(encoding="utf-8")
for forbidden in ("_LAB_SAMPLES", "_SOIL_RESULTS", "_WATER_RESULTS"):
    if forbidden in router:
        raise SystemExit(f"process-local lab SoR forbidden: {forbidden}")
manifest = Path("migrations/MANIFEST.txt").read_text(encoding="utf-8")
if "v156_durable_soil_lab_workflow.sql" not in manifest:
    raise SystemExit("v156 missing from migration manifest")
print("soil_lab_projection_guard_ok")
