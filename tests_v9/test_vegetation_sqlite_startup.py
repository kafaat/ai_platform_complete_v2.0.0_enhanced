"""Concurrent workers must initialize the same new anomaly database safely."""

import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vegetation_anomaly_sqlite", ROOT / "services/vegetation-analysis-service/anomaly_store.py"
)
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)
pytestmark = pytest.mark.unit


def test_concurrent_workers_initialize_one_new_wal_database(tmp_path, monkeypatch):
    connect = store.sqlite3.connect
    local = threading.local()
    barrier = threading.Barrier(8, timeout=10)

    def simultaneous_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        if not getattr(local, "started", False):
            local.started = True
            # Independent SQLite connections reach the first WAL transition together.
            barrier.wait()
        return conn

    monkeypatch.setattr(store.sqlite3, "connect", simultaneous_connect)
    path = str(tmp_path / "shared.db")
    with ThreadPoolExecutor(max_workers=8) as workers:
        stores = list(workers.map(lambda _: store.AnomalyStore(path), range(8)))
    with connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT count(*) FROM signal_anomalies").fetchone()[0] == 0
    assert len(stores) == 8


def test_unwritable_database_fails_without_retry(tmp_path):
    with pytest.raises(store.sqlite3.OperationalError, match="unable to open"):
        store.AnomalyStore(str(tmp_path))


@pytest.mark.parametrize("budget_exhausted", [False, True])
def test_wal_busy_retries_fresh_connection_and_honors_deadline(
    tmp_path, monkeypatch, budget_exhausted
):
    connect = store.sqlite3.connect
    connections = []
    closed = []

    class BusyOnce(store.sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == "PRAGMA journal_mode=WAL":
                error = store.sqlite3.OperationalError("database is locked")
                error.sqlite_errorcode = store.sqlite3.SQLITE_BUSY
                raise error
            return super().execute(sql, *args)

        def close(self):
            closed.append(self)
            super().close()

    def first_connection_busy(*args, **kwargs):
        if not connections:
            kwargs["factory"] = BusyOnce
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(store.sqlite3, "connect", first_connection_busy)
    if budget_exhausted:
        clock = iter([0, 0, 11])
        monkeypatch.setattr(store, "time", SimpleNamespace(monotonic=lambda: next(clock)))
        with pytest.raises(store.sqlite3.OperationalError, match="database is locked"):
            store.AnomalyStore(str(tmp_path / "busy.db"))
        assert len(connections) == 1
    else:
        database = store.AnomalyStore(str(tmp_path / "busy.db"))
        assert len(connections) == 2
        assert database.list("tenant", "field", "season") == []
    assert closed == [connections[0]]
