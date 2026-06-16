"""اختبارات api/crop_introduction.py (offline) — بطاقات إدخال المحاصيل + الفحص الكمّي.

نواة نقيّة بلا قاعدة/شبكة/ملفّات: نتحقّق من حلّ الأسماء والمرادفات (`_resolve`)،
قوائم المرشّحين حسب المنطقة (`list_candidates`)، البطاقة الكاملة (`crop_card`)
بما فيها وسم المنطقة الملائمة، وربط الفحص الكمّي بمحرّك الملاءمة
(`check_field_fit` ↔ `crop_suitability.score_crop`): محصول بلا نطاقات تحمّل
(تفاح المرتفعات) → scored=False، ومحصول مجهول → supported=False، والملوحة
الحاسمة تسقط الدرجة. القيم مشتقّة حرفيّاً من الكود (لا افتراض).
"""

import pytest
from api.crop_introduction import (
    _ALIASES,
    _CARDS,
    _INTRO_TOLERANCE,
    ClimateZone,
    _resolve,
    check_field_fit,
    crop_card,
    list_candidates,
)

pytestmark = pytest.mark.unit


# ─── _resolve: حلّ المفاتيح والمرادفات ────────────────────────────────────


def test_resolve_direct_key():
    assert _resolve("mango") == "mango"
    assert _resolve("date_palm") == "date_palm"


def test_resolve_is_case_insensitive_for_keys():
    # مفتاح الكروت يُطابَق بـ.lower() ⇒ الأحرف الكبيرة تُحلّ.
    assert _resolve("MANGO") == "mango"
    assert _resolve("Citrus") == "citrus"


def test_resolve_strips_whitespace():
    assert _resolve("  mango  ") == "mango"


def test_resolve_arabic_alias():
    assert _resolve("مانجو") == "mango"
    assert _resolve("برتقال") == "citrus"
    assert _resolve("ليمون") == "citrus"
    assert _resolve("زيتون") == "olive"
    assert _resolve("نخيل") == "date_palm"


def test_resolve_unknown_returns_none():
    assert _resolve("زعفران") is None
    assert _resolve("dragonfruit") is None


def test_resolve_empty_returns_none():
    assert _resolve("") is None
    assert _resolve("   ") is None


def test_every_alias_points_to_existing_card():
    for ar, key in _ALIASES.items():
        assert key in _CARDS, f"المرادف «{ar}» يشير لمفتاح مفقود {key}"


# ─── list_candidates: التصفية حسب المنطقة ─────────────────────────────────


def test_list_all_candidates_returns_every_card():
    res = list_candidates()
    assert res["zone_query"] == "all"
    assert len(res["candidates"]) == len(_CARDS)
    # كلّ عنصر يحمل الحقول المتوقّعة فقط (zone قيمة سلسلة، لا Enum).
    first = res["candidates"][0]
    assert set(first) == {"crop", "name_ar", "type_ar", "zone", "product_ar"}
    assert isinstance(first["zone"], str)


def test_list_tihama_excludes_highland_and_jawf_only():
    res = list_candidates("tihama")
    zones = {c["zone"] for c in res["candidates"]}
    # تهامة تقبل TIHAMA و BOTH فقط — لا HIGHLAND ولا JAWF.
    assert ClimateZone.HIGHLAND.value not in zones
    assert ClimateZone.JAWF.value not in zones
    assert zones <= {ClimateZone.TIHAMA.value, ClimateZone.BOTH.value}
    crops = {c["crop"] for c in res["candidates"]}
    assert "mango" in crops  # tihama
    assert "okra" in crops  # both
    assert "citrus" not in crops  # jawf
    assert "apple_highland" not in crops  # highland


def test_list_tihama_arabic_query_same_as_english():
    assert list_candidates("تهامة")["candidates"] == list_candidates("tihama")["candidates"]


def test_list_jawf_includes_jawf_and_both_only():
    res = list_candidates("jawf")
    zones = {c["zone"] for c in res["candidates"]}
    assert zones <= {ClimateZone.JAWF.value, ClimateZone.BOTH.value}
    crops = {c["crop"] for c in res["candidates"]}
    assert "citrus" in crops  # jawf
    assert "okra" in crops  # both
    assert "mango" not in crops  # tihama excluded
    assert "apple_highland" not in crops  # highland excluded


def test_list_highland_returns_only_highland_cards():
    res = list_candidates("المرتفعات")
    crops = {c["crop"] for c in res["candidates"]}
    # المرتفعات الباردة فقط: التفاح والبنّ.
    assert crops == {"apple_highland", "coffee_lowland_inspo"}
    for c in res["candidates"]:
        assert c["zone"] == ClimateZone.HIGHLAND.value


def test_list_unknown_zone_falls_through_to_all():
    # منطقة غير معروفة لا تطابق أيّ فرع تصفية ⇒ تُرجِع كلّ الكروت.
    res = list_candidates("atlantis")
    assert len(res["candidates"]) == len(_CARDS)
    assert res["zone_query"] == "atlantis"


