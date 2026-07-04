"""حارس: فشل قناع المضلّع ⇒ fail-closed (لا بلاطة غير مقنّعة تُخدَّم/تُخزَّن).

الخلل (قبل v29.8): عند فشل ``apply_polygon_mask`` كان الكود يسجّل تحذيراً ثمّ
**يُخزِّن ويُخدِّم** البلاطة غير المقنّعة — تسريب بصريّ خارج حدّ الحقل (fail-open)،
يناقض فلسفة fail-closed للنظام (killswitch/RLS). الإصلاح: عند فشل القناع نتخلّص من
الملفّ المؤقّت ونُعيد None (⇒ الراوتر يُرجِع PNG شفّافة).

هذا اختبار مصدريّ (لا يشغّل rasterio/الشبكة): يتأكّد أنّ فرع فشل القناع يحوي
``return None`` وتنظيف الملفّ، ولا يصل إلى سطر التخزين في الـcache.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TILES = REPO / "services" / "raster-service" / "routers" / "cdse_tiles.py"


@pytest.mark.unit
def test_mask_failure_is_fail_closed() -> None:
    src = TILES.read_text(encoding="utf-8")
    # استخرج كتلة apply_polygon_mask + المُعالِج التالي حتّى سطر التخزين.
    idx = src.find("apply_polygon_mask(cog_path")
    assert idx != -1, "استدعاء apply_polygon_mask اختفى — تحقّق من مسار البلاطة"
    # النافذة من الاستدعاء حتّى أوّل إسناد للـcache بعده.
    cache_idx = src.find("_cdse_tile_cache[cache_key]", idx)
    assert cache_idx != -1, "لم يُعثر على تخزين الـcache بعد القناع"
    block = src[idx:cache_idx]

    # يجب أن يحوي فرع الاستثناء return None (fail-closed) قبل الوصول للتخزين.
    assert "except" in block, "فرع معالجة فشل القناع مفقود"
    assert "return None" in block, (
        "فشل القناع لا يُرجِع None قبل التخزين — بلاطة غير مقنّعة قد تُخدَّم (fail-open)"
    )
    # يجب تنظيف الملفّ المؤقّت عند الفشل (لا تسريب قرص).
    assert re.search(r"os\.unlink\(cog_path\)", block), "فشل القناع لا ينظّف الملفّ المؤقّت"


@pytest.mark.unit
def test_cache_stored_only_after_successful_mask() -> None:
    """التخزين في الـcache يقع بعد نجاح القناع فقط (لا قبله ولا في فرع الفشل)."""
    src = TILES.read_text(encoding="utf-8")
    mask_idx = src.find("apply_polygon_mask(cog_path")
    cache_idx = src.find("_cdse_tile_cache[cache_key]", mask_idx)
    # لا يوجد تخزين cache بين استدعاء القناع وفرع الفشل (return None يسبق التخزين).
    fail_return = src.find("return None", mask_idx)
    assert fail_return != -1 and fail_return < cache_idx, (
        "return None لفشل القناع يجب أن يسبق تخزين الـcache"
    )
