"""حُرّاس صدق النجاح/الحفظ للصور التاريخيّة (تدقيقات الأقمار v8/v9/v10).

فحوص ساكنة على المصدر تمنع انحدار «الحقيقة التشغيليّة الكاذبة»: لا مسار يُعلن
persisted/completed/available ما لم يثبت الحفظ الفعليّ، مع تتبّع النَّسَب والحالة.
كلّها منطق صرف (قراءة ملفّات) — بلا خدمات — فتُشغَّل تحت `pytest -m unit`.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
_PLATFORM = _ROOT / "services" / "sahool-platform" / "api"


def _read(rel: pathlib.Path) -> str:
    return rel.read_text(encoding="utf-8")


# ── V8-01/V10-03: عامل الفحص يعتمد job.result.persisted لا مجرّد completed ──
def test_backfill_worker_requires_persisted_truth():
    src = _read(_RASTER / "backfill_scan_worker.py")
    assert 'result.get("persisted") is True' in src, "worker يجب أن يشترط persisted الفعليّ"
    assert "main.JobStatus.completed and result.get" in src


# ── V9-01: مسار CDSE الأب يفصل الحفظ الفعليّ عن اكتمال المعالجة ──
def test_cdse_parent_tracks_persisted():
    # التفكيك (المرحلة ١٠): مسار CDSE الأب انتقل من main.py إلى raster_cdse_processing.py.
    src = _read(_RASTER / "raster_cdse_processing.py")
    assert "persisted_indices" in src, "مسار CDSE يجب أن يتتبّع الحفظ لكلّ مؤشّر"
    assert "cdse_persisted_count" in src


# ── V10-01: preflight لا يعدّ stale أصلاً موجوداً + يطابق مراجعة الهندسة ──
def test_backfill_preflight_requires_ready_and_geometry():
    src = _read(_RASTER / "backfill_scan_worker.py")
    assert "asset_status = 'ready'" in src, "preflight يجب أن يطلب أصلاً جاهزاً لا مجرّد غير فاشل"
    assert "geometry_revision = $6::int" in src, "preflight يجب أن يطابق مراجعة الهندسة"


# ── V8-08/V9-05/V10-04: الحالة النهائيّة completed_with_errors عند فشل عناصر ──
def test_backfill_run_completed_with_errors():
    src = _read(_RASTER / "backfill_scan_worker.py")
    assert "completed_with_errors" in src
    assert "items_persisted" in src and "items_failed" in src and "items_skipped" in src


# ── V9-04/V10-05: run_item يُوسم processing + job_id قبل المعالجة ──
def test_backfill_item_processing_and_job_id():
    src = _read(_RASTER / "backfill_scan_worker.py")
    assert "SET status='processing', job_id=$2" in src


# ── V10-06: الضبط المستأجِريّ داخل معاملة (set_config(local) يبقى سارياً) ──
def test_worker_tenant_set_within_transaction():
    for fname in ("backfill_scan_worker.py", "cache_invalidation_worker.py"):
        src = _read(_RASTER / fname)
        assert "conn.transaction()" in src, f"{fname} يجب أن يُغلّف الضبط المستأجِريّ في معاملة"


# ── V9-03: استعادة تشغيلة عالقة تجاوزت الإيجار (crash recovery) ──
def test_backfill_lease_reclaim():
    src = _read(_RASTER / "backfill_scan_worker.py")
    assert "make_interval(secs =>" in src, "يجب استعادة التشغيلات العالقة عبر مهلة الإيجار"
    assert "'searching', 'queued', 'processing'" in src


# ── V8-06/V9-08/V10-08: dedupe على مستوى المنتَج (بلا cog_uri في الهويّة) ──
def test_product_level_dedupe_excludes_cog_uri():
    src = _read(_RASTER / "db_persist.py")
    assert "ON CONFLICT (tenant_id, field_id, index_name, acquisition_date, scene_id)\n" in src, (
        "ON CONFLICT يجب أن يكون على مستوى المنتَج بلا cog_uri"
    )
    assert "cog_uri = EXCLUDED.cog_uri" in src, "cog_uri يجب أن يصير قابلاً للتحديث"
    # المهاجرتان مُسجَّلتان في كلا المُشغّلَين
    manifest = _read(_ROOT / "migrations" / "MANIFEST.txt")
    runner = _read(_ROOT / "scripts_v9" / "run_migrations.sql")
    for mig in ("v145_raster_assets_product_dedup.sql", "v146_backfill_runs_outcome_counters.sql"):
        assert mig in manifest, f"{mig} مفقودة من MANIFEST"
        assert mig in runner, f"{mig} مفقودة من run_migrations.sql"


# ── V8-07/V9-07/V10-07: sync fallback يمرّر geometry_revision + المنصّة تستنتجه ──
def test_geometry_revision_flows_through_all_paths():
    raster_fields = _read(_RASTER / "routers" / "fields.py")
    # المسار المتزامن الاحتياطيّ في raster
    assert raster_fields.count("geometry_revision=getattr(req") >= 2
    # المنصّة تستنتج المراجعة من field_geometry_history في مسار backfill proxy
    platform_fields = _read(_PLATFORM / "routers" / "fields.py")
    assert "SELECT MAX(revision) FROM field_geometry_history" in platform_fields
    assert 'payload["geometry_revision"]' in platform_fields


# ── V9-06/V8-04/V10: cdse-tilejson يقبل poly ويحقنه + fail-closed بلا حدود ──
def test_cdse_tilejson_poly_and_failclosed():
    src = _read(_RASTER / "routers" / "cdse_tiles.py")
    assert "poly: str | None = Query(None)" in src
    assert 'tile_params["poly"] = poly' in src
    assert "geom_resolved" in src, "بلا حدود حقيقيّة يجب ألا يُعلن available=true"


# ── V10-10: نقطة حالة تشغيلة backfill (لا نجاح أعمى) ──
def test_backfill_run_status_endpoint_exists():
    src = _read(_RASTER / "routers" / "fields.py")
    assert "/v1/fields/{field_id}/imagery/backfill/{run_id}" in src
    db = _read(_RASTER / "db_persist.py")
    assert "async def get_backfill_run_status" in db


# ── V9-10/V11-01: قرّاء الخريطة/الشريط الزمنيّ = 'ready' حصراً (stale غير مرئيّ) ──
def test_readers_require_ready_status():
    src = _read(_RASTER / "db_persist.py")
    # لا قارئ عرض يستعمل 'asset_status <> failed' (يُدخِل stale)؛ الكلّ = 'ready'.
    assert "asset_status <> 'failed'" not in src, "قرّاء العرض يجب أن يطلبوا ready لا مجرّد غير فاشل"
    assert src.count("asset_status = 'ready'") >= 4, (
        "fetch_latest + list_asset_dates + available_dates(×2)"
    )


# ── V11-04: الطبقة المُعاد ترطيبها تحمل النَّسَب/الهويّة (لا شبكة بلا field_id) ──
def test_rehydrated_layer_carries_lineage():
    # التفكيك (المرحلة ٣): انتقل التنفيذ من main.py إلى layer_lookup.py.
    src = _read(_RASTER / "layer_lookup.py")
    idx = src.find("async def rehydrate_field_layer_from_db")
    body = src[idx : idx + 2500]
    for key in ('"field_id": field_id', '"asset_status"', '"geometry_revision"', '"scene_id"'):
        assert key in body, f"طبقة الترطيب يجب أن تحمل {key}"
    # القارئ يُرجِع هذه الحقول أصلاً
    db = _read(_RASTER / "db_persist.py")
    assert '"asset_status": row["asset_status"]' in db


# ── V8-02/V8-03: العمّال مُفعَّلون افتراضاً في compose الإنتاج ──
def test_prod_compose_enables_async_and_invalidation():
    compose = _read(_ROOT / "docker-compose.v9.yml")
    assert "RASTER_ASYNC_BACKFILL_ENABLED: ${RASTER_ASYNC_BACKFILL_ENABLED:-true}" in compose
    assert (
        "RASTER_CACHE_INVALIDATION_ENABLED: ${RASTER_CACHE_INVALIDATION_ENABLED:-true}" in compose
    )
