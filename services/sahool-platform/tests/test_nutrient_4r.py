"""اختبارات api/nutrient_4r.py (offline) — قواعد 4R للتربة الكلسيّة اليمنيّة.

نواة نقيّة بلا قاعدة/شبكة/ملفّات. نتحقّق من المبدأ الحاكم "المختبر يحكم":
N إرشاديّ دوماً مع تحذير تطاير الأمونيا عند الكلسيّة/الـpH العالي؛ P محجوب
(BLOCKED) بلا تحليل Olsen-P وإلا OK/ADVISORY حسب عتبة 10ppm؛ المغذّيات
الصغرى (Fe/Zn) محجوبة بلا قيمة وإلّا تصحيح ورقي إرشاديّ؛ والخطة الكاملة
تغطّي N/P/Fe/Zn. العتبات (CaCO3≥15، pH≥7.8، Olsen-P<10) والقيم مشتقّة من الكود.
"""

import pytest
from api.nutrient_4r import (
    _CALCAREOUS_THRESHOLD,
    _HIGH_PH_THRESHOLD,
    FourRRecommendation,
    Nutrient,
    RecommendationStatus,
    SoilContext,
    full_4r_plan,
    recommend_micronutrient,
    recommend_nitrogen,
    recommend_phosphorus,
)

pytestmark = pytest.mark.unit

_AMMONIA_WARNING = "خطر تطاير الأمونيا عالٍ — تجنّب نثر اليوريا على السطح"


# ─── النيتروجين: إرشاديّ دائماً + تحذير الكلسيّة ──────────────────────────


def test_nitrogen_is_always_advisory():
    # المعدّل يحتاج هدف إنتاج/تحليل ⇒ لا توصية معدّل قاطعة، الحالة ADVISORY.
    rec = recommend_nitrogen(SoilContext(caco3_pct=20))
    assert rec.nutrient == Nutrient.N
    assert rec.status == RecommendationStatus.ADVISORY
    # المصدر يُفضّل كبريتات/نترات على اليوريا، والوضع banding تحت السطح.
    assert "اليوريا" in rec.source_ar
    assert "banding" in rec.placement_ar


def test_nitrogen_clean_soil_no_warning():
    # تربة غير كلسيّة و pH منخفض ⇒ لا تحذير تطاير.
    rec = recommend_nitrogen(SoilContext(caco3_pct=5.0, ph=7.0))
    assert rec.warnings_ar == []


def test_nitrogen_calcareous_triggers_ammonia_warning():
    rec = recommend_nitrogen(SoilContext(caco3_pct=20.0))
    assert _AMMONIA_WARNING in rec.warnings_ar


def test_nitrogen_high_ph_triggers_ammonia_warning():
    rec = recommend_nitrogen(SoilContext(ph=8.2))
    assert _AMMONIA_WARNING in rec.warnings_ar


def test_nitrogen_caco3_boundary_is_inclusive():
    # العتبة >= 15.0 ⇒ القيمة عند الحدّ نفسها تُفعّل التحذير.
    assert (
        _AMMONIA_WARNING
        in recommend_nitrogen(SoilContext(caco3_pct=_CALCAREOUS_THRESHOLD)).warnings_ar
    )
    # أقلّ بقليل لا يُفعّل (مع pH معروف منخفض — المجهول لا يستبعد الخطر).
    assert (
        recommend_nitrogen(SoilContext(caco3_pct=_CALCAREOUS_THRESHOLD - 0.1, ph=7.0)).warnings_ar
        == []
    )


def test_nitrogen_ph_boundary_is_inclusive():
    assert _AMMONIA_WARNING in recommend_nitrogen(SoilContext(ph=_HIGH_PH_THRESHOLD)).warnings_ar
    assert (
        recommend_nitrogen(SoilContext(ph=_HIGH_PH_THRESHOLD - 0.1, caco3_pct=5.0)).warnings_ar
        == []
    )


