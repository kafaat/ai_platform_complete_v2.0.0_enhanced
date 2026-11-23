#!/usr/bin/env python3
"""F-E11 — المحاكاة تستقبل الإجراء الذي اختاره القرار، أو تقول إنّها لم تحاكِه.

قبل الإصلاح كان ``simulate_adapter`` يستقبل ``decision`` ولا يقرؤه: يرسل
``scenario="recommended_action"`` ثابتاً، فيقارن الموجِّه ريّاً كاملاً ببلا ريّ أيّاً كان
الإجراء المختار (غسيل ملوحة، فحص ميدانيّ، ريّ بمقدار) ثمّ يُسمّى الناتج «أثر الإجراء
المقترَح». كلّ اختبار هنا يقيس **ما وصل** إلى الطلب أو المحرّك، لا وجود حقل.
"""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def adapters():
    import core.field_intelligence_adapters as mod

    return mod


@pytest.fixture
def route():
    import api.routers.simulate as mod

    return mod


def _field_request():
    return SimpleNamespace(field_id="F1", crop="قمح صلب", lat=15.0, lon=44.0, tenant_id="t1")


def _irrigation_decision(quantity=25.0, unit="mm", apply_at="2026-06-12"):
    return {
        "actionable": True,
        "action_type": "irrigation",
        "structured": {"quantity": quantity, "unit": unit, "apply_at": apply_at},
    }


def _capture_post(monkeypatch, adapters, response):
    sent: list[dict] = []

    def _post(url, payload, **kw):
        sent.append({"url": url, "payload": copy.deepcopy(payload)})
        return response(payload) if callable(response) else response

    monkeypatch.setattr(adapters, "_post_json", _post)
    return sent


def _refusal(payload):
    return {
        "available": False,
        "selected_action": payload.get("selected_action"),
        "selected_action_simulated": False,
        "not_simulated_reason": "engine_has_no_dated_application_input",
        "note_ar": "x",
    }


# ══════════════════════════════════════════════════════════════
# المُوائم — الطلب يُبنى من الإجراء المختار
# ══════════════════════════════════════════════════════════════


def test_the_request_carries_the_chosen_action_type_amount_unit_and_time(adapters, monkeypatch):
    sent = _capture_post(monkeypatch, adapters, _refusal)

    adapters.simulate_adapter(_field_request(), _irrigation_decision(), state=None)

    assert len(sent) == 1
    assert sent[0]["url"].endswith("/api/v1/simulate/what-if")
    assert sent[0]["payload"]["selected_action"] == {
        "action_type": "irrigation",
        "amount": {"value": 25.0, "unit": "mm"},
        "apply_at": "2026-06-12",
    }


def test_two_different_amounts_are_two_different_requests(adapters, monkeypatch):
    """العطل الأصليّ: الطلب نفسه بالضبط أيّاً كان المقدار — «سيناريو ثابت»."""
    sent = _capture_post(monkeypatch, adapters, _refusal)

    adapters.simulate_adapter(_field_request(), _irrigation_decision(quantity=10.0), state=None)
    adapters.simulate_adapter(_field_request(), _irrigation_decision(quantity=40.0), state=None)

    assert sent[0]["payload"] != sent[1]["payload"]
    assert [p["payload"]["selected_action"]["amount"]["value"] for p in sent] == [10.0, 40.0]


def test_no_fixed_scenario_name_stands_in_for_the_action(adapters, monkeypatch):
    sent = _capture_post(monkeypatch, adapters, _refusal)

    adapters.simulate_adapter(_field_request(), _irrigation_decision(), state=None)

    assert "scenario" not in sent[0]["payload"]


@pytest.mark.parametrize(
    ("decision", "expected_action"),
    [
        (
            {
                "actionable": True,
                "action_type": "soil_remediation",
                "structured": {"issue": "salinity", "severity": "critical"},
            },
            {"action_type": "soil_remediation", "amount": None, "apply_at": None},
        ),
        (
            {"actionable": True, "action_type": "investigate_stress"},
            {"action_type": "investigate_stress", "amount": None, "apply_at": None},
        ),
    ],
)
def test_todays_policy_actions_are_sent_as_they_are_without_an_invented_amount(
    adapters, monkeypatch, decision, expected_action
):
    """``_derive_policy`` لا يُنتج مقداراً ولا وقتاً اليوم — فلا يُختلَقان في الطلب."""
    sent = _capture_post(monkeypatch, adapters, _refusal)

    out = adapters.simulate_adapter(_field_request(), decision, state=None)

    assert sent[0]["payload"]["selected_action"] == expected_action
    assert out["selected_action_simulated"] is False
    assert out["not_simulated_reason"] == "engine_has_no_dated_application_input"
    assert out["baseline_yield_t_ha"] is None and out["action_yield_t_ha"] is None
    assert out["recommended_action_helps"] is None


