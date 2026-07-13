from pathlib import Path

checks = {
    "migrations/v160_soil_lab_publication_lineage.sql": [
        "published_observation_id", "supersedes_result_id", "published_at"
    ],
    "services/sahool-platform/api/soil_evidence_bridge.py": [
        "supersedes_observation_ids", "result_by_canonical"
    ],
    "services/soil-service/routers/canonical.py": [
        "supersedes_observation_ids", "supersession_reason"
    ],
    "services/soil-service/evidence_adapters.py": [
        "supersedes_observation_id", "supersession_reason"
    ],
}
for name, tokens in checks.items():
    text = Path(name).read_text()
    missing = [token for token in tokens if token not in text]
    assert not missing, f"{name}: missing {missing}"
assert "v160_soil_lab_publication_lineage.sql" in Path("migrations/MANIFEST.txt").read_text()
print("soil_lab_supersession_lineage_guard_ok")
