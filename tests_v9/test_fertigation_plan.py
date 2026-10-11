"""عقد الريّ والتسميد الموحّد — الحساب والحالات الستّ، وبقاؤه غير موصول.

المثال المرجعيّ من مراجعة المالك (توضيحيّ لا وصفة): قطاع 4 هكتارات، احتياج صافٍ 10 مم،
كفاءة 90% ⇒ ~444 م³؛ 16 كجم N محقونة خلال نصف الحجم ⇒ 72 ملجم/لتر أثناء الحقن مقابل 36 على
الرية كلّها.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.precision_agriculture import fertigation_plan as fp
from shared.precision_agriculture.fertigation_plan import (
    FertigationDecisionOutcome,
    FertigationInputs,
    InjectorReadiness,
)

pytestmark = pytest.mark.unit

READY = InjectorReadiness(calibrated=True, flow_interlock=True, backflow_prevention=True)


def _inputs(**overrides):
    base = dict(
        water_need_net_mm=10.0,
        area_ha=4.0,
        application_efficiency=0.9,
        irrigation_method="drip",
        nutrient_need_kg_n=16.0,
        injection_fraction=0.5,
        max_injection_concentration_mg_l=100.0,
        recipe_resolved=True,
        injector=READY,
    )
    base.update(overrides)
    return FertigationInputs(**base)


def test_oxides_are_converted_to_elements_and_back():
    assert fp.p_from_p2o5(100) == pytest.approx(43.64)
    assert fp.k_from_k2o(100) == pytest.approx(83.01)
    assert fp.p2o5_from_p(fp.p_from_p2o5(37.0)) == pytest.approx(37.0)
    assert fp.k2o_from_k(fp.k_from_k2o(12.5)) == pytest.approx(12.5)


def test_the_owner_example_concentration_doubles_inside_the_injection_window():
    decision = fp.decide(_inputs())
    assert decision.outcome is FertigationDecisionOutcome.IRRIGATION_WITH_FERTIGATION
    assert decision.gross_water_m3 == pytest.approx(444.44, abs=0.01)
    assert decision.whole_irrigation_average_mg_l == pytest.approx(36.0)
    assert decision.injection_concentration_mg_l == pytest.approx(72.0)


def test_a_dose_that_does_not_fit_is_split_not_carried_by_extra_water():
    decision = fp.decide(_inputs(max_injection_concentration_mg_l=50.0))
    assert decision.outcome is FertigationDecisionOutcome.SPLIT_DOSE
    assert decision.gross_water_m3 == pytest.approx(444.44, abs=0.01), "الماء لم يُزَد لحمل السماد"
    assert decision.dose_now_kg_n == pytest.approx(11.11, abs=0.01)
    assert decision.dose_now_kg_n + decision.dose_remaining_kg_n == pytest.approx(16.0)
    assert decision.injection_concentration_mg_l == 50.0


@pytest.mark.parametrize(
    "need,reason", [(None, "nutrient_need_unknown"), (0.0, "no_nutrient_need")]
)
def test_irrigation_only_is_the_default_when_nutrients_are_not_established(need, reason):
    decision = fp.decide(_inputs(nutrient_need_kg_n=need))
    assert decision.outcome is FertigationDecisionOutcome.IRRIGATION_ONLY
    assert decision.reasons == [reason] and decision.dose_now_kg_n == 0.0


def test_no_water_need_defers_nutrients_instead_of_irrigating_to_carry_them():
    decision = fp.decide(_inputs(water_need_net_mm=0.0))
    assert decision.outcome is FertigationDecisionOutcome.DEFER_INJECTION
    assert decision.gross_water_m3 is None and decision.dose_remaining_kg_n == 16.0
    assert fp.decide(_inputs(water_need_net_mm=0.0, nutrient_need_kg_n=0.0)).outcome is (
        FertigationDecisionOutcome.NO_ACTION
    )


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"injector": InjectorReadiness()}, "injector_not_calibrated"),
        (
            {"injector": InjectorReadiness(calibrated=True, backflow_prevention=True)},
            "injector_not_interlocked_to_water_flow",
        ),
        ({"recipe_resolved": False}, "recipe_unresolved"),
        ({"injection_fraction": None}, "injection_fraction_unresolved"),
        ({"max_injection_concentration_mg_l": None}, "injection_concentration_limit_unresolved"),
        ({"irrigation_method": "center_pivot"}, "injection_model_missing_for:center_pivot"),
    ],
)
def test_unresolved_recipe_or_hardware_irrigates_without_injecting(overrides, reason):
    decision = fp.decide(_inputs(**overrides))
    assert decision.outcome is FertigationDecisionOutcome.IRRIGATION_ONLY
    assert "injection_blocked" in decision.reasons and reason in decision.reasons
    assert decision.dose_now_kg_n == 0.0 and decision.dose_remaining_kg_n == 16.0


@pytest.mark.parametrize("water", [float("nan"), -1.0, None, True])
def test_an_unresolved_water_need_blocks(water):
    assert fp.decide(_inputs(water_need_net_mm=water)).outcome is FertigationDecisionOutcome.BLOCKED


def test_an_injector_stop_records_what_was_delivered_not_what_was_planned():
    assert fp.delivered_kg(16.0, 222.2, 111.1) == pytest.approx(8.0)
    assert fp.delivered_kg(16.0, 222.2, 400.0) == 16.0


ROOT = Path(__file__).resolve().parents[1]


def test_the_contract_stays_unwired_while_the_schema_forbids_fertigation():
    """لا يستورده مسارٌ إنتاجيّ في ``services/`` ولا ``shared/`` — موضعُه خارج المنصّة لأنّه
    غير موصول (سابقة ``ci10_knowledge_layer_note``: لا تُقبَل وحدةٌ بلا مستهلكٍ إنتاجيّ)."""
    importers = [
        str(p.relative_to(ROOT))
        for base in ("services", "shared")
        for p in (ROOT / base).rglob("*.py")
        if p.name != "fertigation_plan.py"
        and not p.name.startswith("test_")
        and "tests" not in p.parts
        and "fertigation_plan" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert importers == [], f"عقد التسميد موصولٌ بمسار قرار قبل رفع الحجر: {importers}"
    schema = json.loads(
        (
            ROOT
            / "services/sahool-platform/schemas/irrigation-contracts/v1.1-errata2"
            / "decision-evidence-envelope.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["properties"]["fertigation_candidate_id"]["type"] == "null"
    assert schema["properties"]["decision_domains"]["items"]["const"] == "irrigation"
