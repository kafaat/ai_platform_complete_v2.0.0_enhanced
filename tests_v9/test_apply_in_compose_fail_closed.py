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
    """بناءُ الصورة ≠ الإذنُ بالتطبيق: الجاهزيّةُ مُثبَتة، لا SAHOOL_MIGRATE_APPLY ⇒ لا psql، خروجٌ صفريّ مُعلَن."""
    log = _workspace(tmp_path, ready=True)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MIGRATIONS_NOT_APPLIED reason=apply_not_permitted" in result.stdout
    assert _psql_calls(log) == []


def test_a_value_other_than_one_is_not_permission(tmp_path):
    log = _workspace(tmp_path, ready=True)
    for value in ("true", "yes", "0", ""):
        log.write_text("", encoding="utf-8")
        result = _run(tmp_path, SAHOOL_MIGRATE_APPLY=value)
        assert result.returncode == 0, value
        assert "apply_not_permitted" in result.stdout, value
        assert _psql_calls(log) == [], value


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
    assert "SAHOOL_MIGRATE_APPLY" not in text
