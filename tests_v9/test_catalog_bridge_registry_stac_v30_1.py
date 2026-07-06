"""حارس: جسر الكتالوج raster_assets→raster_registry (FINDING-008) + استمرار STAC (FINDING-009).

كلا الجدولَين (raster_registry/stac_item_registry، v114) كانا يفتقدان كاتباً من الأنبوب
فيبقى كتالوج GIS فارغاً. يؤكّد وجود دالّتَي الإدراج بـON CONFLICT الصحيح + ضبط المستأجِر،
تحويل درجة الجودة إلى int[0,100]، وربط الجسر في مسار الأصل وbackfill.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"
RASTER_MAIN = REPO / "services" / "raster-service" / "main.py"
# التفكيك (phase-4): جسر الكتالوج في مسار الأصل انتقل من main.py إلى
# raster_asset_persistence.py (main يعيد تصدير persist_raster_asset فقط).
RASTER_PERSIST = REPO / "services" / "raster-service" / "raster_asset_persistence.py"
FIELDS = REPO / "services" / "raster-service" / "routers" / "fields.py"


def _load_db_persist():
    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    spec = importlib.util.spec_from_file_location("raster_db_persist_cat", DB_PERSIST)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_bridge_functions_exist_with_conflict_and_tenant() -> None:
    src = DB_PERSIST.read_text(encoding="utf-8")
    assert "async def insert_raster_registry_entry" in src
    assert "async def insert_stac_item" in src
    # ON CONFLICT على المفاتيح الفريدة الصحيحة (v114).
    assert "ON CONFLICT (tenant_id, field_id, product_date, index_type, cog_url)" in src
    assert "ON CONFLICT (tenant_id, scene_id)" in src
    # ضبط سياق المستأجِر قبل الإدراج (احترام RLS FORCE + WITH CHECK).
    assert src.count("set_config('app.current_tenant'") >= 2


def test_quality_score_clamped_to_0_100() -> None:
    mod = _load_db_persist()
    assert mod._clamp_score_0_100(0.72) == 72, "0..1 يُضرب في 100"
    assert mod._clamp_score_0_100(85) == 85, "0..100 كما هي"
    assert mod._clamp_score_0_100(250) == 100, "يُقصَر أعلى 100"
    assert mod._clamp_score_0_100(-5) == 0, "يُقصَر أدنى 0"
    assert mod._clamp_score_0_100(None) is None, "None لا يُخترَع"


def test_registry_bridge_wired_in_asset_persist() -> None:
    src = (
        RASTER_MAIN.read_text(encoding="utf-8") + "\n" + RASTER_PERSIST.read_text(encoding="utf-8")
    )
    joined = " ".join(src.split())
    assert "db_persist.insert_raster_registry_entry(" in joined, "الجسر غير موصول بمسار الأصل"
    # لا نجسر أصلاً غير قابل للخدمة (file://).
    assert 'not str(cog_url).startswith("file://")' in joined


def test_stac_persistence_wired_in_backfill() -> None:
    src = FIELDS.read_text(encoding="utf-8")
    assert "async def _persist_selected_stac_scenes" in src
    assert "db_persist.insert_stac_item(" in src
    # يُجدوَل كمهمّة خلفيّة (لا يؤخّر ردّ backfill).
    joined = " ".join(src.split())
    assert "background_tasks.add_task( _persist_selected_stac_scenes" in joined, (
        "استمرار STAC يجب أن يُجدوَل كمهمّة خلفيّة"
    )
    assert "main.SENTINEL_COLLECTION" in src, "collection يجب أن يكون sentinel-2-l2a"
