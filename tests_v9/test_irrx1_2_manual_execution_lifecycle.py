import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

P = Path(__file__).parents[1] / "services/sahool-platform/api/irrigation_manual_execution.py"
spec = importlib.util.spec_from_file_location("manual_execution", P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def recommendation(mode="manual_measured", nominal=100.0):
    now = datetime.now(UTC)
    return m.ManualRecommendationInput(
        execution_id="11111111-1111-1111-1111-111111111111",
        tenant_id="t",
        field_id="f",
        season_id="s",
        system_id="sys",
        recommendation_id="r",
        recommendation_digest="a" * 64,
        mode=mode,
        target_depth_mm=20,
        target_volume_m3=1000,
        nominal_flow_m3_h=nominal,
        valid_from=now,
        valid_until=now + timedelta(days=1),
        created_by="u",
    )


def confirmation(**kw):
    now = datetime.now(UTC)
    base = dict(
        started_at=now,
        stopped_at=now + timedelta(hours=10),
        completion_ratio=1,
        meter_start_m3=100,
        meter_end_m3=1100,
    )
    base.update(kw)
    return m.ManualExecutionConfirmation(**base)


def test_measured_meter_is_ledger_eligible():
    result = m.derive_manual_as_applied(recommendation(), confirmation())
    assert result.actual_volume_m3 == 1000
    assert result.actual_depth_mm == 20
    assert result.ledger_eligible is True


def test_estimated_is_not_ledger_eligible():
    c = confirmation(
        meter_start_m3=None, meter_end_m3=None, measured_flow_m3_h=None, estimated_flow_m3_h=100
    )
    result = m.derive_manual_as_applied(recommendation("manual_estimated"), c)
    assert result.quality == "estimated"
    assert result.ledger_eligible is False


def test_measured_mode_fails_closed_without_measurement():
    c = confirmation(
        meter_start_m3=None, meter_end_m3=None, measured_flow_m3_h=None, estimated_flow_m3_h=100
    )
    result = m.derive_manual_as_applied(recommendation(), c)
    assert "MEASURED_MODE_REQUIRES_MEASURED_EVIDENCE" in result.blocking_reasons
    assert result.ledger_eligible is False


def test_transition_chain_and_illegal_skip():
    assert m.transition_manual_execution(
        m.ManualExecutionState.RECOMMENDED, m.ManualExecutionState.APPROVED
    )
    with pytest.raises(ValueError):
        m.transition_manual_execution(
            m.ManualExecutionState.RECOMMENDED, m.ManualExecutionState.CONFIRMED
        )


def test_meter_regression_rejected():
    with pytest.raises(ValidationError):
        confirmation(meter_start_m3=1000, meter_end_m3=900)


def test_operator_declared_volume_is_accepted_but_not_ledger_eligible():
    c = confirmation(
        meter_start_m3=None,
        meter_end_m3=None,
        measured_flow_m3_h=None,
        manual_volume_m3=750,
        estimated_flow_m3_h=None,
    )
    result = m.derive_manual_as_applied(recommendation("manual_estimated"), c)
    assert result.actual_volume_m3 == 750
    assert result.quality == "operator_declared"
    assert result.ledger_eligible is False
    assert "OPERATOR_DECLARED_VOLUME_REQUIRES_INDEPENDENT_MEASUREMENT" in result.blocking_reasons


def test_operator_declared_volume_does_not_satisfy_measured_mode():
    c = confirmation(
        meter_start_m3=None,
        meter_end_m3=None,
        measured_flow_m3_h=None,
        manual_volume_m3=750,
        estimated_flow_m3_h=None,
    )
    result = m.derive_manual_as_applied(recommendation("manual_measured"), c)
    assert "MEASURED_MODE_REQUIRES_MEASURED_EVIDENCE" in result.blocking_reasons
    assert result.ledger_eligible is False


def test_incomplete_meter_pair_is_rejected():
    with pytest.raises(ValidationError):
        confirmation(meter_start_m3=100, meter_end_m3=None)


# MANUAL-COMPLETION-RATIO-SCALES-MEASURED-VOLUME-01: النسبةُ تقديرُ المشغِّل؛ لا تمسّ حجماً مقيساً أو مُعلَناً.
@pytest.mark.parametrize(
    ("kw", "quality", "volume"),
    [
        ({}, "measured_meter", 1000),  # العدّاد: 1100 − 100
        (
            {"meter_start_m3": None, "meter_end_m3": None, "measured_flow_m3_h": 100},
            "measured_flow",
            1000,  # 100 م³/س × 10 س صافية
        ),
        (
            {"meter_start_m3": None, "meter_end_m3": None, "manual_volume_m3": 700},
            "operator_declared",
            700,
        ),
    ],
)
def test_completion_ratio_never_rescales_an_observed_volume(kw, quality, volume):
    result = m.derive_manual_as_applied(recommendation(), confirmation(completion_ratio=0.5, **kw))
    assert result.quality == quality
    assert result.actual_volume_m3 == volume
    assert result.completion_ratio_applied is False
    assert result.completion_ratio == 0.5  # يُحفَظ مُدخَلاً كما أُدخل، لا يُخفى


def test_measured_flow_volume_already_nets_out_interruptions_once():
    c = confirmation(
        meter_start_m3=None,
        meter_end_m3=None,
        measured_flow_m3_h=100,
        interruptions_minutes=120,
        completion_ratio=0.5,
    )
    result = m.derive_manual_as_applied(recommendation(), c)
    assert result.actual_runtime_h == 8
    assert result.actual_volume_m3 == 800  # لا 400: الانقطاع لا يُطرح مرّتين
    assert result.ledger_eligible is True


@pytest.mark.parametrize(
    ("kw", "rec_kw", "quality"),
    [
        ({"estimated_flow_m3_h": 100}, {}, "estimated"),
        ({}, {"nominal": 100.0}, "estimated_nominal"),
    ],
)
def test_completion_ratio_scales_only_an_estimate(kw, rec_kw, quality):
    c = confirmation(meter_start_m3=None, meter_end_m3=None, completion_ratio=0.5, **kw)
    result = m.derive_manual_as_applied(recommendation("manual_estimated", **rec_kw), c)
    assert result.quality == quality
    assert result.actual_volume_m3 == 500  # 100 × 10 س × 0.5
    assert result.completion_ratio_applied is True
    assert result.ledger_eligible is False  # التقدير لا يدخل الدفتر بالنسبة أو بدونها
