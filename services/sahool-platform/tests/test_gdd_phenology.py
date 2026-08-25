"""حُرّاس تقدير المرحلة بالزمن الحراريّ (GDD) — منطق نقيّ على بطاقات محاصيل حقيقيّة."""

from __future__ import annotations

import math
from datetime import date, timedelta

from core.gdd_phenology import (
    CRITICAL_STAGE,
    gdd_base_c,
    gdd_stage_thresholds,
    phenology_progress,
    project_next_critical_window,
    stage_from_gdd,
)

# WS-C.1c Zero-Legacy: نواة daily_gdd/accumulate_gdd أُزيلت من core.gdd_phenology (مِلك المحرّك
# الآن — services/weather-service/gdd.py، وتُختبَر هناك). يبقى هنا اختبار سياسة المحصول فقط.


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


class TestProjectNextCriticalWindow:
    """W1 — الإسقاط الأماميّ للنافذة الحرجة (متى يدخل الحقل طورَه الأضعف).

    ذرة شاميّة: mid = 650→1100 GDD — مُشتقّة من البطاقة أدناه لا مُثبَّتة يدويّاً.
    """

    TODAY = date(2026, 8, 1)

    def test_critical_stage_reuses_the_platforms_own_definition(self):
        # لا تعريف ثانٍ للحرج: هو نفسه ما يفحصه is_reproductive_stage.
        from core.season_phenology import _stages, is_reproductive_stage

        assert CRITICAL_STAGE == "mid"
        maize_mid = [s for s in _stages("maize") if s["stage"] == CRITICAL_STAGE]
        assert maize_mid, "بطاقة الذرة يجب أن تحمل المرحلة الحرجة"
        mid_day = (maize_mid[0]["day_start"] + maize_mid[0]["day_end"]) // 2
        assert is_reproductive_stage("maize", mid_day) is True

    def test_upcoming_window_carries_dates_and_lead_time(self):
        bounds = next(t for t in gdd_stage_thresholds("maize") if t["stage"] == CRITICAL_STAGE)
        out = project_next_critical_window(
            "maize", accumulated_gdd=500.0, forecast_daily_gdd=[15.0] * 20, today=self.TODAY
        )
        expected_lead = math.ceil((bounds["gdd_start"] - 500.0) / 15.0)
        assert out["status"] == "upcoming"
        assert out["lead_days"] == expected_lead
        assert out["start_date"] == (self.TODAY + timedelta(days=expected_lead)).isoformat()
        assert out["source"] == "gdd_forecast"
        assert out["confidence"] == "medium"

    def test_a_horizon_shorter_than_the_window_end_is_declared_not_extrapolated(self):
        out = project_next_critical_window(
            "maize", accumulated_gdd=500.0, forecast_daily_gdd=[15.0] * 20, today=self.TODAY
        )
        assert out["end_date"] is None
        assert "forecast_horizon_too_short" in out["evidence_missing"]

    def test_inside_the_window_the_unobserved_start_stays_none(self):
        out = project_next_critical_window(
            "maize", accumulated_gdd=700.0, forecast_daily_gdd=[15.0] * 40, today=self.TODAY
        )
        assert out["status"] == "in_window"
        assert out["lead_days"] == 0
        assert out["start_date"] is None  # وقعت في الماضي ولا تُقدَّر بلا تاريخ حراريّ
        assert "window_start_unobserved" in out["evidence_missing"]

    def test_a_passed_window_is_not_projected_again(self):
        out = project_next_critical_window("maize", accumulated_gdd=1200.0, today=self.TODAY)
        assert out["status"] == "past"
        assert out["lead_days"] is None
        assert out["start_date"] is None and out["end_date"] is None

    def test_calendar_fallback_is_announced_with_lower_confidence(self):
        out = project_next_critical_window(
            "maize",
            accumulated_gdd=500.0,
            forecast_daily_gdd=[1.0] * 3,  # أفق لا يبلغ بداية النافذة
            sowing_date=date(2026, 6, 1),
            today=self.TODAY,
        )
        assert out["source"] == "calendar_fallback"
        assert out["confidence"] == "low"
        assert "forecast_horizon_too_short" in out["evidence_missing"]
        assert out["start_date"] is not None  # التقويم يعطي تاريخاً، بثقة أدنى

    def test_missing_gdd_falls_back_to_the_calendar_and_says_why(self):
        out = project_next_critical_window("maize", sowing_date=date(2026, 6, 1), today=self.TODAY)
        assert out["source"] == "calendar_fallback"
        assert "accumulated_gdd_missing" in out["evidence_missing"]

    def test_no_input_fabricates_no_window(self):
        out = project_next_critical_window("maize", today=self.TODAY)
        assert out["status"] == "insufficient_context"
        assert out["start_date"] is None and out["end_date"] is None
        assert out["source"] is None and out["confidence"] is None

    def test_a_corrupt_series_is_invalidated_whole_never_silently_shortened(self):
        for bad in ([15.0, None, 15.0], [15.0, -3.0, 15.0], [15.0, float("nan")], [15.0, "x"]):
            out = project_next_critical_window(
                "maize",
                accumulated_gdd=500.0,
                forecast_daily_gdd=bad,
                sowing_date=date(2026, 6, 1),
                today=self.TODAY,
            )
            # الاتّجاه الخطر: قيمةٌ ساقطة تُزيح الأيّام فيقصر الزمن القياديّ،
            # فيبدو الإنذار المتأخّر مبكراً. السلسلة تُبطَل كلّها ولا تُرقَّع.
            assert "forecast_series_invalid" in out["evidence_missing"]
            assert out["source"] != "gdd_forecast"

    def test_a_perennial_without_gdd_thresholds_says_so(self):
        perennial = next(
            (c for c in ("date_palm", "coffee", "grape") if not gdd_stage_thresholds(c)), None
        )
        assert perennial is not None, "البطاقات يجب أن تحمل مُعمِّراً واحداً بلا عتبات GDD"
        out = project_next_critical_window(perennial, accumulated_gdd=500.0, today=self.TODAY)
        assert "gdd_thresholds_unavailable" in out["evidence_missing"]
        assert out["source"] != "gdd_forecast"

    def test_a_projection_is_never_reported_as_an_observation(self):
        """قاعدة `canonical_phenology_state` لا تُنقَض من هنا: لا ملاحظة بلا راصد."""
        cases = [
            {"accumulated_gdd": 500.0, "forecast_daily_gdd": [15.0] * 20},
            {"accumulated_gdd": 700.0, "forecast_daily_gdd": [15.0] * 40},
            {"accumulated_gdd": 1200.0},
            {"accumulated_gdd": 500.0, "forecast_daily_gdd": [1.0] * 3},
            {"sowing_date": date(2026, 6, 1)},
            {},
        ]
        for kwargs in cases:
            out = project_next_critical_window("maize", today=self.TODAY, **kwargs)
            assert out["status"] != "observed"
            assert out["source"] != "observed"
            assert out["confidence"] != "high"  # سقف الثقة medium: الطقس متوقَّع لا مضمون

    def test_lead_days_is_never_negative(self):
        for das in (0, 30, 60, 90, 200):
            out = project_next_critical_window(
                "maize", sowing_date=self.TODAY - timedelta(days=das), today=self.TODAY
            )
            assert out["lead_days"] is None or out["lead_days"] >= 0
