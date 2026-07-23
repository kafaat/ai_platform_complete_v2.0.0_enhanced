from pathlib import Path

checks = {
    "migrations/v159_soil_observation_supersession_current_pointer.sql": [
        "soil_observation_supersessions",
        "soil_profile_current",
        "FORCE ROW LEVEL SECURITY",
    ],
    "shared/contracts/soil/observation.py": [
        "supersedes_observation_id",
        "soil_observation_cannot_supersede_itself",
    ],
    "services/soil-service/profile_composer.py": ["is_superseded", "received_at"],
    "services/soil-service/soil_store.py": [
        "soil_observation_supersessions",
        "soil_profile_current",
        "observation_superseded",
    ],
}
for name, needles in checks.items():
    text = Path(name).read_text()
    for needle in needles:
        assert needle in text, f"{name}: missing {needle}"
assert (
    "v159_soil_observation_supersession_current_pointer.sql"
    in Path("migrations/MANIFEST.txt").read_text()
)
print("soil_supersession_current_pointer_guard_ok")
