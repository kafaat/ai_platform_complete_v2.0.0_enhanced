"""core/soil_feedback_trend.py — اتّجاه التغذية الراجعة نبات-تربة عبر المواسم (نقيّ، حتميّ).

الفكرة: بدل مقارنة المواسم على الغلّة/NDVI/الأمطار فقط، نقارن **اتّجاه التغذية الراجعة
نبات-تربة** (Soil Feedback Trend) موسماً بعد موسم لنكشف: هل صحّة التربة **تتحسّن** أم
**تتدهور**، و**لماذا**. مثال: 2024 موجب=54 ← 2025 موجب=61 ← 2026 موجب=76 ⇒ اتّجاه
متحسّن، وندلّ على دوافع التغيّر (انخفاض خطر الممرضات، ارتفاع التنوّع الميكروبيّ…).

يُركّب فوق `core/soil_feedback_proxy.py`: كلّ موسم يحمل سِجلّ `PlantSoilFeedback` جاهزاً
(يُحسَب في موقع الاستدعاء عبر `assess_plant_soil_feedback`). هذه الوحدة لا تُعيد حساب
التغذية الراجعة — تأخذ سلسلة سجلّات مرتّبة زمنيّاً (الأقدم→الأحدث) وتستخرج الاتّجاه.

نقيّ تماماً: لا I/O، لا شبكة، لا قاعدة بيانات، لا عشوائيّة، لا numpy. stdlib +
dataclasses فقط. حتميّ بالكامل. كلّ قسمة محروسة. لا انهيار على مدخلات فارغة/موسم واحد.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.soil_feedback_proxy import PlantSoilFeedback

# ── عتبة «الثبات» للاتّجاه: تغيّر net الصافي ضمن ±هذا يُعدّ مستقرّاً (لا تحسّن/تدهور) ──
_STABLE_EPSILON = 3.0

# ── أدنى حركة في درجة فرعيّة لتُذكَر كدافع تغيّر (على مقياس [0,100]) ──
_DRIVER_EPSILON = 4.0


@dataclass(frozen=True)
class SeasonFeedback:
    """يربط معرّف موسم بسِجلّ تغذيته الراجعة نبات-تربة المحسوب مسبقاً."""

    season_id: str
    feedback: PlantSoilFeedback


@dataclass(frozen=True)
class FeedbackTrend:
    """اتّجاه التغذية الراجعة نبات-تربة عبر سلسلة مواسم (مرتّبة زمنيّاً)."""

    seasons_analyzed: int
    positive_series: tuple[tuple[str, float], ...]  # (season_id, positive_feedback_score) زمنيّاً
    net_series: tuple[tuple[str, float], ...]  # (season_id, net_feedback) زمنيّاً
    positive_delta: float | None  # الأحدث ناقص الأقدم لـpositive (None إن <2 موسم)
    net_delta: float | None  # الأحدث ناقص الأقدم لـnet (None إن <2 موسم)
    direction: str  # "improving" | "declining" | "stable" (من اتّجاه net)
    slope_per_season: float | None  # متوسّط تغيّر net لكلّ خطوة موسم (None إن <2)
    drivers_ar: tuple[str, ...]  # شرح عربيّ لِما تغيّر (انخفض خطر الممرضات، ارتفع التنوّع…)
    verdict_ar: str  # حُكم عربيّ من سطر واحد


def _round2(x: float) -> float:
    """تقريب حتميّ إلى منزلتين عشريّتين."""
    return round(x, 2)


def analyze_feedback_trend(history: list[SeasonFeedback]) -> FeedbackTrend:
    """يحلّل اتّجاه التغذية الراجعة نبات-تربة عبر سلسلة مواسم مرتّبة زمنيّاً (نقيّ، حتميّ).

    `history` مرتّبة من الأقدم إلى الأحدث. يُحافَظ على الترتيب في `positive_series`
    و`net_series` كما هو (لا فرز ولا إعادة ترتيب).

    أقلّ من موسمين ⇒ `seasons_analyzed` يعكس المدخل، و`positive_delta`/`net_delta`/
    `slope_per_season` تساوي None، و`direction="stable"`، وملاحظة عربيّة بأنّ الاتّجاه
    يحتاج موسمين على الأقلّ. لا يُرفَع أيّ استثناء على مدخل فارغ/موسم واحد.

    `direction`: من `net_delta` مع عتبة ثبات `_STABLE_EPSILON` (±3.0): فوقها موجباً
    ⇒ "improving"، تحتها سالباً ⇒ "declining"، وإلّا "stable".

    `slope_per_season = (net الأحدث - net الأقدم) / (المواسم - 1)` (قسمة محروسة).

    `drivers_ar`: يقارن الدرجات الفرعيّة لأقدم موسم بأحدث موسم ويذكر أكبر المحرّكات
    بالعربيّة (تغيّر التغذية الموجبة/خطر الممرضات/التنوّع الميكروبيّ/مرونة التربة/التغذية
    السالبة)، ولا يُذكَر إلّا ما تجاوز `_DRIVER_EPSILON`.
    """
    seasons_analyzed = len(history)

    positive_series = tuple((s.season_id, s.feedback.positive_feedback_score) for s in history)
    net_series = tuple((s.season_id, s.feedback.net_feedback) for s in history)

    # ── أقلّ من موسمين: لا اتّجاه ممكن ──
    if seasons_analyzed < 2:
        if seasons_analyzed == 0:
            verdict = "لا مواسم: يحتاج تحليل الاتّجاه موسمين على الأقلّ لكشف مسار صحّة التربة."
        else:
            verdict = "موسم واحد فقط: يحتاج تحليل الاتّجاه موسمين على الأقلّ للمقارنة الزمنيّة."
        return FeedbackTrend(
            seasons_analyzed=seasons_analyzed,
            positive_series=positive_series,
            net_series=net_series,
            positive_delta=None,
            net_delta=None,
            direction="stable",
            slope_per_season=None,
            drivers_ar=(),
            verdict_ar=verdict,
        )

    first = history[0].feedback
    last = history[-1].feedback

    positive_delta = _round2(last.positive_feedback_score - first.positive_feedback_score)
    net_delta = _round2(last.net_feedback - first.net_feedback)

    # ── الميل لكلّ خطوة موسم (قسمة محروسة؛ seasons_analyzed ≥ 2 هنا) ──
    steps = seasons_analyzed - 1
    slope_per_season = (
        _round2((last.net_feedback - first.net_feedback) / steps) if steps > 0 else None
    )

    # ── الاتّجاه من net_delta مع عتبة الثبات ──
    if net_delta > _STABLE_EPSILON:
        direction = "improving"
    elif net_delta < -_STABLE_EPSILON:
        direction = "declining"
    else:
        direction = "stable"

    # ── دوافع التغيّر: قارن أقدم موسم بأحدثه على الدرجات الفرعيّة ──
    drivers: list[str] = []

    d_positive = last.positive_feedback_score - first.positive_feedback_score
    if d_positive > _DRIVER_EPSILON:
        drivers.append(f"ارتفعت درجة التغذية الراجعة الموجبة +{_round2(d_positive)}")
    elif d_positive < -_DRIVER_EPSILON:
        drivers.append(f"انخفضت درجة التغذية الراجعة الموجبة {_round2(d_positive)}")

    d_negative = last.negative_feedback_risk - first.negative_feedback_risk
    if d_negative < -_DRIVER_EPSILON:
        drivers.append(f"انخفض خطر التغذية الراجعة السالبة {_round2(d_negative)}")
    elif d_negative > _DRIVER_EPSILON:
        drivers.append(f"ارتفع خطر التغذية الراجعة السالبة +{_round2(d_negative)}")

    d_pathogen = last.pathogen_accumulation_risk - first.pathogen_accumulation_risk
    if d_pathogen < -_DRIVER_EPSILON:
        drivers.append(f"انخفض خطر تراكم الممرضات {_round2(d_pathogen)}")
    elif d_pathogen > _DRIVER_EPSILON:
        drivers.append(f"ارتفع خطر تراكم الممرضات +{_round2(d_pathogen)}")

    d_microbial = last.microbial_diversity_proxy - first.microbial_diversity_proxy
    if d_microbial > _DRIVER_EPSILON:
        drivers.append(f"ارتفع مؤشّر التنوّع الميكروبيّ +{_round2(d_microbial)}")
    elif d_microbial < -_DRIVER_EPSILON:
        drivers.append(f"انخفض مؤشّر التنوّع الميكروبيّ {_round2(d_microbial)}")

    d_resilience = last.soil_resilience_score - first.soil_resilience_score
    if d_resilience > _DRIVER_EPSILON:
        drivers.append(f"تحسّنت مرونة التربة +{_round2(d_resilience)}")
    elif d_resilience < -_DRIVER_EPSILON:
        drivers.append(f"تراجعت مرونة التربة {_round2(d_resilience)}")

    # ── الحُكم العربيّ ──
    if direction == "improving":
        verdict = (
            f"اتّجاه متحسّن عبر {seasons_analyzed} مواسم: صافي التغذية الراجعة يرتفع "
            f"({_round2(first.net_feedback)} ← {_round2(last.net_feedback)}) — صحّة التربة تتقدّم."
        )
    elif direction == "declining":
        verdict = (
            f"اتّجاه متدهور عبر {seasons_analyzed} مواسم: صافي التغذية الراجعة ينخفض "
            f"({_round2(first.net_feedback)} ← {_round2(last.net_feedback)}) — تدخّل مطلوب."
        )
    else:
        verdict = (
            f"اتّجاه مستقرّ عبر {seasons_analyzed} مواسم: صافي التغذية الراجعة شبه ثابت "
            f"({_round2(first.net_feedback)} ← {_round2(last.net_feedback)})."
        )

    return FeedbackTrend(
        seasons_analyzed=seasons_analyzed,
        positive_series=positive_series,
        net_series=net_series,
        positive_delta=positive_delta,
        net_delta=net_delta,
        direction=direction,
        slope_per_season=slope_per_season,
        drivers_ar=tuple(drivers),
        verdict_ar=verdict,
    )
