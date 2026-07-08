"""حارس ساكن — v151: نَسَب مصدر التعلّم (جسر #2) + تسجيل في المُشغّلَين + توافق مع core."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations" / "v151_learning_source_lineage.sql"


def test_migration_exists():
    assert MIG.exists()


def test_adds_lineage_columns_and_status():
    sql = MIG.read_text(encoding="utf-8")
    for col in (
        "source_type",
        "source_id",
        "field_id",
        "season_id",
        "recommendation_id",
        "decision_id",
        "evidence_snapshot_id",
        "traceability_status",
    ):
        assert col in sql, col
    # nullable + backfill (متوافق للخلف): DEFAULT 'unverified'، idempotent.
    assert "IF NOT EXISTS" in sql and "'unverified'" in sql
    assert "BEGIN" in sql and "COMMIT" in sql


def test_source_type_check_matches_core():
    sql = MIG.read_text(encoding="utf-8")
    from core.learning_source_lineage import VALID_SOURCE_TYPES

    for t in VALID_SOURCE_TYPES:
        assert t in sql, f"نوع مصدر {t} غير مذكور في قيد v151"


def test_registered_in_both_runners():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v151_learning_source_lineage.sql" in manifest
    assert "v151_learning_source_lineage.sql" in runner
