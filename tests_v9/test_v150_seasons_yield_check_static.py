"""حارس ساكن — v150: قيدا CHECK غير-سالبين على غلّة الموسم + تسجيل في المُشغّلَين.

منطق صرف (قراءة ملفّ) — يمنع انحدار تقوية سلامة الموسم (Season Integrity #3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations" / "v150_seasons_yield_nonnegative_check.sql"


def test_migration_file_exists():
    assert MIG.exists(), "v150 migration مفقود"


def test_defines_both_nonnegative_checks():
    sql = MIG.read_text(encoding="utf-8")
    assert "chk_seasons_actual_yield_nonneg" in sql
    assert "chk_seasons_target_yield_nonneg" in sql
    # القيد الفعليّ: NULL أو ≥ 0 (يطابق Pydantic ge=0).
    assert "actual_yield_kg_ha >= 0" in sql
    assert "target_yield_kg_ha >= 0" in sql


def test_is_idempotent_guarded():
    # فحص pg_constraint قبل الإضافة ⇒ آمن لإعادة التشغيل.
    sql = MIG.read_text(encoding="utf-8")
    assert "pg_constraint" in sql
    assert "IF NOT EXISTS" in sql
    assert "BEGIN" in sql and "COMMIT" in sql


def test_registered_in_both_runners():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v150_seasons_yield_nonnegative_check.sql" in manifest
    assert "v150_seasons_yield_nonnegative_check.sql" in runner
