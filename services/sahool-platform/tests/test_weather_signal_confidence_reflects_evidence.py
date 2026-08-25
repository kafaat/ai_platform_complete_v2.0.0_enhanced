"""P4 — الثقةُ تعكس الدليل: حجمَ العيّنة، وتماسكَها، ووجودَها أصلاً.

كانت ثقةُ إشارتَي الصقيع والحرارة نسبةً خاماً ``hours / max(1, hours_evaluated)``
ثمّ تُقَصّ إلى ``[0,1]``. وفيها ثلاثةُ أعطالٍ مقيسة بالتنفيذ:

① **صفر مشاهدة ⇒ ثقةٌ كاملة.** ``compute_scores([])`` يُرجِع ``trafficability_score=0.0``،
  و0.0 دون عتبة ``_TRAFFIC_POOR`` — فتُطلَق «التربةُ غير سالكة» بثقة **1.0** من لا شيء.
  والدرجةُ الصفريّة هناك تعني «لا شيء رُصِد» لا «رُصِد صفر».

② **حجمُ العيّنة غيرُ مرئيّ.** ساعةُ صقيعٍ من ساعة، وأربعٌ وعشرون من أربعٍ وعشرين —
  كلتاهما نسبتُها 1.0. والدليلان ليسا سواءً بحال.

③ **المقامُ مُخترَع في مسار الإنتاج.** ``build_signal_records`` كان يشتقّه
  ``max(1, heat, frost)`` — أي **يُساويه بالبسط** — فتخرج النسبة 1.0 حتماً. مقيس:
  ستُّ ساعات صقيعٍ من أربعٍ وعشرين مُقيَّمة كانت تُبلِّغ **1.0**؛ وهي الآن **0.135**.
  فالخطأُ لم يكن حالةً حدّيّة بل **المسارَ الطبيعيّ**، وبمقدار ٧٫٤ أضعاف.

والعلاجُ ثلاثة أجزاء مقابلها: لا إشارةَ بلا ساعاتٍ مُقيَّمة · حدُّ Wilson الأدنى بدل
النسبة الخام · والمقامُ يُحمَل مقيساً ولا يُشتقّ.
"""

from __future__ import annotations

import pytest
from core.weather_overlay import FieldWeatherScores, compute_scores
from core.weather_overlay_pipeline import build_overlay_record, build_signal_records
from core.weather_signals import _wilson_lower_bound, aggregate_cells_to_hourly, generate_signals

pytestmark = pytest.mark.unit


def _scores(**kw) -> FieldWeatherScores:
    base = dict(
        spray_suitability_score=0.0,
        disease_risk_score=0.0,
        trafficability_score=100.0,
        heat_stress_hours=0,
        frost_risk_hours=0,
        hours_evaluated=24,
        frost_evaluable_hours=24,
        heat_evaluable_hours=24,
    )
    base.update(kw)
    return FieldWeatherScores(**base)


def _conf_of(signals, signal_type: str) -> float | None:
    for s in signals:
        if s.signal_type == signal_type:
            return s.confidence_score
    return None


# ── ① لا دليل ⇒ لا ادّعاء ────────────────────────────────────────────
def test_zero_evaluated_hours_yields_no_signals_at_all():
    """العطلُ الأصليّ حرفيّاً: قائمةُ ساعاتٍ فارغة كانت تُنتِج «التربةُ غير سالكة» بثقة 1.0."""
    assert generate_signals(compute_scores([])) == []


def test_the_empty_overlay_no_longer_claims_impassable_soil():
    """الدرجةُ الصفريّة في التراكب الفارغ تعني «لا شيء رُصِد» — لا تربةً مُشبَعة."""
    empty = compute_scores([])
    assert empty.trafficability_score == 0.0, "الافتراض الذي بُني عليه العطل"
    assert empty.hours_evaluated == 0
    assert not [s for s in generate_signals(empty) if s.signal_type == "trafficability_poor"]


