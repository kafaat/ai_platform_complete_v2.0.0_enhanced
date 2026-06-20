"""اختبار طبقة استخراج سلسلة شرح القرار (api.decision_explain) — نقيّ حتميّ، بلا قاعدة.

يثبت دالّة explain_decision النقيّة:
  (أ) decision_value كامل (profit_aware) ⇒ سلسلة شرح صحيحة (ثقة/إشارات/سياسة/قيود/إجراء)؛
  (ب) حقول غائبة ⇒ غياب صريح (present=False / None) لا اختلاق؛
  (ج) الأنواع الثلاثة (crop_twin / irrigation_plan-only / profit_aware)؛
  (د) السياسة: profit_aware يكشف resolved≠applied؛ crop_twin يشتقّ applied فقط (resolved=None)؛
  (هـ) القيود: المخاطر «يحتاج بيانات» لا تُحتسب قيداً فاعلاً؛ السقوف غير المُمرَّرة None؛
  (و) calibrated=False وdecision_value فارغ/None ⇒ سلسلة بكتل غائبة (لا انهيار).
بلا شبكة/قاعدة/ساعة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.decision_explain import explain_decision  # noqa: E402


def _profit_aware_decision() -> dict:
    """decision_value كامل من المسار الواعي بالربح (profit_aware) — كلّ الحقول حاضرة."""
    return {
        "decision_id": "dec_abc123",
        "field_id": "f-1",
        "crop": "wheat",
        "crop_known": True,
        "confidence": 0.72,
        "data_quality": "partial",
        "water_state": {"needs_irrigation": True, "depletion_mm": 18.0, "deficit_mm": 6.5},
        "nutrient_state": {"stage": "tillering", "remaining_need_kg_ha": 40.0},
        "phenology": {"stage": "vegetative", "past_maturity": False},
        "risks": [
            {"key": "water", "label_ar": "مائي", "level_ar": "مرتفع"},
            {"key": "heat", "label_ar": "حراريّ", "level_ar": "يحتاج بيانات"},
            {"key": "salinity", "label_ar": "ملوحة", "level_ar": "يحتاج بيانات"},
        ],
        "stress_flags": [{"code": "water_deficit", "label_ar": "عجز مائيّ — الريّ مستحقّ"}],
        "irrigation": {
            "policy": "profit_max",
            "total_mm": 24.0,
            "n_events": 2,
            "next_event_day": 1,
            "next_event_mm": 12.0,
            "stress_days": 0,
            "action_ar": "ريّ 12 مم يوم 2",
        },
        "irrigation_plan": {
            "policy": "water_saving",  # تراجع عن resolved لنقص الأسعار
            "total_irrigation_mm": 24.0,
            "max_application_mm": 15.0,
            "season_budget_mm": 300.0,
            "budget_exhausted": False,
        },
        "fertilization": {"due": True, "action_ar": "احتياج متبقٍّ ~40 كجم/هكتار"},
        "dynamic_kc": 0.85,
        "economic_state": {"status": "partial"},
        "policy_decision": {
            "resolved_policy": "profit_max",
            "applied_policy": "water_saving",
            "auto": True,
            "reasons_ar": ["بئر عميق — ماء غالٍ"],
        },
        "calibrated": False,
    }


# ── (أ) decision_value كامل ⇒ سلسلة شرح صحيحة ──


def test_full_decision_yields_correct_chain():
    out = explain_decision(_profit_aware_decision())
    assert out["has_decision_value"] is True
    assert out["calibrated"] is False
    assert out["decision_id"] == "dec_abc123"
    assert out["crop"] == "wheat"

    # confidence
    assert out["confidence"]["value"] == 0.72
    assert out["confidence"]["present"] is True
    assert out["confidence"]["data_quality"] == "partial"

    # signals: حالة المدخلات
    sig = out["signals"]
    assert sig["water"]["present"] is True
    assert sig["water"]["needs_irrigation"] is True
    assert sig["water"]["depletion_mm"] == 18.0
    assert sig["nutrient"]["stage"] == "tillering"
    assert sig["phenology"]["stage"] == "vegetative"
    assert {r["key"] for r in sig["risks"]} == {"water", "heat", "salinity"}
    assert sig["stress_flags"][0]["code"] == "water_deficit"

    # final: الإجراء + الكمّيّة
    final = out["final"]
    assert final["present"] is True
    assert final["recommended_action"] == "ريّ 12 مم يوم 2"
    assert final["next_event_mm"] == 12.0
    assert final["total_irrigation_mm"] == 24.0
    assert final["dynamic_kc"] == 0.85
    assert final["fertilization"]["due"] is True


# ── (د) السياسة: profit_aware يكشف resolved≠applied ──


def test_policy_resolved_differs_from_applied():
    out = explain_decision(_profit_aware_decision())
    pol = out["policy"]
    assert pol["present"] is True
    assert pol["resolved"] == "profit_max"  # ما اختاره الاقتصاد
    assert pol["applied"] == "water_saving"  # ما طبّقته الخطّة (تراجع)
    assert pol["auto"] is True
    assert pol["reasons_ar"] == ["بئر عميق — ماء غالٍ"]


# ── (هـ) القيود ──


def test_constraints_active_risks_only():
    out = explain_decision(_profit_aware_decision())
    con = out["constraints"]
    assert con["max_application_mm"] == 15.0
    assert con["season_budget_mm"] == 300.0
    assert con["budget_exhausted"] is False
    assert con["economic_status"] == "partial"
    # «يحتاج بيانات» (heat/salinity) لا يُحتسب قيداً فاعلاً — فقط مائي «مرتفع».
    assert [r["key"] for r in con["active_risks"]] == ["water"]


# ── (ب) حقول غائبة ⇒ غياب صريح لا اختلاق ──


def test_missing_fields_absent_not_fabricated():
    out = explain_decision({"crop": "barley"})  # decision_value هزيل
    assert out["has_decision_value"] is True  # غير فارغ (فيه crop)
    assert out["confidence"]["value"] is None
    assert out["confidence"]["present"] is False
    assert out["signals"]["water"]["present"] is False
    assert out["signals"]["water"]["needs_irrigation"] is None
    assert out["signals"]["nutrient"]["present"] is False
    assert out["signals"]["risks"] == []
    assert out["constraints"]["max_application_mm"] is None
    assert out["constraints"]["active_risks"] == []
    assert out["constraints"]["economic_status"] is None
    assert out["final"]["present"] is False
    assert out["final"]["recommended_action"] is None
    assert out["policy"]["present"] is False
    assert out["policy"]["resolved"] is None


def test_empty_and_none_decision_value_no_crash():
    for dv in (None, {}, "not-a-dict", 42):
        out = explain_decision(dv)  # type: ignore[arg-type]
        assert out["has_decision_value"] is False  # فارغ/None ⇒ False (لا تلفيق)
        assert out["confidence"]["present"] is False
        assert out["final"]["present"] is False
        assert out["calibrated"] is False


# ── (ج) الأنواع الثلاثة ──


def test_crop_twin_type_derives_applied_policy_only():
    """crop_twin بسيط (لا policy_decision) ⇒ applied من irrigation، resolved=None."""
    dv = {
        "crop": "maize",
        "confidence": 0.6,
        "water_state": {"needs_irrigation": False},
        "irrigation": {"policy": "water_saving", "total_mm": 0.0, "action_ar": "لا ريّ مستحقّ"},
        "risks": [{"key": "water", "label_ar": "مائي", "level_ar": "منخفض"}],
    }
    out = explain_decision(dv)
    assert out["policy"]["present"] is True
    assert out["policy"]["applied"] == "water_saving"
    assert out["policy"]["resolved"] is None  # لم تُختَر آليّاً (لا اختلاق)
    assert out["policy"]["auto"] is False
    # «منخفض» ليس قيداً فاعلاً.
    assert out["constraints"]["active_risks"] == []
    assert out["final"]["recommended_action"] == "لا ريّ مستحقّ"


def test_irrigation_plan_only_type_falls_back_to_plan():
    """نوع يحمل irrigation_plan فقط (لا كتلة irrigation مُؤلَّفة) ⇒ يُشتقّ منه."""
    dv = {
        "crop": "potato",
        "irrigation_plan": {
            "policy": "balanced",
            "total_irrigation_mm": 30.0,
            "max_application_mm": 20.0,
        },
    }
    out = explain_decision(dv)
    assert out["policy"]["applied"] == "balanced"  # من الخطّة
    assert out["final"]["present"] is True
    assert out["final"]["total_irrigation_mm"] == 30.0  # رجوع لإجماليّ الخطّة
    assert out["final"]["recommended_action"] is None  # لا action_ar مُؤلَّف (لا اختلاق)
    assert out["constraints"]["max_application_mm"] == 20.0
