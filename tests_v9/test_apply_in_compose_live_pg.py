"""اختبارُ قبولٍ حقيقيّ للمُهاجر على PostgreSQL حيّ — لا أدواتَ مزيّفة.

تكملةُ ``test_apply_in_compose_fail_closed.py`` (مراجعةُ المالك 2026-10-10: المحاكاةُ لا تكفي).
يعمل على ``TEST_DATABASE_URL`` (وظيفة *Integration Tests*: Postgres+PostGIS حقيقيّ) ولا يكتب فيها
شيئاً: السيناريوهاتُ الثلاثة هنا كلُّها بلا إذنٍ بالتطبيق، والجردُ قبل/بعد يُثبت ذلك من الخادم لا من
stdout. سيناريو «إذنٌ + تطبيق» يحتاج قاعدةً مؤقّتةً يملكها الاختبار ولا يُشغَّل على القاعدة المشتركة.
"""

from __future__ import annotations

import os
import re
import shutil
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


def _psql_shim(tmp_path: Path, *, flip_set: bool = False, only_presence: bool = False) -> str:
    """غلافُ psql يُعيد إنتاج عميل CI (`scripts/ci/provision_pg_client.sh`): يُسقط PGOPTIONS قبل الاستدعاء.
    مع flip_set يُبدّل أمرَ SET إلى off وBEGIN READ ONLY إلى READ WRITE — عميلٌ/وسيطٌ لا يُكرّم تهيئةَ القراءة — ليُقاس أنّ الرفضَ
    يأتي من قيمة الخادم لا من افتراض السكربت."""
    real = shutil.which("psql")
    assert real, "psql غيرُ موجود على PATH"
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    if flip_set:
        # يُقلَب SET وBEGIN معاً في الجلسات المستهدَفة فقط (كلِّها، أو جلسةِ استعلام الغياب وحدها).
        rewrite = (
            'flip=1; case "$*" in *"WITH expected"*) flip=1;; *) flip='
            + ("0" if only_presence else "1")
            + ';; esac\nargs=()\nfor a in "$@"; do\n'
            '  if [ "$flip" = 1 ]; then case "$a" in\n'
            '    "SET SESSION default_transaction_read_only = on") a="SET SESSION default_transaction_read_only = off";;\n'
            '    "BEGIN READ ONLY") a="BEGIN READ WRITE";;\n'
            "  esac; fi\n"
            '  args+=("$a")\ndone\n'
        )
    else:
        rewrite = 'args=("$@")\n'
    (shim_dir / "psql").write_text(
        "#!/usr/bin/env bash\nunset PGOPTIONS\n" + rewrite + f'exec "{real}" "${{args[@]}}"\n',
        encoding="utf-8",
    )
    (shim_dir / "psql").chmod(0o755)
    return f"{shim_dir}:{os.environ['PATH']}"


def test_read_only_holds_when_the_client_drops_pgoptions_and_the_inherited_value_contradicts(
    pg_env, probe_role, tmp_path
):
    """انحدارُ التشغيل 38092839653: عميلٌ يُسقط PGOPTIONS (كعميل CI) + PGOPTIONS موروثٌ يقول off ⇒
    الجلسةُ تبقى read-only لأنّ SET يُنفَّذ داخلها، والخادمُ هو مَن يقول on."""
    before = _inventory(pg_env)
    result = _run(
        pg_env,
        SAHOOL_MIGRATE_APPLY="0",
        PATH=_psql_shim(tmp_path),
        PGOPTIONS="-c default_transaction_read_only=off",
        **probe_role,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "transaction_read_only=on" in result.stdout
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("SCHEMA_INSPECTION "))
    assert "read_only=true" in line.split()
    assert "MIGRATION_INSPECTION_COMPLETED apply=false" in result.stdout
    # الخادمُ نفسُه يشهد أنّ العميلَ أسقط PGOPTIONS (كما في CI) وأنّ القراءةَ مع ذلك مضمونة؛ والقيمةُ الموروثة لا تُطبَع.
    assert "pgoptions_inherited=yes pgoptions_honored_by_server=off" in result.stdout
    assert "default_transaction_read_only=off" not in result.stdout + result.stderr
    assert _inventory(pg_env) == before


