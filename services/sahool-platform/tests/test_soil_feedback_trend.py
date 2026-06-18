"""اختبارات وحدة لـ core.soil_feedback_trend — اتّجاه التغذية الراجعة نبات-تربة عبر المواسم."""

from __future__ import annotations

import pytest
from core.soil_feedback_proxy import PlantSoilFeedback
from core.soil_feedback_trend import (
    FeedbackTrend,
    SeasonFeedback,
    analyze_feedback_trend,
)

pytestmark = pytest.mark.unit


def _fb(
    *,
    positive: float,
    negative: float = 0.0,
    pathogen: float = 0.0,
    microbial: float = 0.0,
    resilience: float = 0.0,
    net: float | None = None,
) -> PlantSoilFeedback:
    """يبني سِجلّ PlantSoilFeedback حتميّاً للاختبار (net = positive - negative ما لم يُمرَّر)."""
    return PlantSoilFeedback(
        positive_feedback_score=positive,
        negative_feedback_risk=negative,
        pathogen_accumulation_risk=pathogen,
        microbial_diversity_proxy=microbial,
        soil_resilience_score=resilience,
        net_feedback=(positive - negative) if net is None else net,
        direction="neutral",
        confidence=0.8,
        inputs_known=8,
        drivers_positive_ar=(),
        drivers_negative_ar=(),
        verdict_ar="اختبار",
    )


def _season(season_id: str, fb: PlantSoilFeedback) -> SeasonFeedback:
    return SeasonFeedback(season_id=season_id, feedback=fb)


def test_three_season_improving_series() -> None:
    """سلسلة موجب 54→61→76 ⇒ اتّجاه متحسّن، فروق موجبة، ميل موجب."""
    history = [
        _season("2024", _fb(positive=54.0, negative=20.0)),
        _season("2025", _fb(positive=61.0, negative=18.0)),
        _season("2026", _fb(positive=76.0, negative=14.0)),
    ]
    t = analyze_feedback_trend(history)
    assert isinstance(t, FeedbackTrend)
    assert t.seasons_analyzed == 3
    assert t.direction == "improving"
    assert t.positive_delta == 22.0  # 76 - 54
    assert t.net_delta is not None and t.net_delta > 0
    assert t.slope_per_season is not None and t.slope_per_season > 0


def test_improving_drivers_mention_improvement() -> None:
    """الاتّجاه المتحسّن يجب أن يذكر ارتفاع التغذية الموجبة في الدوافع."""
    history = [
        _season("2024", _fb(positive=54.0, negative=20.0, microbial=40.0)),
        _season("2026", _fb(positive=76.0, negative=14.0, microbial=70.0)),
    ]
    t = analyze_feedback_trend(history)
    joined = " | ".join(t.drivers_ar)
    assert "التغذية الراجعة الموجبة" in joined
    assert "التنوّع الميكروبيّ" in joined
    assert any("ارتفع" in d for d in t.drivers_ar)


def test_declining_series() -> None:
    """سلسلة هابطة في الصافي ⇒ اتّجاه متدهور وفروق سالبة."""
    history = [
        _season("2024", _fb(positive=72.0, negative=10.0)),
        _season("2025", _fb(positive=60.0, negative=22.0)),
        _season("2026", _fb(positive=48.0, negative=35.0)),
    ]
    t = analyze_feedback_trend(history)
    assert t.direction == "declining"
    assert t.positive_delta is not None and t.positive_delta < 0
    assert t.net_delta is not None and t.net_delta < 0
    assert t.slope_per_season is not None and t.slope_per_season < 0


def test_flat_series_is_stable() -> None:
    """سلسلة شبه ثابتة (ضمن عتبة الثبات) ⇒ مستقرّ."""
    history = [
        _season("2024", _fb(positive=50.0, negative=20.0)),
        _season("2025", _fb(positive=51.0, negative=20.5)),
        _season("2026", _fb(positive=50.5, negative=20.0)),
    ]
    t = analyze_feedback_trend(history)
    assert t.direction == "stable"


