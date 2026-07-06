"""حارس: بنية backfill اللاتزامنيّة (v5-F1/F2/F4 · v6-F1/F2/F4).

يؤكّد أنّ: ترحيل v144 مُسجَّل في المُشغّلَين ويُنشئ backfill_runs/run_items بـidempotency +
RLS؛ النقطة تُرجِع run_id فوراً خلف راية؛ العامل يطالب بـFOR UPDATE SKIP LOCKED ويطبّق
idempotency (ON CONFLICT DO NOTHING) + preflight؛ وموصول كخدمة compose خلف راية.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "migrations" / "v144_backfill_runs.sql"
MANIFEST = REPO / "migrations" / "MANIFEST.txt"
RUN_SQL = REPO / "scripts_v9" / "run_migrations.sql"
FIELDS = REPO / "services" / "raster-service" / "routers" / "fields.py"
WORKER = REPO / "services" / "raster-service" / "backfill_scan_worker.py"
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"
COMPOSE = REPO / "docker-compose.v9.yml"


def test_v144_registered_and_shapes() -> None:
    assert "v144_backfill_runs.sql" in MANIFEST.read_text(encoding="utf-8")
    assert "v144_backfill_runs.sql" in RUN_SQL.read_text(encoding="utf-8")
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS backfill_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS backfill_run_items" in sql
    assert "UNIQUE (tenant_id, idempotency_key)" in sql, "مفتاح idempotency الفريد مطلوب"
    # RLS FORCE على الجدولَين.
    assert sql.count("FORCE ROW LEVEL SECURITY") >= 2


def test_endpoint_returns_run_id_behind_flag() -> None:
    src = FIELDS.read_text(encoding="utf-8")
    assert "def _async_backfill_enabled(" in src
    assert "RASTER_ASYNC_BACKFILL_ENABLED" in src
    joined = " ".join(src.split())
    assert "_dbp.insert_backfill_run(" in joined, "المسار اللاتزامنيّ لا يُنشئ تشغيلة"
    assert '"mode": "async"' in joined and '"run_id": run_id' in joined
    # يبقى المسار المتزامن كتدهور لطيف (dry_run + فشل الإنشاء).
    assert "if _async_backfill_enabled() and not req.dry_run:" in src


def test_worker_claims_idempotent_preflight_and_flag() -> None:
    src = WORKER.read_text(encoding="utf-8")
    assert "FOR UPDATE SKIP LOCKED" in src, "المطالبة يجب أن تكون FOR UPDATE SKIP LOCKED"
    assert "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING" in src, "idempotency مفقود"
    assert "SELECT 1 FROM raster_assets" in src, "preflight على raster_assets مفقود"
    assert "asyncio.to_thread(" in src, "المعالجة الثقيلة يجب أن تكون في threadpool"
    assert "RASTER_ASYNC_BACKFILL_ENABLED" in src
    assert "JOBS_DATABASE_URL" in src
    # يعيد استخدام الوحدات المفكَّكة (phase21: العامل لا يستورد main — لا تكرار منطق).
    # مسح STAC عبر stac_search_helpers.stac_search؛ المعالجة عبر raster_processing_runtime.run_processing.
    assert (
        "stac_search_helpers.stac_search" in src
        and "raster_processing_runtime.run_processing" in src
    )


def test_insert_backfill_run_helper_exists() -> None:
    src = DB_PERSIST.read_text(encoding="utf-8")
    assert "async def insert_backfill_run(" in src
    assert "'planned'" in src, "التشغيلة تبدأ planned"
    # ربط التاريخ عبر ::text::date (درس c564d65: نصّ لـ$::date يفشل).
    assert "$4::text::date" in src


def test_compose_wires_backfill_scan_worker() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-raster-backfill-scan-worker:" in compose
    assert "backfill_scan_worker" in compose
    assert "RASTER_ASYNC_BACKFILL_ENABLED" in compose
