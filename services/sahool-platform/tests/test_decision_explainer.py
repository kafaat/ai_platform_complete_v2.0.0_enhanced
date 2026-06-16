"""اختبارات طبقة تفسير القرار (api.decision_explainer) — دوالّ نقيّة offline.

يتحقّق من بناء طلب Claude (`build_explanation_prompt`)، والشرح البديل offline
(`offline_explanation`)، والمُجمِّع (`explain_decision`): البنية، كلّ فرع شرطي،
وحالات الحوافّ (مدخلات فارغة/None، غياب الدعم، حقن RAG، اختيار مصدر الشرح).
كلّها بلا قاعدة بيانات/شبكة.
"""

import pytest
from api.decision_explainer import (
    _EXPLAINER_MODEL,
    _MAX_TOKENS,
    build_explanation_prompt,
    explain_decision,
    offline_explanation,
)

pytestmark = pytest.mark.unit


def _rich_decision():
    """قرار مدعوم غنيّ بكلّ الحقول الاختياريّة لتغطية كلّ فروع البناء."""
    return {
        "supported": True,
        "location_ar": {
            "governorate_ar": "الجوف",
            "input_ar": "الجوف",
            "zone_name_ar": "السهل الشرقي",
        },
        "suited_crops_ar": ["قمح", "شعير", "ذرة", "سمسم", "دخن", "بصل"],
        "avoid_ar": ["تفاح", "كرز", "خوخ", "كمثرى", "موز"],
        "water_strategy_ar": "ريّ بالتنقيط",
        "actual_climate_data_ar": {
            "annual_rainfall_mm": 120,
            "heat_stress_days_per_year": 45,
        },
        "salinity_alert_ar": "تنبيه ملوحة مرتفعة",
        "alkalinity_alert_ar": "تنبيه قلويّة",
        "chill_hours_ar": {"verdict_ar": "غير كافية للأشجار", "estimated": 0},
        "high_value_opportunities_ar": {"top_3_ar": ["زعفران", "رمّان", "عنب"]},
        "decision_summary_ar": "أرضك ملائمة للحبوب مع إدارة الماء.",
        "rainfed_possible": False,
    }


# ─── build_explanation_prompt ────────────────────────────────────────────


def test_prompt_top_level_structure_and_pinned_model():
    p = build_explanation_prompt(_rich_decision())
    assert p["model"] == _EXPLAINER_MODEL
    assert p["max_tokens"] == _MAX_TOKENS
    assert p["temperature"] == 0  # حتميّة لإعادة الإنتاج
    assert isinstance(p["system"], str) and p["system"]
    assert p["messages"] == [{"role": "user", "content": p["messages"][0]["content"]}]
    assert p["messages"][0]["role"] == "user"


def test_prompt_meta_marks_rule_based_source():
    meta = build_explanation_prompt(_rich_decision())["_meta"]
    assert meta["purpose"] == "decision_explanation"
    assert meta["rule_based_source"] is True
    assert meta["model_version"] == _EXPLAINER_MODEL


def test_prompt_system_forbids_invention():
    system = build_explanation_prompt(_rich_decision())["system"]
    # تعليمات صارمة: شرح فقط دون اختراع محاصيل/أرقام.
    assert "لا تضف محاصيل" in system
    assert "لا تخترع" in system


def test_prompt_facts_include_all_rich_fields():
    content = build_explanation_prompt(_rich_decision())["messages"][0]["content"]
    assert "الجوف" in content
    assert "السهل الشرقي" in content
    # محاصيل ملائمة مقصوصة لخمسة فقط.
    assert "قمح، شعير، ذرة، سمسم، دخن" in content
    assert "بصل" not in content.split("يُتجنّب")[0]  # السادس مُستبعَد
    # يُتجنّب مقصوص لأربعة.
    assert "تفاح، كرز، خوخ، كمثرى" in content
    assert "ريّ بالتنقيط" in content
    assert "120" in content and "45" in content
    assert "تنبيه ملوحة مرتفعة" in content
    assert "تنبيه قلويّة" in content
    assert "غير كافية للأشجار" in content
    assert "زعفران، رمّان، عنب" in content
    assert "أرضك ملائمة للحبوب" in content


def test_prompt_empty_decision_yields_empty_facts_block():
    # قرار فارغ: لا حقائق، لكن البنية الموجَّهة كاملة.
    p = build_explanation_prompt({})
    content = p["messages"][0]["content"]
    assert "إليك تحليل حقل المزارع" in content
    assert "اشرح له هذا بإيجاز" in content
    # لا أسطر حقائق (لا شرطة قائمة قبل كتلة RAG الفارغة).
    assert "- الموقع:" not in content


def test_prompt_location_falls_back_to_input_when_no_governorate():
    decision = {"location_ar": {"input_ar": "صنعاء", "zone_name_ar": "المرتفعات"}}
    content = build_explanation_prompt(decision)["messages"][0]["content"]
    assert "صنعاء" in content
    assert "المرتفعات" in content


def test_prompt_rag_context_injected_when_present():
    content = build_explanation_prompt(_rich_decision(), rag_context="  مرجع موثّق من الجوف  ")[
        "messages"
    ][0]["content"]
    assert "مراجع محلّيّة موثّقة" in content
    assert "مرجع موثّق من الجوف" in content  # مُشذّب (strip)


