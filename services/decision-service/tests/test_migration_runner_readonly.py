"""Regression tests: migration readiness must be read-only."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "decision_migration_runner_readonly", SERVICE_DIR / "migration_runner.py"
)
mr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mr)


class FakeConn:
    def __init__(self, *, journal_exists: bool, rows=None):
        self.journal_exists = journal_exists
        self.rows = rows or []
        self.execute_calls = []
        self.fetch_calls = []

    async def fetchval(self, sql, *args):
        assert "to_regclass" in sql
        assert args == ("public.decision_service_schema_migrations",)
        return self.journal_exists

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        return self.rows

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        raise AssertionError("read-only migration check attempted DDL/DML")


def test_applied_versions_missing_journal_is_read_only():
    conn = FakeConn(journal_exists=False)
    result = asyncio.run(mr.applied_versions(conn))
    assert result == {}
    assert conn.fetch_calls == []
    assert conn.execute_calls == []


def test_applied_versions_existing_journal_reads_rows_only():
    conn = FakeConn(
        journal_exists=True,
        rows=[{"version": "001_decision_sor.sql", "checksum": "abc"}],
    )
    result = asyncio.run(mr.applied_versions(conn))
    assert result == {"001_decision_sor.sql": "abc"}
    assert len(conn.fetch_calls) == 1
    assert conn.execute_calls == []


def test_missing_journal_reports_all_known_migrations_pending(monkeypatch):
    migrations = [
        mr.Migration("001.sql", Path("001.sql"), "a", "SELECT 1"),
        mr.Migration("002.sql", Path("002.sql"), "b", "SELECT 2"),
    ]
    conn = FakeConn(journal_exists=False)

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
    assert conn.execute_calls == []
