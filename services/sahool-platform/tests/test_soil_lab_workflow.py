"""اختبارات دورة حياة فحص التربة المخبري (offline) — انتقالات + invariant النتيجة.

يتحقّق من: المسار الكامل (requested→…→published)؛ منع القفز فوق المراحل؛ invariant
«لا اعتماد/نشر بلا نتيجة»؛ نهائيّة المنشور/الملغى؛ لا-عمل؛ ورفض الحالة المجهولة.
"""

import pytest
from core.engines.soil_lab_workflow import (
    SoilTestStatus,
    SoilWorkflowError,
    validate_soil_transition,
)


def test_full_happy_path_transitions():
    chain = [
        ("requested", "sampled"),
        ("sampled", "in_lab"),
        ("in_lab", "result_received"),
        ("result_received", "approved"),
        ("approved", "published"),
    ]
    for cur, tgt in chain:
        # النتيجة متوفّرة في المراحل المتأخّرة.
        assert validate_soil_transition(cur, tgt, has_result=True) is True


def test_cannot_skip_stages():
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition("requested", "published", has_result=True)
    assert e.value.http_status == 422


def test_result_received_requires_result_data():
    # invariant: الانتقال إلى result_received بلا نتيجة → 422 (لا تأليف قياسات).
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition("in_lab", "result_received", has_result=False)
    assert "نتيجة" in e.value.message_ar


def test_approve_and_publish_require_result():
    with pytest.raises(SoilWorkflowError):
        validate_soil_transition("result_received", "approved", has_result=False)
    assert validate_soil_transition("result_received", "approved", has_result=True) is True


def test_rejected_can_retest_or_cancel():
    assert validate_soil_transition("rejected", "in_lab") is True
    assert validate_soil_transition("rejected", "cancelled") is True


def test_published_is_terminal():
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition("published", "approved", has_result=True)
    assert e.value.http_status == 422


def test_cancelled_is_terminal():
    with pytest.raises(SoilWorkflowError):
        validate_soil_transition("cancelled", "requested")


def test_same_status_is_noop():
    assert validate_soil_transition("in_lab", "in_lab") is False


def test_unknown_status_rejected():
    with pytest.raises(SoilWorkflowError) as e:
        validate_soil_transition("requested", "teleported")
    assert "مجهولة" in e.value.message_ar


def test_transitions_cover_all_statuses():
    # كلّ حالة معرّفة في خريطة الانتقالات (لا حالة يتيمة).
    from core.engines.soil_lab_workflow import SOIL_TEST_TRANSITIONS

    assert set(SOIL_TEST_TRANSITIONS.keys()) == set(SoilTestStatus)
