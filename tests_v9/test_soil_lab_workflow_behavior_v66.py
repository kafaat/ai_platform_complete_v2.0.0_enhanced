"""اختبارات سلوكيّة لآلة حالة فحص التربة (offline) — حالات حدّيّة مكمّلة.

تكمّل services/sahool-platform/tests/test_soil_lab_workflow.py دون تكرار:
تركّز على _coerce (str/Enum)، كلّ الانتقالات غير المسموحة، إلغاء كلّ مرحلة،
نهائيّة rejected-as-source، عدم اشتراط النتيجة للإلغاء/أخذ العيّنة، رمز HTTP،
وتطابق خريطة الانتقالات مع القيم المتوقّعة (لا قفز خلفيّ).
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from core.engines.soil_lab_workflow import (  # noqa: E402, I001
    SOIL_TEST_TRANSITIONS,
    SoilTestStatus,
    SoilWorkflowError,
    _coerce,
    validate_soil_transition,
)


# ---------------------------------------------------------------------------
# _coerce — يقبل str و Enum، ويرفض المجهول.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", list(SoilTestStatus))
def test_coerce_accepts_enum_members(value):
    assert _coerce(value) is value


@pytest.mark.parametrize("value", [s.value for s in SoilTestStatus])
def test_coerce_accepts_string_values(value):
    coerced = _coerce(value)
    assert isinstance(coerced, SoilTestStatus)
    assert coerced.value == value


def test_coerce_rejects_unknown_string():
    with pytest.raises(SoilWorkflowError) as e:
        _coerce("frozen")
    assert "مجهولة" in e.value.message_ar
    assert e.value.http_status == 422


def test_coerce_rejects_uppercase_name_not_value():
    # القيم بحروف صغيرة؛ اسم العضو "REQUESTED" ليس قيمة صالحة.
    with pytest.raises(SoilWorkflowError):
        _coerce("REQUESTED")


# ---------------------------------------------------------------------------
# validate_soil_transition يقبل خلط str/Enum بحرّيّة.
# ---------------------------------------------------------------------------


def test_validate_accepts_mixed_enum_and_str_args():
    assert validate_soil_transition(SoilTestStatus.REQUESTED, "sampled") is True
    assert validate_soil_transition("requested", SoilTestStatus.SAMPLED) is True
    assert validate_soil_transition(SoilTestStatus.REQUESTED, SoilTestStatus.SAMPLED) is True


# ---------------------------------------------------------------------------
# الانتقالات غير المسموحة — مسح شامل لكلّ زوج (cur, tgt) غير مُدرَج.
# ---------------------------------------------------------------------------


def _all_invalid_pairs():
    for cur in SoilTestStatus:
        for tgt in SoilTestStatus:
            if cur == tgt:
                continue  # لا-عمل، يُعالَج منفصلاً
            if tgt not in SOIL_TEST_TRANSITIONS[cur]:
                yield cur, tgt


@pytest.mark.parametrize("cur,tgt", list(_all_invalid_pairs()))
def test_every_disallowed_transition_raises(cur, tgt):
    with pytest.raises(SoilWorkflowError) as e:
        # has_result=True لعزل سبب الفشل: الانتقال نفسه، لا invariant النتيجة.
        validate_soil_transition(cur, tgt, has_result=True)
    assert e.value.http_status == 422
    assert "غير مسموح" in e.value.message_ar


# ---------------------------------------------------------------------------
# الانتقالات المسموحة — مسح شامل لكلّ زوج مُدرَج (مع توفير النتيجة عند اللزوم).
# ---------------------------------------------------------------------------


def _all_valid_pairs():
    for cur, targets in SOIL_TEST_TRANSITIONS.items():
        for tgt in targets:
            yield cur, tgt


@pytest.mark.parametrize("cur,tgt", list(_all_valid_pairs()))
def test_every_allowed_transition_returns_true(cur, tgt):
    assert validate_soil_transition(cur, tgt, has_result=True) is True


# ---------------------------------------------------------------------------
# الإلغاء متاح من كلّ مرحلة غير نهائيّة قبل النتيجة (بلا اشتراط نتيجة).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current",
    ["requested", "sampled", "in_lab", "rejected"],
)
def test_cancel_available_without_result(current):
    # cancelled ليست ضمن _REQUIRES_RESULT → لا تشترط has_result.
    assert validate_soil_transition(current, "cancelled", has_result=False) is True


def test_approved_cannot_cancel():
    # بعد الاعتماد لا يُلغى (المسار الوحيد: published).
    with pytest.raises(SoilWorkflowError):
        validate_soil_transition("approved", "cancelled", has_result=True)


def test_result_received_cannot_cancel():
    with pytest.raises(SoilWorkflowError):
        validate_soil_transition("result_received", "cancelled", has_result=True)


# ---------------------------------------------------------------------------
# invariant النتيجة — لا يُطبَّق على المراحل المبكّرة.
# ---------------------------------------------------------------------------


def test_early_transitions_do_not_require_result():
    # sampled/in_lab خارج _REQUIRES_RESULT → has_result=False مقبول.
    assert validate_soil_transition("requested", "sampled", has_result=False) is True
    assert validate_soil_transition("sampled", "in_lab", has_result=False) is True


def test_publish_requires_result_even_from_approved():
    # PUBLISHED ضمن _REQUIRES_RESULT.
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition("approved", "published", has_result=False)
    assert "نتيجة" in e.value.message_ar


# ---------------------------------------------------------------------------
# دورة إعادة الفحص — rejected → in_lab يعيد الدخول للمختبر.
# ---------------------------------------------------------------------------


def test_reject_then_retest_then_result_cycle():
    assert validate_soil_transition("result_received", "rejected", has_result=True) is True
    assert validate_soil_transition("rejected", "in_lab", has_result=False) is True
    assert validate_soil_transition("in_lab", "result_received", has_result=True) is True


def test_rejected_cannot_jump_to_approved_or_published():
    for tgt in ("approved", "published", "result_received", "sampled"):
        with pytest.raises(SoilWorkflowError):
            validate_soil_transition("rejected", tgt, has_result=True)


# ---------------------------------------------------------------------------
# الحالات النهائيّة — published و cancelled لا تنتقل لأيّ هدف (بما فيه نفسها = لا-عمل).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("terminal", ["published", "cancelled"])
def test_terminal_states_have_no_outgoing_transitions(terminal):
    assert SOIL_TEST_TRANSITIONS[SoilTestStatus(terminal)] == set()


@pytest.mark.parametrize("terminal", ["published", "cancelled"])
def test_terminal_self_transition_is_noop_not_error(terminal):
    # نفس الحالة = لا-عمل idempotent حتّى للنهائيّة (تُعالَج قبل فحص الخريطة).
    assert validate_soil_transition(terminal, terminal, has_result=True) is False


@pytest.mark.parametrize(
    "terminal,target",
    [
        ("published", "approved"),
        ("published", "cancelled"),
        ("published", "rejected"),
        ("cancelled", "requested"),
        ("cancelled", "in_lab"),
        ("cancelled", "published"),
    ],
)
def test_terminal_states_reject_any_real_transition(terminal, target):
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition(terminal, target, has_result=True)
    assert e.value.http_status == 422


# ---------------------------------------------------------------------------
# لا-عمل لكلّ حالة (idempotent) قبل أيّ فحص شرعيّة/invariant.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(SoilTestStatus))
def test_self_transition_is_noop_for_every_status(status):
    assert validate_soil_transition(status, status, has_result=False) is False


# ---------------------------------------------------------------------------
# SoilWorkflowError — البنية والرمز الافتراضيّ.
# ---------------------------------------------------------------------------


def test_error_defaults_to_422():
    err = SoilWorkflowError("خطأ ما")
    assert err.http_status == 422
    assert err.message_ar == "خطأ ما"
    assert str(err) == "خطأ ما"


def test_error_accepts_custom_status():
    err = SoilWorkflowError("ممنوع", http_status=409)
    assert err.http_status == 409


def test_error_is_exception_subclass():
    assert issubclass(SoilWorkflowError, Exception)


# ---------------------------------------------------------------------------
# تطابق الخريطة مع التصميم — لا قفز خلفيّ غير متوقّع، والأهداف كلّها أعضاء صالحة.
# ---------------------------------------------------------------------------


def test_transition_targets_are_all_valid_statuses():
    for targets in SOIL_TEST_TRANSITIONS.values():
        for tgt in targets:
            assert isinstance(tgt, SoilTestStatus)


def test_no_status_transitions_to_itself_in_map():
    # نفس-الحالة يُعالَج كلا-عمل، لا يجب إدراجه في مجموعة الأهداف.
    for cur, targets in SOIL_TEST_TRANSITIONS.items():
        assert cur not in targets


def test_approved_only_path_is_published():
    assert SOIL_TEST_TRANSITIONS[SoilTestStatus.APPROVED] == {SoilTestStatus.PUBLISHED}


def test_requested_cannot_revisit_after_leaving():
    # لا حالة تعود إلى requested (نقطة بدء وحيدة).
    for targets in SOIL_TEST_TRANSITIONS.values():
        assert SoilTestStatus.REQUESTED not in targets
