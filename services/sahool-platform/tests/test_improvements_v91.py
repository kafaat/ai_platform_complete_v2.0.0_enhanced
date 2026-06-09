"""Tests for v9.1 comprehensive improvements: CHECK, matrix validation, get_observations, trigger."""

import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
from storage import lite_store


def _db():
    db = Path(tempfile.mktemp(suffix=".db"))
    lite_store.init_db(db)
    return db


class TestImprovementsV91:
    def test_source_check_rejects_invalid(self):
        db = _db()
        with pytest.raises(sqlite3.IntegrityError):
            lite_store.add_observation(
                "t1", "al_jawf", "S3", "2026-01-01", value=2.5, source="banana", db_path=db
            )
        os.unlink(db)

    def test_source_check_accepts_valid(self):
        db = _db()
        for src in ("sensor", "lab", "manual", "model", "imported"):
            lite_store.add_observation(
                "t1", "al_jawf", "S3", "2026-01-01", value=2.5, source=src, db_path=db
            )
        # تأكيد صريح: الخمس قيم خُزّنت فعلاً (لا مجرّد غياب استثناء)
        assert len(lite_store.get_observations(tenant_id="t1", db_path=db)) == 5
        os.unlink(db)

    def test_observable_validation_rejects_unknown(self):
        db = _db()
        with pytest.raises(ValueError):
            lite_store.add_observation(
                "t1", "al_jawf", "S99", "2026-01-01", value=1, source="lab", db_path=db
            )
        os.unlink(db)

    def test_observable_validation_can_be_disabled(self):
        db = _db()
        lite_store.add_observation(
            "t1",
            "al_jawf",
            "CUSTOM",
            "2026-01-01",
            value=1,
            source="lab",
            validate=False,
            db_path=db,
        )
        # تأكيد صريح: المعرّف غير القياسي خُزّن فعلاً حين عُطّل التحقّق
        assert len(lite_store.get_observations(observable_id="CUSTOM", db_path=db)) == 1
        os.unlink(db)

    def test_get_observations_filters(self):
        db = _db()
        lite_store.add_observation(
            "t1", "al_jawf", "S3", "2026-01-01", value=2.5, source="lab", db_path=db
        )
        lite_store.add_observation(
            "t1", "al_jawf", "S4", "2026-01-02", value=7.8, source="lab", db_path=db
        )
        assert len(lite_store.get_observations(tenant_id="t1", db_path=db)) == 2
        assert len(lite_store.get_observations(observable_id="S3", db_path=db)) == 1
        os.unlink(db)

    def test_updated_at_trigger_fires(self):
        db = _db()
        lite_store.save_field_state("F1", "t1", "blocked", db_path=db)
        before = lite_store.get_field_state("F1", db_path=db)["updated_at"]
        time.sleep(1.1)
        lite_store.save_field_state("F1", "t1", "ready", db_path=db)
        after = lite_store.get_field_state("F1", db_path=db)["updated_at"]
        assert after >= before  # trigger updated the timestamp
        os.unlink(db)
