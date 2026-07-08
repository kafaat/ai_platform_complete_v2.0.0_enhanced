"""حُرّاس تقدير المرحلة بالزمن الحراريّ (GDD) — منطق نقيّ على بطاقات محاصيل حقيقيّة."""

from __future__ import annotations

from core.gdd_phenology import (
    accumulate_gdd,
    daily_gdd,
    gdd_base_c,
    gdd_stage_thresholds,
    phenology_progress,
    stage_from_gdd,
)


class TestDailyGdd:
    def test_basic_mean_minus_base(self):
        assert daily_gdd(10, 20, base_c=0, upper_cap_c=None) == 15.0

    def test_upper_cap_limits_tmax(self):
        # tmax=40 مقصوص إلى 30 ⇒ mean=(30+20)/2=25، −base10 = 15.
        assert daily_gdd(20, 40, base_c=10, upper_cap_c=30) == 15.0

    def test_floored_at_zero_below_base(self):
        assert daily_gdd(0, 5, base_c=10, upper_cap_c=None) == 0.0

    def test_accumulate_sums_series(self):
        total = accumulate_gdd([10, 12], [20, 22], base_c=0, upper_cap_c=None)
        assert total == 15.0 + 17.0


class TestBaseAndThresholds:
    def test_gdd_base_from_card(self):
        assert gdd_base_c("wheat") == 0.0  # قمح C3 بارد
        assert gdd_base_c("maize") == 10.0  # ذرة شاميّة C4
        assert gdd_base_c("nonexistent") is None

    def test_wheat_thresholds_proportional_to_stage_days(self):
        # قمح: gdd_to_maturity=2000، stage_days=[15,25,50,30] (إجمالي 120).
        th = gdd_stage_thresholds("wheat")
        assert [t["stage"] for t in th] == ["initial", "development", "mid", "late"]
        assert th[0]["gdd_start"] == 0.0
        assert th[0]["gdd_end"] == 250.0  # 15/120*2000
        assert th[2]["gdd_start"] == round(40 / 120 * 2000, 1)  # mid يبدأ ~666.7
        assert th[-1]["gdd_end"] == 2000.0  # النضج

    def test_perennial_has_no_gdd_thresholds(self):
        # البُنّ مُعمِّر: gdd_to_maturity=0 ⇒ لا عتبات GDD (صدق: غير منطبق).
        assert gdd_stage_thresholds("coffee") == []


class TestStageFromGdd:
    def test_maps_accumulated_gdd_to_stage(self):
        assert stage_from_gdd("wheat", 100)["stage"] == "initial"
        assert stage_from_gdd("wheat", 800)["stage"] == "mid"
        assert stage_from_gdd("wheat", 1600)["stage"] == "late"

    def test_past_maturity_returns_none(self):
        assert stage_from_gdd("wheat", 2500) is None

    def test_none_gdd_returns_none(self):
        assert stage_from_gdd("wheat", None) is None


class TestPhenologyProgress:
    def test_aligned_days_and_gdd(self):
        # يوم 50 (mid: 40–90) + GDD 800 (mid: 666–1500) ⇒ متوافق.
        p = phenology_progress("wheat", days_since_sowing=50, accumulated_gdd=800)
        assert p["gdd_applicable"] is True
        assert p["days_stage"] == "mid" and p["gdd_stage"] == "mid"
        assert p["divergence"]["direction"] == "aligned"
        assert p["gdd_fraction"] == 0.4  # 800/2000

    def test_thermally_ahead_when_hot(self):
        # يوم 20 (development) لكن GDD 800 (mid) ⇒ الطقس أحرّ ⇒ تقدّم طوريّ.
        p = phenology_progress("wheat", days_since_sowing=20, accumulated_gdd=800)
        assert p["divergence"] == {"diverged": True, "direction": "ahead"}
        assert "أحرّ" in p["note_ar"]

    def test_thermally_behind_when_cold(self):
        # يوم 80 (mid) لكن GDD 300 (development) ⇒ الطقس أبرد ⇒ تأخّر طوريّ.
        p = phenology_progress("wheat", days_since_sowing=80, accumulated_gdd=300)
        assert p["divergence"] == {"diverged": True, "direction": "behind"}
        assert "أبرد" in p["note_ar"]

    def test_maturity_reached_by_gdd(self):
        p = phenology_progress("wheat", days_since_sowing=125, accumulated_gdd=2100)
        assert p["maturity_reached_gdd"] is True

    def test_perennial_gdd_not_applicable_honest(self):
        # البُنّ: GDD غير منطبق ⇒ علَم صريح + ملاحظة، لا رقم مُلفَّق.
        p = phenology_progress("coffee", days_since_sowing=100, accumulated_gdd=900)
        assert p["gdd_applicable"] is False
        assert p["gdd_stage"] is None and p["gdd_to_maturity"] is None
        assert "غير منطبق" in p["note_ar"]

    def test_days_only_when_no_gdd_supplied(self):
        # بلا GDD ممرَّر: يبقى تقدير الأيّام، ولا تباعد.
        p = phenology_progress("wheat", days_since_sowing=50)
        assert p["days_stage"] == "mid"
        assert p["gdd_stage"] is None
        assert p["divergence"]["diverged"] is False