# ─── crop_card: البطاقة الكاملة ───────────────────────────────────────────


def test_crop_card_unknown_is_unsupported_with_listing():
    res = crop_card("زعفران")
    assert res["supported"] is False
    assert "زعفران" in res["message_ar"]
    # يُدرَج اسم عربي معروف ضمن المتاح.
    assert "المانجو" in res["message_ar"]


def test_crop_card_mango_full_shape():
    res = crop_card("mango")
    assert res["supported"] is True
    assert res["crop"] == "mango"
    assert res["name_ar"] == "المانجو"
    assert res["suitable_zone_ar"] == "تهامة"
    assert set(res["requirements_ar"]) == {"climate", "water", "soil"}
    assert res["requirements_ar"]["climate"] == _CARDS["mango"]["climate_ar"]
    assert res["disclaimer_ar"]  # تنبيه صدق دائم الحضور


def test_crop_card_via_arabic_alias():
    res = crop_card("مانجو")
    assert res["supported"] is True
    assert res["crop"] == "mango"


def test_crop_card_zone_labels_match_climatezone():
    # كل قيمة zone تُترجَم لوسم عربي محدّد.
    assert crop_card("citrus")["suitable_zone_ar"] == "الجوف"
    assert (
        crop_card("apple_highland")["suitable_zone_ar"] == "المرتفعات الباردة فقط (لا الجوف/تهامة)"
    )
    assert crop_card("okra")["suitable_zone_ar"] == "تهامة والجوف (حسب الصنف/الارتفاع)"


# ─── check_field_fit: الربط بمحرّك الملاءمة ───────────────────────────────


def test_check_field_fit_unknown_crop_unsupported():
    res = check_field_fit("زعفران", ph=7.0, ec_dsm=2.0)
    assert res["supported"] is False
    assert "زعفران" in res["message_ar"]


def test_check_field_fit_card_without_tolerance_is_not_scored():
    # التفاح له بطاقة لكن لا نطاقات تحمّل كمّيّة ⇒ supported لكن scored=False.
    res = check_field_fit("apple_highland", ph=6.5, ec_dsm=1.0)
    assert res["supported"] is True
    assert res["scored"] is False
    assert res["crop_ar"] == _CARDS["apple_highland"]["name_ar"]
    assert "apple_highland" not in _INTRO_TOLERANCE


def test_check_field_fit_ideal_mango_scores_excellent():
    # mango: ph_opt(5.5,7.5) ec_max 3.0 temp(24,38). داخل الكلّ + مرويّ
    # ⇒ كل المعايير 1.0 ⇒ score 1.0 ⇒ "ممتاز".
    res = check_field_fit("mango", ph=6.5, ec_dsm=1.0, temp_mean_c=30.0, irrigated=True)
    assert res["supported"] is True
    assert res["scored"] is True
    assert res["score"] == 1.0
    assert res["rating_ar"] == "ممتاز"
    # تُلحَق حقول البطاقة العربيّة بالنتيجة الكمّيّة.
    assert res["yemen_fit_ar"] == _CARDS["mango"]["yemen_fit_ar"]
    assert res["caution_ar"] == _CARDS["mango"]["caution_ar"]
    assert res["disclaimer_ar"]


def test_check_field_fit_high_salinity_hard_fails():
    # ملوحة 5.0 > ec_max المانجو 3.0 ⇒ ec_s=0 ⇒ hard_fail ⇒ score=min(.,0.35).
    res = check_field_fit("mango", ph=6.5, ec_dsm=5.0, temp_mean_c=30.0, irrigated=True)
    assert res["scored"] is True
    assert res["score"] == pytest.approx(0.35)
    assert res["rating_ar"] == "غير مناسب"


def test_check_field_fit_rainfed_below_min_lowers_score():
    # غير مرويّ ومطر دون الحدّ الأدنى للمانجو (600) ⇒ rain_s<1 ⇒ score<1.
    res = check_field_fit(
        "mango", ph=6.5, ec_dsm=1.0, season_rain_mm=100.0, temp_mean_c=30.0, irrigated=False
    )
    assert res["scored"] is True
    assert res["score"] < 1.0


def test_check_field_fit_uses_card_tolerance_values():
    # date_palm يتحمّل ملوحة عالية (ec_max 12.0): ملوحة 5.0 لا تُسقطه.
    res = check_field_fit("date_palm", ph=8.0, ec_dsm=5.0, temp_mean_c=30.0, irrigated=True)
    assert res["scored"] is True
    assert res["rating_ar"] != "غير مناسب"
    assert res["score"] > 0.5


def test_intro_tolerance_keys_are_subset_of_cards():
    # كل محصول له نطاقات تحمّل لا بدّ أن يملك بطاقة.
    for key in _INTRO_TOLERANCE:
        assert key in _CARDS, f"نطاق تحمّل بلا بطاقة: {key}"
