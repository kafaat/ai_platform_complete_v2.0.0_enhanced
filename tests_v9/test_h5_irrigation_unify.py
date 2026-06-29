"""H5 — توحيد الملوحة في compute_irrigation: مفتاح اختياريّ مُطفأ افتراضيّاً.

قرار المستخدم: «بلا ملوحة افتراضيّاً، قابلة للإدخال في أيّ مرحلة». هذا الملفّ نواة نقيّة
(fao56 فقط، بلا api) فلا يحتاج تخطّياً في بيئة «Unit Tests» الأدنى.

يقفل التوحيد:
  - off (افتراضيّ): حقل مالح (soil_ece>العتبة) ⇒ Ks=1.0، LR=0.0، الصافي = ETc−مطر
    (لا خفض ملوحة ولا غسيل). salinity_applied=False (شفافيّة: مُطفأة لا محذوفة).
  - on: نفس المدخلات ⇒ Ks<1.0 وLR>0.0، يطابقان مصدر الحقيقة الوحيد مباشرةً
    (salinity_stress_ks / leaching_requirement — Eq.81 / Eq.82). الصيغ لم تتغيّر.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines.fao56 import (  # noqa: E402
    CropKcProfile,
    SoilZone,
    WeatherDay,
    compute_irrigation,
    leaching_requirement,
    salinity_stress_ks,
)


def _weather() -> WeatherDay:
    return WeatherDay(42, 22, 25, 3.5, 27, 16.15, 1100, 200)


def _crop() -> CropKcProfile:
    # عتبة الملوحة 6.8 dS/m، الميل 16% لكلّ dS/m فوق العتبة
    return CropKcProfile("sorghum", 0.30, 1.05, 0.55, [20, 35, 40, 30], 6.8, 16.0)


def _zone() -> SoilZone:
    return SoilZone("s", "sandy", 80, 0.5, 1.15, "fast", 60)


# مدخلات مالحة صريحة: تربة 8.8 > عتبة 6.8، وماء ريّ 2.0 dS/m
_SOIL_ECE = 8.8
_WATER_EC = 2.0
_RAIN = 3.0


def test_default_off_salty_field_no_reduction_no_leaching():
    """الافتراضيّ off: حقل مالح ⇒ Ks=1.0، LR=0.0، الصافي = ETc(مضبوط بالتربة) − مطر."""
    r = compute_irrigation(
        _weather(),
        _crop(),
        _zone(),
        days_after_planting=50,
        soil_ece=_SOIL_ECE,
        water_ec=_WATER_EC,
        effective_rainfall_mm=_RAIN,
    )
    assert r.ks_salinity == 1.0
    assert r.leaching_fraction == 0.0
    assert r.salinity_applied is False
    # لا خفض ملوحة ⇒ etc_adjusted == etc_zone (etc * ke_factor)؛ الصافي = ذاك − المطر
    expected_net = max(0.0, r.etc_adjusted_mm - _RAIN)
    assert abs(r.net_irrigation_mm - round(expected_net, 2)) < 0.01


def test_opt_in_matches_truth_source_directly():
    """on: نفس المدخلات ⇒ Ks<1.0 وLR>0.0، يطابقان الدالّتين المرجعيّتين مباشرةً."""
    crop = _crop()
    r = compute_irrigation(
        _weather(),
        crop,
        _zone(),
        days_after_planting=50,
        soil_ece=_SOIL_ECE,
        water_ec=_WATER_EC,
        effective_rainfall_mm=_RAIN,
        apply_salinity=True,
    )
    ks_ref = salinity_stress_ks(crop, _SOIL_ECE)
    lr_ref = leaching_requirement(_WATER_EC, crop.salt_tolerance_ece)
    assert ks_ref < 1.0
    assert lr_ref > 0.0
    assert r.ks_salinity == round(ks_ref, 3)
    assert r.leaching_fraction == round(lr_ref, 3)
    assert r.salinity_applied is True


def test_off_vs_on_diverge_on_salty_inputs():
    """on يخفض الملوحة ويضيف غسيلاً ⇒ etc_adjusted أقلّ وLR أعلى من off."""
    common = dict(
        weather=_weather(),
        crop=_crop(),
        zone=_zone(),
        days_after_planting=50,
        soil_ece=_SOIL_ECE,
        water_ec=_WATER_EC,
        effective_rainfall_mm=_RAIN,
    )
    r_off = compute_irrigation(**common)
    r_on = compute_irrigation(**common, apply_salinity=True)
    # off لا يخفض ⇒ etc_adjusted أكبر؛ on يضيف غسيلاً ⇒ LR أكبر
    assert r_on.etc_adjusted_mm < r_off.etc_adjusted_mm
    assert r_on.leaching_fraction > r_off.leaching_fraction
