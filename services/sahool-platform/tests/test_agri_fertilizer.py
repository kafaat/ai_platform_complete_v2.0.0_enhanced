"""اختبارات وحدة لأداة حاسبة احتياج الأسمدة (fertilizer_requirement)."""

from __future__ import annotations

import pytest
from core.agri_tools.tools.fertilizer import compute

pytestmark = pytest.mark.unit


def test_urea_full_chain():
    # غلّة 6 طن/هكتار × امتصاص 25 كغ/طن = 150 احتياج.
    # إمداد تربة 30 → صافٍ 120. كفاءة 0.75 → 160 للتطبيق.
    # يوريا 46% → 160 / 0.46 ≈ 347.83 كغ/هكتار.
    out = compute(
        {
            "target_yield_t_ha": 6.0,
            "uptake_kg_per_t": 25.0,
            "soil_supply_kg_ha": 30.0,
            "fertilizer_grade_pct": 46.0,
            "use_efficiency": 0.75,
        }
    )
    assert out["crop_demand_kg_ha"] == 150.0
    assert out["net_nutrient_kg_ha"] == 120.0
    assert out["nutrient_to_apply_kg_ha"] == 160.0
    assert out["product_kg_ha"] == pytest.approx(347.83, abs=0.01)


def test_soil_supply_clamps_net_to_zero():
    # إمداد التربة يفوق الاحتياج → الصافي لا يصير سالباً، بل صفر.
    out = compute(
        {
            "target_yield_t_ha": 4.0,
            "uptake_kg_per_t": 20.0,  # احتياج = 80
            "soil_supply_kg_ha": 120.0,  # > الاحتياج
            "fertilizer_grade_pct": 46.0,
            "use_efficiency": 0.7,
        }
    )
    assert out["crop_demand_kg_ha"] == 80.0
    assert out["net_nutrient_kg_ha"] == 0.0
    assert out["nutrient_to_apply_kg_ha"] == 0.0
    assert out["product_kg_ha"] == 0.0


def test_efficiency_default_applied():
    # كفاءة غير ممرَّرة (None) → الافتراضيّ 0.7.
    out = compute(
        {
            "target_yield_t_ha": 5.0,
            "uptake_kg_per_t": 14.0,  # احتياج = 70، صافٍ = 70
            "soil_supply_kg_ha": 0.0,
            "fertilizer_grade_pct": 100.0,
            "use_efficiency": None,
        }
    )
    # 70 / 0.7 = 100 للتطبيق؛ نسبة 100% → 100 منتج.
    assert out["nutrient_to_apply_kg_ha"] == 100.0
    assert out["product_kg_ha"] == 100.0


def test_soil_supply_default_zero():
    # إمداد التربة غير ممرَّر (None) → الافتراضيّ 0 (الصافي = الاحتياج كاملاً).
    out = compute(
        {
            "target_yield_t_ha": 2.0,
            "uptake_kg_per_t": 30.0,  # احتياج = 60
            "soil_supply_kg_ha": None,
            "fertilizer_grade_pct": 50.0,
            "use_efficiency": 1.0,
        }
    )
    assert out["net_nutrient_kg_ha"] == 60.0
    assert out["nutrient_to_apply_kg_ha"] == 60.0
    # نسبة 50% → ضِعف كمّيّة العنصر.
    assert out["product_kg_ha"] == 120.0


def test_grade_percentage_scaling():
    # نسبة العنصر تقسم الكمّيّة: 100 عنصر بنسبة 20% → 500 منتج.
    out = compute(
        {
            "target_yield_t_ha": 10.0,
            "uptake_kg_per_t": 10.0,  # احتياج = 100
            "soil_supply_kg_ha": 0.0,
            "fertilizer_grade_pct": 20.0,
            "use_efficiency": 1.0,
        }
    )
    assert out["nutrient_to_apply_kg_ha"] == 100.0
    assert out["product_kg_ha"] == 500.0
