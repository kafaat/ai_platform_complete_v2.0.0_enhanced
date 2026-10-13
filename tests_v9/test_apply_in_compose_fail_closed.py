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

import hashlib
import os
import re
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


def _write_contract(
    tmp_path: Path, *, min_tables: int = 2, min_columns: int = 1, sha: str | None = None
) -> None:
    """عقدٌ مصغَّر صريح للمانيفست المؤقّت (مربوطٌ ببصمته ما لم يُطلب غيرُ ذلك)."""
    manifest = tmp_path / "migrations" / "MANIFEST.txt"
    digest = sha or hashlib.sha256(manifest.read_bytes()).hexdigest()
    (tmp_path / "migrations" / "schema_probe_contract.env").write_text(
        f"MANIFEST_SHA256={digest}\nMIN_TABLES={min_tables}\nMIN_COLUMNS={min_columns}\n",
        encoding="utf-8",
    )


def _run(tmp_path: Path, **extra_env: str | None) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "PGHOST": "sahool-postgres.railway.internal",
        "PGPORT": "5432",
        "PGUSER": "sahool_user",
        "PGPASSWORD": "x",
        "PGDATABASE": "sahool",
        "MIG_DIR": str(tmp_path / "migrations"),
        "INGEST_DB_PASSWORD": "x",  # السكربت يرفض الافتراضيّ التطويريّ المعروف
        "APP_DB_PASSWORD": "x",
        "JOBS_DB_PASSWORD": "x",
        **extra_env,
    }
    for name in [k for k, v in env.items() if v is None]:
        del env[name]  # None = the variable is absent, not empty
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
    _write_contract(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql PGOPTIONS=[$PGOPTIONS] $*" >> "{log}"\n'
        # السطرُ الأوّل من كلّ ناتج: تأكيدُ الخادم أنّ المعاملة read-only (كما يطبعه probe_sql الحقيقيّ).
        'echo "RO_CONFIRMED=on pgoptions_honored=on"\n'
        'case "$*" in\n'
        '  *"version()"*) echo "on|PostgreSQL 16.13 fake|sahool|probe_user|10.0.0.1|f";;\n'
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


def test_read_only_is_set_inside_every_session_not_only_through_pgoptions(tmp_path):
    """التشغيل 38092839653: عميلُ psql في CI (provision_pg_client.sh) لا يمرّر PGOPTIONS فأنكر الخادمُ
    read-only. الضمانةُ يجب أن تُحمَل في الجلسة نفسِها: `SET SESSION default_transaction_read_only = on`
    أوّلَ `-c` في كلّ استدعاء وقبل الاستعلام — فلا يُعاد الاعتمادُ على بيئة العميل خلسةً."""
    log = _probe_workspace(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [c for c in _psql_calls(log) if c.startswith("psql ")]
    assert calls
    for call in calls:
        argv = call.split(" PGOPTIONS=[", 1)[1].split("] ", 1)[1]
        first_c = argv.find(" -c ")
        assert first_c >= 0, call
        # أوّلُ أمرٍ معاملةٌ READ ONLY صريحة، ثمّ تأكيدُ الخادم، ثمّ SET (دفاعٌ ثانٍ) — كلُّها قبل الاستعلام.
        assert argv[first_c:].startswith(" -c BEGIN READ ONLY -c SELECT 'RO_CONFIRMED='"), call
        assert " -c SET SESSION default_transaction_read_only = on -c " in argv, call
    # الاستعلامُ متعدّدُ الأسطر يقطع سطرَ السجلّ؛ COMMIT يُعَدّ على النصّ كاملاً: واحدٌ لكلّ استدعاء.
    assert log.read_text(encoding="utf-8").count("-c COMMIT") == len(calls)


@pytest.mark.parametrize(
    "first_line",
    [
        "",
        "garbage",
        "RO_CONFIRMED=",
        "RO_CONFIRMED=on",
        "RO_CONFIRMED=on  pgoptions_honored=on",
        "ro_confirmed=on pgoptions_honored=on",
    ],
    ids=["empty", "garbage", "no-value", "no-pgoptions-field", "double-space", "lowercase"],
)
def test_a_missing_empty_or_malformed_confirmation_is_rejected_not_assumed(tmp_path, first_line):
    """مراجعةُ المالك 2026-10-11: غيابُ `RO_CONFIRMED=on` أو ناتجٌ فارغ/مشوَّه ⇒ رفضٌ وخروج 3، لا متابعة."""
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\n'
        + (f'echo "{first_line}"\n' if first_line else "")
        + 'case "$*" in *"version()"*) echo "on|PostgreSQL|sahool|u|a|f";; esac\nexit 0\n',
    )
    result = _run(tmp_path)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "reason=session_not_read_only observed_transaction_read_only=" in result.stderr
    assert "pgoptions_inherited=no pgoptions_honored_by_server=" in result.stderr
    assert "SCHEMA_STATE readable=true" not in result.stdout
    assert "MIGRATION_INSPECTION_COMPLETED" not in result.stdout
    assert not any("WITH expected" in c for c in _psql_calls(log))


def test_the_failure_line_never_prints_the_pgoptions_value(tmp_path):
    """تُسجَّل حالةُ PGOPTIONS (توريث/تكريم) لا قيمتُه — فقد تحمل البيئةُ ما لا يُنشَر."""
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\necho "RO_CONFIRMED=off pgoptions_honored=off"\nexit 0\n',
    )
    result = _run(tmp_path, PGOPTIONS="-c search_path=secret_schema_name")
    assert result.returncode == 3
    assert "pgoptions_inherited=yes pgoptions_honored_by_server=off" in result.stderr
    assert "secret_schema_name" not in result.stdout + result.stderr


