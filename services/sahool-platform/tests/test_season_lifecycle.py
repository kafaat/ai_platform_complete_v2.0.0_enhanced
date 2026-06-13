"""اختبارات دورة حياة الموسم (offline) — انتقالات الحالة الصريحة.

يتحقّق من: الانتقالات المسموحة (planned→active/closed، active→closed)؛ منع إحياء
المُغلَق؛ لا-عمل عند نفس الحالة؛ ورفض الحالة المجهولة (422).
"""

import pytest
from api.season_lifecycle import (
    SeasonStatus,
    SeasonTransitionError,
    validate_status_transition,
)


def test_planned_to_active_allowed():
    assert validate_status_transition("planned", "active") is True


def test_planned_to_closed_allowed():
    assert validate_status_transition(SeasonStatus.PLANNED, SeasonStatus.CLOSED) is True


def test_active_to_closed_allowed():
    assert validate_status_transition("active", "closed") is True


def test_same_status_is_noop_not_transition():
    # نفس الحالة → لا-عمل (idempotent)، لا تغيير — False لا استثناء.
    assert validate_status_transition("active", "active") is False


def test_closed_is_terminal_no_revival():
    with pytest.raises(SeasonTransitionError) as e:
        validate_status_transition("closed", "active")
    assert e.value.http_status == 422
    assert "نهائيّة" in e.value.message_ar


def test_active_to_planned_not_allowed():
    with pytest.raises(SeasonTransitionError):
        validate_status_transition("active", "planned")


def test_unknown_status_rejected():
    with pytest.raises(SeasonTransitionError) as e:
        validate_status_transition("active", "frozen")
    assert e.value.http_status == 422
    assert "مجهولة" in e.value.message_ar
