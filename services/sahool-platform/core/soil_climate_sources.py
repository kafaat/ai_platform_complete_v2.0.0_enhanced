"""سِجِلّ مصادر التربة/المناخ (V70) — تصنيف صادق بأربع طبقات.

على نمط سِجِلّي الصور والطقس. ``tier`` يصنّف النضج:
- ``production_baseline``: موصول ويُستعمَل الآن (active=True).
- ``planned_baseline``: مُتحقَّق ومفيد، غير موصول بعد (active=False).
- ``research_layer``: طبقة بحثيّة متقدّمة — لا تُفعَّل دون تحقّق محلّيّ.
- ``manual_download_only``: تحميل يدويّ فقط.

**صدق:** ``active=True`` فقط لما يستدعيه الكود فعلاً — SoilGrids موصول
(``soil-service/soilgrids_client.py`` → ``rest.isric.org``)؛ البقيّة غير موصولة.
**أمن/موثوقيّة:** لا رابط Baidu يُعتمَد مصدراً رسميّاً (المواقع الأصليّة فقط + checksum
عند الاستيراد). النطاق الجغرافيّ لكلّ طبقة بحثيّة يُتحقَّق قبل الاعتماد (لا افتراض تغطية).
"""

from __future__ import annotations

from typing import Any

SOIL_CLIMATE_TIERS = {
    "production_baseline",
    "planned_baseline",
    "research_layer",
    "manual_download_only",
}

SOIL_CLIMATE_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "soilgrids": {
        "id": "soilgrids",
        "label": "SoilGrids (ISRIC)",
        "tier": "production_baseline",
        "active": True,  # موصول فعلاً: soil-service/soilgrids_client.py + /soil/soilgrids.
        "verified": True,
        "free": True,
        "auth": "none",
        "license": "CC-BY-4.0",
        "coverage_yemen": True,
        "resolution": "250m (عدّة أعماق)",
        "roles": [
            "soil_texture",
            "ph",
            "cec",
            "organic_carbon",
            "bulk_density",
            "total_nitrogen",
            "suitability_baseline",
        ],
        "warning": "خطّ أساس عالميّ 250م — ليس بديلاً عن تحليل مختبر محلّيّ (خشن للمدرّجات/الحقول الصغيرة).",
    },
    "worldclim": {
        "id": "worldclim",
        "label": "WorldClim v2.1",
        "tier": "planned_baseline",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "resolution": "~1km (1970–2000 normals + 19 bioclim)",
        "roles": ["climate_normals", "crop_suitability", "ecological_zoning", "long_term_baseline"],
        "note": "مناخ طويل المدى/ملاءمة محاصيل — لا لقرار الرشّ/المطر اليوميّ.",
    },
    "esa_cci_landcover": {
        "id": "esa_cci_landcover",
        "label": "ESA CCI Land Cover",
        "tier": "planned_baseline",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "registration",
        "coverage_yemen": True,
        "resolution": "~300m (1992–2022)",
        "roles": ["landcover_context", "regional_bulletin_context", "non_field_masking"],
        "note": "غطاء أرضيّ عامّ 300م — للتفاصيل الزراعيّة WorldCover/WorldCereal 10م أفضل.",
    },
    "global_soil_erodibility": {
        "id": "global_soil_erodibility",
        "label": "Global Soil Erodibility (ESDAC/JRC)",
        "tier": "research_layer",
        "active": False,
        "verified": "partial",
        "free": True,
        "auth": "registration (بعض المنتجات)",
        "coverage_yemen": "needs_dataset_check",  # صدق: يُتحقَّق النطاق/الدقّة/الترخيص لكلّ dataset.
        "requires_verification": True,
        "roles": ["erosion_risk", "slope_soil_risk", "conservation_planning"],
        "note": "خطر تعرية — قويّ مع DEM slope + rainfall erosivity + landcover؛ تحقّق النطاق أوّلاً.",
    },
    "advanced_soil_ecology_layers": {
        "id": "advanced_soil_ecology_layers",
        "label": "DOC/MBC/MBN/MBP/fMAOC/BNPP/GPP (research)",
        "tier": "research_layer",
        "active": False,
        "verified": "partial",
        "free": True,
        "auth": "dataset_dependent",
        "coverage_yemen": "dataset_dependent",
        "requires_verification": True,
        "requires_local_validation_yemen": True,
        "roles": ["soil_health_research", "carbon_modeling", "ecological_baseline"],
        "note": (
            "طبقات بيئيّة/كربون متقدّمة — لصحّة التربة/تقارير الكربون لاحقاً. لا تُغني عن "
            "SoilGrids/تحليل مختبر/قياسات EC-pH محلّيّة؛ لا اعتماد دون تحقّق محلّيّ."
        ),
    },
}


def active_soil_climate_sources() -> list[str]:
    """مصادر التربة/المناخ الموصولة فعلاً (active=True) — صدق لا طموح."""
    return [k for k, v in SOIL_CLIMATE_SOURCE_REGISTRY.items() if v.get("active")]


def soil_climate_sources_by_tier(tier: str) -> list[str]:
    """أسماء المصادر في طبقة نضج مُعيَّنة (production_baseline/planned_baseline/…)."""
    return [k for k, v in SOIL_CLIMATE_SOURCE_REGISTRY.items() if v.get("tier") == tier]


def has_baidu_source() -> bool:
    """صدق/موثوقيّة: هل يُعتمَد أيّ رابط Baidu كمصدر؟ (يجب أن يبقى False دائماً)."""
    import json

    blob = json.dumps(SOIL_CLIMATE_SOURCE_REGISTRY, ensure_ascii=False).lower()
    return "baidu" in blob
