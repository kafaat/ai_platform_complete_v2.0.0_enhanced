"""نصائح لا تتجاوز ما تعرفه — أمراضٌ عائليّة، محصولٌ مجهول بلا عمق، ومعرفةٌ غير مؤكَّدة.

١. ``disease_risk`` يُسمّي أمراض العائل من بطاقته فقط، ولا يوصي برشٍّ من الطقس وحده.
٢. محصولٌ بلا بطاقة (Kc عامّ) ⇒ نطاقٌ استشاريّ و``recommended_mm=None`` وقيد
   ``crop_unknown_generic_kc`` — لا عمقَ ريٍّ قابلاً للتنفيذ (``water_balance`` و
   ``irrigation_advice`` و``recommend_irrigation`` ومركز التوصيات).
٣. معرفةٌ مجتمعيّة معلَّقة لا تُدرَج «مُطبَّقة»؛ و``local_knowledge`` من جسم الطلب يُسقَط.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from api.irrigation_recommendation_policy import recommend_irrigation
from api.recommendations_hub import RecommendationContext, _irrigation_rec
from api.water_balance import (
    CROP_UNKNOWN_LIMITATION,
    GENERIC_KC_UNCERTAINTY,
    WeatherInput,
    water_balance,
)
from api.weather_advice import disease_risk, irrigation_advice
from core.crop_cards.loader import (
    DISEASE_WEATHER_PATTERNS,
    crop_diseases,
    list_crop_cards,
    load_crop_card,
    validate_crop_card,
)
from core.recommendation_engine import generate_recommendation
from knowledge.farmer_knowledge import (
    Confidence,
    FarmerKnowledge,
    KnowledgeType,
    VerificationStatus,
)

pytestmark = pytest.mark.unit

_SPRAY_WORDS = ("رشّ وقائيّ", "للرشّ", "فكّر في رشّ")


# ─── ١. أمراض عائليّة ───────────────────────────────────────────────


class TestHostSpecificDiseaseRisk:
    def test_late_blight_named_for_potato_not_for_wheat_or_unknown(self):
        potato = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0, crop="potato")
        wheat = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0, crop="wheat")
        unknown = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0, crop="dragonfruit")
        assert any("اللفحة المتأخّرة" in d for d in potato["diseases_ar"])
        assert not any("اللفحة المتأخّرة" in d for d in wheat["diseases_ar"])
        assert any("الصدأ" in d for d in wheat["diseases_ar"])
        assert unknown["diseases_ar"] == []

    def test_crop_without_disease_list_is_generic_weather_risk(self):
        r = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0, crop="maize")
        assert r["risk_level"] == "high"
        assert r["host_specific"] is False
        assert r["diseases_ar"] == []
        assert r["limitations"] == ["no_host_disease_list"]
        assert "افحص الحقل" in r["advice_ar"]

    def test_none_crop_names_no_disease(self):
        r = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0)
        assert r["diseases_ar"] == []
        assert r["crop_id"] is None

    def test_disease_filtered_by_weather_pattern(self):
        # grape: downy mildew needs free water (humid_wet); powdery mildew is humid_warm_dry.
        wet = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0, crop="grape")
        dry = disease_risk(temp_c=25.0, humidity_pct=75.0, rain_mm_3d=0.0, crop="grape")
        assert any("البياض الزغبيّ" in d for d in wet["diseases_ar"])
        assert not any("البياض الدقيقيّ" in d for d in wet["diseases_ar"])
        assert any("البياض الدقيقيّ" in d for d in dry["diseases_ar"])
        assert not any("البياض الزغبيّ" in d for d in dry["diseases_ar"])

    @pytest.mark.parametrize("crop", ["potato", "tomato", "wheat", "grape", "maize", None])
    @pytest.mark.parametrize(
        ("temp", "rh", "rain"), [(20.0, 90.0, 15.0), (22.0, 85.0, 0.0), (40.0, 20.0, 0.0)]
    )
    def test_never_recommends_spraying_from_weather(self, crop, temp, rh, rain):
        r = disease_risk(temp_c=temp, humidity_pct=rh, rain_mm_3d=rain, crop=crop)
        assert r["spray_recommended"] is False
        assert not any(w in r["advice_ar"] for w in _SPRAY_WORDS)
        if r["risk_level"] != "low":
            assert "افحص الحقل" in r["advice_ar"]
            assert "لا ترشّ قبل تأكيد المُمرِض" in r["advice_ar"]


class TestCropCardDiseasesBlock:
    def test_all_cards_with_diseases_validate(self):
        for cid in list_crop_cards():
            card = load_crop_card(cid)
            assert validate_crop_card(card)["valid"], cid
            items = crop_diseases(cid)
            if card.get("diseases") is not None:
                assert items, cid
                assert {i["favoured_by"] for i in items} <= DISEASE_WEATHER_PATTERNS

    def test_expected_host_lists(self):
        assert {d["id"] for d in crop_diseases("potato")} == {"late_blight"}
        assert {d["id"] for d in crop_diseases("tomato")} == {"late_blight"}
        assert {d["id"] for d in crop_diseases("wheat")} == {"rust", "septoria_tritici_blotch"}
        assert "downy_mildew" in {d["id"] for d in crop_diseases("grape")}
        assert crop_diseases("maize") is None
        assert crop_diseases(None) is None

    @pytest.mark.parametrize(
        ("block", "needle"),
        [
            ("x", "diseases ليست كتلة"),
            ({"items": [{"id": "a", "name_ar": "ا", "name_en": "A"}]}, "مصدر"),
            ({"source": "s", "items": []}, "items"),
            (
                {
                    "source": "s",
                    "items": [{"id": "a", "name_ar": "ا", "name_en": "A", "favoured_by": "hot"}],
                },
                "favoured_by",
            ),
            (
                {
                    "source": "s",
                    "items": [
                        {"id": "a", "name_ar": "ا", "name_en": "A", "favoured_by": "humid_wet"},
                        {"id": "a", "name_ar": "ب", "name_en": "B", "favoured_by": "humid_wet"},
                    ],
                },
                "مكرّر",
            ),
            (
                {
                    "source": "s",
                    "items": [
                        {"id": "Bad Id", "name_ar": "ا", "name_en": "A", "favoured_by": "humid_wet"}
                    ],
                },
                "id غير صالح",
            ),
        ],
    )
    def test_validator_rejects_malformed_block(self, block, needle):
        card = dict(load_crop_card("wheat"))
        card["diseases"] = block
        res = validate_crop_card(card)
        assert not res["valid"]
        assert any(needle in e for e in res["errors"]), res["errors"]


# ─── ٢. محصول مجهول ⇒ نطاق لا عمق ──────────────────────────────────


class TestUnknownCropIsAdvisoryRange:
    def test_water_balance_unknown_crop_has_no_actionable_depth(self):
        r = water_balance(WeatherInput(t_min_c=15, t_max_c=30), "dragonfruit", "mid", et0_mm=6.0)
        d = r.to_dict()
        assert d["net_irrigation_mm"] is None
        assert d["recommended_mm"] is None
        assert d["crop_known"] is False
        assert d["limitations"] == [CROP_UNKNOWN_LIMITATION]
        low, high = d["advisory_range_mm"]["low"], d["advisory_range_mm"]["high"]
        etc = 6.0 * 1.1
        assert low == round(etc * (1 - GENERIC_KC_UNCERTAINTY), 1)
        assert high == round(etc * (1 + GENERIC_KC_UNCERTAINTY), 1)
        assert "رُيّ بهذا العمق" not in d["advice_ar"]
        assert "لا عمقَ ريٍّ للتنفيذ" in d["advice_ar"]

    def test_water_balance_known_crop_shape_unchanged(self):
        d = water_balance(
            WeatherInput(t_min_c=15, t_max_c=30), "wheat", "mid", et0_mm=6.0
        ).to_dict()
        assert "recommended_mm" not in d and "limitations" not in d
        assert d["net_irrigation_mm"] == 6.9

    def test_irrigation_advice_unknown_crop(self):
        r = irrigation_advice(et0_mm=6.0, crop="dragonfruit", stage="mid")
        assert r["recommended_mm"] is None
        assert r["crop_known"] is False
        assert r["limitations"] == [CROP_UNKNOWN_LIMITATION]
        assert r["advisory_range_mm"]["low"] < r["advisory_range_mm"]["high"]
        assert "لا عمقَ ريٍّ للتنفيذ" in r["rationale_ar"]

    def test_irrigation_advice_known_crop_and_override_are_actionable(self):
        known = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
        assert known["recommended_mm"] == 6.9
        assert known["advisory_range_mm"] is None and known["limitations"] == []
        # An explicit Kc (phenology curve or caller-supplied) is no longer the generic curve.
        override = irrigation_advice(et0_mm=6.0, crop="dragonfruit", stage="mid", kc_override=0.9)
        assert override["recommended_mm"] == 5.4
        assert override["crop_known"] is True

    def test_recommend_irrigation_unknown_crop_has_no_net_or_gross(self):
        rec = recommend_irrigation(
            et0_mm=6.0,
            crop="dragonfruit",
            stage="mid",
            rain_recent_mm=0.0,
            forecast_rain_mm=0.0,
            soil_ece=6.0,
            crop_salt_tolerance_ece=2.0,
            water_ec=1.0,
            drainage="fast",
            irrigation_efficiency=0.8,
        )
        assert rec["net_irrigation_mm"] is None
        assert rec["gross_irrigation_mm"] is None
        assert rec["salinity_leaching_mm"] == 0.0
        assert rec["limitations"] == [CROP_UNKNOWN_LIMITATION]
        assert rec["advisory_range_mm"] is not None

    def test_recommend_irrigation_known_crop_unchanged(self):
        rec = recommend_irrigation(
            et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0, forecast_rain_mm=0.0
        )
        assert rec["net_irrigation_mm"] == 6.9
        assert rec["gross_irrigation_mm"] is not None
        assert rec["limitations"] == []

    def test_hub_title_carries_range_not_single_depth(self):
        ctx = RecommendationContext(
            field_id="f1",
            crop="dragonfruit",
            stage="mid",
            et0_mm=6.0,
            rain_recent_mm=0.0,
            forecast_rain_mm=0.0,
            today=date(2026, 11, 8),
        )
        rec = _irrigation_rec(ctx)
        assert rec is not None
        assert "تقديريّ" in rec.title_ar
        assert "ريّ مُوصى به" not in rec.title_ar


# ─── ٣. معرفة مجتمعيّة ─────────────────────────────────────────────


def _fk(status: VerificationStatus, content: str) -> FarmerKnowledge:
    return FarmerKnowledge(
        content,
        KnowledgeType.SPATIAL,
        content,
        "t1",
        "al_jawf",
        "Z1",
        Confidence.HIGH,
        verification_status=status,
        data_agreement=status == VerificationStatus.CONFIRMED,
    )


class TestCommunityKnowledgeVerification:
    def test_pending_tip_is_not_listed_as_applied(self):
        tips = [
            _fk(VerificationStatus.CONFIRMED, "مؤكَّدة"),
            _fk(VerificationStatus.PENDING, "معلَّقة"),
            _fk(VerificationStatus.REJECTED, "مرفوضة"),
        ]
        rec = generate_recommendation({"quality_grade": "HIGH"}, local_knowledge=tips)
        applied = [e["content"] for e in rec.backend.local_knowledge_applied]
        pending = [e["content"] for e in rec.backend.local_knowledge_pending_unverified]
        assert applied == ["مؤكَّدة"]
        assert pending == ["معلَّقة"]
        assert rec.backend.local_knowledge_pending_unverified[0]["verification_status"] == "pending"

    def test_client_supplied_local_knowledge_is_dropped(self, monkeypatch, caplog):
        import core.api_adapter as adapter
        from core.canonical_schemas import UserRole, UserSchema

        captured: dict = {}

        class _Result:
            delivered = False
            reason_ar = "x"
            rec_id = "r"

        def _fake(**kwargs):
            captured.update(kwargs)
            return _Result()

        monkeypatch.setattr(adapter, "orchestrate_recommendation", _fake)
        monkeypatch.setattr(adapter, "asdict", lambda _r: {})
        adapter._reset_rate_limiter()
        user = UserSchema(
            user_id="u1", tenant_id="t1", role=UserRole.AGRONOMIST, name_ar="x", is_active=True
        )
        payload = {
            "tenant_id": "t1",
            "field_id": "f1",
            "farm_id": "fm1",
            "crop": "wheat",
            "validation": {"quality_grade": "HIGH"},
            "local_knowledge": [
                {"content_ar": "ازرع بعد المطر", "verification_status": "confirmed"}
            ],
        }
        with caplog.at_level(logging.INFO, logger="core.api_adapter"):
            adapter.handle_recommendation_request(adapter.ApiRequest(user=user, payload=payload))
        assert captured["local_knowledge"] is None
        assert any("local_knowledge ignored" in m for m in caplog.messages)
