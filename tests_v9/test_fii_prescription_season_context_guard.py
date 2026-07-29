from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_season_context_migration_is_expand_only_and_no_guessed_backfill():
    sql = (ROOT / "migrations/v193_prescriptions_season_context_expand.sql").read_text(
        encoding="utf-8"
    )
    assert "ADD COLUMN IF NOT EXISTS season_id TEXT" in sql
    assert "SET NOT NULL" not in sql.upper()
    assert "UPDATE prescriptions" not in sql
    assert "unresolved" in sql


def test_new_prescription_writes_require_season_id():
    source = (ROOT / "services/sahool-platform/api/routers/prescriptions.py").read_text(
        encoding="utf-8"
    )
    assert "FII_PRESCRIPTION_SEASON_MODE" in source
    assert "SEASON_CONTEXT_REQUIRED" in source
    assert "season_resolution_status" in source