def test_a_decision_without_an_action_type_is_not_sent_at_all(adapters, monkeypatch):
    """قرار «تابِع عن قرب» (اتّجاه NDVI هابط) قابل للتنفيذ بلا نوع إجراء: لا شيء يُحاكى."""
    sent = _capture_post(monkeypatch, adapters, _refusal)

    out = adapters.simulate_adapter(
        _field_request(), {"actionable": True, "recommendations_ar": ["تابع"]}, state=None
    )

    assert sent == []
    assert out["selected_action"] is None
    assert out["selected_action_simulated"] is False
    assert out["not_simulated_reason"] == "decision_has_no_action_type"
    assert out["recommended_action_helps"] is None


@pytest.mark.parametrize(
    "structured",
    [
        {"quantity": "كثير", "unit": "mm", "apply_at": "2026-06-12"},
        {"quantity": True, "unit": "mm", "apply_at": "2026-06-12"},
        {"quantity": -5, "unit": "mm", "apply_at": "2026-06-12"},
        {"quantity": float("nan"), "unit": "mm", "apply_at": "2026-06-12"},
        {"quantity": 25.0, "unit": "", "apply_at": "2026-06-12"},
        {"quantity": 25.0, "apply_at": "2026-06-12"},
    ],
)
def test_an_unusable_amount_is_sent_as_missing_not_repaired(adapters, monkeypatch, structured):
    sent = _capture_post(monkeypatch, adapters, _refusal)

    adapters.simulate_adapter(
        _field_request(),
        {"actionable": True, "action_type": "irrigation", "structured": structured},
        state=None,
    )

    assert sent[0]["payload"]["selected_action"]["amount"] is None


def test_an_answer_that_does_not_confirm_the_selected_action_is_not_reported_as_its_effect(
    adapters, monkeypatch
):
    """نسخة أقدم من المنصّة تتجاهل ``selected_action`` وتُعيد مقارنة الريّ العامّة.

    أرقامها ليست أثر الإجراء المختار، فلا تُنسَب إليه (نشر متدرّج).
    """
    _capture_post(
        monkeypatch,
        adapters,
        {
            "available": True,
            "scenario": "reduce_irrigation",
            "baseline_yield_t_ha": 3.0,
            "action_yield_t_ha": 4.0,
            "water_saved_mm": 120.0,
            "recommended_action_helps": True,
        },
    )

    out = adapters.simulate_adapter(_field_request(), _irrigation_decision(), state=None)

    assert out["selected_action_simulated"] is False
    assert out["not_simulated_reason"] == "simulator_did_not_confirm_selected_action"
    assert out["baseline_yield_t_ha"] is None and out["action_yield_t_ha"] is None
    assert out["water_saved_mm"] is None
    assert out["recommended_action_helps"] is None


def test_an_unreachable_simulator_is_stated_not_silent(adapters, monkeypatch):
    _capture_post(monkeypatch, adapters, None)

    out = adapters.simulate_adapter(_field_request(), _irrigation_decision(), state=None)

    assert out["selected_action_simulated"] is False
    assert out["not_simulated_reason"] == "simulator_unreachable"
    assert out["selected_action"]["action_type"] == "irrigation"


def test_a_confirmed_simulation_is_relayed_with_the_action_it_tested(adapters, monkeypatch):
    """عقد المُوائم حين يؤكّد المحاكي أنّه حاكى الإجراء نفسه (لا يُنتجه المحاكي اليوم)."""

    def _confirmed(payload):
        return {
            "available": True,
            "selected_action": payload["selected_action"],
            "selected_action_simulated": True,
            "baseline_yield_t_ha": 3.0,
            "action_yield_t_ha": 3.01,
            "water_saved_mm": -25.0,
        }

    _capture_post(monkeypatch, adapters, _confirmed)

    out = adapters.simulate_adapter(_field_request(), _irrigation_decision(), state=None)

    assert out["selected_action_simulated"] is True
    assert out["not_simulated_reason"] is None
    assert out["selected_action"]["amount"] == {"value": 25.0, "unit": "mm"}
    assert out["baseline_yield_t_ha"] == 3.0 and out["action_yield_t_ha"] == 3.01
    assert out["recommended_action_helps"] is False