def test_a_real_impassable_soil_still_signals():
    """ضبطٌ: لولاه لمرّ «لا إشارة أبداً» بوصفه إصلاحاً."""
    sig = generate_signals(_scores(trafficability_score=10.0, hours_evaluated=24))
    assert _conf_of(sig, "trafficability_poor") == 0.9


# ── ② حجمُ العيّنة يظهر في الرقم ──────────────────────────────────────
def test_one_hour_of_frost_is_not_as_confident_as_a_full_day():
    """كلتا النسبتين الخام 1.0 — والفرقُ بينهما هو كلّ الحمولة."""
    one = _conf_of(
        generate_signals(_scores(frost_risk_hours=1, hours_evaluated=1, frost_evaluable_hours=1)),
        "frost_imminent",
    )
    day = _conf_of(
        generate_signals(
            _scores(frost_risk_hours=24, hours_evaluated=24, frost_evaluable_hours=24)
        ),
        "frost_imminent",
    )

    assert one is not None and day is not None
    assert one < day, "مشاهدةٌ واحدة تساوي يوماً كاملاً — حجمُ العيّنة غيرُ مرئيّ"
    assert one < 0.5, "ثقةٌ عالية من مشاهدةٍ يتيمة"
    assert day < 1.0, "لا يقينَ كاملاً من عيّنة منتهية"


def test_more_stress_hours_out_of_the_same_window_is_more_confident():
    """الترتيبُ يجب أن يبقى صحيحاً بعد الإصلاح — وإلّا صار الرقم بلا معنى قراريّ."""
    few = _conf_of(
        generate_signals(_scores(heat_stress_hours=3, hours_evaluated=24)), "heat_stress"
    )
    many = _conf_of(
        generate_signals(_scores(heat_stress_hours=18, hours_evaluated=24)), "heat_stress"
    )

    assert few is not None and many is not None and few < many


@pytest.mark.parametrize(("k", "n"), [(1, 1), (2, 2), (6, 24), (12, 24), (24, 24)])
def test_the_lower_bound_never_exceeds_the_raw_proportion(k: int, n: int):
    """حدٌّ أدنى يتجاوز التقدير النقطيّ ليس حدّاً أدنى — يقيسه هذا مباشرةً."""
    lower = _wilson_lower_bound(k, n)
    assert lower is not None and 0.0 <= lower <= k / n


# ── ③ المدخلُ المتناقض لا يُقَصّ ─────────────────────────────────────
@pytest.mark.parametrize(("k", "n"), [(50, 24), (1, 0), (5, -1), (-1, 10)])
def test_an_impossible_count_has_no_lower_bound(k: int, n: int):
    """``None`` لا ``0.0``: الأخيرُ رقمٌ صالح يدخل المقارنات، والمطلوبُ ألّا يدخل."""
    assert _wilson_lower_bound(k, n) is None


def test_an_incoherent_score_emits_no_stress_signal():
    sig = generate_signals(_scores(frost_risk_hours=50, heat_stress_hours=99, hours_evaluated=24))
    assert not [s for s in sig if s.signal_type in {"frost_imminent", "heat_stress"}]


# ── ④ المقام يُحمَل ولا يُشتقّ (مسار الإنتاج) ────────────────────────
def _frost_rows(total_hours: int, frost_hours: int) -> list[dict]:
    return [
        {
            "hour": h,
            "cell_key": "A",
            "temp_min": 0 if h < frost_hours else 15,
            "temp_max": 20,
            "precip_sum": 0.0,
        }
        for h in range(total_hours)
    ]


def test_the_overlay_record_carries_the_measured_denominator():
    rec = build_overlay_record("fld", "t", _frost_rows(24, 6))

    assert rec["hours_evaluated"] == 24
    assert rec["frost_evaluable_hours"] == 24
    assert rec["heat_evaluable_hours"] == 24
    assert rec["frost_risk_hours"] == 6


