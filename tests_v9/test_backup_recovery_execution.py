"""Execute backup shell control flow with isolated fake PostgreSQL clients."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def environment(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    scripts = {
        "curl": 'cat >> "$TEST_METRICS"\n',
        "psql": 'echo 0\n',
        "pg_verifybackup": 'test -f "$1/backup_manifest"\n',
        "pg_dump": 'for arg in "$@"; do case "$arg" in --file=*) printf dump > "${arg#--file=}";; esac; done\n',
        "pg_restore": 'echo "; archive catalog"\n',
        "pg_basebackup": 'for arg in "$@"; do case "$arg" in --pgdata=*) dest="${arg#--pgdata=}";; esac; done\nmkdir "$dest"\nprintf 16 > "$dest/PG_VERSION"\nprintf manifest > "$dest/backup_manifest"\n',
    }
    for name, script in scripts.items():
        p = binary / name
        p.write_text("#!/bin/bash\nset -eu\n" + script)
        p.chmod(0o755)
    env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}", "BACKUP_DIR": str(tmp_path / "backups"), "TEST_METRICS": str(tmp_path / "metrics")}
    env.pop("AWS_ACCESS_KEY_ID", None)
    return env


def run(script, *args, env):
    return subprocess.run(["bash", str(ROOT / "scripts" / script), *map(str, args)], env=env, capture_output=True, text=True)


def test_empty_cleanup_and_full_job_succeed(environment):
    result = run("backup_postgres.sh", "cleanup", env=environment)
    assert result.returncode == 0, result.stderr
    assert "Deleted 0" in result.stderr
    result = run("backup_postgres.sh", "full", env=environment)
    assert result.returncode == 0, result.stderr
    assert 'sahool_backup_success{type="full"} 1' in Path(environment["TEST_METRICS"]).read_text()


def test_cleanup_failure_cannot_report_overall_success(environment):
    environment["RETENTION_DAYS_LOCAL"] = "invalid"
    result = run("backup_postgres.sh", "full", env=environment)
    assert result.returncode != 0
    metrics = Path(environment["TEST_METRICS"]).read_text()
    assert 'sahool_backup_success{type="full"} 0' in metrics
    assert 'sahool_backup_success{type="full"} 1' not in metrics, "success belongs after every required stage"


def test_wal_same_segment_replay_and_collision(environment, tmp_path):
    source = tmp_path / "segment"
    source.write_bytes(b"first segment")
    filename = "000000010000000000000001"
    assert run("backup_postgres.sh", "wal_archive", source, filename, env=environment).returncode == 0
    assert run("backup_postgres.sh", "wal_archive", source, filename, env=environment).returncode == 0
    source.write_bytes(b"different segment")
    assert run("backup_postgres.sh", "wal_archive", source, filename, env=environment).returncode != 0
    assert (Path(environment["BACKUP_DIR"]) / "wal" / filename).read_bytes() == b"first segment"


def test_wal_path_traversal_rejected(environment, tmp_path):
    source = tmp_path / "segment"
    source.write_bytes(b"data")
    assert run("backup_postgres.sh", "wal_archive", source, "../outside", env=environment).returncode != 0


def test_physical_base_and_pg16_recovery_prepare(environment, tmp_path):
    result = run("backup_postgres.sh", "base", env=environment)
    assert result.returncode == 0, result.stderr
    base = next((Path(environment["BACKUP_DIR"]) / "base").glob("base_*"))
    wal = Path(environment["BACKUP_DIR"]) / "wal"
    target = tmp_path / "recovery"
    args = ("--pitr", base, "--target-dir", target, "--wal-dir", wal, "--target-time", "2026-09-13T10:00:00Z")
    assert run("restore_postgres.sh", *args, "--dry-run", env=environment).returncode == 0
    assert not target.exists(), "dry run must not prepare a data directory"
    result = run("restore_postgres.sh", *args, env=environment)
    assert result.returncode == 0, result.stderr
    assert (target / "recovery.signal").is_file()
    assert "recovery_target_action = 'pause'" in (target / "postgresql.auto.conf").read_text()
    assert run("restore_postgres.sh", *args, env=environment).returncode != 0


def test_logical_dump_is_not_accepted_as_physical_base(environment, tmp_path):
    dump = tmp_path / "logical.dump"
    dump.write_bytes(b"dump")
    assert run("restore_postgres.sh", "--pitr", dump, env=environment).returncode != 0