# ══════════════════════════════════════════════════════════════
# الموجِّه — إجراء لا يُعبَّر عنه لا يُستبدَل بسيناريو ثابت
# ══════════════════════════════════════════════════════════════


def _engine_must_not_run(monkeypatch):
    import shared.wofost as pkg

    async def _forbidden(*a, **k):
        raise AssertionError("شُغِّل المحرّك بسيناريو ثابت بدل الإجراء المختار")

    monkeypatch.setattr(pkg, "simulate_wofost", _forbidden)


def _what_if(route, selected_action=None, **kw):
    args = {"field_id": "F1", "lat": 15.0, "lon": 44.0}
    args.update(kw)
    if selected_action is not None:
        args["selected_action"] = selected_action
    req = route.SelectedActionWhatIfRequest(**args)
    return asyncio.run(route.simulate_what_if(req, user=None))


@pytest.mark.parametrize(
    ("selected_action", "reason"),
    [
        ({"action_type": "soil_remediation"}, "action_type_not_modelled"),
        ({"action_type": "investigate_stress"}, "action_type_not_modelled"),
        (
            {
                "action_type": "fertilization",
                "amount": {"value": 50, "unit": "kg/ha"},
                "apply_at": "2026-06-12",
            },
            "action_type_not_modelled",
        ),
        ({"action_type": "irrigation", "apply_at": "2026-06-12"}, "action_amount_missing"),
        (
            {"action_type": "irrigation", "amount": {"value": 25, "unit": "mm"}},
            "action_time_missing",
        ),
        (
            {
                "action_type": "irrigation",
                "amount": {"value": 25, "unit": "mm"},
                "apply_at": "2026-06-12",
            },
            "engine_has_no_dated_application_input",
        ),
    ],
)
def test_an_action_the_simulator_cannot_express_is_refused_by_name(
    route, monkeypatch, selected_action, reason
):
    _engine_must_not_run(monkeypatch)

    out = _what_if(route, selected_action)

    assert out["available"] is False
    assert out["error_code"] == "SELECTED_ACTION_NOT_SIMULATED"
    assert out["selected_action_simulated"] is False
    assert out["not_simulated_reason"] == reason
    assert out["selected_action"]["action_type"] == selected_action["action_type"]
    for key in ("baseline_yield_t_ha", "action_yield_t_ha", "recommended_action_helps"):
        assert key not in out, f"رقمٌ بلا محاكاة: {key}"


def test_the_refusal_does_not_depend_on_the_legacy_scenario_field(route, monkeypatch):
    """``scenario`` لا يُعيد السيناريو الثابت من الباب الخلفيّ حين يُرسَل إجراء مختار."""
    _engine_must_not_run(monkeypatch)

    out = _what_if(route, {"action_type": "soil_remediation"}, scenario="recommended_action")

    assert out["selected_action_simulated"] is False
    assert "scenario_irrigation_fraction" not in out


@pytest.mark.parametrize(
    "selected_action",
    [
        {"action_type": ""},
        {"action_type": "irrigation", "amount": {"value": 0, "unit": "mm"}},
        {"action_type": "irrigation", "amount": {"value": -1, "unit": "mm"}},
        {"action_type": "irrigation", "amount": {"value": 25, "unit": ""}},
        {"action_type": "irrigation", "amount": {"value": 25}},
        {"action_type": "irrigation", "amount": 25},
    ],
)
def test_a_malformed_selected_action_is_rejected_by_the_model(route, selected_action):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        route.SelectedActionWhatIfRequest(field_id="F1", selected_action=selected_action)


