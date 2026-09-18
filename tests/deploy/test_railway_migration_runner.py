from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy" / "railway" / "Dockerfile.migrate"


def test_railway_migration_runner_is_one_shot_and_contains_psql():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM postgres:16-alpine" in text
    assert "COPY migrations/ /migrations/" in text
    assert 'ENTRYPOINT ["bash", "/migrations/apply_in_compose.sh"]' in text


def test_railway_migration_runner_does_not_embed_database_credentials():
    text = DOCKERFILE.read_text(encoding="utf-8")
    forbidden_values = (
        "PGPASSWORD=",
        "APP_DB_PASSWORD=",
        "JOBS_DB_PASSWORD=",
        "INGEST_DB_PASSWORD=",
    )
    for forbidden in forbidden_values:
        assert forbidden not in text
