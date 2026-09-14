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
    water_summary_from_row,
    water_summary_payload,
)


def test_water_summary_from_sql_row_keeps_unmeasured_water_unknown():
    """Copilot على #1001 (مكتومة): مسارا HTTP كانا يُغلّفان SUM بـCOALESCE(…,0) ثمّ `or 0.0`."""
    unmeasured = {"water_volume_m3": None, "water_records_total": 2, "water_records_measured": 0}
    assert water_summary_from_row(unmeasured) == {
        "water_volume_m3": None,
        "water_records_total": 2,
        "water_records_measured": 0,
        "water_records_unmeasured": 2,
    }
    assert water_summary_payload(unmeasured) == {
        "water_volume_m3": None,
        "water_measurement": {
            "records_total": 2,
            "records_measured": 0,
            "records_unmeasured": 2,
            "complete": False,
        },
    }
    measured = {"water_volume_m3": 900.0, "water_records_total": 1, "water_records_measured": 1}
    assert water_summary_payload(measured)["water_volume_m3"] == 900.0
    assert water_summary_payload(measured)["water_measurement"]["complete"] is True
    # بلا سجلّات ماء أصلاً: الأعمدة NULL/0 ⇒ مجهول واكتمالٌ تافه (كعقد summarize_operational_records).
    empty = {"water_volume_m3": None, "water_records_total": None, "water_records_measured": None}
    assert water_summary_payload(empty)["water_measurement"] == {
        "records_total": 0,
        "records_measured": 0,
        "records_unmeasured": 0,
        "complete": True,
    }


def test_router_summary_queries_do_not_coalesce_water_to_zero():
    """كلا الاستعلامين (ملخّص HTTP وملخّص الموسم) يُصدِران SUM بلا COALESCE مع عدّادي القياس."""
    from pathlib import Path

    router = Path(__file__).resolve().parents[1] / "api/routers/farm_operations_ledger.py"
    src = router.read_text(encoding="utf-8")
    assert "COALESCE((SELECT SUM(water_volume_m3)" not in src
    assert 'float(row["water_volume_m3"] or 0.0)' not in src
    assert src.count("AS water_records_total") == 2
    assert src.count("AS water_records_measured") == 2
    assert "water_summary_payload(row)" in src and "water_summary_from_row(row)" in src


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


def test_missing_water_volume_is_unknown_not_zero():
    """U04 (التدقيق الموحَّد 2026-09-13): ساعات ريّ بلا حجم مقيس كانت تصير 0 م³/هكتار."""
    op = OperationLedgerRecord(
        record_id="op1",
        tenant_id="t1",
        field_id="field1",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.IRRIGATION,
    )
    summary = summarize_operational_records(
        [op],
        water=[WaterRecord("op1", "field1", "well1", None, 4, None, None)],
        energy=[EnergyRecord("op1", EnergySource.SOLAR, kwh=12)],
    )
    assert summary.water_volume_m3 is None
    assert summary.water_records_total == 1
    assert summary.water_records_measured == 0
    assert summary.water_records_unmeasured == 1
    assert summary.water_measurement_complete is False
    row = ai_feature_row(summary, area_ha=2)
    assert row["water_volume_m3"] is None
    assert row["water_m3_per_ha"] is None
    assert row["kwh_per_m3"] is None
    assert row["water_measurement"] == {
        "records_total": 1,
        "records_measured": 0,
        "records_unmeasured": 1,
        "complete": False,
    }


def test_partially_measured_water_sums_only_measured_records_and_declares_the_gap():
    op = OperationLedgerRecord(
        record_id="op1",
        tenant_id="t1",
        field_id="field1",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.IRRIGATION,
    )
    summary = summarize_operational_records(
        [op],
        water=[
            WaterRecord("op1", "field1", "well1", None, 3, 60, "meter"),
            WaterRecord("op1", "field1", "well1", None, 3, None, None),
        ],
    )
    assert summary.water_volume_m3 == 60
    assert summary.water_records_measured == 1 and summary.water_records_unmeasured == 1
    assert summary.water_measurement_complete is False
    assert ai_feature_row(summary, area_ha=2)["water_m3_per_ha"] == 30


def test_no_water_records_at_all_is_unknown_and_trivially_complete():
    op = OperationLedgerRecord(
        record_id="op1",
        tenant_id="t1",
        field_id="field1",
        operation_date=date(2026, 1, 2),
        operation_type=OperationType.OTHER,
    )
    summary = summarize_operational_records([op])
    assert summary.water_volume_m3 is None
    assert summary.water_records_total == 0
    assert summary.water_measurement_complete is True


class _Conn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.mark.asyncio
async def test_persist_operation_subrecords_writes_each_kind_with_the_operation_identity():
    """نُقِل من الراوتر (راتشِت الحجم): السجلّات الفرعيّة تُربَط بالعمليّة والمستأجِر والتاريخ."""
    from core.farm_operations_ledger import persist_operation_subrecords

    conn = _Conn()
    counts = await persist_operation_subrecords(
        conn,
        tenant_id="11111111-1111-1111-1111-111111111111",
        operation_id="oplog_abc",
        record_date=date(2026, 1, 2),
        farm_id="farm1",
        field_id="field1",
        water=_Obj(
            well_id="w1",
            pump_id=None,
            pivot_id=None,
            hours_operated=4,
            water_volume_m3=None,
            measurement_method=None,
            notes=None,
        ),
        energy=_Obj(
            energy_source="solar",
            kwh=12,
            diesel_liters=None,
            hours_operated=4,
            equipment_id=None,
            well_id="w1",
            pivot_id=None,
            notes=None,
        ),
        equipment=[
            _Obj(
                equipment_id="p1",
                operator_id=None,
                hours_worked=4,
                fuel_liters=None,
                maintenance_cost=None,
                notes=None,
            )
        ],
        labor=[_Obj(worker_id=None, workers_count=2, hours=4, wage_amount=None, notes=None)] * 2,
        inputs=[],
    )
    assert counts == {"water": 1, "energy": 1, "equipment": 1, "labor": 2, "inputs": 0}
    tables = [sql.split("INSERT INTO ")[1].split()[0] for sql, _ in conn.calls]
    assert tables == [
        "farm_water_records",
        "farm_energy_records",
        "farm_equipment_records",
        "farm_labor_records",
        "farm_labor_records",
    ]
    for _sql, args in conn.calls:
        assert args[0] == "11111111-1111-1111-1111-111111111111"
        assert args[1] == "oplog_abc"
        assert args[2] == date(2026, 1, 2)
    # الحجمُ الغائب يُدرَج None لا 0 (U04 يبدأ من الإدخال).
    assert conn.calls[0][1][9] is None


@pytest.mark.asyncio
async def test_persist_operation_subrecords_with_nothing_writes_nothing():
    from core.farm_operations_ledger import persist_operation_subrecords

    conn = _Conn()
    counts = await persist_operation_subrecords(
        conn,
        tenant_id="t",
        operation_id="o",
        record_date=date(2026, 1, 2),
        farm_id=None,
        field_id=None,
    )
    assert counts == {"water": 0, "energy": 0, "equipment": 0, "labor": 0, "inputs": 0}
    assert conn.calls == []
