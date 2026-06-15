"""Tests for field_state, lab cycle, consent — the real gaps from v9.1.0 review."""

import os
import tempfile
from pathlib import Path

from storage import lite_store


def _db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    lite_store.init_db(db)
    return db


class TestFieldState:
    def test_save_and_get_field_state(self):
        db = _db()
        lite_store.save_field_state("F1", "t1", "limited", "skip", 50, db_path=db)
        s = lite_store.get_field_state("F1", db_path=db)
        assert s["quality_state"] == "limited"
        assert s["completeness"] == 50
        os.unlink(db)

    def test_field_state_upsert(self):
        db = _db()
        lite_store.save_field_state("F1", "t1", "blocked", db_path=db)
        lite_store.save_field_state("F1", "t1", "ready", completeness=100, db_path=db)
        s = lite_store.get_field_state("F1", db_path=db)
        assert s["quality_state"] == "ready"  # updated, not duplicated
        os.unlink(db)

    def test_lab_cycle_pending_to_ready(self):
        db = _db()
        lite_store.save_field_state("F2", "t1", "pending_lab", db_path=db)
        lite_store.create_lab_request("F2", "t1", db_path=db)
        result = lite_store.receive_lab_results("F2", db_path=db)
        assert result["new_state"] == "ready"
        assert result["notify"]
        s = lite_store.get_field_state("F2", db_path=db)
        assert s["quality_state"] == "ready"
        os.unlink(db)

    def test_consent_recorded(self):
        db = _db()
        lite_store.record_consent("t1", "data_governance", "v1.0", db_path=db)
        with lite_store.connect(db) as conn:
            n = conn.execute("SELECT COUNT(*) c FROM user_consent").fetchone()["c"]
        assert n == 1
        os.unlink(db)

    def test_tenant_isolation_columns(self):
        # multi-tenant: every state row carries tenant_id
        db = _db()
        lite_store.save_field_state("F1", "tenant_A", "ready", db_path=db)
        s = lite_store.get_field_state("F1", db_path=db)
        assert s["tenant_id"] == "tenant_A"
        os.unlink(db)
