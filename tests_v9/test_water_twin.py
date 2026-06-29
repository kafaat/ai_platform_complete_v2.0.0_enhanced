"""اختبار وحدة لمحرّك Water Twin (مسار رطوبة التربة الأماميّ، FAO-56) — نقيّ بلا قاعدة.

يقفل الفيزياء: ميزان نضوب الجذور، Ks تحت الإجهاد (ETa=Ks·ETc)، القصّ [0,TAW]، محوّلات «ماذا لو»
(تأجيل/تحجيم الريّ)، والمقارنة الصادقة (أيّام إجهاد/استهلاك ماء — لا غلّة مُلفّقة).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.water_twin import (  # noqa: E402
    DayPlan,
    compare_scenarios,
    delay_irrigation,
    scale_irrigation,
    simulate_trajectory,
)


def test_depletion_increases_with_etc_no_water():
    """بلا مطر/ريّ، النضوب يزداد بمقدار ETc يوميّاً (طالما لا إجهاد)."""
    days = [DayPlan(etc_mm=5.0) for _ in range(3)]
    traj = simulate_trajectory(0.0, taw_mm=100.0, raw_mm=50.0, days=days)
    # 3 أيّام × 5مم، لا إجهاد (Dr يبقى ≤ RAW=50) ⇒ Ks=1 ⇒ ETa=5 كاملة.
    assert traj.states[0].depletion_mm == pytest.approx(5.0)
    assert traj.states[2].depletion_mm == pytest.approx(15.0)
    assert traj.stress_days == 0
    assert traj.total_eta_mm == pytest.approx(15.0)


def test_irrigation_and_rain_reduce_depletion():
    """المطر والريّ يخفّضان النضوب؛ الفائض لا يجعل النضوب سالباً (قصّ عند 0)."""
    days = [DayPlan(etc_mm=4.0, rain_mm=2.0, irrigation_mm=10.0)]
    traj = simulate_trajectory(5.0, taw_mm=100.0, raw_mm=50.0, days=days)
    # Dr = 5 + 4 - 2 - 10 = -3 ⇒ يُقصّ إلى 0.
    assert traj.states[0].depletion_mm == pytest.approx(0.0)
    assert traj.final_soil_moisture_pct == pytest.approx(100.0)


def test_stress_reduces_eta_via_ks():
    """عند تجاوز RAW: Ks<1 فيُخفَّض ETa، ويُعلَّم اليوم إجهاداً."""
    # نبدأ قرب RAW كي يدخل الإجهاد سريعاً. TAW=100 RAW=40، Dr0=40.
    days = [DayPlan(etc_mm=20.0)]
    traj = simulate_trajectory(40.0, taw_mm=100.0, raw_mm=40.0, days=days)
    s = traj.states[0]
    # بداية اليوم Dr=40=RAW ⇒ Ks=1 ⇒ ETa=20 ⇒ Dr=60 > RAW ⇒ stressed.
    assert s.eta_mm == pytest.approx(20.0)
    assert s.depletion_mm == pytest.approx(60.0)
    assert s.stressed is True
    # اليوم التالي يبدأ Dr=60>RAW ⇒ Ks=(100-60)/(100-40)=0.667 ⇒ ETa مُخفَّض.
    traj2 = simulate_trajectory(60.0, taw_mm=100.0, raw_mm=40.0, days=[DayPlan(etc_mm=20.0)])
    assert traj2.states[0].ks == pytest.approx((100 - 60) / (100 - 40), rel=1e-3)
    assert traj2.states[0].eta_mm < 20.0


def test_depletion_clamped_to_taw():
    """النضوب لا يتجاوز TAW (الذبول التامّ) مهما زاد ETc."""
    traj = simulate_trajectory(90.0, taw_mm=100.0, raw_mm=40.0, days=[DayPlan(etc_mm=50.0)])
    assert traj.states[0].depletion_mm <= 100.0
    assert traj.states[0].soil_moisture_pct >= 0.0


def test_delay_irrigation_shifts_events():
    """تأجيل الريّ ينقل العمق لأيّام لاحقة؛ المنزاح خارج الأفق يُفقَد."""
    days = [DayPlan(etc_mm=5, irrigation_mm=20), DayPlan(etc_mm=5), DayPlan(etc_mm=5)]
    delayed = delay_irrigation(days, 1)
    assert delayed[0].irrigation_mm == 0
    assert delayed[1].irrigation_mm == 20
    # تأجيل يتجاوز الأفق ⇒ يُفقَد الريّ.
    lost = delay_irrigation(days, 5)
    assert sum(d.irrigation_mm for d in lost) == 0


def test_scale_irrigation():
    """تحجيم الريّ يضرب العمق؛ المعامل السالب يرفع خطأ."""
    days = [DayPlan(etc_mm=5, irrigation_mm=20)]
    assert scale_irrigation(days, 0.8)[0].irrigation_mm == pytest.approx(16.0)
    with pytest.raises(ValueError):
        scale_irrigation(days, -0.1)


def test_compare_reports_water_vs_stress_tradeoff():
    """المقارنة تُظهِر مقايضة الماء مقابل الإجهاد دون ادّعاء غلّة."""
    base = [DayPlan(etc_mm=8, irrigation_mm=8) for _ in range(5)]  # ريّ يطابق ETc ⇒ نضوب ثابت
    scen = scale_irrigation(base, 0.5)  # نصف الريّ ⇒ نضوب متزايد ⇒ إجهاد محتمل
    out = compare_scenarios(100.0, 40.0, 10.0, base, scen)
    assert out["scenario_type"] == "water_twin_trajectory"
    metrics = {c["metric_ar"]: c for c in out["comparisons"]}
    # البديل يستهلك ريّاً أقلّ.
    assert metrics["إجماليّ الريّ"]["scenario"] < metrics["إجماليّ الريّ"]["baseline"]
    # البديل لا يقلّ إجهاداً عن الأساس (نصف الريّ).
    assert metrics["أيّام الإجهاد"]["scenario"] >= metrics["أيّام الإجهاد"]["baseline"]
    # صدق: لا مقياس غلّة في المخرَج.
    assert all(
        "غلّة" not in c["metric_ar"] and "إنتاج" not in c["metric_ar"] for c in out["comparisons"]
    )
    assert "الغلّة" in out["summary_ar"]  # يصرّح بعدم نمذجة الغلّة


@pytest.mark.parametrize(
    "taw,raw,init",
    [
        (0.0, 10.0, 0.0),  # TAW غير موجب
        (100.0, 0.0, 0.0),  # RAW غير موجب
        (100.0, 120.0, 0.0),  # RAW > TAW
        (100.0, 40.0, 150.0),  # نضوب ابتدائيّ > TAW
    ],
)
def test_invalid_inputs_raise(taw, raw, init):
    """مدخلات فيزيائيّة غير صالحة ⇒ ValueError (لا حساب مُلفّق)."""
    with pytest.raises(ValueError):
        simulate_trajectory(init, taw_mm=taw, raw_mm=raw, days=[DayPlan(etc_mm=5)])


def test_negative_day_value_raises():
    """قيمة يوميّة سالبة (ETc/مطر/ريّ) ⇒ ValueError."""
    with pytest.raises(ValueError):
        simulate_trajectory(0.0, 100.0, 40.0, days=[DayPlan(etc_mm=-1.0)])