def test_the_production_path_uses_the_measured_denominator_not_the_numerator():
    """الحمولةُ كلُّها: ٦ من ٢٤ كانت تُبلِّغ 1.0 لأنّ المقام اشتُقّ ``max(1, heat, frost)=6``.

    فالنسبةُ تصير 6/6 مهما اتّسعت النافذة — الخطأُ في المسار الطبيعيّ لا في حالةٍ حدّيّة.
    """
    rec = build_overlay_record("fld", "t", _frost_rows(24, 6))
    frost = next(
        s for s in build_signal_records("fld", "t", rec) if s["signal_type"] == "frost_imminent"
    )

    assert frost["payload"]["frost_evaluable_hours"] == 24, "عاد المقام مُخترَعاً"
    # والحضورُ المنشور تشخيصاً لا يجوز أن يكذب هو الآخر: اشتقاقُه `max(1, heat, frost)`
    # يجعله 6 بدل 24، فيقرأ المُشخِّص نافذةً أضيق ممّا قِيست.
    assert frost["payload"]["hours_present"] == 24, "الحضورُ المنشور مُشتقٌّ لا مقيس"
    assert frost["payload"]["frost_hours"] == 6
    assert frost["confidence_score"] < 0.3, (
        "ستُّ ساعاتٍ من أربعٍ وعشرين تُبلِّغ ثقةً عالية — المقام مُساوٍ للبسط"
    )


def test_an_overlay_without_the_denominator_claims_nothing():
    """المقامُ الغائب لا يُخترَع. سجلٌّ قديمٌ بلا المفتاح ⇒ لا إشارة، لا ثقةٌ مُلفَّقة."""
    rec = build_overlay_record("fld", "t", _frost_rows(24, 6))
    rec.pop("frost_evaluable_hours")

    assert build_signal_records("fld", "t", rec) == []


# ── ⑤ أساسُ الرقم منشورٌ مع الرقم ────────────────────────────────────
def test_the_payload_carries_the_numerator_denominator_and_basis():
    """من يقرأ ثقةً عليه أن يستطيع مراجعة أساسها بلا الرجوع إلى الشيفرة."""
    sig = generate_signals(_scores(frost_risk_hours=6, hours_evaluated=24))
    payload = next(s for s in sig if s.signal_type == "frost_imminent").payload

    assert payload["frost_hours"] == 6
    assert payload["frost_evaluable_hours"] == 24
    assert payload["confidence_basis"] == "wilson_lower_bound_95"


# ══ ⑥ المقامُ المخصوص: البسطُ والمقامُ من فضاءِ ملاحظةٍ واحد ══════════
#
# `hours_evaluated` يعدّ كلّ ساعةٍ **حاضرة**، و`frost_risk_hours` يشترط
# `temp_min_c is not None`. فالساعةُ الحاضرة بلا `temp_min` تدخل المقامَ ولا
# يمكنها دخولُ البسط أبداً — وWilson فوق كسرٍ كهذا يُحسِّن تقديرَ اللايقين على
# نسبةٍ لا معنى لها. المقامُ الصحيح هو **الفرص** لا الحضور.


def _mixed_rows(total: int, frost: int, missing_temp_min: int) -> list[dict]:
    """ساعاتٌ حاضرة، بعضُها بلا ``temp_min`` إطلاقاً — أي غيرُ قابلة لتقييم الصقيع."""
    rows = []
    for h in range(total):
        row = {"hour": h, "cell_key": "A", "temp_max": 20, "precip_sum": 0.0}
        if h < total - missing_temp_min:
            row["temp_min"] = 0 if h < frost else 15
        rows.append(row)
    return rows


def test_hours_without_a_reading_are_not_counted_as_frost_opportunities():
    """الحالةُ المقيسة حرفيّاً: ٢٤ حاضرة · ١٢ منها بلا ``temp_min`` · ٦ صقيع.

    النسبةُ الصادقة 6/12 = 0.5، لا 6/24 = 0.25.
    """
    scores = compute_scores(aggregate_cells_to_hourly(_mixed_rows(24, 6, 12)))

    assert scores.hours_evaluated == 24, "الساعاتُ الحاضرة"
    assert scores.frost_evaluable_hours == 12, "الفرصُ القابلة لتقييم الصقيع"
    assert scores.frost_risk_hours == 6
    assert scores.frost_risk_hours / scores.frost_evaluable_hours == 0.5


