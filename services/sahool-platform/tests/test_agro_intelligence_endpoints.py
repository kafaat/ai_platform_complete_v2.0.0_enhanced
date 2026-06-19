"""اختبارات نقاط ذكاء النظام الزراعيّ-البيئيّ (routers/agro_intelligence) — استدعاء مباشر.

النقاط حسابيّة صرفة (بلا قاعدة)، فنختبر المعالِجات مباشرةً بتمرير مستخدم مُصادَق —
متفادين TestClient/المصادقة (نفس نمط test_decision_policies_endpoint). نتحقّق أنّ
كلّ نقطة تُسلسِل مخرَج نواتها الصحيح وتأخذ المستأجِر من المستخدم.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.agro_intelligence import (
    CropRiskRequest,
    CropRotationRequest,
    DecisionPlaybookRequest,
    FeedbackTrendRequest,
    SeasonComparisonRequest,
    SeasonCropRequest,
    SeasonFeedbackInputRequest,
    SeasonMetricsRequest,
    SoilFeedbackInputsRequest,
    WeatherSignalRequest,
    WorkOrderFromRecommendationRequest,
    crop_risk_endpoint,
    crop_rotation_endpoint,
    decision_playbook_endpoint,
    plant_soil_feedback_endpoint,
    plant_soil_feedback_trend_endpoint,
    season_comparison_endpoint,
    work_order_from_recommendation_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-agro",
    tenant_id="00000000-0000-0000-0000-000000000007",
    role=UserRole.OWNER,
    name_ar="مزارع",
)


def test_crop_risk_endpoint_returns_risks():
    out = crop_risk_endpoint(
        CropRiskRequest(crop="wheat", disease_risk_score=0.9, frost_risk_hours=6), user=_USER
    )
    assert out["crop"] == "wheat"
    assert isinstance(out["risks"], list) and len(out["risks"]) >= 1
    # كلّ خطر مُسلسَل بحقوله النواتيّة.
    for r in out["risks"]:
        assert {"risk_type", "crop", "severity", "score", "reason_ar"} <= set(r)


def test_plant_soil_feedback_endpoint_good_profile_positive():
    out = plant_soil_feedback_endpoint(
        SoilFeedbackInputsRequest(
            rotation_diversity=0.9,
            legume_ratio=0.6,
            cover_crop_ratio=0.7,
            organic_matter_additions_per_yr=4,
            tillage_intensity=0.1,
            soil_organic_carbon_pct=2.5,
        ),
        user=_USER,
    )
    assert out["direction"] == "positive"
    assert out["positive_feedback_score"] > out["negative_feedback_risk"]
    assert 0.0 <= out["confidence"] <= 1.0


def test_plant_soil_feedback_endpoint_empty_neutral():
    out = plant_soil_feedback_endpoint(SoilFeedbackInputsRequest(), user=_USER)
    assert out["direction"] == "neutral"
    assert out["inputs_known"] == 0


def test_feedback_trend_endpoint_improving():
    def season(sid, host, soc):
        return SeasonFeedbackInputRequest(
            season_id=sid,
            inputs=SoilFeedbackInputsRequest(
                rotation_diversity=soc, host_repeat_risk=host, soil_organic_carbon_pct=soc * 3
            ),
        )

    out = plant_soil_feedback_trend_endpoint(
        FeedbackTrendRequest(
            seasons=[season("2024", 0.8, 0.3), season("2025", 0.4, 0.6), season("2026", 0.1, 0.9)]
        ),
        user=_USER,
    )
    assert out["seasons_analyzed"] == 3
    assert out["direction"] == "improving"
    assert len(out["positive_series"]) == 3


def test_crop_rotation_endpoint_monoculture_negative():
    out = crop_rotation_endpoint(
        CropRotationRequest(
            history=[SeasonCropRequest(season_id=f"s{i}", crop_id="wheat") for i in range(4)]
        ),
        user=_USER,
    )
    assert out["seasons_analyzed"] == 4
    assert out["direction"] == "negative"
    assert out["max_consecutive_same"] == 4


def test_crop_rotation_endpoint_diverse_positive():
    out = crop_rotation_endpoint(
        CropRotationRequest(
            history=[
                SeasonCropRequest(season_id="s1", crop_id="wheat"),
                SeasonCropRequest(season_id="s2", crop_id="clover", is_legume=True),
                SeasonCropRequest(season_id="s3", crop_id="maize", is_cover_crop=True),
                SeasonCropRequest(season_id="s4", crop_id="barley"),
            ]
        ),
        user=_USER,
    )
    assert out["legume_ratio"] > 0.0
    assert out["direction"] in {"positive", "neutral"}


def test_season_comparison_endpoint_returns_metrics():
    out = season_comparison_endpoint(
        SeasonComparisonRequest(
            current=SeasonMetricsRequest(season_id="2026", crop_id="wheat", yield_t_ha=6.0),
            previous=SeasonMetricsRequest(season_id="2025", crop_id="wheat", yield_t_ha=5.0),
        ),
        user=_USER,
    )
    assert "metrics" in out
    assert out["metrics"]["yield_t_ha"]["direction"] == "up"
    assert out["metrics"]["yield_t_ha"]["better"] is True


def test_decision_playbook_endpoint_frost_dominates():
    out = decision_playbook_endpoint(
        DecisionPlaybookRequest(
            crop="wheat",
            weather_signals=[
                WeatherSignalRequest(signal_type="frost_imminent", confidence_score=0.9),
                WeatherSignalRequest(signal_type="spray_window_open", confidence_score=0.8),
            ],
        ),
        user=_USER,
    )
    assert "صقيع" in out["main_judgement"] or any("صقيع" in e for e in out["evidence"])
    assert out["review_after"]  # غير فارغ أبداً
    assert 0.0 <= out["confidence"] <= 1.0
    # asdict يُبقي tuple؛ FastAPI يُسلسِله JSON array — نتحقّق من تسلسل غير فارغ.
    assert len(out["do_today"]) >= 1


def test_decision_playbook_endpoint_composes_soil_and_risk():
    out = decision_playbook_endpoint(
        DecisionPlaybookRequest(
            crop="tomato",
            crop_risk_inputs=CropRiskRequest(crop="tomato", disease_risk_score=0.95),
            soil_feedback_inputs=SoilFeedbackInputsRequest(host_repeat_risk=0.9, salinity_ds_m=7.0),
        ),
        user=_USER,
    )
    assert out["main_judgement"]
    assert isinstance(out["escalate_if"], (list, tuple))


def test_decision_playbook_endpoint_empty_neutral():
    out = decision_playbook_endpoint(DecisionPlaybookRequest(), user=_USER)
    assert out["review_after"]
    assert out["confidence"] <= 0.5


def test_work_order_from_recommendation_infers_type():
    out = work_order_from_recommendation_endpoint(
        WorkOrderFromRecommendationRequest(
            field_id="fld_1", recommendation={"action": "ابدأ ريّ الحقل اليوم", "id": "rec_9"}
        ),
        user=_USER,
    )
    assert out["inferred"] is True
    assert out["work_order"]["wo_type"] == "irrigation"
    # المستأجِر من المستخدم المُصادَق لا من جسم الطلب.
    assert out["work_order"]["tenant_id"] == "00000000-0000-0000-0000-000000000007"
    assert out["work_order"]["status"] == "planned"


def test_work_order_from_recommendation_unknown_type_not_inferred():
    out = work_order_from_recommendation_endpoint(
        WorkOrderFromRecommendationRequest(
            field_id="fld_1", recommendation={"action": "خطوة غامضة بلا نوع"}
        ),
        user=_USER,
    )
    assert out["inferred"] is False
    assert out["work_order"] is None
