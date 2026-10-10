"""اختبارُ قبولٍ حقيقيّ للمُهاجر على PostgreSQL حيّ — لا أدواتَ مزيّفة.

تكملةُ ``test_apply_in_compose_fail_closed.py`` (مراجعةُ المالك 2026-10-10: المحاكاةُ لا تكفي).
يعمل على ``TEST_DATABASE_URL`` (وظيفة *Integration Tests*: Postgres+PostGIS حقيقيّ) ولا يكتب فيها
شيئاً: السيناريوهاتُ الثلاثة هنا كلُّها بلا إذنٍ بالتطبيق، والجردُ قبل/بعد يُثبت ذلك من الخادم لا من
stdout. سيناريو «إذنٌ + تطبيق» يحتاج قاعدةً مؤقّتةً يملكها الاختبار ولا يُشغَّل على القاعدة المشتركة.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "migrations" / "apply_in_compose.sh"
INVENTORY_SQL = (
    "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'public' AND c.relkind = 'r')"
    " || '|' || (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public')"
    " || '|' || (SELECT count(*) FROM pg_roles)"
    " || '|' || (SELECT count(*) FROM pg_policies)"
)


@pytest.fixture(scope="module")
def pg_env() -> dict[str, str]:
    url = os.environ.get("TEST_DATABASE_URL", "")
    # MIGRATOR_CERTIFICATION_REQUIRED=1 (وظيفة Integration Tests): أيُّ تخطٍّ يصير فشلاً صلباً — لا شهادةَ
    # خضراءَ بالتخطّي حين تسقط القاعدة أو يُنزَع DSN يوماً ما (مراجعةُ المالك الرابعة 2026-10-10).
    required = os.environ.get("MIGRATOR_CERTIFICATION_REQUIRED") == "1"
    bail = pytest.fail if required else pytest.skip
    if not url:
        bail("TEST_DATABASE_URL غير مضبوط — يعمل في وظيفة Integration Tests")
    u = urlparse(url)
    env = {
        "PATH": os.environ["PATH"],
        "PGHOST": u.hostname or "localhost",
        "PGPORT": str(u.port or 5432),
        "PGUSER": u.username or "",
        "PGPASSWORD": u.password or "",
        "PGDATABASE": u.path.lstrip("/"),
        "MIG_DIR": str(ROOT / "migrations"),
        "INGEST_DB_PASSWORD": "unused-in-read-only-scenarios",
    }
    # الحياةُ تُفحص بـpsql (الذي يحتاجه السكربتُ أصلاً) لا بـpg_isready، كي لا يتحوّل غيابُ أداةٍ إلى خطأ.
    alive = subprocess.run(
        ["psql", "-X", "-At", "-c", "select 1"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if alive.returncode or alive.stdout.strip() != "1":
        bail("لا خادمَ حيّاً على TEST_DATABASE_URL: " + alive.stderr.strip()[:200])
    return env


PROBE_ROLE = "sahool_probe_ro"


@pytest.fixture(scope="module")
def probe_role(pg_env) -> dict[str, str]:
    """دورُ قراءةٍ فقط من PostgreSQL نفسِه (LOGIN، بلا CREATE/INSERT): الضمانةُ من الخادم لا من عدّ الصفوف."""
    sql = f"""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN
        CREATE ROLE {PROBE_ROLE} LOGIN PASSWORD 'probe_ro_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
      END IF;
    END $$;
    GRANT CONNECT ON DATABASE {pg_env["PGDATABASE"]} TO {PROBE_ROLE};
    GRANT USAGE ON SCHEMA public TO {PROBE_ROLE};
    REVOKE CREATE ON SCHEMA public FROM {PROBE_ROLE};
    """
    created = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-c", sql],
        env=pg_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if created.returncode:
        pytest.fail("تعذّر إنشاءُ دور القراءة: " + created.stderr.strip()[:300])
    return {"PROBE_PGUSER": PROBE_ROLE, "PROBE_PGPASSWORD": "probe_ro_pw"}


def _inventory(env: dict[str, str]) -> str:
    out = subprocess.run(
        ["psql", "-X", "-At", "-c", INVENTORY_SQL],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    return out.stdout.strip()


def _run(env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={**env, **extra},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


def test_an_unreachable_database_exits_nonzero_without_any_migration_call(pg_env):
    before = _inventory(pg_env)
    # بلا إذنٍ عمداً: الاختبارُ الحيّ لا يمنح إذنَ التطبيق أبداً (حمايةُ القاعدة المشتركة)؛ وبرهانُ
    # «حتّى مع الإذن» مُغطّىً بالمحاكاة في test_apply_in_compose_fail_closed.py.
    result = _run(pg_env, PGHOST="127.0.0.1", PGPORT="9", MIGRATE_READY_ATTEMPTS="2")
    assert result.returncode != 0
    assert "MIGRATIONS_NOT_APPLIED reason=database_unreachable" in result.stderr
    assert "→ " not in result.stdout, "ظهر سطرُ تطبيق ملفّ"
    assert _inventory(pg_env) == before


def test_a_ready_database_without_permission_is_inspected_read_only_and_unchanged(
    pg_env, probe_role
):
    before = _inventory(pg_env)
    result = _run(pg_env, SAHOOL_MIGRATE_APPLY="0", **probe_role)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "transaction_read_only=on" in result.stdout
    assert "SCHEMA_STATE readable=true read_only=on" in result.stdout
    assert "MIGRATION_INSPECTION_COMPLETED apply=false" in result.stdout
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("SCHEMA_INSPECTION "))
    fields = dict(kv.split("=", 1) for kv in line.split()[1:])
    assert fields["status"] in {"PASS", "INCOMPLETE"}
    assert fields["read_only"] == "true"
    assert int(fields["files_parsed"]) > 0 and len(fields["manifest_sha256"]) == 64
    assert f"user={PROBE_ROLE}" in result.stdout, "القراءةُ لم تجرِ بدور القراءة"
    assert "→ " not in result.stdout
    assert _inventory(pg_env) == before, "تغيّر المخطَّط/الأدوار بلا إذن"


def test_the_probe_role_cannot_write_even_outside_the_read_only_session(pg_env, probe_role):
    """ضمانةُ الصلاحيّات من PostgreSQL نفسِه: الدورُ بلا CREATE على public وبلا جلسة read-only."""
    env = {
        **pg_env,
        "PGUSER": probe_role["PROBE_PGUSER"],
        "PGPASSWORD": probe_role["PROBE_PGPASSWORD"],
    }
    attempt = subprocess.run(
        [
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE TABLE probe_role_must_not_write (x int)",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert attempt.returncode != 0
    assert "permission denied" in attempt.stderr


def test_a_failed_schema_probe_on_a_ready_database_is_not_a_success(pg_env):
    before = _inventory(pg_env)
    result = _run(pg_env, PROBE_PGUSER="sahool_probe_role_that_does_not_exist")
    assert result.returncode == 3, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "SCHEMA_PROBE_FAILED exit=3" in result.stderr
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert "→ " not in result.stdout
    assert _inventory(pg_env) == before
