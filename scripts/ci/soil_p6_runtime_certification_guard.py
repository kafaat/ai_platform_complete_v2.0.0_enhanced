from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    "migrations/v166_soil_p6_runtime_certification.sql": [
        "soil_runtime_certification_runs",
        "soil_runtime_certification_evidence",
        "FORCE ROW LEVEL SECURITY",
        "WITH CHECK",
    ],
    "shared/contracts/soil/p6.py": [
        "RuntimeCertificationRun",
        "CertificationEvidence",
        "CertificationPolicy",
    ],
    "services/soil-service/p6_certification.py": [
        "evaluate_run",
        "manifest_hash",
        "verify_manifest",
        "migrations_not_applied_through_v166",
    ],
    "services/soil-service/routers/p6_certification.py": [
        "/soil/runtime-certifications/evaluate",
        "/soil/runtime-certifications/{run_id}/verify",
    ],
    "scripts/soil/run_production_certification.py": [
        "runtime_evidence_not_supplied",
        "database_probe_failed",
        "--external-evidence",
    ],
    "tests_v9/test_soil_p6_runtime_integration.py": [
        "expired_projection_lease_is_reclaimed",
        "concurrent_supersession_accepts_one_replacement",
        "pytest.mark.integration",
    ],
}
for f, tokens in checks.items():
    s = (root / f).read_text(encoding="utf-8")
    for token in tokens:
        assert token in s, f"{f}: missing {token}"
ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
assert "soil_p6_runtime_certification_guard.py" in ci
assert "pytest -v -m integration" in ci
manifest = (root / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
assert "v166_soil_p6_runtime_certification.sql" in manifest
print("soil_p6_runtime_certification_guard_ok")
