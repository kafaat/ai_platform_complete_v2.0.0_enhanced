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
