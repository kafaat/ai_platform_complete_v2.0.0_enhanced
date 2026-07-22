#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "shared/contracts/soil/observation.py": [
        "soil-observation.v1",
        "idempotency_key",
        "depth_from_cm",
    ],
    "migrations/v155_soil_observations_profiles.sql": [
        "soil_observations",
        "soil_profile_snapshots",
        "FORCE ROW LEVEL SECURITY",
    ],
    "services/soil-service/profile_composer.py": [
        "compose_snapshot",
        "soil-profile-selection.v1",
        "quality_gate",
    ],
    "services/soil-service/routers/canonical.py": [
        "/v1/soil/observations",
        "/soil/profile/rebuild",
        "/soil/profile/history",
    ],
    "services/soil-service/routers/readings.py": ["Canonical dual-write", "persist_observation"],
}
errors = []
for rel, needles in required.items():
    p = ROOT / rel
    if not p.exists():
        errors.append(f"missing:{rel}")
        continue
    text = p.read_text(encoding="utf-8")
    for n in needles:
        if n not in text:
            errors.append(f"missing_contract:{rel}:{n}")
manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
if "v155_soil_observations_profiles.sql" not in manifest:
    errors.append("migration_not_in_manifest")
if errors:
    raise SystemExit("\n".join(errors))
print("soil_canonical_store_guard_ok")
