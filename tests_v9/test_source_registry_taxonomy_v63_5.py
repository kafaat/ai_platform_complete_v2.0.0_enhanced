"""تحقّق V63.5 — تصنيف سِجِلّ المصادر الصادق (بعد مراجعة قنوات الصور 2026-07-07).

- ASTER GDEM مُسجَّل كـDEM مُخطَّط (active=False) يغطّي اليمن.
- سِجِلّ المصادر الخارجيّة (usgs/planet/maxar/china) منفصل: active_provider=False دائماً،
  source_type صالح، وChina قيد التقييم (requires_verification).
- لا تداخل بين المزوّدين والمصادر الخارجيّة والبحثيّة.
- المزوّدون النشطون يقتصرون على cdse/element84/local_cog (صدق: SciHub مُغلَق ⇒ لا يُضاف).

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


def test_active_providers_are_exactly_the_wired_free_ones():
    # صدق: فقط الموصولون فعلاً نشطون (لا SciHub، لا مبالغة).
    assert set(M.active_providers()) == {"element84", "cdse", "local_cog"}


def test_aster_gdem_registered_as_planned_dem():
    g = M.PROVIDER_REGISTRY["aster_gdem"]
    assert g["active"] is False and g["category"] == "dem"
    assert g["coverage_yemen"] is True and g["verified"] is True
    assert "aster_gdem" in M.planned_providers()


def test_external_sources_never_active_and_typed():
    for name in M.external_sources():
        meta = M.EXTERNAL_SOURCE_REGISTRY[name]
        assert meta["active_provider"] is False, f"{name} مصدر خارجيّ ليس مزوّداً موصولاً"
        assert meta["source_type"] in M._EXTERNAL_SOURCE_TYPES
    # الأنواع الأربعة ممثَّلة.
    assert M.sources_by_type("commercial") == ["planet_scope"]
    assert M.sources_by_type("event_open_data") == ["maxar_open_data"]
    assert M.sources_by_type("manual_download") == ["usgs_earthexplorer"]


def test_china_gaofen_requires_verification_not_production():
    g = M.EXTERNAL_SOURCE_REGISTRY["china_gaofen"]
    assert g["active_provider"] is False
    assert g.get("requires_verification") is True  # لا إنتاج قبل تحقّق ترخيص/API
    assert g["source_type"] == "research_manual"


def test_registries_are_mutually_disjoint():
    providers = set(M.PROVIDER_REGISTRY)
    research = set(M.RESEARCH_REGISTRY)
    external = set(M.EXTERNAL_SOURCE_REGISTRY)
    assert providers.isdisjoint(research)
    assert providers.isdisjoint(external)
    assert research.isdisjoint(external)


def test_status_endpoint_exposes_external_sources():
    src = (_RASTER / "routers" / "observability.py").read_text(encoding="utf-8")
    assert "EXTERNAL_SOURCE_REGISTRY" in src, "نقطة الحالة تكشف المصادر الخارجيّة"
