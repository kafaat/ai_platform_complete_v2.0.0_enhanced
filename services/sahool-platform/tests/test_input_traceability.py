"""اختبارات تتبّع مدخلات الإنتاج من البذرة للحصاد (offline).

يتحقّق من: النَسَب المرتّب (بذرة→مدخلات→حصاد)؛ صدق الكلفة الجزئيّة (لا تأليف
للغائب)؛ كلفة/هكتار وكلفة/طنّ بشروطها؛ وحالات الاكتمال/الجزئيّة/الفراغ.
"""

from core.engines.input_traceability import (
    InputApplication,
    TraceabilityState,
    build_input_ledger,
)


def _seed(cost=None):
    return InputApplication(activity_type="planting", product_name="بذور قمح", cost=cost)


def _fert(cost=None):
    return InputApplication(activity_type="fertilization", product_name="NPK", cost=cost)


def _spray(cost=None):
    return InputApplication(activity_type="spraying", product_name="مبيد فطري", cost=cost)


# ─── الفراغ ───────────────────────────────────────────────────────────────


def test_no_inputs_is_empty_state():
    out = build_input_ledger([], field_id="f1")
    assert out["state"] == TraceabilityState.NO_INPUTS.value
    assert out["total_cost"] == 0.0
    assert out["by_input_type"] == {}


# ─── التجميع + ترتيب النَسَب ──────────────────────────────────────────────


def test_groups_by_input_type_in_seed_to_harvest_order():
    out = build_input_ledger([_spray(cost=100), _seed(cost=500), _fert(cost=300)], field_id="f1")
    # الترتيب يبدأ بالبذرة ثمّ السماد ثمّ المبيد (نَسَب منطقي).
    assert list(out["by_input_type"].keys()) == ["seed", "fertilizer", "pesticide"]
    assert out["total_cost"] == 900.0


# ─── صدق الكلفة الجزئيّة (لا تأليف للغائب) ────────────────────────────────


def test_missing_cost_excluded_and_coverage_reported():
    out = build_input_ledger([_seed(cost=500), _fert(cost=None)], field_id="f1")
    # السماد بلا كلفة ⇒ لا يُضاف للإجمالي، والتغطية 50%.
    assert out["total_cost"] == 500.0
    assert out["cost_coverage"] == 0.5
    assert any("تغطية" in g for g in out["gaps_ar"])


# ─── الاقتصاد بشروطه ──────────────────────────────────────────────────────


def test_cost_per_ha_requires_area():
    no_area = build_input_ledger([_seed(cost=600)], field_id="f1")
    assert no_area["cost_per_ha"] is None
    with_area = build_input_ledger([_seed(cost=600)], field_id="f1", area_ha=3.0)
    assert with_area["cost_per_ha"] == 200.0


def test_cost_per_ton_requires_area_and_harvest():
    # كلفة 900، مساحة 3ha ⇒ 300/ha؛ إنتاجيّة 1.5 t/ha ⇒ 200/طنّ.
    out = build_input_ledger(
        [_seed(cost=500), _fert(cost=400)],
        field_id="f1",
        area_ha=3.0,
        harvest_yield_t_ha=1.5,
    )
    assert out["cost_per_ha"] == 300.0
    assert out["cost_per_ton"] == 200.0


def test_no_harvest_means_no_cost_per_ton():
    out = build_input_ledger([_seed(cost=600)], field_id="f1", area_ha=3.0)
    assert out["cost_per_ton"] is None
    assert any("حصاد" in g for g in out["gaps_ar"])


def test_cost_per_ton_uses_raw_values_not_double_rounded():
    # كلفة/طنّ تُحسب من القيم الخام total/(area·yield)، لا من cost_per_ha المقرّب.
    # total=10, area=3, yield=0.6 ⇒ خام 10/1.8=5.556→5.56 (لا 3.33/0.6=5.55).
    out = build_input_ledger([_seed(cost=10)], field_id="f1", area_ha=3.0, harvest_yield_t_ha=0.6)
    assert out["cost_per_ha"] == 3.33
    assert out["cost_per_ton"] == 5.56


# ─── الاكتمال ─────────────────────────────────────────────────────────────


def test_complete_state_needs_seed_harvest_and_full_cost():
    out = build_input_ledger(
        [_seed(cost=500), _fert(cost=400)],
        field_id="f1",
        area_ha=2.0,
        harvest_yield_t_ha=2.0,
    )
    assert out["state"] == TraceabilityState.COMPLETE.value


def test_partial_when_seed_missing():
    out = build_input_ledger([_fert(cost=400)], field_id="f1", area_ha=2.0, harvest_yield_t_ha=2.0)
    assert out["state"] == TraceabilityState.PARTIAL.value
    assert any("بذر" in g for g in out["gaps_ar"])
