"""اختبار وحدة لعمق الجذور الديناميكيّ Zr وTAW منه (FAO-56 §8) — نقيّ بلا قاعدة.

يقفل: النموّ الخطّيّ لـ``root_depth_m`` (DAP=0 ⇒ Zr_min؛ ≥days_to_max ⇒ Zr_max؛ الوسط
خطّيّ)، القصّ على ``[zr_min, zr_max]``، اشتقاق ``days_to_max`` من ``stage_days`` في
``root_depth_for_crop``، أنّ ``taw_from_root_depth`` يزيد مع Zr (FAO-56 Eq. 82)، وأنّ
المدخلات غير الصالحة تُعطي سلوكاً معرَّفاً. **إضافيّ فقط** — لا يمسّ المسار المفرد/المزدوج.
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
    root_depth_for_crop,
    root_depth_m,
    taw_from_root_depth,
    theta_fc_wp_for_texture,
)


def _crop() -> CropKcProfile:
    # (crop_id, kc_initial, kc_mid, kc_end, stage_days[ini,dev,mid,late], salt_ece, salt_slope)
    return CropKcProfile("sorghum", 0.30, 1.05, 0.55, [20, 35, 40, 30], 6.8, 16.0)


# ── النموّ الخطّيّ لـZr ────────────────────────────────────────────────
class TestRootDepthLinear:
    def test_dap_zero_returns_zr_min(self):
        # DAP=0 ⇒ لم تنمُ الجذور بعد ⇒ Zr = zr_min
        assert root_depth_m(0, zr_min=0.30, zr_max=1.20, days_to_max=55) == pytest.approx(0.30)

    def test_dap_negative_returns_zr_min(self):
        # قبل الزراعة (DAP<0) ⇒ سلوك معرَّف = zr_min
        assert root_depth_m(-5, zr_min=0.30, zr_max=1.20, days_to_max=55) == pytest.approx(0.30)

    def test_at_days_to_max_returns_zr_max(self):
        assert root_depth_m(55, zr_min=0.30, zr_max=1.20, days_to_max=55) == pytest.approx(1.20)

    def test_beyond_days_to_max_clamped_to_zr_max(self):
        # ≥ days_to_max ⇒ مقصوص عند zr_max (لا يتجاوزه)
        assert root_depth_m(200, zr_min=0.30, zr_max=1.20, days_to_max=55) == pytest.approx(1.20)

    def test_midpoint_is_linear(self):
        # عند نصف المدّة ⇒ منتصف النطاق بالضبط (نموّ خطّيّ)
        zr = root_depth_m(27.5, zr_min=0.30, zr_max=1.20, days_to_max=55)
        assert zr == pytest.approx(0.30 + 0.5 * (1.20 - 0.30))

    def test_monotonic_increasing(self):
        a = root_depth_m(10, 0.30, 1.20, 55)
        b = root_depth_m(20, 0.30, 1.20, 55)
        c = root_depth_m(40, 0.30, 1.20, 55)
        assert 0.30 <= a < b < c <= 1.20


# ── القصّ والمدخلات غير الصالحة ───────────────────────────────────────
class TestRootDepthEdgeCases:
    def test_result_clamped_within_range(self):
        # كلّ القيم الوسطيّة داخل [zr_min, zr_max]
        for dap in (0, 1, 13, 27, 54, 55, 100):
            zr = root_depth_m(dap, 0.30, 1.20, 55)
            assert 0.30 <= zr <= 1.20

    def test_days_to_max_zero_defined_behaviour(self):
        # days_to_max غير صالح (0) ⇒ نموّ لحظيّ آمن إلى zr_max (لا قسمة على صفر)
        assert root_depth_m(5, zr_min=0.30, zr_max=1.20, days_to_max=0) == pytest.approx(1.20)

    def test_days_to_max_negative_defined_behaviour(self):
        assert root_depth_m(5, zr_min=0.30, zr_max=1.20, days_to_max=-10) == pytest.approx(1.20)

    def test_inverted_bounds_stay_clamped(self):
        # zr_min > zr_max (مدخل غير منطقيّ) ⇒ النتيجة تبقى داخل المجال المقصوص
        zr = root_depth_m(30, zr_min=1.20, zr_max=0.30, days_to_max=55)
        assert 0.30 <= zr <= 1.20


# ── الغلاف المحصوليّ (اشتقاق days_to_max من stage_days) ─────────────────
class TestRootDepthForCrop:
    def test_derives_days_to_max_from_stage_days(self):
        crop = _crop()  # stage_days = [20, 35, ...] ⇒ days_to_max = 55
        # عند نهاية development (يوم 55) ⇒ Zr = zr_max
        assert root_depth_for_crop(crop, 55, zr_min=0.30, zr_max=1.20) == pytest.approx(1.20)
        # قبلها مباشرةً ⇒ أقلّ من الأقصى
        assert root_depth_for_crop(crop, 30, 0.30, 1.20) < 1.20
        # متطابق مع التمرير الصريح لـdays_to_max
        assert root_depth_for_crop(crop, 30, 0.30, 1.20) == pytest.approx(
            root_depth_m(30, 0.30, 1.20, days_to_max=55)
        )

    def test_dap_zero_returns_zr_min(self):
        assert root_depth_for_crop(_crop(), 0, 0.30, 1.20) == pytest.approx(0.30)


# ── TAW من عمق الجذور (FAO-56 Eq. 82) ─────────────────────────────────
class TestTawFromRootDepth:
    def test_taw_formula_explicit_theta(self):
        # TAW = 1000·(θFC − θWP)·Zr ؛ (0.25−0.10)·1.0·1000 = 150 mm
        taw = taw_from_root_depth(1.0, theta_fc=0.25, theta_wp=0.10)
        assert taw == pytest.approx(150.0)

    def test_taw_increases_with_root_depth(self):
        shallow = taw_from_root_depth(0.30, texture="loam")
        deep = taw_from_root_depth(1.20, texture="loam")
        assert 0.0 < shallow < deep
        # خطّيّ في Zr ⇒ TAW(1.20)/TAW(0.30) = 4
        assert deep == pytest.approx(shallow * 4.0)

    def test_taw_uses_texture_table_when_theta_absent(self):
        fc, wp = theta_fc_wp_for_texture("loam")
        assert taw_from_root_depth(1.0, texture="loam") == pytest.approx(1000.0 * (fc - wp))

    def test_unknown_texture_falls_back_to_loam(self):
        assert theta_fc_wp_for_texture("unknown_xyz") == theta_fc_wp_for_texture("loam")

    def test_clay_holds_more_available_water_than_sand(self):
        # الطين يحتفظ بماء متاح أكثر من الرمل (وسطيّات FAO-56 Table 19)
        taw_clay = taw_from_root_depth(1.0, texture="clay")
        taw_sand = taw_from_root_depth(1.0, texture="sand")
        assert taw_clay > taw_sand > 0.0

    def test_taw_non_negative_for_zero_or_negative_zr(self):
        assert taw_from_root_depth(0.0, texture="loam") == 0.0
        assert taw_from_root_depth(-1.0, texture="loam") == 0.0
