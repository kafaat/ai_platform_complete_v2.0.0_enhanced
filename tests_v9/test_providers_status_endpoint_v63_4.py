"""تحقّق V63.4 — نقطة حالة المزوّدين (/v1/providers/status) تكشف السِجِلّ الصادق.

- الراوت يكشف active/planned + PROVIDER_REGISTRY + RESEARCH_REGISTRY + المزوّد الافتراضيّ.
- صدق: المخرَج مبنيّ من raster_scene_model (active يعكس الوصل؛ لا مزوّد وهميّ).
- حارس ساكن للراوت + تحقّق دلاليّ من بيانات السِجِلّ.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402


def test_providers_status_route_declared():
    src = (_RASTER / "routers" / "observability.py").read_text(encoding="utf-8")
    assert '@router.get("/v1/providers/status")' in src, "يجب إعلان نقطة حالة المزوّدين"
    assert "active_providers()" in src and "PROVIDER_REGISTRY" in src
    assert "RESEARCH_REGISTRY" in src, "المصادر البحثيّة تُكشَف منفصلة"
    assert "HISTORICAL_SEARCH_PROVIDER" in src, "المزوّد الافتراضيّ يُكشَف"


def test_status_payload_is_honest():
    # المخرَج الذي ستبنيه النقطة (نفس الدوال) صادق: active يستبعد المُخطَّطين.
    active = M.active_providers()
    planned = M.planned_providers()
    assert "element84" in active
    for p in ("wapor", "worldcereal", "nasa_hls", "planetary_computer"):
        assert p in planned and p not in active
    # المصادر البحثيّة لا تدّعي توفير صور.
    assert all(v["provides_imagery"] is False for v in M.RESEARCH_REGISTRY.values())
    # لا تداخل بين مزوّدي الصور والمصادر البحثيّة.
    assert set(M.PROVIDER_REGISTRY).isdisjoint(set(M.RESEARCH_REGISTRY))
