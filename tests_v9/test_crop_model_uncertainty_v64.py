"""تحقّق V64 — «لا غلّة بلا عدم يقين»: كلّ مخرَج simulate يحمل نطاقاً نموذجيّاً.

- ``simulate`` يُرفِق ``yield_interval`` دائماً (نقطة + حدّان + عدم يقين + ثقة + مُوجِّهات).
- النطاق يحيط بالنقطة (low ≤ point ≤ high) وحتميّ (تكرار الإدخال ⇒ تكرار المخرَج).
- مدخلات أوفى ⇒ نطاق أضيق (رتابة صدق: نقص البيانات يوسّع النطاق).
- المُوجِّهات تُدرِج سبب كلّ توسيع (لا رقم بلا سبب).
- ``method="deterministic_model_band"`` صريح — ليس conformal التجريبيّ (فصل صادق).
- ``profit_planner`` يمرّر مدى ربح (low ≤ expected ≤ high) عند توفّر النطاق.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_AGRIAI = _ROOT / "services" / "agriai-engine"
if str(_AGRIAI) not in sys.path:
    sys.path.insert(0, str(_AGRIAI))

import profit_planner as P  # noqa: E402
import wofost_adapter as W  # noqa: E402

_RICH = {
    "crop": {"max_yield_kg_ha": 8000.0, "water_use_efficiency": 18.0},
    "weather": {"gdd": 1600.0, "total_rain_mm": 300.0},
    "soil": {"available_water_mm": 60.0},
    "agromanagement": {"irrigation_mm": 120.0},
}


def test_simulate_always_carries_yield_interval():
    out = W.simulate({}, {}, {}, {})
    assert "yield_interval" in out, "لا غلّة بلا عدم يقين"
    yi = out["yield_interval"]
    for key in ("point_kg_ha", "low_kg_ha", "high_kg_ha", "relative_uncertainty", "confidence"):
        assert key in yi


def test_interval_brackets_point_and_is_ordered():
    out = W.simulate(**_RICH)
    yi = out["yield_interval"]
    assert yi["low_kg_ha"] <= yi["point_kg_ha"] <= yi["high_kg_ha"]
    assert 0.0 <= yi["relative_uncertainty"] <= 0.6
    assert yi["confidence"] in {"high", "medium", "low"}


def test_richer_inputs_narrow_the_band():
    empty = W.simulate({}, {}, {}, {})["yield_interval"]["relative_uncertainty"]
    rich = W.simulate(**_RICH)["yield_interval"]["relative_uncertainty"]
    assert rich < empty, "نقص المدخلات يجب أن يوسّع عدم اليقين"


def test_missing_inputs_are_named_in_drivers():
    yi = W.simulate({}, {}, {}, {})["yield_interval"]
    drivers = yi["drivers"]
    for expected in (
        "missing_daily_weather",
        "missing_rainfall",
        "missing_soil_water",
        "missing_irrigation_plan",
    ):
        assert expected in drivers, f"يجب إدراج المُوجِّه {expected} (لا رقم بلا سبب)"


def test_method_is_model_band_not_conformal():
    # صدق: نطاق نموذجيّ صريح — لا يدّعي المعايرة التجريبيّة (conformal).
    yi = W.simulate(**_RICH)["yield_interval"]
    assert yi["method"] == "deterministic_model_band"
    assert "conformal" in yi["note_ar"]  # يُحيل صراحةً إلى النطاق المُعايَر المنفصل


def test_simulate_is_deterministic():
    a = W.simulate(**_RICH)
    b = W.simulate(**_RICH)
    assert a == b  # لا عشوائيّة — قابل لإعادة الإنتاج في CI


def test_near_crossover_widens_uncertainty():
    # عند تساوي القيد الحراريّ والمائيّ تقريباً ⇒ مُوجِّه قرب العتبة يظهر.
    crop = {"max_yield_kg_ha": 1800.0, "water_use_efficiency": 18.0, "gdd_to_maturity": 1500.0}
    # water_limited = 100*18 = 1800؛ thermal = 1800*(1500/1500)=1800 ⇒ تساوٍ تامّ
    out = W.simulate(crop, {"gdd": 1500.0}, {"available_water_mm": 0.0}, {"irrigation_mm": 100.0})
    assert "near_limiting_factor_crossover" in out["yield_interval"]["drivers"]


# ── تمرير عدم اليقين إلى مُخطِّط الربح ────────────────────────────────────────────
def test_profit_planner_propagates_profit_range():
    sim = W.simulate(**_RICH)
    cand = {
        "name": "wheat",
        "price_per_kg": 2.0,
        "costs": {"seed": 100.0},
        "yield_kg_ha": sim["yield_kg_ha"],
        "yield_interval": sim["yield_interval"],
    }
    ev = P.evaluate_candidate(cand)
    assert ev["expected_profit_low"] <= ev["expected_profit"] <= ev["expected_profit_high"]
    assert ev["yield_confidence"] in {"high", "medium", "low"}


def test_profit_planner_backward_compatible_without_interval():
    # مرشّح قديم بلا yield_interval ⇒ لا مفاتيح مدى (توافق خلفيّ).
    ev = P.evaluate_candidate({"name": "x", "yield_kg_ha": 1000, "price_per_kg": 1.0})
    assert "expected_profit" in ev
    assert "expected_profit_low" not in ev and "expected_profit_high" not in ev