def test_a_session_the_server_reports_writable_fails_closed_on_live_postgres(
    pg_env, probe_role, tmp_path
):
    """الجانبُ المغلق من العقد على خادمٍ حقيقيّ: حين لا تُكرَّم تهيئةُ القراءة (SET مقلوبٌ إلى off وبلا
    PGOPTIONS) يُعلن الخادمُ off ⇒ خروج 3 وreason=session_not_read_only ولا استعلامَ مخطَّط ولا تغيير."""
    before = _inventory(pg_env)
    result = _run(
        pg_env, SAHOOL_MIGRATE_APPLY="0", PATH=_psql_shim(tmp_path, flip_set=True), **probe_role
    )
    assert result.returncode == 3, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert (
        "SCHEMA_INSPECTION status=ERROR read_only=false reason=session_not_read_only"
        in result.stderr
    )
    # القيمةُ المرصودة من الخادم وPGOPTIONS تُسجَّلان في سطر الفشل (تنبيه Gap Watch 2026-10-11) بلا أسرار.
    assert "observed_transaction_read_only=off" in result.stderr
    assert "pgoptions_inherited=no pgoptions_honored_by_server=off" in result.stderr
    assert (
        "probe_ro_pw" not in result.stderr and "default_transaction_read_only=" not in result.stderr
    )
    assert "SCHEMA_PROBE_FAILED exit=3" in result.stderr
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert "SCHEMA_STATE readable=true" not in result.stdout
    assert _inventory(pg_env) == before


def test_the_presence_query_itself_must_run_in_a_server_confirmed_read_only_transaction(
    pg_env, probe_role, tmp_path
):
    """تنبيه Gap Watch 2026-10-11: التأكيدُ لكلّ استعلام لا للهويّة وحدها — جلسةُ الهويّة سليمة،
    وجلسةُ استعلام الغياب وحدها تفقد READ ONLY ⇒ خروج 3 ولا SCHEMA_STATE ولا تغيير."""
    before = _inventory(pg_env)
    result = _run(
        pg_env,
        SAHOOL_MIGRATE_APPLY="0",
        PATH=_psql_shim(tmp_path, flip_set=True, only_presence=True),
        **probe_role,
    )
    assert result.returncode == 3, result.stdout + result.stderr
    assert "transaction_read_only=on" in result.stdout, "جلسةُ الهويّة كان يجب أن تبقى read-only"
    assert "reason=session_not_read_only observed_transaction_read_only=off" in result.stderr
    assert "SCHEMA_STATE readable=true" not in result.stdout
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert _inventory(pg_env) == before


# ── SCHEMA_CATALOG: RLS, policies and triggers of the catalog files' tables (owner decision 2026-11-24) ──
PROBE = ROOT / "migrations" / "probe_schema_state.sh"


def _probe(env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PROBE)],
        env={**env, **extra},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


