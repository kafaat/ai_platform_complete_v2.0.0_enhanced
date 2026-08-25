"""حُرّاس الحقيقة التشغيليّة الموحّدة للحقل-الموسم (field_season_state_projection) — نقيّ."""

from __future__ import annotations

from datetime import date, timedelta

from api.field_season_projection import assemble_field_season_state


class TestFullProjection:
    def _full(self):
        # قمح: بذار 2025-11-01 (مثاليّ)، اليوم +50 يوماً ⇒ mid؛ GDD 800 ⇒ mid (متّسق).
        return assemble_field_season_state(
            field_id="F101",
            season_id="ssn_x",
            crop="wheat",
            cultivar="wheat_aziz",
            sowing_date=date(2025, 11, 1),
            today=date(2025, 12, 21),
            accumulated_gdd=800,
            observed_ndvi=0.40,  # تحت المتوقّع لـmid ⇒ تعارض
            observed_ndmi=0.05,
            valid_pixel_ratio=0.9,
            cloud_pct=5,
            weather_signals={"tmax_c": 34},  # ≥ عتبة تزهير القمح 31 ⇒ عقم
            water_stress_factor=0.5,
            water_deficit_7d_mm=30,
            open_tasks_count=2,
        )

    def test_effective_stage_prefers_gdd(self):
        s = self._full()
        assert s["current_stage"] == "mid"
        assert s["stage_source"] == "gdd"
        assert s["days_after_sowing"] == 50

    def test_current_kc_present(self):
        assert self._full()["current_kc"] is not None

    def test_calendar_status_optimal(self):
        assert self._full()["calendar_status"] == "optimal"

    def test_stage_risk_flags_flowering_heat_and_water(self):
        risks = {r["code"] for r in self._full()["weather_stage_risks"]["risks"]}
        assert "flowering_heat_sterility" in risks
        assert "flowering_water" in risks

    def test_eo_mismatch_below_expected(self):
        assert self._full()["eo_stage_mismatch"]["status"] == "below_expected"

    def test_requires_review_true_on_convergent_problems(self):
        assert self._full()["requires_review"] is True

    def test_confidence_medium_with_live_signals(self):
        assert self._full()["season_confidence"] == "medium"

    def test_evidence_used_lists_present_signals(self):
        used = set(self._full()["evidence_used"])
        assert {"crop", "sowing_date", "ndvi", "weather", "water", "open_tasks"} <= used


class TestHonestyMissingData:
    def test_sparse_inputs_low_confidence(self):
        # لا إشارات حيّة (لا NDVI/طقس/ماء) ⇒ ثقة منخفضة + evidence_missing.
        s = assemble_field_season_state(
            crop="wheat", sowing_date=date(2025, 11, 1), today=date(2025, 12, 21)
        )
        assert s["season_confidence"] == "low"
        assert {"ndvi", "weather", "water"} <= set(s["evidence_missing"])

    def test_unknown_crop_still_returns_structure(self):
        s = assemble_field_season_state(crop="nonexistent", sowing_date=date(2026, 5, 1))
        assert s["crop"] is None
        assert s["calendar_status"] == "unknown"  # لا تقويم ⇒ unknown صادق
        assert s["current_stage"] is None

    def test_perennial_no_annual_stage(self):
        # البُنّ مُعمِّر: لا phenology حوليّة ⇒ current_stage None، لا تعطّل.
        s = assemble_field_season_state(
            crop="coffee", sowing_date=date(2025, 1, 1), today=date(2025, 6, 1), observed_ndvi=0.6
        )
        assert s["current_stage"] is None
        assert s["eo_stage_mismatch"]["status"] == "inconclusive"

    def test_schema_and_no_fabrication_when_empty(self):
        s = assemble_field_season_state()
        assert s["schema"] == "field_season_state.v1"
        assert s["current_stage"] is None
        assert s["current_kc"] is None
        assert s["season_confidence"] == "low"


class TestCriticalWindowInTheUnifiedTruth:
    """W2 — النافذة الحرجة داخل الحقيقة الموحّدة، لا بجانبها.

    الموحِّد هو ما يقرؤه الذكاء/الواجهة/التقارير؛ فوضعُ الإسقاط خارجه يجعله نواةً
    لا يراها أحد. وهذا يفحص الوصل نفسه لا حساب النافذة (مُختبَرٌ في موضعه).
    """

    TODAY = date(2026, 8, 1)

    def _daily(self, hot=(), tmax_hot=38.0):
        return [
            {
                "date": (self.TODAY + timedelta(days=i)).isoformat(),
                "gdd": 15.0,
                "tmax_c": tmax_hot if i in hot else 30.0,
            }
            for i in range(1, 41)
        ]

    def _state(self, **over):
        kwargs = dict(
            field_id="f1",
            crop="maize",
            sowing_date=date(2026, 6, 1),
            today=self.TODAY,
            accumulated_gdd=500.0,
        )
        kwargs.update(over)
        return assemble_field_season_state(**kwargs)

    def test_the_unifier_publishes_the_window_and_its_collisions(self):
        state = self._state(forecast_daily=self._daily(hot=(12, 13)))
        assert state["critical_window"]["status"] == "upcoming"
        assert state["critical_window"]["lead_days"] == 10
        assert state["critical_window"]["source"] == "gdd_forecast"
        assert state["critical_window_collisions"]["status"] == "collisions"
        assert [e["lead_days"] for e in state["critical_window_collisions"]["events"]] == [12, 13]

    def test_a_collision_raises_requires_review(self):
        assert self._state(forecast_daily=self._daily(hot=(12, 13)))["requires_review"] is True

    def test_without_a_forecast_the_unifier_degrades_and_says_so(self):
        state = self._state()
        assert state["critical_window"]["source"] == "calendar_fallback"
        assert state["critical_window_collisions"]["status"] == "insufficient_context"
        assert state["critical_window_collisions"]["events"] == []

    def test_the_daily_gdd_series_is_received_never_recomputed_here(self):
        """WS-C.1c: حسابُ GDD اليوميّ مِلكُ محرّك الطقس. مُدخَلٌ بلا `gdd` لا يُلفَّق له.

        السلسلة الناقصة تُبطَل كلّها فيهبط الحساب إلى التقويم مُعلِناً — ولا تُشتقّ
        درجاتُ نموٍّ من الحرارة هنا (لكانت نواةً ثانية تنحرف عن الأولى بصمت).
        """
        no_gdd = [
            {"date": (self.TODAY + timedelta(days=i)).isoformat(), "tmax_c": 30.0}
            for i in range(1, 41)
        ]
        state = self._state(forecast_daily=no_gdd)
        assert state["critical_window"]["source"] == "calendar_fallback"

    def test_the_window_answers_when_while_stage_risk_answers_today(self):
        """④ و⑦ سؤالان مختلفان — ولا يُغني أحدهما عن الآخر.

        حرارةٌ اليوم دون العتبة، وحرارةٌ فوقها داخل النافذة بعد ١٢ يوماً:
        ④ هادئ و⑦ يُنذر. لو كانا سؤالاً واحداً لتساويا.
        """
        state = self._state(
            weather_signals={"tmax_c": 30.0},
            forecast_daily=self._daily(hot=(12,), tmax_hot=40.0),
        )
        assert state["weather_stage_risks"]["overall_severity"] in ("none", "low")
        assert state["critical_window_collisions"]["max_severity"] == "high"
