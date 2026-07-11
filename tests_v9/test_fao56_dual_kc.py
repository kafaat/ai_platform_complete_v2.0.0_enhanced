"""اختبارات المعامل المزدوج FAO-56 (Kcb + Ke + Ks) — نواة نقيّة بلا خدمات.

يثبت السلوك الإضافيّ لـ`compute_etc_dual` (FAO-56 Ch.7, Eq. 71/72/74/75/80):
  - Ke يرفع ETc على التربة العارية/المرحلة المبكّرة (سطح مبلّل حديثاً).
  - Ks يُخفّض المسار المزدوج تحت الإجهاد الملحيّ.
  - المسار المزدوج ≈ المفرد حين Ke→0 (Kr=0 بجفاف السطح) وKs=1.
  - دوالّ FAO-56 الفرعيّة (Kr, few, Kc_max, Kcb) سليمة حدوديّاً.
  - المسار المفرد القائم (compute_irrigation) لم يتغيّر (حارس إضافيّة).
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
    WeatherDay,
    compute_etc_dual,
    evaporation_reduction_kr,
    few_exposed_wetted,
    kc_for_age,
    kc_max,
    kcb_for_age,
    salinity_stress_ks,
    tew_rew_for_texture,
)


def _weather() -> WeatherDay:
    # يوم صيفيّ جافّ حارّ (مرتفعات اليمن) — مطابق لاختبارات المحرّك القائمة.
    return WeatherDay(42, 22, 25, 3.5, 27, 16.15, 1100, 200)


def _crop() -> CropKcProfile:
    return CropKcProfile("sorghum", 0.30, 1.05, 0.55, [20, 35, 40, 30], 6.8, 16.0)


# ── دوالّ FAO-56 الفرعيّة ─────────────────────────────────────────────
class TestDualSubFunctions:
    def test_kr_stage1_full_evaporation(self):
        # De ≤ REW ⇒ Kr=1 (المرحلة الأولى، طاقة-محدودة)
        assert evaporation_reduction_kr(de_mm=2.0, tew_mm=16.0, rew_mm=8.0) == 1.0

    def test_kr_stage2_declines(self):
        # De > REW ⇒ Kr ينخفض خطّيّاً
        kr = evaporation_reduction_kr(de_mm=12.0, tew_mm=16.0, rew_mm=8.0)
        # (16-12)/(16-8) = 0.5
        assert abs(kr - 0.5) < 1e-9

    def test_kr_zero_when_fully_dry(self):
        assert evaporation_reduction_kr(de_mm=16.0, tew_mm=16.0, rew_mm=8.0) == 0.0

    def test_few_limited_by_canopy_and_wetting(self):
        # few = min(1-fc, fw)
        assert abs(few_exposed_wetted(fc=0.3, fw=1.0) - 0.7) < 1e-9
        assert abs(few_exposed_wetted(fc=0.3, fw=0.4) - 0.4) < 1e-9

    def test_kc_max_floor_above_kcb(self):
        # Kc_max لا ينزل دون Kcb+0.05
        km = kc_max(kcb=1.2, wind_speed_m_s=2.0, rh_min_pct=45.0, crop_height_m=0.5)
        assert km >= 1.2 + 0.05

    def test_kcb_below_single_kc(self):
        crop = _crop()
        kc_mid, _ = kc_for_age(crop, 70)
        kcb_mid, _ = kcb_for_age(crop, 70)
        assert kcb_mid < kc_mid
        assert kcb_mid >= 0.15

    def test_tew_rew_table_defaults(self):
        tew_sand, rew_sand = tew_rew_for_texture("sand")
        tew_loam, rew_loam = tew_rew_for_texture("loam")
        # الرمل يحتفظ بماء أقلّ ⇒ TEW أصغر من الطميّ
        assert tew_sand < tew_loam
        # القوام المجهول يقع على "loam"
        assert tew_rew_for_texture("unknown_texture") == tew_rew_for_texture("loam")


# ── السلوك المزدوج ────────────────────────────────────────────────────
class TestDualKc:
    def test_ke_raises_etc_on_bare_wet_soil(self):
        """تربة عارية مبكّرة + سطح مبلّل حديثاً ⇒ Ke>0 يرفع ETc المزدوج فوق
        ما يعطيه Kcb وحده."""
        w, crop = _weather(), _crop()
        # مرحلة أوليّة (يوم 5)، De=0 (سطح مبلّل)، fw=1 (رّيّ سطحيّ)
        r = compute_etc_dual(w, crop, days_after_planting=5, de_mm=0.0, fw=1.0, et0_override=6.0)
        assert r.ke > 0.0
        # ETc المزدوج أكبر من مساهمة الأساس وحدها (Kcb·Ks·ET0)
        basal_only = r.kcb * r.ks * r.et0_mm
        assert r.etc_dual_mm > basal_only

    def test_dry_surface_collapses_ke(self):
        """سطح جافّ تماماً (De≥TEW) ⇒ Kr=0 ⇒ Ke=0 ⇒ المزدوج يقترب من المفرد
        المبنيّ على Kcb (لا Kc المدمج)."""
        w, crop = _weather(), _crop()
        tew, _ = tew_rew_for_texture("loam")
        r = compute_etc_dual(w, crop, days_after_planting=70, de_mm=tew + 5.0, et0_override=6.0)
        assert r.ke == 0.0
        # مع Ke=0 وKs=1: kc_dual = Kcb فقط
        assert abs(r.kc_dual - r.kcb) < 1e-9

    def test_dual_approx_single_when_ke_zero_and_ks_one(self):
        """حين Ke→0 وKs=1 وإزاحة Kcb=0 ⇒ المزدوج ≈ المفرد (Kc·ET0)."""
        w, crop = _weather(), _crop()
        tew, _ = tew_rew_for_texture("loam")
        # kcb_offset=0 ⇒ Kcb=Kc؛ De كبير ⇒ Ke=0؛ soil_ece=0 ⇒ Ks=1
        r = compute_etc_dual(
            w,
            crop,
            days_after_planting=70,
            de_mm=tew + 10.0,
            kcb_offset=0.0,
            soil_ece=0.0,
            et0_override=6.0,
        )
        assert r.ks == 1.0
        assert r.ke == 0.0
        assert abs(r.etc_dual_mm - r.etc_single_mm) < 0.02

    def test_ks_reduces_dual_under_salinity(self):
        """الإجهاد الملحيّ يُخفّض الأساس في المسار المزدوج (Ke لا يتأثّر)."""
        w, crop = _weather(), _crop()
        # سطح جافّ لعزل أثر Ks على الأساس (Ke=0)
        tew, _ = tew_rew_for_texture("loam")
        r_no_stress = compute_etc_dual(
            w, crop, days_after_planting=70, de_mm=tew + 5.0, soil_ece=5.0, et0_override=6.0
        )
        r_stress = compute_etc_dual(
            w, crop, days_after_planting=70, de_mm=tew + 5.0, soil_ece=10.0, et0_override=6.0
        )
        assert r_no_stress.ks == 1.0  # تحت العتبة 6.8
        assert r_stress.ks < 1.0
        assert r_stress.etc_dual_mm < r_no_stress.etc_dual_mm

    def test_drip_reduces_ke_vs_flood(self):
        """رّيّ بالتنقيط (fw صغير) يبلّل سطحاً أقلّ ⇒ Ke أصغر من الرّيّ السطحيّ."""
        w, crop = _weather(), _crop()
        r_flood = compute_etc_dual(
            w, crop, days_after_planting=5, de_mm=0.0, fw=1.0, et0_override=6.0
        )
        r_drip = compute_etc_dual(
            w, crop, days_after_planting=5, de_mm=0.0, fw=0.3, et0_override=6.0
        )
        assert r_drip.ke < r_flood.ke

    def test_sandy_soil_dries_faster(self):
        """الرمل (TEW أصغر) يصل للمرحلة الثانية أسرع ⇒ Kr أقلّ عند نفس De."""
        w, crop = _weather(), _crop()
        # De بين REW الرملي (3) وREW الطميّ (8) ⇒ الرمل في المرحلة 2، الطميّ في 1
        r_sand = compute_etc_dual(
            w, crop, days_after_planting=5, de_mm=6.0, texture="sand", et0_override=6.0
        )
        r_loam = compute_etc_dual(
            w, crop, days_after_planting=5, de_mm=6.0, texture="loam", et0_override=6.0
        )
        assert r_sand.kr < r_loam.kr

    def test_assumptions_documented(self):
        """الافتراضات تُصرَّح (صدق منهجيّ) حين تغيب المُدخلات."""
        w, crop = _weather(), _crop()
        r = compute_etc_dual(w, crop, days_after_planting=30, et0_override=6.0)
        # على الأقلّ: Kcb مُشتقّ + TEW/REW جدوليّة + RHmin مُقدَّر + fc مُقدَّر
        joined = " ".join(r.assumptions)
        assert "Kcb" in joined
        assert "TEW/REW" in joined

    def test_worked_fao56_example_ke_order_of_magnitude(self):
        """مثال FAO-56 الفصل 7 (Ex.30/31): Ke النموذجيّ بعد رّيّ كامل بين ~0.2
        و~1.2 حسب المرحلة. نتحقّق أنّ المسار يقع في هذا النطاق الفيزيائيّ."""
        w, crop = _weather(), _crop()
        r = compute_etc_dual(
            w,
            crop,
            days_after_planting=8,
            de_mm=0.0,
            fw=1.0,
            texture="sandy loam",
            et0_override=6.0,
        )
        assert 0.15 <= r.ke <= 1.3
        # المعامل المركّب لا يتجاوز Kc_max الفيزيائيّ
        assert r.kc_dual <= r.kc_max + 1e-9


# ── حارس الإضافيّة: المسار المفرد لم يتغيّر ────────────────────────────
class TestSinglePathUnchanged:
    def test_single_kc_curve_unchanged(self):
        crop = _crop()
        kc, _ = kc_for_age(crop, 70)
        assert kc == 1.05  # قيمة البطاقة، لم تتغيّر
        # salinity_ks القائم لم يتغيّر
        assert salinity_stress_ks(crop, 5.0) == 1.0


# ── ETc-dual canonical: et0_override + soil_ece=None (إغلاق SSOT/H5) ──
class TestEtcDualCanonicalParams:
    def test_et0_override_replaces_internal_et0(self):
        """et0_override ⇒ ETc تُحسب بـET0 المُمرَّر لا penman الداخليّ (SSOT موحّد)."""
        w, crop = _weather(), _crop()
        forced = 3.0  # ≠ penman الداخليّ (≈9-10 لهذا الطقس)
        r = compute_etc_dual(w, crop, days_after_planting=40, et0_override=forced)
        assert r.et0_mm == forced
        # ETc = kc_dual · ET0_override (بدقّة التقريب)
        assert abs(r.etc_dual_mm - round(r.kc_dual * forced, 2)) < 0.02
        assert any("et0_override" in a.lower() or "الكنسيّ" in a for a in r.assumptions)

    def test_missing_override_raises(self):
        """بلا et0_override ⇒ خطأ صريح (fail-closed): ET0 يُنفَّذ في محرّك الطقس لا محلّيّاً."""
        w, crop = _weather(), _crop()
        with pytest.raises(ValueError):
            compute_etc_dual(w, crop, days_after_planting=40)

    def test_soil_ece_none_disables_salinity(self):
        """soil_ece=None ⇒ Ks=1 (الملوحة غير مطبّقة) + assumption — لا تُدخَل ضمنيّاً."""
        w, crop = _weather(), _crop()
        r = compute_etc_dual(w, crop, days_after_planting=40, soil_ece=None, et0_override=6.0)
        assert r.ks == 1.0
        assert any("الملوحة غير مطبّقة" in a for a in r.assumptions)

    def test_soil_ece_value_still_applies_ks(self):
        """soil_ece=رقم فوق العتبة ⇒ Ks<1 (السلوك القائم محفوظ)."""
        w = _weather()
        # محصول حسّاس: عتبة 2.0، ميل 10%/dS·m⁻¹ ⇒ EC=7 ⇒ خسارة كبيرة
        crop = CropKcProfile("sensitive", 0.30, 1.05, 0.55, [20, 35, 40, 30], 2.0, 10.0)
        r = compute_etc_dual(w, crop, days_after_planting=40, soil_ece=7.0, et0_override=6.0)
        assert r.ks < 1.0
