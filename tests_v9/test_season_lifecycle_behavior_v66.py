"""اختبارات سلوكيّة نقيّة لآلة حالة الموسم (season_lifecycle).

تكمّل التغطية القائمة في services/sahool-platform/tests/test_season_lifecycle.py
وتركّز على: _coerce (str/Enum)، تساوي القيمة بين str وEnum، لا-عمل لكلّ حالة،
رسائل/رموز الأخطاء، نهائيّة closed لكلّ هدف، واكتمال جدول الانتقالات.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api.season_lifecycle import (  # noqa: E402
    SEASON_TRANSITIONS,
    SeasonStatus,
    SeasonTransitionError,
    _coerce,
    validate_status_transition,
)

# ---- _coerce: يقبل str وEnum ويرجع SeasonStatus ----


@pytest.mark.parametrize("value", ["planned", "active", "closed"])
def test_coerce_accepts_str(value):
    result = _coerce(value)
    assert isinstance(result, SeasonStatus)
    assert result.value == value


@pytest.mark.parametrize("member", list(SeasonStatus))
def test_coerce_accepts_enum_idempotent(member):
    assert _coerce(member) is member


def test_coerce_unknown_raises_with_422_and_allowed_list():
    with pytest.raises(SeasonTransitionError) as e:
        _coerce("frozen")
    assert e.value.http_status == 422
    assert "مجهولة" in e.value.message_ar
    # الرسالة تُعدّد كلّ الحالات المسموحة
    for s in SeasonStatus:
        assert s.value in e.value.message_ar


def test_coerce_empty_string_rejected():
    with pytest.raises(SeasonTransitionError):
        _coerce("")


# ---- تكافؤ str وEnum في الانتقالات ----


def test_str_and_enum_inputs_equivalent_for_valid_transition():
    assert validate_status_transition("planned", "active") is True
    assert validate_status_transition(SeasonStatus.PLANNED, SeasonStatus.ACTIVE) is True
    # مزيج str/Enum يعمل أيضاً
    assert validate_status_transition("planned", SeasonStatus.ACTIVE) is True
    assert validate_status_transition(SeasonStatus.PLANNED, "active") is True


# ---- لا-عمل (idempotent) لكلّ حالة: نفس الحالة → False ----


@pytest.mark.parametrize("member", list(SeasonStatus))
def test_same_status_returns_false_for_every_state(member):
    assert validate_status_transition(member, member) is False
    assert validate_status_transition(member.value, member.value) is False


# ---- كلّ انتقال صالح يُرجِع True ----


@pytest.mark.parametrize(
    "current,target",
    [
        (SeasonStatus.PLANNED, SeasonStatus.ACTIVE),
        (SeasonStatus.PLANNED, SeasonStatus.CLOSED),
        (SeasonStatus.ACTIVE, SeasonStatus.CLOSED),
    ],
)
def test_every_allowed_transition_returns_true(current, target):
    assert validate_status_transition(current, target) is True


# ---- كلّ انتقال غير صالح (بين حالات معروفة، مختلفة) يرفع الخطأ ----


@pytest.mark.parametrize(
    "current,target",
    [
        (SeasonStatus.ACTIVE, SeasonStatus.PLANNED),
        (SeasonStatus.CLOSED, SeasonStatus.PLANNED),
        (SeasonStatus.CLOSED, SeasonStatus.ACTIVE),
    ],
)
def test_every_disallowed_transition_raises(current, target):
    with pytest.raises(SeasonTransitionError) as e:
        validate_status_transition(current, target)
    assert e.value.http_status == 422
    assert "غير مسموح" in e.value.message_ar
    # الرسالة تذكر مصدر وهدف الانتقال
    assert current.value in e.value.message_ar
    assert target.value in e.value.message_ar


# ---- closed نهائيّة: أيّ هدف مختلف يُرفض برسالة «نهائيّة» ----


@pytest.mark.parametrize("target", [SeasonStatus.PLANNED, SeasonStatus.ACTIVE])
def test_closed_is_terminal_for_all_targets(target):
    with pytest.raises(SeasonTransitionError) as e:
        validate_status_transition(SeasonStatus.CLOSED, target)
    assert "نهائيّة" in e.value.message_ar


def test_closed_to_closed_is_noop_not_error():
    # نفس الحالة النهائيّة = لا-عمل، ليست خطأً
    assert validate_status_transition("closed", "closed") is False


# ---- خصائص الاستثناء نفسه ----


def test_transition_error_default_status_is_422():
    err = SeasonTransitionError("رسالة")
    assert err.http_status == 422
    assert err.message_ar == "رسالة"
    assert str(err) == "رسالة"


def test_transition_error_custom_status_preserved():
    err = SeasonTransitionError("رسالة", http_status=409)
    assert err.http_status == 409


# ---- اكتمال/سلامة جدول الانتقالات (مصدر واحد للحقيقة) ----


def test_transition_table_covers_all_statuses():
    assert set(SEASON_TRANSITIONS.keys()) == set(SeasonStatus)


def test_closed_has_no_outgoing_transitions():
    assert SEASON_TRANSITIONS[SeasonStatus.CLOSED] == set()


def test_table_matches_validate_for_every_pair():
    # الجدول هو المصدر الوحيد: كلّ زوج مختلف يطابق سلوك validate.
    for cur in SeasonStatus:
        for tgt in SeasonStatus:
            if cur == tgt:
                assert validate_status_transition(cur, tgt) is False
            elif tgt in SEASON_TRANSITIONS[cur]:
                assert validate_status_transition(cur, tgt) is True
            else:
                with pytest.raises(SeasonTransitionError):
                    validate_status_transition(cur, tgt)
