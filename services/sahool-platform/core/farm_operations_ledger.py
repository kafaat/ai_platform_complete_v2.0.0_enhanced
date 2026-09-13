"""core/farm_operations_ledger.py — سجلات تشغيل زراعية رقابية قابلة للتحليل.

هذه النواة لا تنفذ محاسبة مزدوجة ولا تزامناً مع ERP. هي طبقة تشكيل/تحليل نقيّة
لـ Farm Operations Ledger: أعمال يومية، مياه، طاقة، معدات، عمالة، ومدخلات.
تُستخدم من الراوتر والاختبارات دون قاعدة بيانات، وتغذي لاحقاً Cost Intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class BusinessUnitType(str, Enum):
    CROPS = "crops"
    ORCHARDS = "orchards"
    LIVESTOCK = "livestock"
    POULTRY = "poultry"
    APIARY = "apiary"
    AQUACULTURE = "aquaculture"
    PROCESSING = "processing"
    SERVICES = "services"


class ProductionUnitType(str, Enum):
    FIELD = "field"
    ORCHARD_BLOCK = "orchard_block"
    BARN = "barn"
    GREENHOUSE = "greenhouse"
    PIVOT = "pivot"
    WELL = "well"
    POND = "pond"
    APIARY = "apiary"
    FARM_LEVEL = "farm_level"


class OperationType(str, Enum):
    LAND_PREPARATION = "land_preparation"
    PLANTING = "planting"
    IRRIGATION = "irrigation"
    FERTILIZATION = "fertilization"
    PEST_CONTROL = "pest_control"
    HARVEST = "harvest"
    TRANSPORT = "transport"
    PACKAGING = "packaging"
    STORAGE = "storage"
    LIVESTOCK_CARE = "livestock_care"
    MAINTENANCE = "maintenance"
    OTHER = "other"


class ExecutionMode(str, Enum):
    SELF = "self"
    RENTED_EQUIPMENT = "rented_equipment"
    CONTRACTOR = "contractor"
    MIXED = "mixed"


class EnergySource(str, Enum):
    SOLAR = "solar"
    GRID = "grid"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class InputType(str, Enum):
    SEED = "seed"
    FERTILIZER = "fertilizer"
    PESTICIDE = "pesticide"
    FEED = "feed"
    AMENDMENT = "amendment"
    PACKAGING = "packaging"
    OTHER = "other"


class SyncStatus(str, Enum):
    CONTROL_ONLY = "control_only"  # رقابي فقط داخل SAHOOL
    READY_FOR_SYNC = "ready_for_sync"  # قابل للترحيل المالي
    SYNCED = "synced"
    SYNC_FAILED = "sync_failed"


@dataclass(frozen=True)
class LedgerCostLine:
    category: str
    amount: float
    currency: str = "YER"
    source: str = "manual"


@dataclass(frozen=True)
class OperationLedgerRecord:
    record_id: str
    tenant_id: str
    operation_date: date
    operation_type: OperationType
    season_id: str | None = None
    farm_id: str | None = None
    field_id: str | None = None
    production_unit_id: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.SELF
    contractor_id: str | None = None
    notes: str | None = None
    cost_lines: tuple[LedgerCostLine, ...] = field(default_factory=tuple)
    sync_status: SyncStatus = SyncStatus.CONTROL_ONLY


@dataclass(frozen=True)
class WaterRecord:
    operation_id: str | None
    field_id: str | None
    well_id: str | None
    pivot_id: str | None
    hours_operated: float | None
    water_volume_m3: float | None
    measurement_method: str | None = None  # meter/estimate/calculated


@dataclass(frozen=True)
class EnergyRecord:
    operation_id: str | None
    energy_source: EnergySource
    kwh: float | None = None
    diesel_liters: float | None = None
    hours_operated: float | None = None
    equipment_id: str | None = None
    well_id: str | None = None
    pivot_id: str | None = None


@dataclass(frozen=True)
class EquipmentRecord:
    operation_id: str | None
    equipment_id: str
    hours_worked: float | None = None
    fuel_liters: float | None = None
    maintenance_cost: float | None = None


@dataclass(frozen=True)
class LaborRecord:
    operation_id: str | None
    worker_id: str | None
    workers_count: int | None = None
    hours: float | None = None
    wage_amount: float | None = None


@dataclass(frozen=True)
class InputRecord:
    operation_id: str | None
    input_type: InputType
    inventory_item_id: str | None
    quantity: float
    unit: str
    estimated_cost: float | None = None


@dataclass(frozen=True)
class LedgerSummary:
    total_cost: float
    direct_cost: float
    indirect_cost: float
    currency: str
    cost_breakdown: dict[str, float]
    # U04: None حين لا يوجد حجمٌ مقيس — الغائب ليس صفراً (صفر يعني «لم يُستهلك ماء»).
    water_volume_m3: float | None
    energy_kwh: float
    diesel_liters: float
    equipment_hours: float
    labor_hours: float
    input_quantities: dict[str, float]
    record_count: int
    syncable_cost: float
    control_only: bool
    # اكتمالُ قياس الماء (U04): كم سجلّ ريّ حمل حجماً مقيساً وكم سجلّ بلا حجم.
    water_records_total: int = 0
    water_records_measured: int = 0
    water_records_unmeasured: int = 0

    @property
    def water_measurement_complete(self) -> bool:
        """صحيح فقط حين كلُّ سجلّات الماء مقيسة (بلا سجلّات ⇒ لا شيء ليُقاس ⇒ True)."""
        return self.water_records_unmeasured == 0


def _non_negative(value: float | int | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    v = float(value)
    if v < 0:
        raise ValueError(f"{field_name} يجب أن يكون >= 0")
    return v


def validate_operation_record(record: OperationLedgerRecord) -> None:
    """حارس نقيّ: كل سجل يجب أن ينتمي لمستأجر وأن يرتبط بوحدة إنتاج أو حقل أو مزرعة."""
    if not record.tenant_id:
        raise ValueError("tenant_id مطلوب")
    if not (record.field_id or record.production_unit_id or record.farm_id):
        raise ValueError("يجب ربط السجل بحقل أو وحدة إنتاج أو مزرعة")
    for line in record.cost_lines:
        _non_negative(line.amount, field_name=f"cost_lines.{line.category}")


def summarize_operational_records(
    operations: list[OperationLedgerRecord],
    *,
    water: list[WaterRecord] | None = None,
    energy: list[EnergyRecord] | None = None,
    equipment: list[EquipmentRecord] | None = None,
    labor: list[LaborRecord] | None = None,
    inputs: list[InputRecord] | None = None,
    currency: str = "YER",
) -> LedgerSummary:
    """يلخص السجلات الرقابية إلى أرقام تشغيلية/مالية أولية.

    لا يحسب قيود محاسبية ولا يزامن ERP؛ فقط يجمّع ما سُجّل فعلاً. القيم الناقصة
    لا تُلفّق وتُحسب 0 في الإجماليات التشغيلية.
    """
    cost_breakdown: dict[str, float] = {}
    total = 0.0
    syncable = 0.0
    for op in operations:
        validate_operation_record(op)
        for line in op.cost_lines:
            amount = _non_negative(line.amount, field_name=line.category) or 0.0
            cost_breakdown[line.category] = cost_breakdown.get(line.category, 0.0) + amount
            total += amount
            if op.sync_status in {
                SyncStatus.READY_FOR_SYNC,
                SyncStatus.SYNCED,
                SyncStatus.SYNC_FAILED,
            }:
                syncable += amount

    # تبويب مبسّط: administrative/overhead/management = غير مباشر، والباقي مباشر.
    indirect_keys = {"administration", "overhead", "supervision", "security", "management"}
    indirect = sum(v for k, v in cost_breakdown.items() if k in indirect_keys)
    direct = total - indirect

    # U04 (التدقيق الموحَّد 2026-09-13): كان الحجمُ الغائب يُجمَع صفراً فتخرج خاصيّةُ
    # التعلّم water_m3_per_ha=0 عن ريٍّ سُجِّلت ساعاتُه بلا حجم. الآن: يُجمَع المقيسُ
    # وحدَه، ويُعلَن عددُ المقيس/غير المقيس، وغيابُ أيّ قياس ⇒ None لا 0.
    measured_volumes = [
        v
        for v in (
            _non_negative(r.water_volume_m3, field_name="water_volume_m3") for r in (water or [])
        )
        if v is not None
    ]
    water_records_total = len(water or [])
    water_records_measured = len(measured_volumes)
    water_volume = sum(measured_volumes) if measured_volumes else None
    energy_kwh = sum((_non_negative(r.kwh, field_name="kwh") or 0.0) for r in (energy or []))
    diesel = sum(
        (_non_negative(r.diesel_liters, field_name="diesel_liters") or 0.0) for r in (energy or [])
    )
    eq_hours = sum(
        (_non_negative(r.hours_worked, field_name="hours_worked") or 0.0) for r in (equipment or [])
    )
    labor_hours = sum((_non_negative(r.hours, field_name="hours") or 0.0) for r in (labor or []))
    input_quantities: dict[str, float] = {}
    for r in inputs or []:
        qty = _non_negative(r.quantity, field_name="input.quantity") or 0.0
        key = f"{r.input_type.value}:{r.unit}"
        input_quantities[key] = input_quantities.get(key, 0.0) + qty

    return LedgerSummary(
        total_cost=total,
        direct_cost=direct,
        indirect_cost=indirect,
        currency=currency,
        cost_breakdown=cost_breakdown,
        water_volume_m3=water_volume,
        energy_kwh=energy_kwh,
        diesel_liters=diesel,
        equipment_hours=eq_hours,
        labor_hours=labor_hours,
        input_quantities=input_quantities,
        record_count=len(operations),
        syncable_cost=syncable,
        control_only=syncable == 0.0,
        water_records_total=water_records_total,
        water_records_measured=water_records_measured,
        water_records_unmeasured=water_records_total - water_records_measured,
    )


def ai_feature_row(summary: LedgerSummary, *, area_ha: float | None = None) -> dict[str, Any]:
    """صف features آمن للتعلم المستقبلي؛ لا يتنبأ ولا يوصي هنا.

    U04: خصائصُ الماء تكون ``None`` حين لا حجمَ مقيساً، ويرافقها اكتمالُ القياس — فلا
    يتعلّم نموذجٌ أنّ ريّاً بلا عدّاد كان صفر أمتار مكعّبة.
    """
    area = _non_negative(area_ha, field_name="area_ha") if area_ha is not None else None
    volume = summary.water_volume_m3
    return {
        "total_cost": summary.total_cost,
        "direct_cost": summary.direct_cost,
        "indirect_cost": summary.indirect_cost,
        "water_volume_m3": volume,
        "water_measurement": {
            "records_total": summary.water_records_total,
            "records_measured": summary.water_records_measured,
            "records_unmeasured": summary.water_records_unmeasured,
            "complete": summary.water_measurement_complete,
        },
        "energy_kwh": summary.energy_kwh,
        "diesel_liters": summary.diesel_liters,
        "equipment_hours": summary.equipment_hours,
        "labor_hours": summary.labor_hours,
        "cost_per_ha": summary.total_cost / area if area else None,
        "water_m3_per_ha": volume / area if (area and volume is not None) else None,
        "kwh_per_m3": summary.energy_kwh / volume if (volume is not None and volume > 0) else None,
        "provenance": {
            "source": "farm_operations_ledger",
            "prediction": False,
            "recommendation": False,
        },
    }
