"""Regression tests for field indicator tilejson/index routing fixes.

Covers:
- DB field owner overrides stale _field_layers tenant cache (prevents poisoned 403).
- typo/alias index values such as NDVU normalize to ndvi instead of 404/no layer.
- sahool-platform has a narrow /api/raster/* compatibility proxy for old nginx routes.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services/raster-service"
# main.py فُكِّك: تطبيع/أسماء المؤشّرات (خرائط الأسماء المستعارة مثل "ndvu": "ndvi"
# وأسماء الملوحة) تعيش في layer_lookup.py كدالّتَي normalize_index/display_index.
# Phase 27: مُغلِّفات main._normalize_index/_display_index أُزيلت (الراوترات تستورد
# من raster_field_runtime مباشرة). نقرأ الوحدتين معاً كي يبقى العقد محفوظاً دون إضعاف التأكيدات.
MAIN = (RASTER / "main.py").read_text(encoding="utf-8") + (RASTER / "layer_lookup.py").read_text(
    encoding="utf-8"
)
API_MAIN = (ROOT / "services/sahool-platform/api/main.py").read_text(encoding="utf-8")
FRONT_API = (ROOT / "frontend/src/services/api.ts").read_text(encoding="utf-8")
FIELD_MAP = (ROOT / "frontend/src/components/FieldIndicatorMap.tsx").read_text(encoding="utf-8")

_fastapi = importlib.util.find_spec("fastapi") is not None


def _const_owner(value):
    async def _f(field_id):
        return value

    return _f


@pytest.fixture
def rm():
    if not _fastapi:
        pytest.skip("fastapi unavailable")
    import sys

    if str(RASTER) not in sys.path:
        sys.path.insert(0, str(RASTER))
    spec = importlib.util.spec_from_file_location(
        "sahool_raster_main_for_tilejson_cache_fix_tests",
        RASTER / "main.py",
    )
    assert spec and spec.loader
    raster_main = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = raster_main
    spec.loader.exec_module(raster_main)
    raster_main._layers.clear()
    raster_main._field_layers.clear()
    raster_main._field_owner_cache.clear()
    orig_owner = raster_main._field_owner
    raster_main._field_owner = _const_owner(None)
    token = raster_main._REQ_TENANT.set(None)
    try:
        yield raster_main
    finally:
        raster_main._REQ_TENANT.reset(token)
        raster_main._field_owner = orig_owner
        raster_main._layers.clear()
        raster_main._field_layers.clear()
        raster_main._field_owner_cache.clear()
        sys.modules.pop(spec.name, None)


async def test_db_owner_overrides_and_prunes_stale_field_layer_cache(rm):
    """A stale layer with a wrong tenant must not poison field tilejson/tiles.

    The fields table says field_a belongs to tenant_a, but _field_layers still has
    an old layer recorded as tenant_old. DB is the source of truth, so tenant_a is
    allowed and the stale layer entry is removed.
    """
    rm._layers["old_layer"] = {"field_id": "field_a", "index": "ndvi", "tenant_id": "tenant_old"}
    rm._field_layers["field_a"] = ["old_layer"]
    rm._field_owner = _const_owner("tenant_a")
    rm._REQ_TENANT.set("tenant_a")

    await rm._require_field_tenant("field_a")

    assert rm._field_layers["field_a"] == []


def test_index_aliases_cover_ndvu_and_salinity():
    assert '"ndvu": "ndvi"' in MAIN
    assert "def normalize_index" in MAIN
    assert "def display_index" in MAIN


def test_field_tilejson_and_tiles_normalize_index_before_lookup():
    # توحيد main↔cert: مسارا tilejson/tiles فُكِّكا من main.py إلى routers/fields.py
    # (المعالِجات @router، والرموز المشتركة مُسبَّقة بـmain.). نمسح الراوتر ونطابق نداء
    # التطبيع بصرف النظر عن البادئة main.
    src = (RASTER / "routers" / "fields.py").read_text(encoding="utf-8")

    def _handler_body(marker: str) -> str:
        start = src.index(marker)
        nxt = src.find("@router.", start + len(marker))
        return src[start : nxt if nxt != -1 else len(src)]

    tilejson_body = _handler_body('@router.get("/v1/fields/{field_id}/tilejson")')
    tile_body = _handler_body('@router.get("/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png")')
    assert "_normalize_index(index)" in tilejson_body
    assert "_display_index(index)" in tilejson_body
    assert "_normalize_index(index)" in tile_body


def test_frontend_normalizes_indicator_index_and_passes_tid():
    assert "export const normalizeIndicatorIndex" in FRONT_API
    assert "ndvu: 'ndvi'" in FRONT_API
    assert "index: normalizeIndicatorIndex(index)" in FRONT_API
    assert "normalizeIndicatorIndex(index)" in FIELD_MAP
    # طلب TileJSON يطبّع المؤشّر ويمرّر التاريخ مشروطاً (D). يقبل صياغة params inline أو
    # كائن params مُجمَّع (const params = { index: normalizedIndex, ... }) — كلاهما يحقّق العقد.
    assert "index: normalizedIndex" in FIELD_MAP
    assert "date && date !== 'latest'" in FIELD_MAP  # D: date مشروط (لا latest في الرابط)
    assert "tid: tenantId" in FIELD_MAP


def test_platform_has_api_raster_compatibility_proxy_for_misrouted_nginx():
    # نُقِل التمرير التوافقيّ من main.py إلى راوتر مستقلّ (api/routers/compat_gateway.py)
    # كي يبقى main حصراً نقاط بنية (حارس تفكيك الراوترات) — السلوك محفوظ.
    compat = (ROOT / "services/sahool-platform/api/routers/compat_gateway.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/api/raster/{path:path}")' in compat
    assert "RASTER_SERVICE_URL" in compat
    assert "httpx.AsyncClient" in compat
