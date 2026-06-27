from datetime import date

import pytest
from core.farm_operations_ledger import (
    EnergyRecord,
    EnergySource,
    EquipmentRecord,
    ExecutionMode,
    InputRecord,
    InputType,
    LedgerCostLine,
    OperationLedgerRecord,
    OperationType,
    SyncStatus,
    WaterRecord,
    ai_feature_row,
    summarize_operational_records,
    validate_operation_record,
)


def test_summarize_operational_records_control_ledger():
    ops = [
        OperationLedgerRecord(
            record_id="op1",
            tenant_id="t1",
            farm_id="farm1",
            field_id="field1",
            season_id="wheat-2026",
            operation_date=date(2026, 1, 2),
            operation_type=OperationType.IRRIGATION,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(
                LedgerCostLine("water", 120),
                LedgerCostLine("administration", 20),
            ),
        )
    ]
    summary = summarize_operational_records(
        ops,
        water=[WaterRecord("op1", "field1", "well1", "pivot1", 6, 950, "meter")],
        energy=[EnergyRecord("op1", EnergySource.SOLAR, kwh=45, hours_operated=6)],
        equipment=[EquipmentRecord("op1", "pivot1", hours_worked=6)],
        inputs=[InputRecord("op1", InputType.FERTILIZER, "urea", 200, "kg", 300)],
    )
    assert summary.total_cost == 140
    assert summary.direct_cost == 120
    assert summary.indirect_cost == 20
    assert summary.water_volume_m3 == 950
    assert summary.energy_kwh == 45
    assert summary.equipment_hours == 6
    assert summary.input_quantities["fertilizer:kg"] == 200
    assert summary.control_only is True


def test_syncable_cost_is_only_for_ready_records():
    ops = [
        OperationLedgerRecord(
            record_id="op1",
            tenant_id="t1",
            field_id="field1",
            operation_date=date(2026, 1, 2),
            operation_type=OperationType.HARVEST,
            sync_status=SyncStatus.READY_FOR_SYNC,
            cost_lines=(LedgerCostLine("harvest", 500),),
        )
    ]
    summary = summarize_operational_records(ops)
    assert summary.syncable_cost == 500
    assert summary.control_only is False


def test_ai_feature_row_is_descriptive_not_predictive():
    op = OperationLedgerRecord(
        record_id="op1",
        tenant_id="t1",
        field_id="field1",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.IRRIGATION,
        cost_lines=(LedgerCostLine("water", 100),),
    )
    summary = summarize_operational_records(
        [op],
        water=[WaterRecord("op1", "field1", "well1", None, 3, 60, "meter")],
        energy=[EnergyRecord("op1", EnergySource.SOLAR, kwh=12)],
    )
    row = ai_feature_row(summary, area_ha=2)
    assert row["cost_per_ha"] == 50
    assert row["water_m3_per_ha"] == 30
    assert row["kwh_per_m3"] == 0.2
    assert row["provenance"] == {
        "source": "farm_operations_ledger",
        "prediction": False,
        "recommendation": False,
    }


def test_operation_requires_tenant_and_scope():
    op = OperationLedgerRecord(
        record_id="op1",
        tenant_id="",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.OTHER,
    )
    with pytest.raises(ValueError):
        validate_operation_record(op)

    op2 = OperationLedgerRecord(
        record_id="op2",
        tenant_id="t1",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.OTHER,
    )
    with pytest.raises(ValueError):
        validate_operation_record(op2)
