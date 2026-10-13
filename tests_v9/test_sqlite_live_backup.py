"""Live SQLite snapshots preserve WAL commits without publishing partial files."""

import importlib.util
import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SOURCE = Path(__file__).resolve().parents[1] / "services/sahool-platform/storage/lite_store.py"
_SPEC = importlib.util.spec_from_file_location("sqlite_backup_store", _SOURCE)
store = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(store)


@pytest.fixture
def live_db(tmp_path):
    db = tmp_path / "live.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, payload TEXT)")
    writer.execute("INSERT INTO records VALUES (1, 'committed')")
    writer.commit()
    assert Path(str(db) + "-wal").stat().st_size > 0
    try:
        yield db, writer
    finally:
        writer.close()


def read_rows(path):
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        return connection.execute("SELECT id, payload FROM records ORDER BY id").fetchall()
    finally:
        connection.close()


def test_snapshot_includes_committed_wal_but_excludes_uncommitted_rows(live_db, tmp_path):
    db, writer = live_db
    writer.execute("INSERT INTO records VALUES (2, 'uncommitted')")
    result = store.backup_db(db, str(tmp_path / "snapshots"))
    assert isinstance(result, str)
    assert read_rows(result) == [(1, "committed")]
    assert writer.in_transaction
    assert writer.execute("SELECT COUNT(*) FROM records").fetchone() == (2,)
    assert not Path(result + "-wal").exists()
    assert not Path(result + "-shm").exists()


def test_concurrent_backups_publish_distinct_complete_snapshots(live_db, tmp_path):
    db, _ = live_db
    destination = tmp_path / "snapshots"
    destination.mkdir()
    existing = destination / "sahool_existing.db"
    existing.write_bytes(b"previous snapshot")
    with ThreadPoolExecutor(max_workers=4) as workers:
        paths = list(workers.map(lambda _: store.backup_db(db, str(destination)), range(8)))
    assert len(set(paths)) == 8
    assert all(read_rows(path) == [(1, "committed")] for path in paths)
    assert existing.read_bytes() == b"previous snapshot"
    assert not list(destination.glob(".sahool_*"))


def test_foreign_key_failure_does_not_publish_snapshot(tmp_path):
    db = tmp_path / "invalid.db"
    with sqlite3.connect(db) as source:
        source.executescript(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
            "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));"
            "INSERT INTO child VALUES (99);"
        )
    destination = tmp_path / "snapshots"
    with pytest.raises(sqlite3.IntegrityError, match="foreign key check"):
        store.backup_db(db, str(destination))
    assert list(destination.iterdir()) == []


def test_missing_source_is_not_created_or_published(tmp_path):
    missing = tmp_path / "missing.db"
    destination = tmp_path / "snapshots"
    with pytest.raises(sqlite3.OperationalError):
        store.backup_db(missing, str(destination))
    assert not missing.exists()
    assert list(destination.iterdir()) == []


def test_interrupted_copy_never_publishes_partial_database(live_db, tmp_path, monkeypatch):
    db, _ = live_db
    destination = tmp_path / "snapshots"
    real_connect = sqlite3.connect

    class InterruptedSource(sqlite3.Connection):
        def backup(self, target, **kwargs):
            target.execute("CREATE TABLE partial (id INTEGER)")
            target.commit()
            raise sqlite3.OperationalError("copy interrupted")

    def connect_with_interrupted_source(database, *args, **kwargs):
        if kwargs.get("uri"):
            kwargs["factory"] = InterruptedSource
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect_with_interrupted_source)
    with pytest.raises(sqlite3.OperationalError, match="copy interrupted"):
        store.backup_db(db, str(destination))
    assert list(destination.iterdir()) == []


def test_publication_failure_keeps_existing_snapshot_and_cleans_temporary(
    live_db, tmp_path, monkeypatch
):
    db, _ = live_db
    destination = tmp_path / "snapshots"
    destination.mkdir()
    existing = destination / "sahool_existing.db"
    existing.write_bytes(b"previous snapshot")

    def refuse_publish(*args):
        raise OSError("publication unavailable")

    monkeypatch.setattr("os.link", refuse_publish)
    with pytest.raises(OSError, match="publication unavailable"):
        store.backup_db(db, str(destination))
    assert list(destination.iterdir()) == [existing]
    assert existing.read_bytes() == b"previous snapshot"


@pytest.mark.skipif(os.name != "posix", reason="Directory fsync is a POSIX durability guarantee")
def test_directory_sync_failure_retracts_snapshot(live_db, tmp_path, monkeypatch):
    db, _ = live_db
    destination = tmp_path / "snapshots"
    real_fsync = os.fsync

    def fail_directory_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory sync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="directory sync failed"):
        store.backup_db(db, str(destination))
    assert list(destination.iterdir()) == []