def test_prompt_rag_block_absent_when_none_or_blank():
    base = build_explanation_prompt(_rich_decision())["messages"][0]["content"]
    blank = build_explanation_prompt(_rich_decision(), rag_context="   ")["messages"][0]["content"]
    assert "مراجع محلّيّة موثّقة" not in base
    assert "مراجع محلّيّة موثّقة" not in blank


def test_prompt_high_value_with_empty_top3_omits_line():
    decision = {"high_value_opportunities_ar": {"top_3_ar": []}}
    content = build_explanation_prompt(decision)["messages"][0]["content"]
    assert "فرص عالية القيمة" not in content


# ─── offline_explanation ─────────────────────────────────────────────────


def test_offline_unsupported_returns_needs_clarification():
    decision = {"supported": False, "needs_clarification_ar": "وضّح الإحداثيّات"}
    assert offline_explanation(decision) == "وضّح الإحداثيّات"


def test_offline_unsupported_falls_back_to_message_then_default():
    # لا توضيح لكن رسالة موجودة.
    assert offline_explanation({"supported": False, "message_ar": "رسالة"}) == "رسالة"
    # لا توضيح ولا رسالة → النصّ الافتراضي.
    default = offline_explanation({"supported": False})
    assert "تعذّر تحليل الموقع" in default


def test_offline_supported_full_text_covers_all_branches():
    text = offline_explanation(_rich_decision())
    assert "حقلك في الجوف يقع ضمن «السهل الشرقي»." in text
    # محاصيل مقصوصة لأربعة.
    assert "الأنسب لمناخك: قمح، شعير، ذرة، سمسم." in text
    # rainfed_possible=False → جملة الريّ.
    assert "الأمطار لا تكفي" in text
    assert "انتبه للملوحة" in text
    # chill estimated==0 → جملة تجنّب أشجار البرودة.
    assert "تجنّب الأشجار المحتاجة لبرودة شتويّة" in text
    assert "أرضك ملائمة للحبوب مع إدارة الماء." in text
    # تذييل ثابت دائماً.
    assert "القرار النهائي لك" in text


def test_offline_rainfed_true_omits_irrigation_line():
    decision = {"supported": True, "rainfed_possible": True, "suited_crops_ar": ["قمح"]}
    text = offline_explanation(decision)
    assert "الأمطار لا تكفي" not in text


def test_offline_rainfed_defaults_true_when_key_absent():
    # المفتاح غائب → الافتراضي True → لا جملة ريّ.
    text = offline_explanation({"supported": True, "suited_crops_ar": ["قمح"]})
    assert "الأمطار لا تكفي" not in text


def test_offline_chill_nonzero_omits_avoid_chill_line():
    decision = {
        "supported": True,
        "chill_hours_ar": {"estimated": 400},
        "suited_crops_ar": ["تفاح"],
    }
    text = offline_explanation(decision)
    assert "تجنّب الأشجار المحتاجة لبرودة شتويّة" not in text


def test_offline_minimal_supported_only_footer():
    # مدعوم بلا أيّ تفاصيل → التذييل الثابت فقط.
    text = offline_explanation({"supported": True})
    assert text.startswith("القرار النهائي لك")


# ─── explain_decision ────────────────────────────────────────────────────


def test_explain_uses_ai_text_when_present():
    out = explain_decision(_rich_decision(), ai_response_text="  شرح من كلود  ")
    assert out["explanation_ar"] == "شرح من كلود"  # مُشذّب
    assert out["explanation_source"] == "ai"
    assert out["supported"] is True
    assert out["prompt_for_server"] is None  # لا حاجة للطلب حين توفّر الشرح
    assert "الذكاء الاصطناعي (Claude)" in out["note_ar"]
    assert "يشرح ولا يقرّر" in out["disclaimer_ar"]


def test_explain_falls_back_to_offline_when_ai_blank():
    decision = _rich_decision()
    out = explain_decision(decision, ai_response_text="   ")
    assert out["explanation_source"] == "rule_based_offline"
    # نفس نصّ الشرح offline.
    assert out["explanation_ar"] == offline_explanation(decision)
    # حين لا AI → يُرفَق طلب الخادم لاستدعاء لاحق.
    assert out["prompt_for_server"] is not None
    assert out["prompt_for_server"]["model"] == _EXPLAINER_MODEL


def test_explain_none_ai_uses_offline():
    out = explain_decision(_rich_decision(), ai_response_text=None)
    assert out["explanation_source"] == "rule_based_offline"
    assert out["prompt_for_server"] is not None


def test_explain_rag_used_flag_reflects_context():
    yes = explain_decision(_rich_decision(), rag_context="مرجع")
    no = explain_decision(_rich_decision(), rag_context="  ")
    none = explain_decision(_rich_decision())
    assert yes["rag_used"] is True
    assert no["rag_used"] is False
    assert none["rag_used"] is False


def test_explain_supported_defaults_false_when_absent():
    out = explain_decision({}, ai_response_text="نصّ")
    assert out["supported"] is False
