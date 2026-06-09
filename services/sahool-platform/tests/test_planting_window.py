"""Tests for planting-window engine: finds heat-safe sowing date, mandatory frost trade-off warning,
MEDIUM ceiling (weather forecast not guaranteed), no 'optimal' overclaim (survivorship bias)."""
from core.engines.planting_window import find_planting_window, days_to_accumulate_gdd


class TestGddDays:
    def test_accumulates_to_target(self):
        assert days_to_accumulate_gdd(50, [10]*10) == 5

    def test_none_if_never_reached(self):
        assert days_to_accumulate_gdd(1000, [10]*10) is None


class TestPlantingWindow:
    def _gdd(self):
        return {0: [10]*100, 15: [10]*100}

    def test_finds_safe_window(self):
        tmax = {0: [20]*75 + [28]*25, 15: [20]*75 + [28]*25}
        r = find_planting_window(flowering_gdd=800, daily_gdd_by_sowing=self._gdd(),
            daily_tmax_by_sowing=tmax, heat_threshold_c=31.0)
        assert r.safe_window_found
        assert r.flowering_max_temp_c < 31.0

    def test_no_safe_window_when_all_hot(self):
        tmax = {0: [38]*100, 15: [38]*100}
        r = find_planting_window(flowering_gdd=800, daily_gdd_by_sowing=self._gdd(),
            daily_tmax_by_sowing=tmax, heat_threshold_c=31.0)
        assert not r.safe_window_found
        assert r.confidence == "low"

    def test_ceiling_is_medium_not_high(self):
        # CRITICAL: الطقس متوقّع لا مضمون → السقف MEDIUM لا HIGH
        tmax = {0: [25]*100, 15: [25]*100}
        r = find_planting_window(flowering_gdd=500, daily_gdd_by_sowing=self._gdd(),
            daily_tmax_by_sowing=tmax, heat_threshold_c=31.0)
        assert r.confidence == "medium"

    def test_frost_tradeoff_warning(self):
        # CRITICAL: تقديم قبل آخر صقيع → تحذير المقايضة إلزامي
        tmax = {0: [25]*100}
        r = find_planting_window(flowering_gdd=500, daily_gdd_by_sowing={0: [10]*100},
            daily_tmax_by_sowing=tmax, heat_threshold_c=31.0, frost_risk_offset_days=20)
        assert r.frost_risk
        assert any("صقيع" in w for w in r.warnings_ar)

    def test_never_claims_optimal(self):
        # لا ادّعاء "الأمثل" (تحيّز ناجي) — "خيار مجرّب"
        tmax = {0: [25]*100}
        r = find_planting_window(flowering_gdd=500, daily_gdd_by_sowing={0: [10]*100},
            daily_tmax_by_sowing=tmax, heat_threshold_c=31.0)
        assert any("مجرّب" in w for w in r.warnings_ar)


