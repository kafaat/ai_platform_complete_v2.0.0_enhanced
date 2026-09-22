"""WATER-LEDGER-AUTO — منطق التراكم اليوميّ النقيّ (FAO-56) بلا قاعدة.

يثبت: التراكم Dr_t = clamp(Dr_prev + ETc − P_eff − I, 0, TAW)، والافتراضات
المُعلَنة (bootstrap / قصّ قيد سابق شاذّ / ريّ غير مُقاس / سقف TAW)، وسيادة
القيد اليدويّ، ورفض المدخلات الفاسدة.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api.water_balance import _effective_rain
from api.water_ledger_auto import (
    AUTO_CREATED_BY,
    CONFIDENCE_AUTO,
    CONFIDENCE_BOOTSTRAP,
    compute_daily_ledger_entry,
    manual_entry_takes_precedence,
)

#: جذرُ المستودع — تُقرأ منه شيفرةُ المُستدعي (مسارٌ مجمَّد لا يُستورَد هنا).
ROOT = Path(__file__).resolve().parents[3]


def test_daily_accumulation_matches_fao56_identity():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=40.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=6.0,
        kc=1.15,
        rain_mm=2.0,
        irrigation_mm=10.0,
    )
    etc = round(1.15 * 6.0, 2)
    expected = 40.0 + etc - _effective_rain(2.0) - 10.0
    assert entry["etc_mm"] == etc
    assert entry["depletion_mm"] == round(expected, 2)
    assert entry["bootstrap"] is False
    assert entry["confidence"] == CONFIDENCE_AUTO
    assert entry["notes"] == []
    assert entry["decision"] == "auto:daily_balance"


def test_bootstrap_is_declared_with_lower_confidence():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=None,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert entry["bootstrap"] is True
    assert entry["confidence"] == CONFIDENCE_BOOTSTRAP
    assert "bootstrap_assumed_field_capacity" in entry["notes"]
    # اليوم الأوّل من Dr=0: الاستنزاف = ETc فقط.
    assert entry["depletion_mm"] == 5.0


def test_depletion_clamps_at_zero_and_taw_with_declared_flags():
    # ريّ غزير يدفع الحساب تحت الصفر ⇒ يُقصّ إلى 0 (لا استنزاف سالب).
    wet = compute_daily_ledger_entry(
        prev_depletion_mm=10.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=4.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=60.0,
    )
    assert wet["depletion_mm"] == 0.0
    assert wet["deficit_mm"] == 0.0

    # جفاف يتجاوز السعة ⇒ سقف TAW مع علم مُعلَن (إجهاد فوق المتاح لا يُخفى).
    dry = compute_daily_ledger_entry(
        prev_depletion_mm=118.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=8.0,
        kc=1.2,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert dry["depletion_mm"] == 120.0
    assert "depletion_capped_at_taw" in dry["notes"]
    assert dry["deficit_mm"] == 60.0


def test_out_of_range_previous_entry_is_clamped_and_declared():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=500.0,  # قيد يدويّ قديم شاذّ فوق TAW
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=0.0001,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert "previous_depletion_clamped" in entry["notes"]
    assert entry["depletion_mm"] <= 100.0


def test_untracked_irrigation_volume_is_flagged_not_fabricated():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_volume_untracked=True,
    )
    assert "irrigation_volume_untracked" in entry["notes"]
    assert "irrigation_volume_untracked" in entry["decision"]


def test_invalid_inputs_are_rejected_not_guessed():
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(
            prev_depletion_mm=0.0,
            taw_mm=0.0,
            raw_mm=0.0,
            et0_mm=5.0,
            kc=1.0,
            rain_mm=0.0,
            irrigation_mm=0.0,
        )
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(
            prev_depletion_mm=0.0,
            taw_mm=100.0,
            raw_mm=50.0,
            et0_mm=-1.0,
            kc=1.0,
            rain_mm=0.0,
            irrigation_mm=0.0,
        )


def test_manual_entry_precedence():
    assert manual_entry_takes_precedence("haithm") is True
    assert manual_entry_takes_precedence(AUTO_CREATED_BY) is False
    assert manual_entry_takes_precedence(None) is False


def test_worker_kind_is_wired():
    """العامل مُسجَّل في phase_runtime_workers (kind + CLI) — حارس توصيل ساكن."""
    from pathlib import Path

    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text()
    assert "async def run_water_ledger_once" in src
    assert '"water_ledger": run_water_ledger_once' in src
    assert "WATER_LEDGER_AUTO_ENABLED" in src
    assert "manual_entry_takes_precedence" in src
    compose = (Path(__file__).parents[3] / "docker-compose.v9.yml").read_text()
    assert "sahool-water-ledger-worker:" in compose
    assert "- water_ledger" in compose


def test_missing_precipitation_is_a_declared_assumption_not_a_silent_zero():
    """هطول مفقود ⇒ يُفترَض 0mm بعلم مُعلَن precipitation_assumed_zero (لا تعبئة صامتة)."""
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=10.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        rain_assumed_zero=True,
    )
    assert "precipitation_assumed_zero" in entry["notes"]
    assert "precipitation_assumed_zero" in entry["decision"]
    assert entry["effective_rain_mm"] == 0.0


def test_measured_rain_does_not_flag_assumption():
    """هطول مقيس (بما فيه 0 مقيس) ⇒ لا علم افتراض (الافتراضيّ False)."""
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=10.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert "precipitation_assumed_zero" not in entry["notes"]


def test_worker_distinguishes_missing_precip_from_measured_zero():
    """الحارس الساكن: العامل يميّز الهطول المفقود عن 0 المقيس ويمرّر العلم."""
    from pathlib import Path

    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text()
    assert "rain_assumed_zero = _precip is None" in src
    assert "rain_assumed_zero=rain_assumed_zero" in src


# ── `UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01` — الثقةُ تتبع ما افتُرِض ──


def test_untracked_irrigation_volume_does_not_carry_full_confidence():
    """**العطلُ بعينه:** قيدٌ يُقرّ أنّ حجمَ الريّ مجهول ثمّ يُعلِن ثقةَ يومٍ مقيس.

    الملاحظةُ كانت تُكتب في `notes` ولا يسمعها شيء — ومَن يقرأ الصفَّ يرى `0.7`،
    أي الرقمَ نفسَه ليومٍ قِيست مدخلاتُه كلُّها.
    """
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_volume_untracked=True,
    )
    assert "irrigation_volume_untracked" in entry["notes"]
    assert entry["bootstrap"] is False, "المقدّمة: ليست حالةَ bootstrap"
    assert entry["confidence"] == CONFIDENCE_BOOTSTRAP, (
        "يومٌ حدُّ الريّ فيه مفترَضٌ لا مقيس خرج بثقةِ يومٍ مقيسٍ بالكامل"
    )


def test_missing_precipitation_does_not_carry_full_confidence():
    """الهطولُ **المفقود** (لا المقيسُ صفراً) افتراضٌ يُحيّز النتيجة في الاتّجاه نفسِه."""
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        rain_assumed_zero=True,
    )
    assert "precipitation_assumed_zero" in entry["notes"]
    assert entry["confidence"] == CONFIDENCE_BOOTSTRAP


def test_a_measured_dry_day_keeps_full_confidence():
    """**الشاهدُ الإيجابيّ — وبدونه يصير الخفضُ بوّابةً لا تُغلَق بعملٍ صحيح.**

    المُستدعي يفرّق «هطولٌ مقيسٌ = صفر» عن «هطولٌ مفقود» (`_precip is None`). فيومٌ
    جافٌّ **مقيس** بلا ريّ مدخلاتُه كلُّها معلومة، ويجب أن يبقى `CONFIDENCE_AUTO` —
    وإلّا انخفضت ثقةُ أكثر الأيّام بلا سبب وصار الرقمُ بلا معنى.
    """
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert entry["notes"] == []
    assert entry["confidence"] == CONFIDENCE_AUTO


def test_the_two_assumptions_bias_depletion_upward_not_symmetrically():
    """**لماذا الخفضُ مستحقّ:** الافتراضان يرفعان الاستنزاف، فيدفعان نحو ريٍّ زائد.

    حيازةٌ في اتّجاهٍ معروف لا ضجيجٌ متماثل — ولذلك لا يكفي أن تُكتَب ملاحظةٌ نصّيّة.
    """
    base = dict(prev_depletion_mm=30.0, taw_mm=200.0, raw_mm=100.0, et0_mm=5.0, kc=1.0, rain_mm=8.0)
    truthful = compute_daily_ledger_entry(**base, irrigation_mm=12.0)
    untracked = compute_daily_ledger_entry(
        **base, irrigation_mm=0.0, irrigation_volume_untracked=True
    )
    assert untracked["depletion_mm"] > truthful["depletion_mm"], (
        "ريٌّ غيرُ مُقاسٍ يجب أن يُنتِج استنزافاً أعلى — وهو اتّجاه الضرر"
    )
    dry = compute_daily_ledger_entry(**{**base, "rain_mm": 0.0}, irrigation_mm=12.0)
    assert dry["depletion_mm"] > truthful["depletion_mm"]


def test_confidence_is_derived_from_the_notes_not_from_a_second_list():
    """قائمتان تنحرفان: علَمٌ يُضاف إلى `notes` ولا يُحدَّث معه شرطُ الثقة يبيت صامتاً."""
    import inspect

    from api import water_ledger_auto as mod

    source = inspect.getsource(mod.compute_daily_ledger_entry)
    assert "_BIASING_ASSUMPTIONS.intersection(notes)" in source, (
        "الثقةُ لا تُشتقّ من `notes` — فأيُّ علَمٍ جديدٍ لن يُخفّضها"
    )
    assert mod._BIASING_ASSUMPTIONS <= {
        "irrigation_volume_untracked",
        "precipitation_assumed_zero",
        "irrigation_unobserved",
    }, "علَمٌ في المجموعة لا تُصدِره الدالّة — حراسةٌ على لا شيء"


# ── `irrigation_unobserved`: «لم يُرصَد سجلٌّ» ≠ «لم يُروَ» ──────────────────────


def test_no_irrigation_row_is_unobserved_not_a_measured_zero():
    """**العطلُ الأصليّ:** صفرُ صفوفٍ كان يدخل الميزانَ ريّاً مقداره صفرٌ مقيس.

    والصادقُ «لم يُرصَد له سجلُّ ريّ» — صحيحةٌ للحقل المطريّ وللمرويّ من بئرٍ بلا
    تسجيل معاً. فلا يُخترَع تمييزٌ لا تسنده البيانات، ولا يُدَّعى قياسٌ لم يقع.
    """
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_unobserved=True,
    )
    assert "irrigation_unobserved" in entry["notes"]
    assert entry["confidence"] == CONFIDENCE_BOOTSTRAP


def test_the_ledger_is_still_written_for_an_unobserved_day():
    """**لا يُحرَم الحقلُ المطريُّ الصادقُ من ميزانه** — إلغاءُ اليوم عطلٌ معاكسُ الاتّجاه.

    القيدُ يبقى **أدنى تقديرٍ للماء المضاف**: يُحسَب ويُكتَب، وتُخفَّض ثقتُه فقط.
    """
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_unobserved=True,
    )
    assert entry["depletion_mm"] == 35.0, "حسابُ اليوم أُلغي بدل أن تُخفَّض ثقتُه"
    assert entry["etc_mm"] == 5.0


def test_unobserved_and_untracked_are_distinct_claims():
    """**العلَمان يقولان شيئين مختلفين، ودمجُهما يُفقِد التشخيص.**

    `untracked` = صفٌّ **موجود** بحجمٍ غائب (رُصد ريٌّ، جُهِل مقدارُه).
    `unobserved` = **لا صفَّ أصلاً** (لم يُرصَد شيء). شرطُ الأوّل
    `COUNT(*) FILTER (WHERE volume_mm IS NULL)` لا يتحقّق أبداً بلا صفّ — ولهذا
    بالذات لم يكن العطلُ مغطّى.
    """
    untracked = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_volume_untracked=True,
    )
    unobserved = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_unobserved=True,
    )
    assert untracked["notes"] == ["irrigation_volume_untracked"]
    assert unobserved["notes"] == ["irrigation_unobserved"]
    assert untracked["decision"] != unobserved["decision"], (
        "القراران متطابقان — فُقِد التمييزُ بين «سجلٌّ بلا حجم» و«لا سجلَّ أصلاً»"
    )


def test_a_measured_irrigation_run_keeps_full_confidence():
    """**الشاهدُ الإيجابيّ:** يومٌ له صفُّ ريٍّ بحجمٍ مقيس يبقى `CONFIDENCE_AUTO`.

    بدونه يصير كلُّ يومٍ منخفضَ الثقة، فيفقد الرقمُ معناه — وهي «بوّابةٌ لا تُغلَق
    بعملٍ صحيح».
    """
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=12.0,
    )
    assert entry["notes"] == []
    assert entry["confidence"] == CONFIDENCE_AUTO


def test_the_worker_derives_unobserved_from_a_row_count_not_from_the_sum():
    """`SUM(volume_mm)=0` يقع أيضاً على صفوفٍ حجمُها صفرٌ مقيس — فلا يصلح شرطاً.

    الشرطُ الصحيح `COUNT(*)`؛ ويُقرأ من المصدر لأنّ المُستدعي في مسارٍ مجمَّد.
    """
    source = (ROOT / "services/sahool-platform/api/phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    assert "COUNT(*) AS runs" in source, "العدّادُ غائبٌ عن الاستعلام"
    assert 'irrigation_unobserved=not int(irr["runs"] or 0)' in source, (
        "العلَمُ لا يُشتقّ من عدد الصفوف"
    )


# ─── D07/D08 من التدقيق الموحَّد (2026-09-22) ─────────────────────────────────


def _ok(**kw):
    base = dict(
        prev_depletion_mm=10.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=2.0,
        irrigation_mm=0.0,
    )
    base.update(kw)
    return base


@pytest.mark.parametrize("rain", [0, 1, 10, 50, 74.99, 75, 100, 150, 249.99, 250, 250.01, 500])
def test_effective_rain_never_exceeds_the_rain_that_fell(rain):
    """D07 — **ماءٌ من العدم.** الفعّالُ لا يتجاوز المدخلَ في أيّ نقطة.

    كان الحدُّ `75` والثابتُ `92.5`، وكلاهما محرَّفٌ عن USDA-SCS. فـ`75` مم تُرجِع
    **`100`** مم «فعّالة»، و`100` تُرجِع `102.5`. والمطرُ الفعّال يُطرَح من الاحتياج،
    فمُبالَغُه يُنقِص الاستنزافَ ⇒ **ريٌّ دون الحاجة**.
    """
    assert _effective_rain(rain) <= rain + 1e-9, f"مطرٌ فعّالٌ يتجاوز المدخل عند {rain}"


def test_effective_rain_is_continuous_at_the_scs_breakpoint():
    """والقفزةُ زالت لأنّ الحدَّ صار حيث تتّصل الصيغةُ بالبناء لا حيث اتُّفِق.

    كانت القفزةُ عند `75` تساوي **٣٤.٠١ مم**. وعند `250` يُعطي الفرعان `150.0`
    كلاهما — فالاتّصالُ خاصّيّةُ الصيغة. ولم يُقَصَّ الناتجُ عند المدخل: القصُّ
    كان سيُخفي الفرعَ المحرَّفَ ويُبقي القفزةَ تحت غطاء.
    """
    left = _effective_rain(249.999999)
    right = _effective_rain(250.000001)
    assert abs(right - left) < 1e-4, f"قفزةٌ عند الحدّ: {abs(right - left)}"
    assert _effective_rain(250) == pytest.approx(150.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["taw_mm", "et0_mm", "kc", "rain_mm", "irrigation_mm", "raw_mm"])
def test_a_non_finite_input_is_rejected_not_turned_into_a_plausible_number(field, bad):
    """D08 — كلُّ مقارنةٍ مع `NaN` تُرجِع `False`، فكان يمرّ من كلّ الحُرّاس.

    المقيس: `et0_mm=NaN` أنتج نواتجَ `NaN` **بثقة 0.7**، و`Infinity` أنتج `ETc`
    غيرَ منتهٍ ثمّ قُصَّ الاستنزافُ عند `TAW` — برقم الثقة نفسِه. فالحالةُ غيرُ
    المعرَّفةِ كانت تُحوَّل إلى قيمةٍ **تبدو صحيحة**.
    """
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(**_ok(**{field: bad}))


def test_a_boolean_is_not_accepted_where_a_measurement_is_required():
    """و`True` عددٌ في بايثون، فـ`kc=True` كان يُحسَب `ETc = et0 × 1` صامتاً."""
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(**_ok(kc=True))


def test_raw_above_taw_is_rejected_as_an_inverted_capacity_relation():
    """RAW جزءٌ من TAW بالتعريف؛ انقلابُهما يجعل عتبةَ الريّ فوق السعة كلّها."""
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(**_ok(raw_mm=120.0, taw_mm=100.0))


def test_a_sound_day_still_computes_after_the_new_guards():
    """والاتّجاه الآخر: يومٌ سليمٌ يمرّ — وإلّا كان العلاجُ تعطيلَ الدفتر."""
    out = compute_daily_ledger_entry(**_ok())
    assert out["confidence"] == CONFIDENCE_AUTO
    assert out["etc_mm"] == pytest.approx(5.0)
