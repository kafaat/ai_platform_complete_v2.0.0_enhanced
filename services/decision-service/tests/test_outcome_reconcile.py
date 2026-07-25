"""مُصالِح النتائج (P1-13a) — اختبار وحدة نقيّ (بلا قاعدة).

يؤكّد: فكّ العدّ المزدوج (unique_decisions) · نسبة النجاح فوق القابل للحسم فقط · دلو unknown
لغير المحسوم (لا اختلاق) · اشتقاق النجاح من إشارات مختلفة (success منطقيّ / outcome نصّيّ / غلّة).
"""

from outcome_reconcile import reconcile_outcomes


def test_success_rate_only_over_evaluable_rows():
    orows = [
        {"decision_id": "d1", "success": True},
        {"decision_id": "d2", "success": False},
        {"decision_id": "d3", "success": None},  # غير محسوم ⇒ unknown، لا يدخل النسبة
    ]
    out = reconcile_outcomes(orows, [])
    assert out["sample_count"] == 3
    assert out["evaluated_count"] == 2
    assert out["success_count"] == 1
    assert out["success_rate"] == 0.5  # 1 من 2 المحسومَين، لا 1 من 3
    assert out["by_source"]["outcome_record"]["unknown"] == 1


def test_unique_decisions_unmasks_double_count():
    # نفس القرار d1 موصوف في الجدولَين ⇒ sample_count=2 لكن unique_decisions=1.
    orows = [{"decision_id": "d1", "success": True}]
    rrows = [{"decision_id": "d1", "outcome": "success"}]
    out = reconcile_outcomes(orows, rrows)
    assert out["sample_count"] == 2
    assert out["unique_decisions"] == 1


def test_by_kind_dedups_shared_decision_id():
    # B3: قرارٌ موصوفٌ في الجدولَين لا يُحسَب مرّتَين في by_kind/النسبة المنشورة —
    # يُدمَج بمفتاح decision_id (أولويّة outcome_record). صفوف بلا مفتاح تُعدّ منفردةً.
    orows = [{"decision_id": "d1", "success": True}]
    rrows = [
        {"decision_id": "d1", "outcome": "success"},
        {"outcome": "failed"},
    ]  # d1 مكرَّر + keyless
    out = reconcile_outcomes(orows, rrows)
    assert out["by_kind"] == {"success": 1, "failure": 1, "unknown": 0}  # d1 مرّة، keyless مرّة
    assert out["evaluated_count"] == 2
    assert out["success_rate"] == 0.5  # ليست 0.667 (لا عدّ مزدوج لـd1)


def test_recommendation_success_from_text_and_yield():
    rrows = [
        {"decision_id": "d1", "outcome": "success"},  # نصّ
        {"decision_id": "d2", "outcome": "failed"},
        {"decision_id": "d3", "actual_yield_t_ha": 6.0, "predicted_yield_t_ha": 5.0},  # بلغ ⇒ نجاح
        {"decision_id": "d4", "actual_yield_t_ha": 3.0, "predicted_yield_t_ha": 5.0},  # دون ⇒ فشل
        {"decision_id": "d5", "accepted": True},  # قبول وحده ليس نتيجة ⇒ unknown
    ]
    out = reconcile_outcomes([], rrows)
    b = out["by_source"]["recommendation_outcomes"]
    assert b["success"] == 2 and b["failure"] == 2 and b["unknown"] == 1


def test_empty_is_honest_none_rate():
    out = reconcile_outcomes([], [])
    assert out["sample_count"] == 0
    assert out["success_rate"] is None
    assert out["by_kind"] == {"success": 0, "failure": 0, "unknown": 0}


def test_by_kind_totals_match():
    orows = [{"decision_id": "d1", "success": True}, {"decision_id": "d2", "success": False}]
    rrows = [{"decision_id": "d3", "outcome": "success"}, {"decision_id": "d4"}]
    out = reconcile_outcomes(orows, rrows)
    k = out["by_kind"]
    assert k["success"] + k["failure"] + k["unknown"] == out["sample_count"]
    assert k["success"] == 2 and k["failure"] == 1 and k["unknown"] == 1
