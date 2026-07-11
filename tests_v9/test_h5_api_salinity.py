"""اختبار وحدة لفجوة H5 (طبقة الـAPI): اتّساق الملوحة مع المحرّك + إزالة تكرار الغسيل.

يقفل الصدق على ثلاثة محاور:
  • ``water_balance`` بـ ``apply_salinity=False`` (الافتراضيّ) ⇒ السلوك القائم تماماً
    (نفس net/etc القديم — لا انحدار، ``salinity_applied=False``).
  • ``apply_salinity=True`` مع ECe فوق العتبة ⇒ Ks مُطبَّق على ETc (يخفض الاحتياج)،
    و ``salinity_applied=True`` — بنفس صيغة المحرّك (Eq.81).
  • ``salinity_management.leaching_requirement`` يفوّض إلى ``fao56.leaching_requirement``
    (نفس الكسر لنفس المدخلات — مصدر صيغة واحد، لا تكرار).

الملوحة opt-in بقرار المستخدم: مُطفأة افتراضيّاً (بلا Ks، بلا غسيل).

نمط التخطّي كـ tests_v9/test_etc_dual_weather.py: استيراد api.* يتطلّب تبعيّات المنصّة؛
في وظيفة CI «Unit Tests» الأدنى (بلا api/requirements) نتخطّى الوحدة كاملةً بصدق.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api import salinity_management as sal  # noqa: E402
    from api.water_balance import WeatherInput, water_balance  # noqa: E402
    from core.engines.fao56 import (  # noqa: E402
        leaching_requirement as fao56_leaching_requirement,
    )
    from core.engines.fao56 import (  # noqa: E402
        salinity_stress_ks as fao56_salinity_stress_ks,
    )
    from core.season_phenology import crop_kc_profile, resolve_crop_id  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable (minimal Unit Tests env)", allow_module_level=True)


def _weather() -> WeatherInput:
    # طقس ثابت بلا إشعاع/رطوبة/رياح ⇒ Hargreaves حتميّ (لا شبكة).
    return WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)


# ─── المحور 1: off = السلوك القائم تماماً (لا انحدار) ───────────────────────


def test_salinity_off_is_default_and_unchanged():
    """الافتراضيّ off ⇒ نفس net/etc القديم + salinity_applied=False."""
    w = _weather()
    base = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=6.0)
    # تمرير ECe/ECw مع البقاء off ⇒ يُتجاهلان تماماً (لا أثر).
    off = water_balance(w, "wheat", "mid", rain_mm=0, soil_ece=10.0, water_ec=3.0, et0_mm=6.0)

    assert base.salinity_applied is False
    assert off.salinity_applied is False
    assert math.isclose(off.etc_mm, base.etc_mm, rel_tol=1e-12)
    assert math.isclose(off.net_irrigation_mm, base.net_irrigation_mm, rel_tol=1e-12)
    # net القائم = ETc − مطر فعّال (هنا المطر صفر) — الصيغة القديمة محفوظة.
    assert math.isclose(off.net_irrigation_mm, off.etc_mm, rel_tol=1e-12)
    # شكل القاموس القائم محفوظ تماماً off: الحقل لا يظهر إلّا عند تطبيق الملوحة.
    assert "salinity_applied" not in off.to_dict()
    assert set(off.to_dict()) == {
        "et0_mm",
        "method",
        "kc",
        "kc_source_ar",
        "etc_mm",
        "effective_rain_mm",
        "net_irrigation_mm",
        "advice_ar",
    }


# ─── المحور 2: on = Ks مُطبَّق بصيغة المحرّك ─────────────────────────────────


def test_salinity_on_applies_engine_ks_to_etc():
    """on مع ECe فوق العتبة ⇒ ETc يُضرب في Ks (نفس قيمة المحرّك) + الاحتياج ينخفض."""
    w = _weather()
    off = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=6.0)
    on = water_balance(w, "wheat", "mid", rain_mm=0, soil_ece=10.0, apply_salinity=True, et0_mm=6.0)

    profile = crop_kc_profile(resolve_crop_id("wheat"))
    assert profile is not None
    ks = fao56_salinity_stress_ks(profile, 10.0)
    assert ks < 1.0  # ECe=10 > عتبة القمح 6 ⇒ إجهاد فعليّ

    assert on.salinity_applied is True
    assert on.to_dict().get("salinity_applied") is True
    # ETc المُجهَد = ETc الأساس × Ks (نفس صيغة fao56، لا تكرار).
    assert math.isclose(on.etc_mm, off.etc_mm * ks, rel_tol=1e-9)
    # الاحتياج المُجهَد < الاحتياج بلا ملوحة (Ks<1 يخفض ETc ⇒ صافٍ أقلّ).
    assert on.net_irrigation_mm < off.net_irrigation_mm


def test_salinity_on_below_threshold_keeps_ks_one():
    """ECe دون العتبة ⇒ Ks=1 ⇒ ETc بلا تغيير رغم تفعيل الخطّاف (salinity_applied=True)."""
    w = _weather()
    off = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=6.0)
    on = water_balance(w, "wheat", "mid", rain_mm=0, soil_ece=2.0, apply_salinity=True, et0_mm=6.0)
    assert on.salinity_applied is True
    assert math.isclose(on.etc_mm, off.etc_mm, rel_tol=1e-12)


def test_salinity_on_unknown_crop_degrades_to_off_honestly():
    """محصول بلا بطاقة ⇒ تعذّر بناء البروفايل ⇒ off بصدق (لا ملوحة مُلفَّقة)."""
    w = _weather()
    on = water_balance(
        w, "__no_such_crop__", "mid", rain_mm=0, soil_ece=10.0, apply_salinity=True, et0_mm=6.0
    )
    assert on.salinity_applied is False


def test_salinity_on_adds_leaching_above_net():
    """on مع ECw ⇒ يُضاف احتياج الغسيل فوق الصافي (Eq.82) بنفس كسر المحرّك."""
    w = _weather()
    profile = crop_kc_profile(resolve_crop_id("wheat"))
    assert profile is not None
    # بلا ملوحة تربة (ECe دون العتبة) ⇒ Ks=1، فالفرق كلّه من الغسيل.
    no_leach = water_balance(
        w, "wheat", "mid", rain_mm=0, soil_ece=0.0, apply_salinity=True, et0_mm=6.0
    )
    with_leach = water_balance(
        w, "wheat", "mid", rain_mm=0, soil_ece=0.0, water_ec=3.0, apply_salinity=True, et0_mm=6.0
    )
    lr = fao56_leaching_requirement(3.0, profile.salt_tolerance_ece)
    assert lr > 0.0
    assert math.isclose(
        with_leach.net_irrigation_mm, no_leach.net_irrigation_mm * (1.0 + lr), rel_tol=1e-9
    )


# ─── المحور 3: إزالة تكرار الغسيل — التفويض للمحرّك ──────────────────────────


def test_leaching_requirement_delegates_to_fao56():
    """salinity_management.leaching_requirement == fao56.leaching_requirement (الكسر)."""
    cases = [(0.7, 6.0), (1.5, 4.0), (3.0, 8.0), (2.0, 6.0)]
    for ecw, threshold in cases:
        d = sal.leaching_requirement(ecw, threshold)
        engine = fao56_leaching_requirement(ecw, threshold)
        assert d["feasible"] is True
        # الكسر القاموسيّ = كسر المحرّك تماماً (مصدر صيغة واحد).
        assert math.isclose(d["leaching_fraction"], round(engine, 3), rel_tol=0, abs_tol=1e-9)


def test_leaching_requirement_infeasible_when_salinity_too_high():
    """ملوحة الماء تتجاوز قدرة الغسيل (المقام ≤ 0) ⇒ feasible=False (الواجهة محفوظة)."""
    d = sal.leaching_requirement(ecw_dsm=40.0, crop_threshold_ece=4.0)
    assert d["feasible"] is False
