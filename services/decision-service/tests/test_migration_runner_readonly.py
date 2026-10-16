"""Regression tests: migration readiness must be read-only."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "decision_migration_runner_readonly", SERVICE_DIR / "migration_runner.py"
)
mr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mr
SPEC.loader.exec_module(mr)


class ReadOnlyConnectionProbe:
    def __init__(self, *, journal_exists: bool, rows=None):
        self.journal_exists = journal_exists
        self.rows = rows or []
        self.mutation_attempts = []
        self.fetch_calls = []

    async def fetchval(self, sql, *args):
        assert "to_regclass" in sql
        assert args == ("public.decision_service_schema_migrations",)
        return self.journal_exists

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        return self.rows

    async def execute(self, sql, *args):
        self.mutation_attempts.append((sql, args))
        raise AssertionError("read-only migration check attempted DDL/DML")


def test_applied_versions_missing_journal_is_read_only():
    conn = ReadOnlyConnectionProbe(journal_exists=False)
    result = asyncio.run(mr.applied_versions(conn))
    assert result == {}
    assert conn.fetch_calls == []
    assert conn.mutation_attempts == []


def test_scoped_034_rejects_unapproved_source_before_connecting(monkeypatch):
    async def connect():
        pytest.fail("a source checksum mismatch must fail before connecting")

    monkeypatch.setattr(mr, "_connect", connect)
    monkeypatch.setenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
    with pytest.raises(RuntimeError, match="reviewed SHA-256"):
        asyncio.run(mr.apply_composition_only("0" * 64))


def test_scoped_034_requires_explicit_schema_authorization(monkeypatch):
    monkeypatch.delenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", raising=False)
    with pytest.raises(SystemExit, match="Refusing to apply"):
        asyncio.run(mr.apply_composition_only("0" * 64))


@pytest.mark.parametrize(
    "fault", ["prior_pending", "prior_checksum", "target_checksum", "later_checksum", "unknown"]
)
def test_scoped_034_journal_plan_fails_closed(fault):
    migrations = mr.load_migrations()
    prior = [m for m in migrations if m.version < mr.COMPOSITION_VERSION]
    target = next(m for m in migrations if m.version == mr.COMPOSITION_VERSION)
    later = next(m for m in migrations if m.version > mr.COMPOSITION_VERSION)
    applied = {m.version: m.checksum for m in prior}
    if fault == "prior_pending":
        applied.pop(prior[-1].version)
    elif fault == "prior_checksum":
        applied[prior[0].version] = "altered"
    elif fault == "target_checksum":
        applied[target.version] = "altered"
    elif fault == "later_checksum":
        applied[later.version] = "altered"
    else:
        applied["999_unknown.sql"] = "unreviewed"
    with pytest.raises(RuntimeError):
        mr._validate_composition_journal(migrations, applied)


def test_scoped_034_allows_later_pending_and_repeat():
    migrations = mr.load_migrations()
    for ceiling in [
        "033_tenant_boundary_hardening.sql",
        mr.COMPOSITION_VERSION,
        migrations[-1].version,
    ]:
        applied = {m.version: m.checksum for m in migrations if m.version <= ceiling}
        mr._validate_composition_journal(migrations, applied)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--apply-034-only"],
        ["--check", "--expected-sha256", "0" * 64],
        ["--apply", "--expected-sha256", "0" * 64],
        ["--inspect-034", "--expected-sha256", "0" * 64],
    ],
)
def test_scoped_034_cli_requires_an_unambiguous_operation(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["migration_runner.py", *arguments])
    with pytest.raises(SystemExit) as exc:
        mr.main()
    assert exc.value.code == 2


def test_applied_versions_existing_journal_reads_rows_only():
    conn = ReadOnlyConnectionProbe(
        journal_exists=True,
        rows=[{"version": "001_decision_sor.sql", "checksum": "abc"}],
    )
    result = asyncio.run(mr.applied_versions(conn))
    assert result == {"001_decision_sor.sql": "abc"}
    assert len(conn.fetch_calls) == 1
    assert conn.mutation_attempts == []


def test_missing_journal_reports_all_known_migrations_pending(monkeypatch):
    migrations = [
        mr.Migration("001.sql", Path("001.sql"), "a", "SELECT 1"),
        mr.Migration("002.sql", Path("002.sql"), "b", "SELECT 2"),
    ]
    conn = ReadOnlyConnectionProbe(journal_exists=False)

    async def connect():
        return conn

    async def close():
        return None

    conn.close = close
    monkeypatch.setattr(mr, "load_migrations", lambda: migrations)
    monkeypatch.setattr(mr, "_connect", connect)

    result = asyncio.run(mr.check_migrations())
    assert result == {
        "ok": False,
        "pending": ["001.sql", "002.sql"],
        "checksum_mismatches": [],
        "known_migrations": ["001.sql", "002.sql"],
    }
    assert conn.mutation_attempts == []


@pytest.mark.parametrize("changed", ["033", "034"])
def test_scoped_pair_checks_both_source_hashes_before_connect(monkeypatch, changed):
    async def connect():
        pytest.fail("source checksums must be verified before connecting")

    monkeypatch.setattr(mr, "_connect", connect)
    monkeypatch.setenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
    known = {m.version: m.checksum for m in mr.load_migrations()}
    first = "0" * 64 if changed == "033" else known[mr.HARDENING_VERSION]
    second = "0" * 64 if changed == "034" else known[mr.COMPOSITION_VERSION]
    with pytest.raises(RuntimeError, match="reviewed SHA-256"):
        asyncio.run(mr.apply_hardening_pair(first, second))


def test_scoped_pair_accepts_real_032_baseline_but_034_only_rejects_it():
    migrations = mr.load_migrations()
    applied = {m.version: m.checksum for m in migrations if m.version < mr.HARDENING_VERSION}
    mr._validate_composition_journal(migrations, applied, include_hardening=True)
    with pytest.raises(RuntimeError, match="033"):
        mr._validate_composition_journal(migrations, applied)


@pytest.mark.parametrize(
    "fault",
    ["missing_032", "checksum_001", "checksum_033", "checksum_034", "unknown", "034_without_033"],
)
def test_scoped_pair_rejects_invalid_journal(fault):
    migrations = mr.load_migrations()
    applied = {m.version: m.checksum for m in migrations if m.version < mr.HARDENING_VERSION}
    if fault == "missing_032":
        applied.pop(max(applied))
    elif fault == "checksum_001":
        applied[min(applied)] = "altered"
    elif fault == "checksum_033":
        applied[mr.HARDENING_VERSION] = "altered"
    elif fault == "checksum_034":
        applied[mr.HARDENING_VERSION] = next(
            m.checksum for m in migrations if m.version == mr.HARDENING_VERSION
        )
        applied[mr.COMPOSITION_VERSION] = "altered"
    elif fault == "034_without_033":
        applied[mr.COMPOSITION_VERSION] = next(
            m.checksum for m in migrations if m.version == mr.COMPOSITION_VERSION
        )
    else:
        applied["999_unreviewed.sql"] = "unknown"
    with pytest.raises(RuntimeError):
        mr._validate_composition_journal(migrations, applied, include_hardening=True)


def test_scoped_boundary_executor_rejects_any_extra_migration():
    with pytest.raises(RuntimeError, match="explicit 034 or 033"):
        asyncio.run(
            mr._apply_boundary_scope(
                {
                    mr.HARDENING_VERSION: "a",
                    mr.COMPOSITION_VERSION: "b",
                    "035_decision_version_binding.sql": "c",
                }
            )
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--apply-033-034-only"],
        ["--apply-033-034-only", "--expected-sha256", "0" * 64],
        ["--apply-033-034-only", "--expected-033-sha256", "0" * 64],
        ["--apply-034-only", "--expected-033-sha256", "0" * 64, "--expected-sha256", "0" * 64],
        ["--check", "--expected-033-sha256", "0" * 64],
    ],
)
def test_scoped_pair_cli_requires_both_hashes_and_exact_operation(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["migration_runner.py", *arguments])
    with pytest.raises(SystemExit) as exc:
        mr.main()
    assert exc.value.code == 2
