from pathlib import Path

checks = {
    "shared/contracts/soil/use_policy.py": ["validate_soil_use", "HIGH_RISK_USES"],
    "services/soil-service/evidence_adapters.py": [
        "observations_from_properties",
        "SoilObservationSource",
    ],
    "services/soil-service/routers/canonical.py": ["/soil/evidence", "EvidenceBatchIn"],
    "services/decision-service/main.py": [
        "DECISION_REQUIRE_SOIL_EVIDENCE_GATE",
        "validate_soil_use",
    ],
}
for filename, needles in checks.items():
    text = Path(filename).read_text()
    for needle in needles:
        assert needle in text, f"{filename}: missing {needle}"
for filename in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
    assert "DECISION_REQUIRE_SOIL_EVIDENCE_GATE" in Path(filename).read_text(), filename
print("soil_full_chain_guard_ok")