def test_adding_unreadable_hours_does_not_move_frost_confidence():
    """الشرطُ الحاسم الذي طلبه العقد: ساعاتٌ ليست فرصاً لا تُغيّر الثقة.

    لو دخلت المقامَ لخفّضت الثقةَ بمجرّد أن يُرسِل المزوّد ساعاتٍ ناقصة —
    أي لصار الرقمُ رهنَ اكتمال بياناتٍ لا علاقةَ لها بالحدث.
    """
    tight = compute_scores(aggregate_cells_to_hourly(_mixed_rows(12, 6, 0)))
    padded = compute_scores(aggregate_cells_to_hourly(_mixed_rows(24, 6, 12)))

    conf_tight = _conf_of(generate_signals(tight), "frost_imminent")
    conf_padded = _conf_of(generate_signals(padded), "frost_imminent")

    assert tight.hours_evaluated == 12 and padded.hours_evaluated == 24
    assert conf_tight == conf_padded, "ساعاتٌ غيرُ قابلة للتقييم حرّكت الثقة"


def test_each_event_uses_its_own_denominator_not_the_other_s():
    """`temp_max` متاحٌ دائماً و`temp_min` نصفُ الوقت — فالمقامان يفترقان."""
    scores = compute_scores(aggregate_cells_to_hourly(_mixed_rows(24, 6, 12)))

    assert scores.frost_evaluable_hours == 12
    assert scores.heat_evaluable_hours == 24
    assert scores.frost_evaluable_hours != scores.heat_evaluable_hours


def test_a_missing_max_reading_shrinks_only_the_heat_denominator():
    """الاتّجاه المعاكس: نقصُ ``temp_max`` لا يمسّ مقامَ الصقيع."""
    rows = [
        {"hour": h, "cell_key": "A", "temp_min": 0, "precip_sum": 0.0}
        | ({"temp_max": 45} if h < 8 else {})
        for h in range(24)
    ]
    scores = compute_scores(aggregate_cells_to_hourly(rows))

    assert scores.heat_evaluable_hours == 8
    assert scores.frost_evaluable_hours == 24


# ── حدودٌ صريحة على المقام المخصوص ──────────────────────────────────
def test_zero_events_out_of_a_full_window_is_zero_confidence():
    """0/N: لا حدث ⇒ لا إشارة أصلاً؛ والحدُّ الأدنى على 0/N صفرٌ لا شيءَ دونه."""
    assert _wilson_lower_bound(0, 24) == 0.0
    assert not [
        s
        for s in generate_signals(_scores(frost_risk_hours=0, frost_evaluable_hours=24))
        if s.signal_type == "frost_imminent"
    ]


def test_every_opportunity_realised_is_the_highest_the_data_allows():
    """N/N: النسبةُ الخام 1.0، والحدُّ الأدنى أعلى ما تسمح به العيّنة **دونها**.

    وهذا مقصودٌ لا نقص: حدٌّ أدنى يبلغ 1.0 يعني يقيناً كاملاً من عيّنة منتهية —
    وهو ادّعاءُ Wald الذي رُفِض. والقيمةُ تصعد باتّساع العيّنة ولا تبلغ الواحد.
    """
    small = _wilson_lower_bound(6, 6)
    large = _wilson_lower_bound(240, 240)

    assert small is not None and large is not None
    assert small < large < 1.0
    assert _conf_of(
        generate_signals(_scores(frost_risk_hours=24, frost_evaluable_hours=24)), "frost_imminent"
    ) == pytest.approx(_wilson_lower_bound(24, 24), abs=1e-4)


def test_more_events_than_opportunities_is_inconsistent_not_clamped():
    """k > n: تناقضٌ في النَّسَب لا في الحساب — فلا إشارة، ولا قصٌّ صامت إلى 1.0."""
    sig = generate_signals(_scores(frost_risk_hours=13, frost_evaluable_hours=12))

    assert not [s for s in sig if s.signal_type == "frost_imminent"]


