"""حارس FINDING-001 (تدقيق صور الأقمار v2، 2026-07-05): طلب «latest» لا يُعيد
تاريخاً تاريخيّاً أقدم بعد ترطيبه من القاعدة.

السيناريو المُعاد إنتاجه في التدقيق: ترطيب 2026-05-01 يملأ الذاكرة بطبقة db_ غير
مخصّصة بالتاريخ، ثمّ طلب latest يُعيدها كأحدث بلا استشارة القاعدة. الإصلاح: معرّفات
مخصّصة بالتاريخ + latest يستشير القاعدة ويختار الأحدث. ساكن+وحدويّ (بلا Postgres).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

RASTER = os.path.join(os.path.dirname(__file__), "..", "services", "raster-service")
_fastapi = importlib.util.find_spec("fastapi") is not None


@pytest.fixture
def rm():
    if not _fastapi:
        pytest.skip("fastapi غير متاح — يُنفَّذ في وظيفة الوحدات الكاملة")
    if RASTER not in sys.path:
        sys.path.insert(0, RASTER)
    spec = importlib.util.spec_from_file_location(
        "sahool_raster_main_for_latest_stale_test", os.path.join(RASTER, "main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    m._layers.clear()
    m._field_layers.clear()
    try:
        yield m
    finally:
        m._layers.clear()
        m._field_layers.clear()
        sys.modules.pop(spec.name, None)


def test_latest_consults_db_and_returns_newest_not_stale_rehydrate(rm, monkeypatch):
    field = "fld_stale_latest_demo"
    tenant = "11111111-1111-1111-1111-111111111111"
    rm._REQ_TENANT.set(tenant)

    # قاعدة وهميّة: طلب تاريخ محدّد يُعيد القديم؛ طلب latest يُعيد الأحدث.
    async def fake_fetch(field_id, index, date, tenant_id=None):
        newest = {
            "cog_url": "file:///tmp/newest.tif",
            "acquisition_date": "2026-06-10",
            "bounds_4326": [0, 0, 1, 1],
        }
        older = {
            "cog_url": "file:///tmp/older.tif",
            "acquisition_date": "2026-05-01",
            "bounds_4326": [0, 0, 1, 1],
        }
        return older if (date and date != "latest") else newest

    monkeypatch.setattr(
        rm.db_persist if hasattr(rm, "db_persist") else rm,
        "fetch_latest_asset",
        fake_fetch,
        raising=False,
    )
    import db_persist as _dbp

    monkeypatch.setattr(_dbp, "fetch_latest_asset", fake_fetch)
    monkeypatch.setattr(rm.object_store, "exists_locally", lambda *_a, **_k: True)

    # ١) رطّب تاريخاً محدّداً قديماً (يملأ الذاكرة).
    old = asyncio.run(rm._resolve_field_layer(field, "ndvi", "2026-05-01"))
    assert old is not None and old["acquisition_date"] == "2026-05-01"

    # ٢) اطلب latest — يجب أن يُعيد الأحدث (2026-06-10) لا القديم المُرطَّب.
    latest = asyncio.run(rm._resolve_field_layer(field, "ndvi", "latest"))
    assert latest is not None
    assert latest["acquisition_date"] == "2026-06-10", (
        f"latest أعاد تاريخاً قديماً ({latest['acquisition_date']}) — انحدار FINDING-001"
    )
