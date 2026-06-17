"""اختبارات قائمة على الخصائص (Property-Based) لثوابت الأعمال الزراعيّة — Hypothesis.

النوع 3+5 من هرم التحقّق: بدل أمثلة يدويّة، تُولِّد Hypothesis آلاف المدخلات العشوائيّة
وتبحث عن حالات حدّيّة تكسر **ثابتاً تجاريّاً** (لا تنفي وجود اختبار، بل تُثبت خاصّيّة):

  • أمثَلة الريّ: الكمّيّة ∈ [0, min(مطلوب,ميزانيّة)]، الموفَّر ≥ 0، الدرجة ∈ [0,1]، منتهية.
  • قياس الأثر: نسبة النجاح ∈ [0,1]، الموفَّر ≥ 0، نُفِّذ+فشل ≤ الإجماليّ، records ≤ نُفِّذ.
  • مؤشّرات الغطاء: NDVI/NDRE/NDMI ∈ [-1,1] لمدخلات انعكاس [0,1]، منتهية (حارس القسمة).
  • الذكاء الاقتصاديّ: القيمة المُتجنَّبة ≥ 0 لمدخلات صالحة.
  • القرار الموحّد: الثقة ∈ [0,1]؛ محجوب ⇒ خطّة فارغة.

تُحمَّل band_math بالمسار (numpy فقط). تتطلّب hypothesis (في requirements-test).
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys

import pytest

pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.agronomic_decision import DomainSignal, Urgency, reconcile_decision  # noqa: E402
from core.cross_domain_optimization import optimize_irrigation  # noqa: E402
from core.economic_intelligence import summarize_economics  # noqa: E402
from core.impact_measurement import ImpactRecord, measure_impact  # noqa: E402

_finite = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)


# ── أمثَلة الريّ ──
@settings(max_examples=400)
@given(
    requested=_finite,
    min_yield=_finite,
    budget=st.one_of(st.none(), _finite),
    we=st.floats(0, 1, allow_nan=False),
    steps=st.integers(1, 40),
)
def test_optimize_irrigation_invariants(requested, min_yield, budget, we, steps):
    r = optimize_irrigation(
        requested,
        min_mm_for_yield=min_yield,
        budget_mm=budget,
        weights={"water_efficiency": we, "yield_security": 1 - we},
        steps=steps,
    )
    # الثابت على القيم المُبلَّغة (كلاهما مُقرَّب 2 خانة، التقريب رتيب ⇒ applied ≤ requested):
    assert r.applied_water_mm >= 0.0, "كمّيّة سالبة"
    assert r.applied_water_mm <= r.requested_water_mm + 1e-9, "applied يتجاوز requested المُبلَّغ"
    if budget is not None:
        assert r.applied_water_mm <= round(budget, 2) + 1e-9, "applied يتجاوز الميزانيّة"
    assert r.water_saved_mm >= -1e-6, "ماء موفَّر سالب"
    assert -1e-9 <= r.score <= 1.0 + 1e-9, "درجة خارج [0,1]"
    assert math.isfinite(r.applied_water_mm) and math.isfinite(r.score), "قيمة غير منتهية"
    for v in r.objective_scores.values():
        assert -1e-9 <= v <= 1.0 + 1e-9


# ── قياس الأثر ──
_outcome = st.sampled_from(["executed", "failed", "queued", ""])


@settings(max_examples=300)
@given(
    recs=st.lists(
        st.builds(
            ImpactRecord,
            action_type=st.sampled_from(["irrigation", "spray", "fertilize", ""]),
            outcome=_outcome,
            water_requested_mm=st.one_of(st.none(), _finite),
            water_applied_mm=st.one_of(st.none(), _finite),
        ),
        max_size=40,
    )
)
def test_measure_impact_invariants(recs):
    s = measure_impact(recs)
    assert 0.0 <= s.success_rate <= 1.0
    assert s.water_saved_mm >= -1e-6, "ماء موفَّر سالب"
    assert s.executed + s.failed <= s.total_decisions
    assert s.water_records <= s.executed, "سجلّات ماء أكثر من المُنفَّذة"
    assert s.water_applied_mm <= s.water_requested_mm + 1e-6


# ── الذكاء الاقتصاديّ ──
@settings(max_examples=200)
@given(
    saved=_finite,
    executed=st.integers(0, 10000),
    rate=st.floats(0, 1, allow_nan=False),
    area=st.one_of(st.none(), st.floats(0.01, 1e5, allow_nan=False)),
    cost=st.one_of(st.none(), _finite),
)
def test_economics_invariants(saved, executed, rate, area, cost):
    impact = {"water_saved_mm": saved, "executed": executed, "success_rate": rate}
    e = summarize_economics(impact, area_ha=area, water_cost_per_m3=cost)
    if e.water_saved_m3 is not None:
        assert e.water_saved_m3 >= -1e-6
    if e.water_cost_avoided is not None:
        assert e.water_cost_avoided >= -1e-6, "تكلفة متجنَّبة سالبة"
    # القيمة لا تُحسَب إلّا بمدخلات كاملة (صدق)
    if area is None or cost is None:
        assert e.water_cost_avoided is None


# ── القرار الموحّد ──
@settings(max_examples=200)
@given(
    signals=st.lists(
        st.builds(
            DomainSignal,
            domain=st.sampled_from(["weather", "soil", "pest", "economics"]),
            action=st.sampled_from(["irrigate", "spray", "none", "reduce_water"]),
            urgency=st.sampled_from(list(Urgency)),
            halt=st.booleans(),
            confidence=st.floats(0, 1, allow_nan=False),
        ),
        max_size=12,
    )
)
def test_reconcile_decision_invariants(signals):
    d = reconcile_decision("f1", signals)
    assert 0.0 <= d.confidence <= 1.0
    assert d.state in ("ready", "blocked")
    if any(s.halt for s in signals):
        assert d.state == "blocked" and d.action_plan == [], "halt لا يحجب الخطّة"


# ── مؤشّرات الغطاء (band_math) — تُحمَّل بالمسار (numpy فقط) ──
np = pytest.importorskip("numpy")
_bm_path = os.path.join(os.path.dirname(__file__), "..", "..", "raster-service", "band_math.py")
_bm_spec = importlib.util.spec_from_file_location("band_math_prop", _bm_path)
_BM = importlib.util.module_from_spec(_bm_spec)
_bm_spec.loader.exec_module(_BM)

_refl = st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)


def _scalar(fn, *vals):
    out = fn(*[np.array([v]) for v in vals], np)
    return float(out[0])


@settings(max_examples=400)
@given(red=_refl, nir=_refl)
def test_ndvi_bounded(red, nir):
    out = _scalar(_BM.ndvi, red, nir)
    assert math.isfinite(out), "NDVI غير منتهٍ (حارس القسمة فشل)"
    assert -1.0 - 1e-9 <= out <= 1.0 + 1e-9, "NDVI خارج [-1,1]"


@settings(max_examples=400)
@given(nir=_refl, rededge=_refl)
def test_ndre_bounded(nir, rededge):
    out = _scalar(_BM.ndre, nir, rededge)
    assert math.isfinite(out) and -1.0 - 1e-9 <= out <= 1.0 + 1e-9, "NDRE خارج [-1,1]"


@settings(max_examples=400)
@given(nir=_refl, swir1=_refl)
def test_moisture_bounded(nir, swir1):
    out = _scalar(_BM.moisture, nir, swir1)
    assert math.isfinite(out) and -1.0 - 1e-9 <= out <= 1.0 + 1e-9, "NDMI خارج [-1,1]"


@settings(max_examples=400)
@given(red=_refl, nir=_refl)
def test_msavi_finite(red, nir):
    out = _scalar(_BM.msavi, red, nir)
    assert math.isfinite(out), "MSAVI غير منتهٍ (قصّ الجذر السالب فشل)"