def test_single_season_no_crash_deltas_none() -> None:
    """موسم واحد ⇒ مستقرّ، الفروق/الميل None، بلا انهيار."""
    history = [_season("2026", _fb(positive=60.0, negative=15.0))]
    t = analyze_feedback_trend(history)
    assert t.seasons_analyzed == 1
    assert t.direction == "stable"
    assert t.positive_delta is None
    assert t.net_delta is None
    assert t.slope_per_season is None
    assert t.drivers_ar == ()
    assert "موسم" in t.verdict_ar


def test_empty_history_no_crash() -> None:
    """مدخل فارغ ⇒ بلا انهيار، كلّ الفروق None، سلاسل فارغة."""
    t = analyze_feedback_trend([])
    assert t.seasons_analyzed == 0
    assert t.direction == "stable"
    assert t.positive_delta is None
    assert t.net_delta is None
    assert t.slope_per_season is None
    assert t.positive_series == ()
    assert t.net_series == ()


def test_positive_series_ordering_preserved() -> None:
    """يُحفَظ ترتيب المدخل في positive_series وnet_series (لا فرز)."""
    history = [
        _season("2024", _fb(positive=54.0, negative=20.0)),
        _season("2025", _fb(positive=61.0, negative=18.0)),
        _season("2026", _fb(positive=76.0, negative=14.0)),
    ]
    t = analyze_feedback_trend(history)
    assert t.positive_series == (("2024", 54.0), ("2025", 61.0), ("2026", 76.0))
    assert [sid for sid, _ in t.net_series] == ["2024", "2025", "2026"]


def test_slope_computed_correctly() -> None:
    """الميل = (net الأحدث - net الأقدم) / (المواسم - 1) على حالة مصمّمة."""
    # net: 10 ← 30 ← 40 عبر 3 مواسم ⇒ (40 - 10) / 2 = 15.0
    history = [
        _season("a", _fb(positive=10.0, negative=0.0, net=10.0)),
        _season("b", _fb(positive=30.0, negative=0.0, net=30.0)),
        _season("c", _fb(positive=40.0, negative=0.0, net=40.0)),
    ]
    t = analyze_feedback_trend(history)
    assert t.slope_per_season == 15.0
    assert t.net_delta == 30.0


def test_two_season_slope_uses_single_step() -> None:
    """موسمان ⇒ الميل = الفرق الكامل (خطوة واحدة)، ويساوي net_delta."""
    history = [
        _season("2025", _fb(positive=40.0, negative=0.0, net=40.0)),
        _season("2026", _fb(positive=60.0, negative=0.0, net=60.0)),
    ]
    t = analyze_feedback_trend(history)
    assert t.net_delta == 20.0
    assert t.slope_per_season == 20.0
    assert t.direction == "improving"


def test_pathogen_drop_cited_as_driver() -> None:
    """انخفاض خطر تراكم الممرضات يُذكَر كدافع تغيّر."""
    history = [
        _season("2024", _fb(positive=55.0, negative=20.0, pathogen=70.0, resilience=30.0)),
        _season("2026", _fb(positive=62.0, negative=18.0, pathogen=40.0, resilience=55.0)),
    ]
    t = analyze_feedback_trend(history)
    joined = " | ".join(t.drivers_ar)
    assert "تراكم الممرضات" in joined
    assert "مرونة التربة" in joined


def test_small_movers_below_epsilon_not_cited() -> None:
    """حركات الدرجات الفرعيّة دون العتبة لا تُذكَر كدوافع."""
    history = [
        _season("2024", _fb(positive=50.0, negative=20.0, microbial=50.0)),
        _season("2025", _fb(positive=51.0, negative=20.0, microbial=51.0)),
    ]
    t = analyze_feedback_trend(history)
    # تغيّر الموجب +1 والميكروبيّ +1 كلاهما دون العتبة ⇒ لا دوافع.
    assert t.drivers_ar == ()
