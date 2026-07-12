from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_asyncpg_dependency_present():
    req = ROOT / "services" / "sahool-platform" / "api" / "requirements.txt"
    assert "asyncpg" in req.read_text(encoding="utf-8")


def test_field_create_projection_best_effort():
    fields = ROOT / "services" / "sahool-platform" / "api" / "routers" / "fields.py"
    text = fields.read_text(encoding="utf-8")
    assert "projection must not break field create" in text
    assert "asyncpg.UndefinedColumnError" in text


def test_v104_field_create_contract_migration_in_manifest():
    migration = ROOT / "migrations" / "v104_fields_create_contract.sql"
    manifest = ROOT / "migrations" / "MANIFEST.txt"
    assert migration.exists()
    mtext = migration.read_text(encoding="utf-8")
    for needle in [
        "ADD COLUMN IF NOT EXISTS geometry",
        "ADD COLUMN IF NOT EXISTS planting_date",
        "CREATE TABLE IF NOT EXISTS field_state",
        "ADD COLUMN IF NOT EXISTS agronomic",
    ]:
        assert needle in mtext
    assert "v104_fields_create_contract.sql" in manifest.read_text(encoding="utf-8")


def test_jobs_database_env_present_and_migrations_continue_idempotently():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")  # لا نشحن .env (أسرار)؛ نفحص القالب
    assert "JOBS_DB_PASSWORD" in env
    assert "JOBS_DATABASE_URL" in env
    script = (ROOT / "migrations" / "apply_in_compose.sh").read_text(encoding="utf-8")
    assert "ON_ERROR_STOP=0" in script
