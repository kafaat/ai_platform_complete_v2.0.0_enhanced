"""اختبارات المُجمِّع الموحَّد للتوصيات (api.recommendations_hub) — منطق نقيّ.

يغطّي: بناء الفئات الأربع (irrigation/fertilizer/disease/yield)، تعيين الأولويّة،
الفرز بالأولويّة، والتدهور الرشيق عند غياب سياق الطقس/البذار (لا تلفيق).
لا حاجة لقاعدة أو شبكة — كلّ شيء offline.
"""

from datetime import date, timedelta

from api.recommendations_hub import (
    CATEGORIES,
    PRIORITY_ORDER,
    Recommendation,
    RecommendationContext,
    build_recommendations,
)


def _cats(recs: list[Recommendation]) -> set[str]:
    return {r.category for r in recs}


def _by_cat(recs: list[Recommendation], cat: str) -> Recommendation:
    return next(r for r in recs if r.category == cat)


class TestFullContext:
    """سياق كامل (طقس + موسم) ⇒ كلّ الفئات الأربع تظهر."""

    def _ctx(self, **over) -> RecommendationContext:
        base = dict(
            field_id="field_01",
            crop="wheat",
            stage="development",
            today=date(2026, 6, 11),
            sowing_date=date(2026, 6, 1),  # حديث ⇒ الحصاد بعيد
            et0_mm=6.0,
            rain_recent_mm=0.0,
            forecast_rain_mm=0.0,
            soil_moisture_pct=20.0,  # تربة جافّة ⇒ إلحاح أعلى
            temp_c=20.0,
            humidity_pct=85.0,  # رطب
            rain_mm_3d=12.0,  # مبلّل ⇒ خطر أمراض
        )
        base.update(over)
        return RecommendationContext(**base)

    def test_all_four_categories_present(self):
        recs = build_recommendations(self._ctx())
        assert _cats(recs) == set(CATEGORIES)

    def test_each_rec_has_required_shape(self):
        for r in build_recommendations(self._ctx()):
            assert r.category in CATEGORIES
            assert r.priority in PRIORITY_ORDER
            assert r.title_ar and isinstance(r.title_ar, str)
            assert r.detail_ar and isinstance(r.detail_ar, str)
            assert r.source and isinstance(r.source, str)

    def test_dry_soil_drives_high_irrigation_priority(self):
        recs = build_recommendations(self._ctx(et0_mm=10.0, soil_moisture_pct=20.0))
        assert _by_cat(recs, "irrigation").priority == "high"

    def test_high_disease_environment_is_high_priority(self):
        # رطوبة عالية + حرارة معتدلة + مطر تراكميّ ⇒ خطر مرتفع.
        recs = build_recommendations(self._ctx(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0))
        assert _by_cat(recs, "disease").priority == "high"

    def test_development_stage_fertilizer_is_nitrogen_high(self):
        recs = build_recommendations(self._ctx(stage="development"))
        fert = _by_cat(recs, "fertilizer")
        assert fert.priority == "high"
        assert "النيتروجين" in fert.title_ar or "(N)" in fert.title_ar

    def test_sorted_by_priority_descending(self):
        recs = build_recommendations(self._ctx())
        ranks = [PRIORITY_ORDER[r.priority] for r in recs]
        assert ranks == sorted(ranks)


class TestGracefulDegradation:
    """غياب جزء من السياق ⇒ تخطّي توصيته بلا تلفيق."""

    def test_no_weather_skips_irrigation_and_disease(self):
        ctx = RecommendationContext(
            field_id="f1",
            crop="tomato",
            stage="mid",
            sowing_date=date(2026, 1, 1),
            today=date(2026, 6, 11),
            # لا et0/temp/humidity ⇒ لا ريّ ولا أمراض
        )
        recs = build_recommendations(ctx)
        cats = _cats(recs)
        assert "irrigation" not in cats
        assert "disease" not in cats
        # التسميد والحصاد لا يحتاجان طقساً ⇒ يبقيان
        assert "fertilizer" in cats
        assert "yield" in cats

    def test_no_sowing_date_skips_yield(self):
        ctx = RecommendationContext(field_id="f1", crop="wheat", stage="mid", et0_mm=5.0)
        recs = build_recommendations(ctx)
        assert "yield" not in _cats(recs)
        assert "fertilizer" in _cats(recs)  # لا يزال متاحاً

    def test_unknown_crop_skips_yield_but_keeps_fertilizer(self):
        ctx = RecommendationContext(
            field_id="f1",
            crop="dragonfruit",  # غير معروف في جدول الدورة
            stage="mid",
            sowing_date=date(2026, 1, 1),
            today=date(2026, 6, 11),
        )
        recs = build_recommendations(ctx)
        assert "yield" not in _cats(recs)
        assert "fertilizer" in _cats(recs)

    def test_empty_context_still_returns_fertilizer(self):
        # أدنى سياق ممكن: لا محصول، لا طقس، لا بذار ⇒ يبقى التسميد العامّ فقط.
        recs = build_recommendations(RecommendationContext(field_id="f1"))
        assert _cats(recs) == {"fertilizer"}


class TestYieldWindow:
    """نافذة الحصاد التقديريّة من البذار + دورة المحصول."""

    def test_near_maturity_is_high_priority(self):
        # قمح دورته ~130 يوماً؛ نضع البذار قبل ~125 يوماً ⇒ اقتراب الحصاد.
        today = date(2026, 6, 11)
        ctx = RecommendationContext(
            field_id="f1",
            crop="wheat",
            stage="late",
            today=today,
            sowing_date=today - timedelta(days=125),
        )
        rec = _by_cat(build_recommendations(ctx), "yield")
        assert rec.priority == "high"

    def test_overdue_harvest_is_high_priority(self):
        today = date(2026, 6, 11)
        ctx = RecommendationContext(
            field_id="f1",
            crop="wheat",
            stage="late",
            today=today,
            sowing_date=today - timedelta(days=200),  # تجاوز ~130 + الهامش
        )
        rec = _by_cat(build_recommendations(ctx), "yield")
        assert rec.priority == "high"

    def test_far_from_harvest_is_low_priority(self):
        today = date(2026, 6, 11)
        ctx = RecommendationContext(
            field_id="f1",
            crop="wheat",
            stage="initial",
            today=today,
            sowing_date=today - timedelta(days=10),  # بداية الموسم
        )
        rec = _by_cat(build_recommendations(ctx), "yield")
        assert rec.priority == "low"