def test_an_invalid_application_time_is_rejected_not_guessed(route, monkeypatch):
    from fastapi import HTTPException

    _engine_must_not_run(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _what_if(
            route,
            {
                "action_type": "irrigation",
                "amount": {"value": 25, "unit": "mm"},
                "apply_at": "بعد غد",
            },
        )
    assert exc.value.status_code == 422
    assert "apply_at" in str(exc.value.detail)


def test_a_request_without_a_selected_action_is_labelled_a_generic_comparison(route, monkeypatch):
    """مقارنة الريّ العامّة باقية لمستهلكها (الواجهة)، لكنّها تُسمّى باسمها."""
    import shared.wofost as pkg

    async def _arm(*a, **k):
        return {
            "simulation": {"yield_t_ha": 1.0},
            "water_balance": {"irrigation_applied_mm": 10.0},
            "parameter_resolution": {"degraded": False},
        }

    monkeypatch.setattr(pkg, "simulate_wofost", _arm)

    out = _what_if(route, scenario="recommended_action")

    assert out["available"] is True
    assert out["comparison_kind"] == "generic_irrigation_scenario"
    assert out["selected_action_simulated"] is False
    assert out["selected_action"] is None


# ══════════════════════════════════════════════════════════════
# المنسِّق — المحاكاة تشرح القرار ولا تختاره
# ══════════════════════════════════════════════════════════════


def _run_coordinator(simulate_fn):
    from core.field_intelligence_coordinator import FieldRequest, run_field_intelligence

    def sens(req):
        return {
            "ndvi": 0.3,
            "ndre": 0.25,
            "cloud_cover": 10,
            "resolution_m": 10.0,
            "observed_at": "2026-06-10T00:00:00+00:00",
        }

    def soil(req):
        return {"ec_dsm": 8.0, "sampled_at": "2026-06-09T00:00:00+00:00"}

    req = FieldRequest(field_id="f1", lat=16.79, lon=44.33, crop="قمح صلب", tenant_id="t1")
    return run_field_intelligence(req, sensing_fn=sens, soil_fn=soil, simulate_fn=simulate_fn)


def _policy_core(result):
    d = result.policy_decision
    return (d.get("actionable"), d.get("action_type"), tuple(d.get("recommendations_ar") or ()))


def test_the_output_states_that_the_simulation_only_explains_the_decision():
    result = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": False, "not_simulated_reason": "x"}
    )

    assert result.policy_decision["actionable"] is True, "شرط الاختبار: قرار قابل للتنفيذ"
    assert result.simulation["decision_influence"] == "explains_only"
    assert result.simulation["decision_influence_note_ar"]


def test_a_simulate_fn_cannot_claim_it_influenced_the_decision():
    result = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": True, "decision_influence": "influenced"}
    )

    assert result.simulation["decision_influence"] == "explains_only"


def test_a_failed_simulation_still_states_its_role():
    def _boom(req, d, s):
        raise RuntimeError("down")

    result = _run_coordinator(_boom)

    assert "error" in result.simulation
    assert result.simulation["decision_influence"] == "explains_only"


def test_the_selected_policy_is_the_same_whatever_the_simulation_says():
    without = _run_coordinator(None)
    helps = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": True, "recommended_action_helps": True}
    )
    hurts = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": True, "recommended_action_helps": False}
    )

    assert _policy_core(without) == _policy_core(helps) == _policy_core(hurts)
    assert without.simulation == {}


def test_the_feasibility_caveat_needs_a_simulation_of_the_selected_action():
    """«أثر محدود للإجراء المقترَح» لا يُقال عن مقارنةٍ لم تحاكِ الإجراء المختار."""
    generic = _run_coordinator(lambda req, d, s: {"recommended_action_helps": False})
    not_simulated = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": False, "recommended_action_helps": False}
    )
    simulated = _run_coordinator(
        lambda req, d, s: {"selected_action_simulated": True, "recommended_action_helps": False}
    )

    assert "simulation_caveat_ar" not in generic.policy_decision
    assert "simulation_caveat_ar" not in not_simulated.policy_decision
    assert simulated.policy_decision["simulation_caveat_ar"]


def test_the_live_adapter_receives_the_decision_the_policy_selected(adapters, monkeypatch):
    """السلسلة كاملةً: ما يصل الطلب هو ``action_type`` الذي اشتقّته السياسة."""
    sent = _capture_post(monkeypatch, adapters, _refusal)

    result = _run_coordinator(adapters.simulate_adapter)

    assert result.policy_decision["action_type"] == "soil_remediation"
    assert sent[0]["payload"]["selected_action"]["action_type"] == "soil_remediation"
    assert result.simulation["selected_action_simulated"] is False
    assert result.simulation["not_simulated_reason"] == "engine_has_no_dated_application_input"
    assert "simulation_caveat_ar" not in result.policy_decision
