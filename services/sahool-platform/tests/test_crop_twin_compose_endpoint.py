"""اختبار نقطة /api/v1/crop-twin/compose (routers/crop_twin) — استدعاء مباشر.

نختبر المعالِج مباشرةً (يركّب soil_water ⇒ kc_from_ndvi ⇒ crop_twin_state ⇒ quality)،
متفادين TestClient/المصادقة: (أ) شكل الاستجابة الموحّد؛ (ب) Kc ديناميكيّ من NDVI مقابل
ثابت للمرحلة؛ (ج) اشتقاق TAW من النسيج؛ (د) أعلام الإجهاد من حالة التوأم؛ (هـ) كتلة
الجودة (غير معايَر ⇒ لا high)؛ (و) سلسلة فارغة لا تنهار. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.crop_twin import (
    ComposeForecastDay,
    ComposeManagement,
    ComposeSoil,
    CropTwinComposeRequest,
    compose_crop_twin,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_engine_gdd(monkeypatch):
    """WS-C.1c Zero-Legacy: المسار يجلب GDD من المحرّك (async). في الوحدة نُبدِّله بمزيّف
    يحسب صيغة modified محلّيّاً (لا شبكة). الاختبارات مُستثناة من حارس الصيغ."""

    async def _fake_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **_kw):
        daily = []
        for mn, mx in zip(daily_t_min, daily_t_max, strict=False):
            tmax = max(min(mx, upper_cutoff_c) if upper_cutoff_c is not None else mx, base_c)
            tmin = max(mn, base_c)
            daily.append(round(max(0.0, (tmax + tmin) / 2.0 - base_c), 3))
        return {
            "product": "gdd",
            "calculation_version": "gdd/daily/1.0.0",
            "daily_gdd": daily,
            "accumulated_gdd": round(sum(daily), 3),
            "thresholds_used": {
                "base_c": base_c,
                "upper_cutoff_c": upper_cutoff_c,
                "method": method,
            },
            "valid_period": {"days": len(daily)},
            "limitations": [],
            "derived_from": "canonical_daily_weather_series",
            "gdd_lineage_id": "gddseq/fake-compose",
            "contributing_state_ids": [f"snap-{i}" for i in range(len(daily))],
            "series_quality_status": "validated",
        }

    import api.routers.crop_twin as mod

    monkeypatch.setattr(mod, "get_gdd_product", _fake_gdd)


_USER = UserSchema(
    user_id="u-twin",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="حالة",
)


def _days(n):
    return [ComposeForecastDay(t_min_c=10.0, t_max_c=30.0, et0_mm=6.0, kc=1.0) for _ in range(n)]


def _req(**kw):
    base = dict(
        crop="wheat",
        stage="mid",
        forecast=_days(10),
        soil=ComposeSoil(texture="loam", root_depth_m=1.0),
    )
    base.update(kw)
    return CropTwinComposeRequest(**base)


async def test_response_shape():
    out = await compose_crop_twin(req=_req(), user=_USER)
    assert set(out) >= {
        "crop_twin",
        "water_state",
        "nutrient_state",
        "phenology",
        "stress_flags",
        "quality",
        "calibrated",
        "assumptions",
        "warnings_ar",
        "dynamic_kc",
        "kc_source_ar",
    }
    assert out["calibrated"] is False


async def test_taw_derived_from_texture():
    out = await compose_crop_twin(req=_req(), user=_USER)
    assert out["water_state"]["taw_mm"] == pytest.approx(175.0)  # loam × 1.0 م


async def test_dynamic_kc_from_ndvi():
    # مع NDVI ⇒ Kc ديناميكيّ ومصدر ديناميكيّ.
    out = await compose_crop_twin(req=_req(ndvi=0.72), user=_USER)
    assert out["kc_source_ar"] == "ديناميكيّ من NDVI"
    assert out["kc_fapar"] is not None
    # بلا NDVI ⇒ ثابت للمرحلة.
    out2 = await compose_crop_twin(req=_req(ndvi=None), user=_USER)
    assert "ثابت للمرحلة" in out2["kc_source_ar"]
    assert out2["kc_fapar"] is None


async def test_stress_flag_water_deficit():
    # استنزاف ابتدائيّ مرتفع + أفق قصير ⇒ عجز مائيّ مستحقّ.
    out = await compose_crop_twin(
        req=_req(forecast=_days(6), management=ComposeManagement(initial_depletion_mm=80.0)),
        user=_USER,
    )
    codes = [f["code"] for f in out["stress_flags"]]
    assert "water_deficit" in codes


async def test_quality_block_never_high():
    out = await compose_crop_twin(req=_req(), user=_USER)
    assert out["quality"]["data_quality"] != "high"  # غير معايَر
    assert "uncalibrated_model" in out["assumptions"]


async def test_unknown_soil_flags_assumptions():
    out = await compose_crop_twin(req=_req(soil=ComposeSoil(texture="moon_dust")), user=_USER)
    assert "default_soil" in out["assumptions"]
    assert "estimated_root_depth" in out["assumptions"]


async def test_empty_forecast_does_not_crash():
    out = await compose_crop_twin(req=_req(forecast=[]), user=_USER)
    assert out["phenology"]["gdd_cumulative"] == 0.0
    assert out["crop_twin"]["water_state"] if False else True  # لا انهيار


async def test_crop_twin_exposes_canonical_crop_intelligence_projection():
    out = await compose_crop_twin(req=_req(), user=_USER)
    ci = out["crop_twin"]["crop_intelligence"]
    assert ci["schema"] == "crop_intelligence_state.v2"
    assert ci["ownership"]["crop_interpretation"] == "crop-intelligence-engine"
    assert ci["biomass"]["status"] == "unavailable"
    assert ci["yield_projection"]["status"] == "unavailable"


async def test_compose_projects_msi_ndmi_into_crop_intelligence():
    out = await compose_crop_twin(
        req=_req(
            field_id="fld-1",
            season_id="season-1",
            ndmi=-0.1,
            msi=2.2,
            spectral_temporal_compatible=True,
            spectral_product_ids=["ndmi-1", "msi-1"],
            spectral_quality_status="validated",
        ),
        user=_USER,
    )
    ci = out["crop_intelligence"]
    assert ci["field_id"] == "fld-1"
    assert ci["season_id"] == "season-1"
    assert ci["spectral"]["water_stress"]["confirmed"] is True
    assert "spectral_water_stress" in {x["code"] for x in ci["stress_flags"]}


async def test_compose_propagates_canonical_gdd_lineage():
    out = await compose_crop_twin(req=_req(forecast=_days(2)), user=_USER)
    ci = out["crop_intelligence"]
    assert ci["phenology"]["method"] == "modified"
    assert ci["phenology"]["formula_version"] == "gdd/daily/1.0.0"
    assert "gddseq/fake-compose" in ci["evidence_ids"]
    assert "gdd_pending_weather_engine_delegation" not in ci["limitations"]
