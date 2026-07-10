"""حارس ساكن: توصية الريّ تظلّ موصولة باستنزاف منطقة الجذور (WS-D.1).

يمنع انحدار الوصلة: منتِج التوصية يجب أن يقبل مدخلات الاستنزاف (Dr/TAW) وأن يُصدِّر
قرار الإطلاق؛ والراوتر يجب أن يمرّرها. غياب أيّها ⇒ عودة الفجوة (إشارة محسوبة تُهمَل).
"""

import inspect
from pathlib import Path

from api.irrigation_recommendation_policy import recommend_irrigation

_ROUTER = (
    Path(__file__).resolve().parents[1] / "api" / "routers" / "irrigation_recommendation.py"
).read_text(encoding="utf-8")


def test_recommend_irrigation_accepts_depletion_inputs():
    params = inspect.signature(recommend_irrigation).parameters
    for name in ("depletion_mm", "taw_mm", "raw_fraction", "water_stress_class", "policy"):
        assert name in params, f"recommend_irrigation فقد مدخل الاستنزاف {name!r}"


def test_recommend_irrigation_emits_trigger_decision():
    out = recommend_irrigation(
        et0_mm=5.0, crop="wheat", depletion_mm=60.0, taw_mm=100.0, policy="water_saving"
    )
    for key in ("should_irrigate", "trigger_reason", "target_refill_mm", "raw_mm", "policy_knobs"):
        assert key in out, f"مخرَج التوصية فقد مفتاح قرار الإطلاق {key!r}"
    assert out["calibrated"] is False  # صدق: غير معايَر يمنيّاً


def test_router_passes_depletion_inputs_through():
    # المدخلات مُعلَنة في نموذج الطلب وتُمرَّر إلى المنتِج (لا تُبتَر عند الحدّ).
    for token in ("depletion_mm", "taw_mm", "water_stress_class", "policy"):
        assert f"{token}=req.{token}" in _ROUTER, f"الراوتر لا يمرّر {token!r} للمنتِج"