def test_nitrogen_unknown_soil_assumes_volatilisation_risk():
    # None ليست صفراً: CaCO3/pH مجهولان ⇒ تحذير محافظ «افترض الخطر» لا صمت.
    rec = recommend_nitrogen(SoilContext())
    assert rec.status == RecommendationStatus.ADVISORY
    assert len(rec.warnings_ar) == 1
    assert "CaCO3/pH unknown — assume risk" in rec.warnings_ar[0]
    # Only one of the two known and below threshold still cannot exclude the risk.
    assert recommend_nitrogen(SoilContext(caco3_pct=5.0)).warnings_ar
    assert recommend_nitrogen(SoilContext(ph=7.0)).warnings_ar


def test_phosphorus_unknown_caco3_assumes_fixation_risk():
    rec = recommend_phosphorus(SoilContext(p_ppm=20.0))
    assert any("CaCO3/pH unknown — assume risk" in w for w in rec.warnings_ar)
    assert recommend_phosphorus(SoilContext(p_ppm=20.0, caco3_pct=5.0)).warnings_ar == []


# ─── الفوسفور: محجوب بلا تحليل، وإلّا حسب عتبة Olsen-P ─────────────────────


def test_phosphorus_blocked_without_lab_analysis():
    # absence-of-authority ⇒ BLOCKED (مبدأ حاكم).
    rec = recommend_phosphorus(SoilContext(caco3_pct=25.0))  # كلسيّة لكن بلا p_ppm
    assert rec.status == RecommendationStatus.BLOCKED
    assert rec.source_ar == "—"
    assert "تحليل" in rec.rate_ar
    assert rec.warnings_ar  # تحذير التثبيت موجود


def test_phosphorus_sufficient_is_ok_low_rate():
    # p_ppm 20 >= 10 ⇒ ليس منخفضاً ⇒ OK، ومعدّل "منخفض".
    rec = recommend_phosphorus(SoilContext(p_ppm=20.0, caco3_pct=5.0))
    assert rec.status == RecommendationStatus.OK
    assert rec.rate_ar.startswith("منخفض")
    assert "20" in rec.rate_ar
    # غير كلسيّة ⇒ لا تحذير تثبيت.
    assert rec.warnings_ar == []


def test_phosphorus_low_is_advisory_high_rate():
    # p_ppm 5 < 10 ⇒ منخفض ⇒ ADVISORY، ومعدّل "مرتفع".
    rec = recommend_phosphorus(SoilContext(p_ppm=5.0, caco3_pct=20.0))
    assert rec.status == RecommendationStatus.ADVISORY
    assert rec.rate_ar.startswith("مرتفع")
    # كلسيّة ⇒ تحذير تثبيت الحزم.
    assert any("تثبيت الفوسفور" in w for w in rec.warnings_ar)


def test_phosphorus_olsen_threshold_boundary():
    # عتبة low_p هي p_ppm < 10 ⇒ القيمة 10 بالضبط ليست منخفضة ⇒ OK.
    assert recommend_phosphorus(SoilContext(p_ppm=10.0)).status == RecommendationStatus.OK
    # أقلّ بقليل ⇒ ADVISORY.
    assert recommend_phosphorus(SoilContext(p_ppm=9.9)).status == RecommendationStatus.ADVISORY


def test_phosphorus_non_calcareous_with_value_has_no_fixation_warning():
    rec = recommend_phosphorus(SoilContext(p_ppm=5.0, caco3_pct=5.0))
    assert rec.status == RecommendationStatus.ADVISORY  # منخفض
    assert rec.warnings_ar == []  # غير كلسيّة ⇒ لا تحذير تثبيت


# ─── المغذّيات الصغرى Fe/Zn: محجوبة بلا قيمة، وإلّا تصحيح ورقي ─────────────


def test_iron_blocked_without_value():
    rec = recommend_micronutrient(SoilContext(), Nutrient.FE)
    assert rec.status == RecommendationStatus.BLOCKED
    assert "الحديد" in rec.rate_ar
    assert rec.source_ar == "—"


def test_zinc_blocked_without_value():
    rec = recommend_micronutrient(SoilContext(), Nutrient.ZN)
    assert rec.status == RecommendationStatus.BLOCKED
    assert "الزنك" in rec.rate_ar


