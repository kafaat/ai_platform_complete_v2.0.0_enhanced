"""المُهاجر يُغلق بأمان: لا جاهزيّةَ ⇒ لا اتّصال؛ ولا إذنَ ⇒ لا تطبيق.

MIGRATOR-PROCEEDS-TO-APPLY-AFTER-READINESS-TIMEOUT-01: ``apply_in_compose.sh`` كان يحاول
``pg_isready`` ثلاثين مرّة ثمّ **يتابع إلى تطبيق MANIFEST** بلا فرعٍ للفشل. على Railway
(نشر ``87cc687b``، 2026-10-10، #1158) أوقفه ``psql`` بفشل حلّ الاسم — حمايةٌ من DNS لا من
الشيفرة. وكان أيُّ دفعٍ يمسّ ``Dockerfile.migrate`` يُطلق هجرةَ إنتاجٍ لأنّ بناءَ الصورة
وتشغيلَها شيءٌ واحد على Railway.

الشواهدُ هنا تُشغّل السكربتَ الحقيقيّ بـ``pg_isready``/``psql``/``sleep`` مزيّفةٍ على ``PATH``
وتسجّل كلَّ استدعاءٍ لـ``psql``: أحمرُ على الشيفرة السابقة (كانت تستدعي ``psql`` رغم فشل
الجاهزيّة)، أخضرُ بعد الإصلاح.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "migrations" / "apply_in_compose.sh"


def _fake(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _workspace(tmp_path: Path, *, ready: bool) -> Path:
    """شجرةٌ مؤقّتة: manifest صالح (آخرُ مدخل v206)، وأدواتٌ مزيّفة تسجّل استدعاءاتها."""
    mig = tmp_path / "migrations"
    mig.mkdir()
    (mig / "v001.sql").write_text("select 1;\n", encoding="utf-8")
    (mig / "v206_rls_final_hardening.sql").write_text("select 1;\n", encoding="utf-8")
    (mig / "MANIFEST.txt").write_text("v001.sql\nv206_rls_final_hardening.sql\n", encoding="utf-8")
    log = tmp_path / "psql.log"
    log.write_text("", encoding="utf-8")
    _fake(tmp_path / "pg_isready", "exit 0\n" if ready else "exit 2\n")
    _fake(tmp_path / "psql", f'echo "psql $*" >> "{log}"\nexit 0\n')
    _fake(tmp_path / "sleep", "exit 0\n")  # ٣٠ محاولة × ٢ث لا تُنتظَر فعلاً
    return log


def _run(tmp_path: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "PGHOST": "sahool-postgres.railway.internal",
        "PGPORT": "5432",
        "PGUSER": "sahool_user",
        "PGPASSWORD": "x",
        "PGDATABASE": "sahool",
        "MIG_DIR": str(tmp_path / "migrations"),
        "INGEST_DB_PASSWORD": "x",  # السكربت يرفض الافتراضيّ التطويريّ المعروف
        **extra_env,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        env=env,
        timeout=120,
    )


def _psql_calls(log: Path) -> list[str]:
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_an_unreachable_database_fails_closed_before_any_psql_call(tmp_path):
    """شكلُ نشر 87cc687b: لا pg_isready ينجح ⇒ خروجٌ غيرُ صفريّ، لا استدعاءَ psql، والمضيفُ مُسمّى."""
    log = _workspace(tmp_path, ready=False)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1", MIGRATE_READY_ATTEMPTS="3")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=database_unreachable" in result.stderr
    assert "sahool-postgres.railway.internal:5432" in result.stderr
    assert _psql_calls(log) == [], "psql استُدعي رغم أنّ الجاهزيّة لم تُثبَت"


def test_the_readiness_loop_still_waits_the_configured_number_of_attempts(tmp_path):
    log = _workspace(tmp_path, ready=False)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1", MIGRATE_READY_ATTEMPTS="4")
    assert result.returncode != 0
    assert result.stdout.count("بانتظار postgres") == 4
    assert "attempts=4" in result.stderr
    assert _psql_calls(log) == []


def test_without_explicit_permission_a_ready_database_is_not_migrated(tmp_path):
    """بناءُ الصورة ≠ الإذنُ بالتطبيق: الجاهزيّةُ مُثبَتة، لا SAHOOL_MIGRATE_APPLY ⇒ لا تطبيق، وقراءةٌ ناجحة ⇒ خروجٌ صفريّ مُعلَن."""
    log = _probe_workspace(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "MIGRATION_INSPECTION_COMPLETED apply=false" in result.stdout
    assert not any(" -f " in c for c in _psql_calls(log)), "لا يُطبَّق ملفٌّ بلا إذن"


def test_a_value_other_than_one_is_not_permission(tmp_path):
    log = _probe_workspace(tmp_path)
    for value in ("true", "yes", "0", ""):
        log.write_text("", encoding="utf-8")
        result = _run(tmp_path, SAHOOL_MIGRATE_APPLY=value)
        assert result.returncode == 0, value
        assert "apply_not_permitted" in result.stdout, value
        assert not any(" -f " in c for c in _psql_calls(log)), value


def test_with_permission_and_a_ready_database_the_manifest_is_applied_in_order(tmp_path):
    """الضابط: الإذنُ + الجاهزيّة ⇒ المسارُ القديم كما هو (الهجرتان ثمّ أدوارُ التشغيل)."""
    log = _workspace(tmp_path, ready=True)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _psql_calls(log)
    files = [c.split(" -f ", 1)[1].split()[0] for c in calls if " -f " in c]
    assert [os.path.basename(f) for f in files] == ["v001.sql", "v206_rls_final_hardening.sql"]
    assert "MIGRATIONS_NOT_APPLIED" not in result.stdout + result.stderr
    assert "طُبّقت 2 هجرة" in result.stdout


def test_compose_stacks_grant_the_permission_explicitly():
    """المحلّيّ لم يتغيّر سلوكُه: compose يضبط الإذنَ صراحةً في خدمة sahool-migrate."""
    for name in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        # تعريفُ الخدمة (بمسافتين) لا ذِكرُها في depends_on خدماتٍ أخرى (بستّ مسافات).
        block = text.split("\n  sahool-migrate:\n", 1)[1].split("\n  sahool-", 1)[0]
        assert 'SAHOOL_MIGRATE_APPLY: "1"' in block, name


def test_the_railway_runner_does_not_bake_the_permission_into_the_image():
    """على Railway الإذنُ متغيّرُ بيئةٍ يضبطه المشغِّل عند قرار الهجرة — لا يُخبَز في الصورة."""
    text = (ROOT / "deploy" / "railway" / "Dockerfile.migrate").read_text(encoding="utf-8")
    assert "SAHOOL_MIGRATE_APPLY" not in text, (
        "الإذنُ متغيّرُ مشغِّلٍ يُضبَط عند قرار الهجرة — خبزُه في الصورة يُعيد كلَّ إعادة بناءٍ هجرةً"
    )


# ── قراءةُ حالة المخطَّط حين لا إذنَ بالتطبيق (بوّابةُ #1158 البندان ٣–٤) ──────────────────

PROBE = ROOT / "migrations" / "probe_schema_state.sh"


def _probe_workspace(tmp_path: Path, *, missing: str = "") -> Path:
    """psql مزيّف يسجّل كلَّ استدعاءٍ مع PGOPTIONS، ويُجيب عن استعلام الهويّة واستعلام الغياب."""
    log = _workspace(tmp_path, ready=True)
    (tmp_path / "migrations" / "v001.sql").write_text(
        "CREATE TABLE IF NOT EXISTS alpha (id int);\n"
        "ALTER TABLE alpha ADD COLUMN IF NOT EXISTS extra text;\n",
        encoding="utf-8",
    )
    (tmp_path / "migrations" / "v206_rls_final_hardening.sql").write_text(
        "create table if not exists Beta (id int);\n", encoding="utf-8"
    )
    _fake(
        tmp_path / "psql",
        f'echo "psql PGOPTIONS=[$PGOPTIONS] $*" >> "{log}"\n'
        'case "$*" in\n'
        '  *transaction_read_only*) echo "on|PostgreSQL 16.13 fake|sahool|probe_user|10.0.0.1|f";;\n'
        f'  *"WITH expected"*) printf "%s" "{missing}";;\n'
        "esac\nexit 0\n",
    )
    return log


def test_without_permission_the_job_reports_schema_state_read_only(tmp_path):
    log = _probe_workspace(tmp_path, missing="3|v206_rls_final_hardening.sql|table|beta|")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "SCHEMA_STATE readable=true read_only=on" in result.stdout
    assert "tables=1/2 columns=1/1 first_missing=v206_rls_final_hardening.sql" in result.stdout
    # الاستعلامُ متعدّدُ الأسطر يُسجَّل على أسطرٍ عدّة؛ سطرُ الاستدعاء وحده يبدأ بـpsql.
    calls = [c for c in _psql_calls(log) if c.startswith("psql ")]
    assert calls and all("default_transaction_read_only=on" in c for c in calls), calls
    assert not any(" -f " in c for c in calls), "القراءةُ لا تطبّق ملفّات"


def test_the_probe_refuses_a_session_the_server_did_not_confirm_read_only(tmp_path):
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\n'
        'case "$*" in *transaction_read_only*) echo "off|PostgreSQL|sahool|u|a|t";; esac\nexit 0\n',
    )
    result = _run(tmp_path)
    # الإذنُ غائب ⇒ لا هجرة؛ لكنّ تعذّرَ القراءة ليس نجاحاً (مراجعةُ المالك 2026-10-10): خروج 3.
    assert result.returncode == 3, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "SCHEMA_STATE readable=false reason=session_not_read_only" in result.stderr
    assert "SCHEMA_PROBE_FAILED exit=3" in result.stderr
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert not any("WITH expected" in c for c in _psql_calls(log))
    assert not any(" -f " in c for c in _psql_calls(log))


def test_the_probe_parses_only_the_manifest_files_in_manifest_order(tmp_path):
    log = _probe_workspace(tmp_path)
    (tmp_path / "migrations" / "stray.sql").write_text(
        "CREATE TABLE IF NOT EXISTS stray (id int);\n", encoding="utf-8"
    )
    result = _run(tmp_path)
    assert "stray" not in result.stdout
    query = next(c for c in _psql_calls(log) if "WITH expected" in c)
    assert query.index("'v001.sql','table','alpha'") < query.index(
        "'v001.sql','column','alpha','extra'"
    )
    assert query.index("'alpha','extra'") < query.index(
        "'v206_rls_final_hardening.sql','table','beta'"
    )


def test_a_permitted_run_does_not_probe(tmp_path):
    log = _probe_workspace(tmp_path)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCHEMA_STATE" not in result.stdout + result.stderr
    assert any(" -f " in c for c in _psql_calls(log))


def test_a_failed_schema_probe_is_not_reported_as_success(tmp_path):
    """العيبُ الذي وجده المالك: كان `|| echo …; exit 0` يحوّل فشلَ القراءة إلى نجاح. الآن: خروج 3، لا تطبيق."""
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\necho "psql: error: connection refused" >&2\nexit 2\n',
    )
    result = _run(tmp_path)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert "SCHEMA_STATE readable=false reason=connect_or_query_failed" in result.stderr
    assert "SCHEMA_PROBE_FAILED exit=3" in result.stderr
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert not any(" -f " in c for c in _psql_calls(log))


def test_the_schema_state_line_declares_its_limited_scope(tmp_path):
    """`tables=n/n` وحده لا يُغلق فجوةَ قراءة الحالة: السطرُ يُعلن أنّ القياس وجودُ الجداول/الأعمدة فقط."""
    _probe_workspace(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "scope=tables_and_columns_only" in result.stdout


# ── اكتمالُ تحليل MANIFEST شرطٌ لأيّ نتيجة (مراجعةُ المالك الثالثة 2026-10-10) ────────────────


def test_a_manifest_entry_without_a_readable_file_is_an_error_not_a_partial_pass(tmp_path):
    log = _probe_workspace(tmp_path)
    (tmp_path / "migrations" / "MANIFEST.txt").write_text(
        "v001.sql\nv_missing.sql\nv206_rls_final_hardening.sql\n", encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "SCHEMA_INSPECTION status=ERROR" in result.stderr
    assert "reason=manifest_file_unreadable file=v_missing.sql files_parsed=1" in result.stderr
    assert "readable=true" not in result.stdout
    assert "SCHEMA_INSPECTION status=PASS" not in result.stdout
    assert "SCHEMA_INSPECTION status=INCOMPLETE" not in result.stdout
    # لا استعلامَ قبل اكتمال التحليل، ولا تطبيق.
    assert not any("WITH expected" in c or " -f " in c for c in _psql_calls(log))


def test_an_empty_manifest_is_an_error(tmp_path):
    log = _probe_workspace(tmp_path)
    (tmp_path / "migrations" / "MANIFEST.txt").write_text("# لا شيء\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 3
    assert "reason=manifest_empty" in result.stderr
    assert not any("WITH expected" in c for c in _psql_calls(log))


def test_the_inspection_line_carries_the_contract_fields(tmp_path):
    _probe_workspace(tmp_path, missing="3|v206_rls_final_hardening.sql|table|beta|")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("SCHEMA_INSPECTION "))
    fields = dict(kv.split("=", 1) for kv in line.split()[1:])
    assert fields["status"] == "INCOMPLETE"
    assert fields["read_only"] == "true"
    assert len(fields["manifest_sha256"]) == 64
    assert fields["files_parsed"] == "2"
    assert (fields["expected_tables"], fields["present_tables"]) == ("2", "1")
    assert (fields["expected_columns"], fields["present_columns"]) == ("1", "1")
    assert fields["first_missing"] == "v206_rls_final_hardening.sql"


def test_pass_means_every_expected_object_is_present_and_every_file_parsed(tmp_path):
    _probe_workspace(tmp_path, missing="")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCHEMA_INSPECTION status=PASS read_only=true" in result.stdout
    assert "files_parsed=2" in result.stdout
    assert "first_missing=none" in result.stdout


def test_the_live_acceptance_never_grants_apply_permission():
    """حمايةُ S4: الاختبارُ الحيّ على TEST_DATABASE_URL المشتركة لا يمنح إذنَ التطبيق أبداً."""
    text = (ROOT / "tests_v9" / "test_apply_in_compose_live_pg.py").read_text(encoding="utf-8")
    assert 'SAHOOL_MIGRATE_APPLY="1"' not in text, (
        "سيناريو «إذنٌ + تطبيق» يحتاج قاعدةً مؤقّتةً يملكها الاختبار — لا القاعدةَ المشتركة"
    )
