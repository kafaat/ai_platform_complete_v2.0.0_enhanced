"""اختبارات محرّك اشتقاق Kc (FAO-56 من WOFOST) — نقيّ، حتميّ.

يشمل حُرّاساً صريحة ضدّ أخطاء الشيفرة المرجعيّة (خلط المتغيّرات في تحويل الوحدات).
"""

from __future__ import annotations

import math

import pytest
from core.kc_extraction_engine import (
    DailyFlux,
    derive_daily_kc,
    derive_series,
    fit_fao_stages,
)

pytestmark = pytest.mark.unit


def _flux(tra, evs, tramx, evsmx, et0, dvs=0.0, lai=0.0):
    return DailyFlux(
        tra_cm=tra, evs_cm=evs, tramx_cm=tramx, evsmx_cm=evsmx, et0_mm=et0, dvs=dvs, lai=lai
    )


class TestDailyKc:
    def test_kc_act_uses_tra_plus_evs_in_mm(self):
        # tra=0.3cm, evs=0.1cm ⇒ (3+1)mm / 5mm = 0.8
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.4, 0.2, 5.0))
        assert math.isclose(kc.kc_act, 0.8, rel_tol=1e-9)

    def test_kc_pot_uses_potential_components(self):
        # (tramx+evsmx)=0.6cm ⇒ 6mm/5mm = 1.2
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.4, 0.2, 5.0))
        assert math.isclose(kc.kc_pot, 1.2, rel_tol=1e-9)

    def test_kcb_and_ke_split(self):
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.4, 0.2, 5.0))
        assert math.isclose(kc.kcb_act, 0.6, rel_tol=1e-9)  # 3/5
        assert math.isclose(kc.ke, 0.2, rel_tol=1e-9)  # 1/5
        assert math.isclose(kc.kcb_pot, 0.8, rel_tol=1e-9)  # 4/5

    def test_evs_not_confused_with_tra_regression(self):
        """حارس ضدّ خطأ المرجع (EVS_mm = TR*10): لو خُلِط لتساوت Kcb وKe خطأً.
        هنا tra≠evs فيجب أن تختلف Kcb عن Ke."""
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.4, 0.2, 5.0))
        assert kc.kcb_act != kc.ke  # 0.6 ≠ 0.2 — المتغيّرات صحيحة لكلٍّ

    def test_ks_water_stress_clamped(self):
        # tra<tramx ⇒ إجهاد جزئيّ
        assert math.isclose(derive_daily_kc(_flux(0.15, 0.1, 0.3, 0.2, 5.0)).ks, 0.5, rel_tol=1e-9)
        # tra≥tramx ⇒ يُقَصّ إلى 1.0 (لا إجهاد)
        assert derive_daily_kc(_flux(0.4, 0.1, 0.3, 0.2, 5.0)).ks == 1.0

    def test_zero_et0_yields_none(self):
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.4, 0.2, 0.0))
        assert kc.kc_act is None and kc.kc_pot is None and kc.kcb_act is None and kc.ke is None
        # Ks لا يعتمد على ET0 ⇒ يبقى محسوباً
        assert kc.ks is not None

    def test_cfet_divides_potential_transpiration(self):
        # tramx=0.345cm، cfet=1.15 ⇒ tramx مُصحَّح=0.3cm ⇒ kcb_pot=3/5=0.6
        kc = derive_daily_kc(_flux(0.3, 0.1, 0.345, 0.2, 5.0), cfet=1.15)
        assert math.isclose(kc.kcb_pot, 0.6, rel_tol=1e-9)


class TestFaoStageFit:
    def _season(self):
        # موسم تركيبيّ: DVS يتصاعد 0→2؛ kc_pot ثابت داخل كلّ مرحلة لتسهيل التحقّق.
        fluxes = []
        # ابتدائيّ (DVS<0.2): (tramx+evsmx)=0.3cm ⇒ kc_pot=0.6
        for _ in range(10):
            fluxes.append(_flux(0.1, 0.2, 0.1, 0.2, 5.0, dvs=0.1))
        # منتصف (1.0≤DVS<1.3): (tramx+evsmx)=0.6cm ⇒ kc_pot=1.2
        for _ in range(10):
            fluxes.append(_flux(0.5, 0.1, 0.5, 0.1, 5.0, dvs=1.1))
        # متأخّر (DVS≥1.6): (tramx+evsmx)=0.3cm ⇒ kc_pot=0.6
        for _ in range(15):
            fluxes.append(_flux(0.2, 0.1, 0.2, 0.1, 5.0, dvs=1.7))
        return fluxes

    def test_mid_stage_value(self):
        fluxes = self._season()
        stages = fit_fao_stages(fluxes, derive_series(fluxes))
        assert math.isclose(stages.kc_mid, 1.2, rel_tol=1e-9)

    def test_ini_and_end_values(self):
        fluxes = self._season()
        stages = fit_fao_stages(fluxes, derive_series(fluxes))
        # الابتدائيّ مُنعَّم بمتوسّط متحرّك (يُمزَج قليلاً عند حدّ المرحلة التالية عمداً —
        # سلوك FAO لتنعيم تذبذب التبخّر)، فيقارَب 0.6 لا يساويه بالضبط.
        assert stages.kc_ini == pytest.approx(0.6, abs=0.1)
        # المتأخّر = متوسّط آخر 10 أيّام من النضج (kc_pot الخام، بلا تنعيم) = 0.6 بالضبط.
        assert math.isclose(stages.kc_end, 0.6, rel_tol=1e-9)

    def test_length_mismatch_raises(self):
        fluxes = self._season()
        with pytest.raises(ValueError):
            fit_fao_stages(fluxes, derive_series(fluxes)[:-1])