def test_the_probe_refuses_a_session_the_server_did_not_confirm_read_only(tmp_path):
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\n'
        'echo "RO_CONFIRMED=off pgoptions_honored=off"\n'
        'case "$*" in *"version()"*) echo "off|PostgreSQL|sahool|u|a|t";; esac\nexit 0\n',
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
    _write_contract(tmp_path)
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
    _write_contract(tmp_path)
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


# ── عقدُ الحدّ الأدنى ودلالةُ read_only (مراجعةُ المالك الرابعة 2026-10-10) ──────────────────────

ROOT_MIGRATIONS = ROOT / "migrations"


def _extracted(manifest_dir: Path) -> tuple[str, int, int]:
    """ما يستخرجه السكربتُ نفسُه بأنماطه، لمطابقة العقد المُلتزَم مع MANIFEST الحاليّ."""
    manifest = manifest_dir / "MANIFEST.txt"
    files = [
        ln.strip()
        for ln in manifest.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    tables = columns = 0
    for name in files:
        text = (manifest_dir / name).read_text(encoding="utf-8")
        tables += len(re.findall(r"CREATE TABLE IF NOT EXISTS\s+[a-z0-9_]+", text, re.I))
        columns += len(
            re.findall(
                r"ALTER TABLE\s+[a-z0-9_]+\s+ADD COLUMN IF NOT EXISTS\s+[a-z0-9_]+", text, re.I
            )
        )
    return hashlib.sha256(manifest.read_bytes()).hexdigest(), tables, columns


def test_the_schema_probe_contract_matches_the_manifest():
    """العقدُ المُلتزَم مربوطٌ ببصمة MANIFEST الحاليّة وبعدد الكائنات المستخرَجة — راتشِت لا يُحرَّر يدويّاً."""
    sha, tables, columns = _extracted(ROOT_MIGRATIONS)
    text = (ROOT_MIGRATIONS / "schema_probe_contract.env").read_text(encoding="utf-8")
    fields = dict(
        ln.split("=", 1) for ln in text.splitlines() if "=" in ln and not ln.startswith("#")
    )
    expected = {"MANIFEST_SHA256": sha, "MIN_TABLES": str(tables), "MIN_COLUMNS": str(columns)}
    assert fields == expected, (
        "schema_probe_contract.env لا يطابق MANIFEST الحاليّ — أعِد توليده بهذه القيم: "
        + " ".join(f"{k}={v}" for k, v in expected.items())
    )
    assert tables > 0 and columns > 0, "المانيفست الإنتاجيّ بلا كائناتٍ مستخرَجة — الأنماطُ انكسرت"


def test_a_missing_contract_is_an_error_before_any_connection(tmp_path):
    log = _probe_workspace(tmp_path)
    (tmp_path / "migrations" / "schema_probe_contract.env").unlink()
    result = _run(tmp_path)
    assert result.returncode == 3
    assert (
        "SCHEMA_INSPECTION status=ERROR read_only=unknown reason=contract_missing" in result.stderr
    )
    assert _psql_calls(log) == [], "لا اتّصالَ قبل العقد"


def test_a_contract_signed_for_another_manifest_is_rejected(tmp_path):
    log = _probe_workspace(tmp_path)
    _write_contract(tmp_path, sha="0" * 64)
    result = _run(tmp_path)
    assert result.returncode == 3
    assert "reason=manifest_contract_mismatch" in result.stderr
    assert _psql_calls(log) == []


def test_zero_extracted_objects_never_pass_even_with_a_permissive_contract(tmp_path):
    """الطفرة التي طلبها المالك: ملفّاتٌ صالحة لا تطابق الأنماط ⇒ ERROR لا PASS بلا فحص أيّ كائن."""
    log = _probe_workspace(tmp_path, missing="")
    (tmp_path / "migrations" / "v001.sql").write_text("select 1;\n", encoding="utf-8")
    (tmp_path / "migrations" / "v206_rls_final_hardening.sql").write_text(
        "select 2;\n", encoding="utf-8"
    )
    _write_contract(tmp_path, min_tables=0, min_columns=0)
    result = _run(tmp_path)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "reason=no_objects_extracted files_parsed=2" in result.stderr
    assert "status=PASS" not in result.stdout
    assert _psql_calls(log) == []


def test_fewer_objects_than_the_contract_is_an_error(tmp_path):
    log = _probe_workspace(tmp_path)
    _write_contract(tmp_path, min_tables=5, min_columns=1)
    result = _run(tmp_path)
    assert result.returncode == 3
    assert "reason=objects_below_contract extracted_tables=2 min_tables=5" in result.stderr
    assert _psql_calls(log) == []


def test_read_only_is_unknown_before_the_server_confirms_it_and_false_when_it_denies(tmp_path):
    log = _probe_workspace(tmp_path)
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\necho "psql: error: connection refused" >&2\nexit 2\n',
    )
    result = _run(tmp_path)
    assert "status=ERROR read_only=unknown reason=connect_or_query_failed" in result.stderr
    _fake(
        tmp_path / "psql",
        f'echo "psql $*" >> "{log}"\n'
        'echo "RO_CONFIRMED=off pgoptions_honored=off"\n'
        'case "$*" in *"version()"*) echo "off|PostgreSQL|sahool|u|a|t";; esac\nexit 0\n',
    )
    result = _run(tmp_path)
    assert "status=ERROR read_only=false reason=session_not_read_only" in result.stderr
    assert "read_only=true" not in result.stderr