def test_iron_with_value_is_advisory_foliar_chelate():
    rec = recommend_micronutrient(SoilContext(fe_ppm=2.0), Nutrient.FE)
    assert rec.status == RecommendationStatus.ADVISORY
    assert "Fe-EDDHA" in rec.source_ar  # مصدر مخلّبي للحديد
    assert "ورقي" in rec.placement_ar  # تطبيق ورقي
    assert "2.0" in rec.rate_ar


def test_zinc_with_value_uses_zinc_source():
    rec = recommend_micronutrient(SoilContext(zn_ppm=1.0), Nutrient.ZN)
    assert rec.status == RecommendationStatus.ADVISORY
    assert "كبريتات الزنك" in rec.source_ar
    assert "الزنك" in rec.rate_ar


def test_micronutrient_selects_correct_value_field():
    # FE يقرأ fe_ppm فقط: zn_ppm مُعطًى لكن fe_ppm None ⇒ يبقى محجوباً.
    rec = recommend_micronutrient(SoilContext(zn_ppm=1.0), Nutrient.FE)
    assert rec.status == RecommendationStatus.BLOCKED


# ─── الخطة الكاملة ────────────────────────────────────────────────────────


def test_full_plan_default_covers_npFeZn():
    plan = full_4r_plan(SoilContext())
    assert [p["nutrient"] for p in plan] == [
        Nutrient.N.value,
        Nutrient.P.value,
        Nutrient.FE.value,
        Nutrient.ZN.value,
    ]
    # كلّ عنصر dict مكتمل (مرّ عبر to_dict).
    for p in plan:
        assert set(p) == {
            "nutrient",
            "status",
            "source_ar",
            "rate_ar",
            "timing_ar",
            "placement_ar",
            "warnings_ar",
        }


def test_full_plan_blocks_p_fe_zn_for_unanalyzed_soil():
    # تربة بلا تحاليل ⇒ P/Fe/Zn محجوبة، N إرشاديّ.
    plan = {p["nutrient"]: p["status"] for p in full_4r_plan(SoilContext(caco3_pct=25.0))}
    assert plan["nitrogen"] == RecommendationStatus.ADVISORY.value
    assert plan["phosphorus"] == RecommendationStatus.BLOCKED.value
    assert plan["iron"] == RecommendationStatus.BLOCKED.value
    assert plan["zinc"] == RecommendationStatus.BLOCKED.value


def test_full_plan_custom_nutrient_subset():
    plan = full_4r_plan(SoilContext(), ["nitrogen"])
    assert len(plan) == 1
    assert plan[0]["nutrient"] == Nutrient.N.value


def test_full_plan_unknown_nutrient_raises():
    with pytest.raises(ValueError):
        full_4r_plan(SoilContext(), ["unobtanium"])


# ─── to_dict ──────────────────────────────────────────────────────────────


def test_to_dict_round_trips_fields():
    rec = FourRRecommendation(
        nutrient=Nutrient.K,
        status=RecommendationStatus.OK,
        source_ar="مصدر",
        rate_ar="معدّل",
        timing_ar="وقت",
        placement_ar="مكان",
        warnings_ar=["تحذير"],
    )
    d = rec.to_dict()
    assert d["nutrient"] == "potassium"
    assert d["status"] == "ok"
    assert d["warnings_ar"] == ["تحذير"]


def test_recommendation_default_warnings_is_empty_list():
    rec = FourRRecommendation(
        nutrient=Nutrient.N,
        status=RecommendationStatus.ADVISORY,
        source_ar="s",
        rate_ar="r",
        timing_ar="t",
        placement_ar="p",
    )
    assert rec.warnings_ar == []


def _approved_p(value, *, unit="mg/kg", method="olsen"):
    return {
        "analyte": "phosphorus_mg_kg",
        "result_id": "r-1",
        "sample_id": "s-1",
        "sampled_on": "2026-11-01",
        "zone_id": "north",
        "value_json": value,
        "method_code": method,
        "unit": unit,
    }


