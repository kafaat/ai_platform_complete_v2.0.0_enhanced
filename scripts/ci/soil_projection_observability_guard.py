from pathlib import Path

required = {
    "migrations/v158_soil_projection_observability.sql": ["sahool_soil_projection_queue_stats", "SECURITY DEFINER", "REVOKE ALL"],
    "services/soil-service/projection_observability.py": ["soil_projection_queue_oldest_ready_age_seconds", "readiness_policy", "WORKER_UP"],
    "services/soil-service/routers/health.py": ["/v1/soil/projection/status", "refresh_queue_metrics", "readiness_policy"],
    "services/soil-service/projection_jobs.py": ["JOBS_CLAIMED", "JOBS_COMPLETED", "JOBS_FAILED"],
}
for path, needles in required.items():
    text = Path(path).read_text()
    for needle in needles:
        assert needle in text, f"{path}: missing {needle}"
assert "v158_soil_projection_observability.sql" in Path("migrations/MANIFEST.txt").read_text()
print("soil_projection_observability_guard_ok")