def test_the_integration_job_makes_the_migrator_certification_mandatory():
    """بلا هذا العَلَم يصير نزعُ TEST_DATABASE_URL يوماً ما تحويلاً صامتاً للشهادة إلى تخطٍّ أخضر."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'MIGRATOR_CERTIFICATION_REQUIRED: "1"' in ci


@pytest.mark.parametrize("ingest", [None, ""], ids=["absent", "empty"])
def test_a_permitted_run_without_the_ingest_secret_fails_before_any_write(tmp_path, ingest):
    """DG-05: the check sat after the migrations and two role scripts, so a permitted run without the
    secret failed only after writing. Now it fails before the first psql call."""
    log = _workspace(tmp_path, ready=True)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1", INGEST_DB_PASSWORD=ingest)
    assert result.returncode != 0, result.stdout
    assert "INGEST_DB_PASSWORD is required" in result.stderr
    assert _psql_calls(log) == [], "psql ran before the missing secret was refused"
    assert "طُبّقت" not in result.stdout


def test_the_read_only_inspection_does_not_need_the_ingest_secret(tmp_path):
    """The no-permission branch only reads; requiring a write secret there would fail it for nothing."""
    _workspace(tmp_path, ready=True)
    result = _run(tmp_path, INGEST_DB_PASSWORD=None)
    assert "INGEST_DB_PASSWORD is required" not in result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout


@pytest.mark.parametrize("secret", ["APP_DB_PASSWORD", "JOBS_DB_PASSWORD"])
@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
def test_a_permitted_run_without_a_role_password_fails_before_any_write(tmp_path, secret, value):
    """MIGRATOR-SCRIPT-DEFAULT-ROLE-PASSWORDS-01: an absent password used to fall back to a value
    written in this repository (sahool_app_pw / sahool_jobs_pw), so any deploy that did not set it
    created a login role with a published password. Now a permitted run refuses before psql."""
    log = _workspace(tmp_path, ready=True)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1", **{secret: value})
    assert result.returncode != 0, result.stdout
    assert f"{secret} is required" in result.stderr
    assert _psql_calls(log) == [], "psql ran before the missing password was refused"


def test_the_read_only_inspection_does_not_need_the_role_passwords(tmp_path):
    _workspace(tmp_path, ready=True)
    result = _run(tmp_path, APP_DB_PASSWORD=None, JOBS_DB_PASSWORD=None)
    assert "is required" not in result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout


def test_an_unset_odoo_password_is_announced_not_replaced_by_a_published_one(tmp_path):
    _workspace(tmp_path, ready=True)
    result = _run(tmp_path, SAHOOL_MIGRATE_APPLY="1", ODOO_DB_PASSWORD=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ODOO_ROLE_PASSWORD_UNSET role=odoo_app" in result.stdout


@pytest.mark.parametrize("script", ["apply_in_compose.sh", "bootstrap_postgres.sh"])
def test_no_migration_script_carries_a_published_role_password(script):
    """The literal values themselves, not just the `:-` shape the secrets guard reads."""
    text = (ROOT / "migrations" / script).read_text(encoding="utf-8")
    for published in ("sahool_app_pw", "sahool_jobs_pw", "odoo_app_pw", "sahool_dev_pw"):
        assert published not in text, f"{script} still carries {published}"