@pytest.mark.parametrize("value, status", [(0, "advisory"), ("5", "advisory"), (15, "ok")])
def test_approved_olsen_changes_advice_with_sample_level_provenance(value, status):
    from api.nutrient_4r import approved_sample_4r_plan

    plan = approved_sample_4r_plan("f-1", [_approved_p(value)])
    assert (plan["field_id"], plan["sample_id"], plan["zone_id"]) == (
        "f-1",
        "s-1",
        "north",
    )
    assert plan["scope"] == "sample"
    assert plan["evidence_ids"] == {"p_ppm": "r-1"}
    assert {r["nutrient"]: r["status"] for r in plan["plan"]}["phosphorus"] == status


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_approved_p(5, method=None)],
        [_approved_p(5, method="total_p")],
        [_approved_p(5, unit="%")],
        [_approved_p(True)],
        [_approved_p(-2)],
        [_approved_p("NaN")],
        [_approved_p(5) | {"result_id": None}],
    ],
)
def test_missing_or_incomparable_evidence_does_not_issue_plan(rows):
    from api.nutrient_4r import approved_sample_4r_plan

    plan = approved_sample_4r_plan("f-1", rows)
    assert (plan["status"], plan["plan"], plan["evidence_ids"]) == (
        "unavailable",
        [],
        {},
    )


def test_field_and_manual_http_contracts(monkeypatch):
    from api import main
    from api.main import get_current_user
    from api.routers import nutrients
    from core.canonical_schemas import UserRole, UserSchema
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    tenant = "00000000-0000-0000-0000-000000000001"
    user = UserSchema(user_id="u", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير")
    monkeypatch.setattr(main, "_DB_POOL", None)
    app = FastAPI()
    app.include_router(nutrients.router)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    url = "/api/v1/nutrients/4r-plan"
    assert client.post(url).status_code == 422
    manual = client.post(url, json={"p_ppm": 5})
    assert manual.status_code == 200 and set(manual.json()) == {"plan"}
    assert client.post(url, params={"field_id": "f"}, json={"p_ppm": 5}).status_code == 422
    assert client.post(url, params={"field_id": "f"}).status_code == 503

    scenario = {
        "input_basis": "synthetic",
        "source_ref": "fixture:180ha/pivot-a/wheat-1",
        "nutrient_basis": "N",
        "target_yield_t_ha": 6,
        "uptake_kg_per_t": 25,
        "soil_supply_kg_ha": 30,
        "fertilizer_grade_pct": 46,
        "use_efficiency": 0.75,
    }
    response = client.post(url, json={"p_ppm": 5, "fertilizer_scenario": scenario})
    assert response.status_code == 200
    result = response.json()
    assert result["plan"] == manual.json()["plan"]
    calculation = result["fertilizer_scenario"]
    assert calculation["status"] == "estimated"
    assert calculation["inputs"] == scenario
    assert calculation["estimate"]["nutrient_to_apply_kg_ha"] == 160
    assert calculation["estimate"]["product_kg_ha"] == 347.83
    assert calculation["source_ref_verified"] is False
    assert calculation["lab_supported"] is False
    assert calculation["execution_authorized"] is False
    assert calculation["local_compliance_evaluated"] is False

    # An explicitly zero supply is a scenario input, not an implicit default.
    zero_supply = {**scenario, "soil_supply_kg_ha": 0}
    assert client.post(url, json={"fertilizer_scenario": zero_supply}).status_code == 200
    for key in scenario:
        missing = {k: v for k, v in scenario.items() if k != key}
        assert client.post(url, json={"fertilizer_scenario": missing}).status_code == 422
    for changes in (
        {"source_ref": " "},
        {"nutrient_basis": "P"},
        {"soil_supply_kg_ha": True},
        {"use_efficiency": 0},
        {"target_yield_t_ha": 1e308},
        {"input_basis": "approved_soil_lab"},
        {"execution_authorized": True},
    ):
        invalid = {**scenario, **changes}
        assert client.post(url, json={"fertilizer_scenario": invalid}).status_code == 422
    assert client.post(
        url, params={"field_id": "f"}, json={"fertilizer_scenario": scenario}
    ).status_code == 422
