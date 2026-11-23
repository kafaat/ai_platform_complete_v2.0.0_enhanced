"""Request models of the farm operations ledger router (water, energy, equipment, labour, inputs).

Moved out of ``api/routers/farm_operations_ledger.py`` to keep that router within its frozen
size (``tests/architecture/test_router_size_ratchet.py``), as ``api/field_models`` does for the
fields router. The router re-exports these names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _non_negative_or_none(v: float | None, name: str) -> float | None:
    if v is None:
        return None
    if v < 0:
        raise ValueError(f"{name} must be >= 0")
    return v


class WaterRecordIn(BaseModel):
    well_id: str | None = None
    pump_id: str | None = None
    pivot_id: str | None = None
    hours_operated: float | None = None
    water_volume_m3: float | None = None
    measurement_method: str | None = Field(None, description="meter|estimate|calculated")
    notes: str | None = None

    @field_validator("hours_operated", "water_volume_m3")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class EnergyRecordIn(BaseModel):
    energy_source: str = "unknown"
    kwh: float | None = None
    diesel_liters: float | None = None
    hours_operated: float | None = None
    equipment_id: str | None = None
    well_id: str | None = None
    pivot_id: str | None = None
    notes: str | None = None

    @field_validator("kwh", "diesel_liters", "hours_operated")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class EquipmentRecordIn(BaseModel):
    equipment_id: str
    operator_id: str | None = None
    hours_worked: float | None = None
    fuel_liters: float | None = None
    maintenance_cost: float | None = None
    notes: str | None = None

    @field_validator("hours_worked", "fuel_liters", "maintenance_cost")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class LaborRecordIn(BaseModel):
    worker_id: str | None = None
    workers_count: int | None = None
    hours: float | None = None
    wage_amount: float | None = None
    notes: str | None = None

    @field_validator("workers_count")
    @classmethod
    def _workers_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError("workers_count must be >= 0")
        return v

    @field_validator("hours", "wage_amount")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class InputRecordIn(BaseModel):
    input_type: str
    inventory_item_id: str | None = None
    # F-D11: names the stock batch this input came from; deducted only behind
    # FEATURE_LEDGER_INVENTORY_DEDUCTION (OFF by default), never stored on the input row.
    inventory_batch_id: str | None = None
    quantity: float
    unit: str
    estimated_cost: float | None = None
    notes: str | None = None

    @field_validator("quantity", "estimated_cost")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)
