"""Tests for v9.1 valid review points: PRAGMAs, backup, sanitization."""

import os
import tempfile
from pathlib import Path

import pytest
from storage import lite_store


def _db():
    db = Path(tempfile.mktemp(suffix=".db"))
    lite_store.init_db(db)
    return db


class TestSecurityV91:
    def test_foreign_keys_enabled(self):
        db = _db()
        with lite_store.connect(db) as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        os.unlink(db)

    def test_busy_timeout_set(self):
        db = _db()
        with lite_store.connect(db) as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        os.unlink(db)

    def test_backup_creates_file(self):
        db = _db()
        bdir = tempfile.mkdtemp()
        bk = lite_store.backup_db(db, backup_dir=bdir)
        assert os.path.exists(bk)
        os.unlink(db)

    def test_sanitize_valid_id(self):
        assert lite_store.sanitize_id("al_jawf") == "al_jawf"
        assert lite_store.sanitize_id("farm-001") == "farm-001"

    def test_sanitize_rejects_traversal(self):
        for bad in ("../../etc/passwd", "a/b", "x;rm -rf", "'; DROP"):
            with pytest.raises(ValueError):
                lite_store.sanitize_id(bad)
