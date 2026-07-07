"""تحقّق V70 — سِجِلّ مصادر التربة/المناخ (SoilGrids نشط، البقيّة مُخطَّطة/بحثيّة).

- SoilGrids وحده active (موصول فعلاً في soil-service) بطبقة production_baseline.
- WorldClim/ESA-CCI ⇒ planned_baseline؛ erodibility/ecology ⇒ research_layer (تحقّق محلّيّ).
- **لا Baidu** يُعتمَد مصدراً (تحذير المُراجِع الأهمّ).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from core.soil_climate_sources import (
    SOIL_CLIMATE_SOURCE_REGISTRY,
    SOIL_CLIMATE_TIERS,
    active_soil_climate_sources,
    has_baidu_source,
    soil_climate_sources_by_tier,
)


def test_only_soilgrids_is_active_production_baseline():
    # صدق: SoilGrids موصول فعلاً ⇒ نشط؛ NASA POWER/WorldClim… ليست هنا نشطة.
    assert active_soil_climate_sources() == ["soilgrids"]
    assert soil_climate_sources_by_tier("production_baseline") == ["soilgrids"]
    sg = SOIL_CLIMATE_SOURCE_REGISTRY["soilgrids"]
    assert sg["coverage_yemen"] is True and sg["license"] == "CC-BY-4.0"
    assert "warning" in sg  # لا يُدّعى بديلاً عن تحليل مختبر محلّيّ


def test_planned_and_research_tiers():
    planned = soil_climate_sources_by_tier("planned_baseline")
    assert "worldclim" in planned and "esa_cci_landcover" in planned
    research = soil_climate_sources_by_tier("research_layer")
    assert "global_soil_erodibility" in research
    assert "advanced_soil_ecology_layers" in research
    # الطبقات البحثيّة تحتاج تحقّقاً (لا تفعيل أعمى).
    for r in research:
        assert SOIL_CLIMATE_SOURCE_REGISTRY[r]["requires_verification"] is True
        assert SOIL_CLIMATE_SOURCE_REGISTRY[r]["active"] is False


def test_all_tiers_valid():
    for meta in SOIL_CLIMATE_SOURCE_REGISTRY.values():
        assert meta["tier"] in SOIL_CLIMATE_TIERS


def test_no_baidu_source_ever():
    # تحذير المُراجِع الأهمّ: لا رابط Baidu كمصدر رسميّ/traceability.
    assert has_baidu_source() is False


def test_ecology_layers_require_local_validation():
    eco = SOIL_CLIMATE_SOURCE_REGISTRY["advanced_soil_ecology_layers"]
    assert eco["requires_local_validation_yemen"] is True
    assert eco["coverage_yemen"] == "dataset_dependent"  # لا افتراض تغطية
