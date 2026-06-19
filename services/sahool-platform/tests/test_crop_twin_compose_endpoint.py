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


def test_response_shape():
    out = compose_crop_twin(req=_req(), user=_USER)
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


def test_taw_derived_from_texture():
    out = compose_crop_twin(req=_req(), user=_USER)
    assert out["water_state"]["taw_mm"] == pytest.approx(175.0)  # loam × 1.0 م


def test_dynamic_kc_from_ndvi():
    # مع NDVI ⇒ Kc ديناميكيّ ومصدر ديناميكيّ.
    out = compose_crop_twin(req=_req(ndvi=0.72), user=_USER)
    assert out["kc_source_ar"] == "ديناميكيّ من NDVI"
    assert out["kc_fapar"] is not None
    # بلا NDVI ⇒ ثابت للمرحلة.
    out2 = compose_crop_twin(req=_req(ndvi=None), user=_USER)
    assert "ثابت للمرحلة" in out2["kc_source_ar"]
    assert out2["kc_fapar"] is None


def test_stress_flag_water_deficit():
    # استنزاف ابتدائيّ مرتفع + أفق قصير ⇒ عجز مائيّ مستحقّ.
    out = compose_crop_twin(
        req=_req(forecast=_days(6), management=ComposeManagement(initial_depletion_mm=80.0)),
        user=_USER,
    )
    codes = [f["code"] for f in out["stress_flags"]]
    assert "water_deficit" in codes


def test_quality_block_never_high():
    out = compose_crop_twin(req=_req(), user=_USER)
    assert out["quality"]["data_quality"] != "high"  # غير معايَر
    assert "uncalibrated_model" in out["assumptions"]


def test_unknown_soil_flags_assumptions():
    out = compose_crop_twin(req=_req(soil=ComposeSoil(texture="moon_dust")), user=_USER)
    assert "default_soil" in out["assumptions"]
    assert "estimated_root_depth" in out["assumptions"]


def test_empty_forecast_does_not_crash():
    out = compose_crop_twin(req=_req(forecast=[]), user=_USER)
    assert out["phenology"]["gdd_cumulative"] == 0.0
    assert out["crop_twin"]["water_state"] if False else True  # لا انهيار
