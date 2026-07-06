"""حارس: v143 دورة حياة أصول الراستر (asset_status) + نَسَب الهندسة (geometry_revision).

من تدقيق الأقمار (v2):
- FINDING-011: raster_assets بلا عمود حالة ⇒ لا تمييز جاهز/فاشل/بائت.
- FINDING-004: geometry_revision غير مربوط بمخرجات raster-service.

يؤكّد أنّ: الترحيل v143 مُسجَّل في المُشغّلَين ويضيف العمودين + القيد + الفهارس؛
insert_raster_asset يكتبهما؛ القرّاء يصفّون 'failed'؛ نماذج الطلب تحمل geometry_revision؛
والمنصّة تحلّ المراجعة وتمرّرها عبر مُطلِق المعالجة.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "migrations" / "v143_raster_assets_lifecycle_lineage.sql"
MANIFEST = REPO / "migrations" / "MANIFEST.txt"
RUN_SQL = REPO / "scripts_v9" / "run_migrations.sql"
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"
RASTER_MAIN = REPO / "services" / "raster-service" / "main.py"
IMAGERY_AUTO = REPO / "services" / "sahool-platform" / "api" / "imagery_automation.py"
PLATFORM_FIELDS = REPO / "services" / "sahool-platform" / "api" / "routers" / "fields.py"


def test_v143_migration_registered_in_both_runners() -> None:
    name = "v143_raster_assets_lifecycle_lineage.sql"
    assert name in MANIFEST.read_text(encoding="utf-8"), "v143 غائب عن MANIFEST"
    assert name in RUN_SQL.read_text(encoding="utf-8"), "v143 غائب عن run_migrations.sql"


def test_v143_adds_status_and_revision_columns() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS asset_status" in sql
    assert "CHECK (asset_status IN ('pending', 'ready', 'stale', 'failed'))" in sql
    assert "ADD COLUMN IF NOT EXISTS geometry_revision" in sql
    assert "idx_raster_assets_ready" in sql
    assert "idx_raster_assets_geometry_revision" in sql


def test_insert_writes_status_and_revision() -> None:
    body = _load_and_read(DB_PERSIST, "def insert_raster_asset", span=3600)
    for col in ("asset_status", "geometry_revision"):
        assert col in body, f"INSERT لا يكتب {col}"
    # التوقيع يقبل القيمتين.
    if "asyncpg" not in _sys().modules:
        import types as _t

        _sys().modules["asyncpg"] = _t.ModuleType("asyncpg")
    spec = importlib.util.spec_from_file_location("raster_db_persist_v143", DB_PERSIST)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    params = inspect.signature(mod.insert_raster_asset).parameters
    assert "geometry_revision" in params and "asset_status" in params


def test_readers_filter_failed_assets() -> None:
    src = DB_PERSIST.read_text(encoding="utf-8")
    # v11-F1: شُدِّد الفلتر من «غير فاشل» إلى «ready حصراً» — 'stale' (هندسة قديمة بعد
    # تغيّر الحدود) لم يعد يُقدَّم كصورة صالحة للخريطة/الشريط الزمنيّ. لا قارئ عرض يبقى
    # على '<> failed' (يُدخِل stale)؛ القرّاء الثلاثة = 'ready'.
    assert "asset_status <> 'failed'" not in src, (
        "قرّاء العرض يجب أن يطلبوا 'ready' لا مجرّد غير فاشل"
    )
    assert src.count("asset_status = 'ready'") >= 3, "قرّاء الأصول يجب أن يصفّوا 'ready' حصراً"


def test_request_models_carry_geometry_revision() -> None:
    # نماذج الطلب/الاستجابة انتقلت إلى raster_api_models.py بعد التفكيك (phase10).
    api_models = REPO / "services" / "raster-service" / "raster_api_models.py"
    src = RASTER_MAIN.read_text(encoding="utf-8") + "\n" + api_models.read_text(encoding="utf-8")
    # ProcessRequest + BatchProcessRequest + ProcessCdseRequest + ProcessFromStacRequest.
    assert src.count("geometry_revision: int | None = None") >= 4, (
        "ليست كلّ نماذج الطلب تحمل geometry_revision"
    )
    # المُثابر يمرّر النَّسَب (انتقل جسمه إلى raster_asset_persistence.py بعد التفكيك).
    persist = (REPO / "services" / "raster-service" / "raster_asset_persistence.py").read_text(
        encoding="utf-8"
    )
    joined = " ".join((src + " " + persist).split())
    assert 'geometry_revision=getattr(req, "geometry_revision", None)' in joined


def test_platform_resolves_and_threads_revision() -> None:
    fields = PLATFORM_FIELDS.read_text(encoding="utf-8")
    assert "MAX(revision) FROM field_geometry_history" in fields, "المنصّة لا تحلّ المراجعة السارية"
    assert "geometry_revision=" in fields, "refresh_field_imagery لا يمرّر geometry_revision"
    auto = IMAGERY_AUTO.read_text(encoding="utf-8")
    assert auto.count('"geometry_revision": geometry_revision') >= 2, (
        "الحمولات (cdse + from-stac) لا تحمل geometry_revision"
    )


def _sys():
    import sys

    return sys


def _load_and_read(path: Path, marker: str, span: int) -> str:
    src = path.read_text(encoding="utf-8")
    idx = src.find(marker)
    assert idx != -1, f"لم يُعثَر على {marker!r}"
    return src[idx : idx + span]