def test_no_opportunities_is_unknown_not_certain():
    """n = 0: لا فرصةَ رُصِدت ⇒ لا ثقةَ تُقاس. والصفرُ في المقام لا يصير واحداً."""
    assert _wilson_lower_bound(3, 0) is None
    assert not [
        s
        for s in generate_signals(_scores(frost_risk_hours=3, frost_evaluable_hours=0))
        if s.signal_type == "frost_imminent"
    ]


def test_the_published_denominator_is_the_one_actually_divided_by():
    """نشرُ ``hours_evaluated`` مقاماً كان سيجعل المراجعة مستحيلة: رقمٌ لم يُقسَم عليه."""
    scores = compute_scores(aggregate_cells_to_hourly(_mixed_rows(24, 6, 12)))
    payload = next(s for s in generate_signals(scores) if s.signal_type == "frost_imminent").payload

    assert payload["frost_evaluable_hours"] == 12, "المقام المنشور ليس المقام المستعمَل"
    assert payload["hours_present"] == 24, "الحضورُ يبقى منشوراً للتشخيص، لا مقاماً"
    assert payload["frost_hours"] == 6


def test_the_frost_confidence_is_computed_from_the_frost_denominator_itself():
    """ثغرةٌ كشفها التكذيب لا المراجعة: كانت الاختبارات تؤكّد أنّ المقامَين
    **يفترقان** وأنّ المنشورَ صحيح، ولا تربط **القيمة** بمقامها. فإبدالُ مقام
    الصقيع بمقام الحرارة كان ينجو صامتاً — والرقمُ وحده هو ما يستهلكه القرار.
    """
    scores = compute_scores(aggregate_cells_to_hourly(_mixed_rows(24, 6, 12)))
    assert scores.frost_evaluable_hours == 12 and scores.heat_evaluable_hours == 24

    conf = _conf_of(generate_signals(scores), "frost_imminent")

    assert conf == pytest.approx(_wilson_lower_bound(6, 12), abs=1e-4)
    assert conf != pytest.approx(_wilson_lower_bound(6, 24), abs=1e-4)


def test_the_heat_confidence_is_computed_from_the_heat_denominator_itself():
    """المقابلُ المتماثل — وإلّا حُرِس اتّجاهٌ واحد وتُرِك نظيرُه مكشوفاً."""
    rows = [
        {"hour": h, "cell_key": "A", "temp_min": 5, "precip_sum": 0.0}
        | ({"temp_max": 45} if h < 8 else {})
        for h in range(24)
    ]
    scores = compute_scores(aggregate_cells_to_hourly(rows))
    assert scores.heat_evaluable_hours == 8 and scores.frost_evaluable_hours == 24

    conf = _conf_of(generate_signals(scores), "heat_stress")

    assert conf == pytest.approx(_wilson_lower_bound(scores.heat_stress_hours, 8), abs=1e-4)
    assert conf != pytest.approx(_wilson_lower_bound(scores.heat_stress_hours, 24), abs=1e-4)


def test_a_missing_present_hours_count_fails_closed_rather_than_being_invented():
    """``hours_present`` تشخيصٌ لا مقام — ومع ذلك لا يُخترَع.

    وسجلٌّ بلا عدد الساعات الحاضرة يُسقِط الإشارات **كلَّها**، لا الساعيّتَين:
    حارسُ اللادليل يقرأ الحضورَ لا المقامات المخصوصة، فغيابُه يعني «لم يُقَس شيء».
    وهذا هو الاختيار المُغلَق: اختراعُ حضورٍ لم يُقَس يُنتِج إشاراتٍ بنافذةٍ وهميّة.

    (أوّلُ صياغةٍ لهذا الاختبار افترضت إشارةً بحضورٍ صفريّ — والتشغيلُ كذّبها،
    لا المراجعة: الحارسُ يسبق النشر.)
    """
    rec = build_overlay_record("fld", "t", _frost_rows(24, 6))
    assert rec["frost_evaluable_hours"] == 24, "المقامُ المخصوص ما زال في السجلّ"
    rec.pop("hours_evaluated")

    assert build_signal_records("fld", "t", rec) == []