def _catalog(stdout: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    summary: dict[str, str] = {}
    for ln in stdout.splitlines():
        if ln.startswith("SCHEMA_CATALOG "):
            fields = dict(kv.split("=", 1) for kv in ln.split()[1:] if "=" in kv)
            assert {"file", "table", "rls", "force_rls", "policies", "triggers", "grants"} <= set(
                fields
            ), f"malformed SCHEMA_CATALOG line: {ln!r}"
            rows[fields["table"]] = fields
        elif ln.startswith("SCHEMA_CATALOG_SUMMARY "):
            summary = dict(kv.split("=", 1) for kv in ln.split()[1:] if "=" in kv)
    return rows, summary


def test_the_probe_prints_the_catalog_facts_of_a_named_migration_from_the_server(
    pg_env, probe_role
):
    """v287 on the migrated CI database: FORCE RLS, its five policies and its trigger, read by the RO role."""
    before = _inventory(pg_env)
    result = _probe(pg_env, PROBE_CATALOG_FILES="v287_farm_access_grants.sql", **probe_role)
    assert result.returncode == 0, result.stdout + result.stderr
    rows, summary = _catalog(result.stdout)
    grants = rows["farm_access_grants"]
    assert grants["file"] == "v287_farm_access_grants.sql"
    assert (grants["rls"], grants["force_rls"]) == ("true", "true")
    assert grants["policies"].split(",") == [
        "farm_access_grants_tenant:*:permissive",
        "farm_grant_owner_delete:d:restrictive",
        "farm_grant_owner_insert:a:restrictive",
        "farm_grant_owner_update:w:restrictive",
        "farm_grant_read:r:restrictive",
    ]
    assert grants["triggers"] == "farm_access_grant_provenance:O"
    # grants: non-owner ACL entries as role:PRIV|PRIV (sorted), or none for owner-only defaults.
    assert re.fullmatch(
        r"none|[^,:|=\s]+:[A-Z]+(\|[A-Z]+)*(,[^,:|=\s]+:[A-Z]+(\|[A-Z]+)*)*", grants["grants"]
    ), grants["grants"]
    assert summary["status"] == "READ" and summary["scope"] == "informational_not_gating"
    assert summary["tables"] == summary["present"] == summary["force_rls"] == "1"
    assert result.stdout.rstrip().splitlines()[-1].startswith("SCHEMA_INSPECTION "), (
        "the contract line must stay last"
    )
    assert _inventory(pg_env) == before


def _numbered_manifest() -> tuple[list[str], list[str]]:
    manifest = [
        ln.strip()
        for ln in (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    numbered = [f for f in manifest if f[:1] == "v" and f.split("_", 1)[0][1:].isdigit()]
    return manifest, sorted(numbered, key=lambda f: int(f.split("_", 1)[0][1:]))


def _creates_a_table(name: str) -> bool:
    text = (ROOT / "migrations" / name).read_text(encoding="utf-8")
    return re.search(r"CREATE TABLE IF NOT EXISTS\s+[a-z0-9_]+", text, re.I) is not None


def test_the_default_catalog_is_the_highest_numbered_migration_not_the_last_manifest_line(
    pg_env, probe_role
):
    manifest, numbered = _numbered_manifest()
    newest = [f for f in numbered if _creates_a_table(f)][-1]
    assert manifest[-1] != newest, "MANIFEST re-runs older files after the newest one"
    result = _probe(pg_env, **probe_role)
    assert result.returncode == 0, result.stdout + result.stderr
    _rows, summary = _catalog(result.stdout)
    assert summary["files"] == newest
    assert summary["status"] == "READ"
    assert int(summary["tables"]) > 0


def test_a_migration_that_creates_no_table_never_becomes_the_empty_default_catalog(
    pg_env, probe_role
):
    # v290 adds only a trigger to v289's outbox. As the default it printed tables=0, which hid
    # both v289's row-level security and v290's own trigger; the default now stays on v289 and
    # v290's trigger shows on the outbox row.
    _manifest, numbered = _numbered_manifest()
    assert numbered[-1] == "v290_scouting_verification_initial_state.sql"
    assert not _creates_a_table(numbered[-1])
    result = _probe(pg_env, **probe_role)
    assert result.returncode == 0, result.stdout + result.stderr
    rows, summary = _catalog(result.stdout)
    assert summary["files"] == "v289_scouting_verification_bridge.sql", summary
    assert summary["tables"] == "4" and summary["force_rls"] == "4", summary
    triggers = rows["scouting_verification_outbox"]["triggers"].split(",")
    assert "scouting_verification_delivery_initial_guard:O" in triggers, triggers

    named = _probe(pg_env, PROBE_CATALOG_FILES=numbered[-1], **probe_role)
    _rows, named_summary = _catalog(named.stdout)
    assert named_summary["status"] == "READ" and named_summary["tables"] == "0", named_summary


def test_a_catalog_file_outside_the_manifest_is_reported_and_never_changes_the_verdict(
    pg_env, probe_role
):
    plain = _probe(pg_env, **probe_role)
    odd = _probe(pg_env, PROBE_CATALOG_FILES="not_in_manifest.sql", **probe_role)
    assert plain.returncode == odd.returncode == 0, odd.stdout + odd.stderr
    rows, summary = _catalog(odd.stdout)
    assert rows == {}
    assert summary["status"] == "ERROR"
    assert summary["reason"] == "file_not_in_manifest:not_in_manifest.sql"
    plain_verdict = plain.stdout.rstrip().splitlines()[-1]
    odd_verdict = odd.stdout.rstrip().splitlines()[-1]
    assert plain_verdict == odd_verdict, "a bad catalog file must not change the verdict"
    assert plain_verdict.startswith("SCHEMA_INSPECTION ")


def test_empty_and_repeated_catalog_entries_are_dropped_and_names_are_shown_sanitised(
    pg_env, probe_role
):
    repeated = _probe(
        pg_env,
        PROBE_CATALOG_FILES=",v287_farm_access_grants.sql,, v287_farm_access_grants.sql ,",
        **probe_role,
    )
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    rows, summary = _catalog(repeated.stdout)
    assert summary["files"] == "v287_farm_access_grants.sql", summary
    assert summary["tables"] == "1" and list(rows) == ["farm_access_grants"]

    blank = _probe(pg_env, PROBE_CATALOG_FILES=" , ", **probe_role)
    _rows, blank_summary = _catalog(blank.stdout)
    _rows, default_summary = _catalog(_probe(pg_env, **probe_role).stdout)
    assert blank_summary["files"] == default_summary["files"], "an empty override is the default"

    odd = _probe(pg_env, PROBE_CATALOG_FILES="x,status=PASS", **probe_role)
    odd_line = next(
        ln for ln in odd.stdout.splitlines() if ln.startswith("SCHEMA_CATALOG_SUMMARY ")
    )
    assert " files=x,status?PASS " in odd_line, odd_line
    assert odd_line.count("status=") == 1, "the input must not add a second status field"
