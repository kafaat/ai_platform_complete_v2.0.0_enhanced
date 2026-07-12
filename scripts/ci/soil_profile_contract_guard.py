#!/usr/bin/env python3
"""Fail CI when governed consumers bypass the canonical soil profile contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = [
    ROOT / "shared/contracts/soil/profile.py",
    ROOT / "shared/contracts/soil/soil_profile_snapshot.v1.schema.json",
]
for path in required:
    if not path.exists():
        raise SystemExit(f"soil_profile_contract_guard: missing {path.relative_to(ROOT)}")

ag = (ROOT / "services/agriai-engine/agronomic_context.py").read_text()
if "validate_soil_profile_snapshot" not in ag:
    raise SystemExit("soil_profile_contract_guard: AgriAI does not validate canonical soil profile")
if "canonical_soil_profile_required" not in ag:
    raise SystemExit("soil_profile_contract_guard: AgriAI production fail-closed gate missing")

pit = (ROOT / "services/decision-service/agronomic_context/point_in_time.py").read_text()
if "DECISION_REQUIRE_SOIL_PROFILE" not in pit:
    raise SystemExit("soil_profile_contract_guard: Decision composer soil gate missing")

compose = (ROOT / "docker-compose.v9.yml").read_text()
for token in (
    "AGRIAI_STRICT_CONTEXT: ${AGRIAI_STRICT_CONTEXT:-true}",
    "DECISION_REQUIRE_AGRONOMIC_CONTEXT: ${DECISION_REQUIRE_AGRONOMIC_CONTEXT:-true}",
    "DECISION_REQUIRE_SOIL_PROFILE: ${DECISION_REQUIRE_SOIL_PROFILE:-true}",
):
    if token not in compose:
        raise SystemExit(f"soil_profile_contract_guard: compose enforcement missing: {token}")

print("soil_profile_contract_guard_ok")
