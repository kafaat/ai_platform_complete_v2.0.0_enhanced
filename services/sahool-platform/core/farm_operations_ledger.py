"""core/farm_operations_ledger.py — سجلات تشغيل زراعية رقابية قابلة للتحليل.

هذه النواة لا تنفذ محاسبة مزدوجة ولا تزامناً مع ERP. هي طبقة تشكيل/تحليل نقيّة
لـ Farm Operations Ledger: أعمال يومية، مياه، طاقة، معدات، عمالة، ومدخلات.
تُستخدم من الراوتر والاختبارات دون قاعدة بيانات، وتغذي لاحقاً Cost Intelligence.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from core.authorization import Permission, has_permission
from core.farm_costing import ActualCostLine, SeasonBudgetLine, compute_variances


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


# ─── حالة العمليّة: المخطَّط ليس منفَّذاً ─────────────────────────────────────────────
# كان ``status`` نصّاً حرّاً (v100 بلا CHECK) وكان الملخّص والانحراف والربحيّة تجمع كلَّ
# صفّ — فتُحسَب عمليّةٌ مخطَّطة أو ملغاة أو مؤرَّخةٌ في المستقبل تكلفةً فعليّة.
OPERATION_STATUSES = ("planned", "in_progress", "completed", "cancelled")
COMPLETED_FUTURE_TOLERANCE = timedelta(days=1)  # فارق المناطق الزمنيّة بين الجهاز والخادم
ACTUAL_OPERATION_SQL = "status = 'completed' AND operation_date <= CURRENT_DATE"
PLANNED_OPERATION_SQL = "status IN ('planned', 'in_progress')"


def validate_operation_status(
    status: str, operation_date: date, *, today: date | None = None
) -> str:
    """يرفض حالةً خارج ``OPERATION_STATUSES`` و«منجَزة» مؤرَّخةً بعد الغد (سماحُ يومٍ للمنطقة)."""
    if status not in OPERATION_STATUSES:
        raise ValueError(f"status must be one of {', '.join(OPERATION_STATUSES)}")
    today = today or datetime.now(UTC).date()
    if status == "completed" and operation_date > today + COMPLETED_FUTURE_TOLERANCE:
        raise ValueError("completed operation cannot be dated in the future")
    return status


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


def water_summary_from_row(row: Any) -> dict[str, Any]:
    """يقرأ حجمَ الماء وعدّادات القياس من صفّ SQL مجمَّع (U04) — الغائبُ ``None`` لا ``0``.

    يتوقّع الأعمدة ``water_volume_m3`` (``SUM`` بلا ``COALESCE``) و``water_records_total``
    و``water_records_measured``، ويُعيد وسائطَ ``LedgerSummary`` الأربعة للماء. كان مسارا
    HTTP يُغلّفان المجموعَ بـ``COALESCE(…, 0)`` ثمّ ``or 0.0`` فيخرج الموسمُ غيرُ المقيس
    صفراً رغم عقد الوحدة (Copilot على #1001).
    """
    volume = row["water_volume_m3"]
    total = int(row["water_records_total"] or 0)
    measured = int(row["water_records_measured"] or 0)
    return {
        "water_volume_m3": float(volume) if volume is not None else None,
        "water_records_total": total,
        "water_records_measured": measured,
        "water_records_unmeasured": total - measured,
    }


def water_summary_payload(row: Any) -> dict[str, Any]:
    """حقولُ الماء لردّ HTTP الملخَّص: الحجمُ (أو ``None``) واكتمالُ القياس بالشكل الذي
    يُصدِره ``ai_feature_row`` نفسه."""
    w = water_summary_from_row(row)
    return {
        "water_volume_m3": w["water_volume_m3"],
        "water_measurement": {
            "records_total": w["water_records_total"],
            "records_measured": w["water_records_measured"],
            "records_unmeasured": w["water_records_unmeasured"],
            "complete": w["water_records_unmeasured"] == 0,
        },
    }


# ─── إدامة السجلّات الفرعيّة لعمليّةٍ واحدة ──────────────────────────────────────────
# نُقِلت من راوتر `farm_operations_ledger` (راتشِت حجم الراوترات: لا راوترَ يكبر) — الكاتبُ
# ما زال sahool-platform والمعاملةُ هي معاملةُ المُنادي؛ لا اتّصالَ يُفتح هنا.
async def persist_operation_subrecords(
    conn,
    *,
    tenant_id: str,
    operation_id: str,
    record_date: date,
    farm_id: str | None,
    field_id: str | None,
    water=None,
    energy=None,
    equipment=(),
    labor=(),
    inputs=(),
) -> dict[str, int]:
    """يُدرِج سجلّات الماء/الطاقة/المعدّات/العمالة/المدخلات المرتبطة بعمليّة محفوظة.

    يُستدعى **داخل** معاملة العمليّة (فشلُ أيّ سجلّ يُرجِع الكلَّ). يُعيد عدَّ الصفوف لكلّ
    نوع للشفافيّة. الكائناتُ الفرعيّة تُقرأ بالسمات (نماذج الراوتر) — لا تبعيّة على api.
    """
    counts = {"water": 0, "energy": 0, "equipment": 0, "labor": 0, "inputs": 0}
    if water:
        await conn.execute(
            """INSERT INTO farm_water_records
               (tenant_id, operation_id, record_date, farm_id, field_id, well_id, pump_id,
                pivot_id, hours_operated, water_volume_m3, measurement_method, notes)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
            tenant_id,
            operation_id,
            record_date,
            farm_id,
            field_id,
            water.well_id,
            water.pump_id,
            water.pivot_id,
            water.hours_operated,
            water.water_volume_m3,
            water.measurement_method,
            water.notes,
        )
        counts["water"] = 1
    if energy:
        await conn.execute(
            """INSERT INTO farm_energy_records
               (tenant_id, operation_id, record_date, energy_source, kwh, diesel_liters,
                hours_operated, equipment_id, well_id, pivot_id, notes)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
            tenant_id,
            operation_id,
            record_date,
            energy.energy_source,
            energy.kwh,
            energy.diesel_liters,
            energy.hours_operated,
            energy.equipment_id,
            energy.well_id,
            energy.pivot_id,
            energy.notes,
        )
        counts["energy"] = 1
    for e in equipment or ():
        await conn.execute(
            """INSERT INTO farm_equipment_records
               (tenant_id, operation_id, record_date, equipment_id, operator_id, hours_worked,
                fuel_liters, maintenance_cost, notes)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)""",
            tenant_id,
            operation_id,
            record_date,
            e.equipment_id,
            e.operator_id,
            e.hours_worked,
            e.fuel_liters,
            e.maintenance_cost,
            e.notes,
        )
        counts["equipment"] += 1
    for lab in labor or ():
        await conn.execute(
            """INSERT INTO farm_labor_records
               (tenant_id, operation_id, record_date, worker_id, workers_count, hours,
                wage_amount, notes)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)""",
            tenant_id,
            operation_id,
            record_date,
            lab.worker_id,
            lab.workers_count,
            lab.hours,
            lab.wage_amount,
            lab.notes,
        )
        counts["labor"] += 1
    for i in inputs or ():
        await conn.execute(
            """INSERT INTO farm_input_records
               (tenant_id, operation_id, record_date, input_type, inventory_item_id, quantity,
                unit, estimated_cost, notes)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)""",
            tenant_id,
            operation_id,
            record_date,
            i.input_type,
            i.inventory_item_id,
            i.quantity,
            i.unit,
            i.estimated_cost,
            i.notes,
        )
        counts["inputs"] += 1
    return counts


# ─── F-D11: deducting a recorded input from a named inventory batch ──────────────────────
# The platform owns ``inventory_batches`` (db_ownership.yml). The step runs inside the ledger
# record's transaction: each named batch row is locked (the reservation), checked and reduced
# by a conditional UPDATE that cannot go below zero. No unit conversion: units must match.
_STOCK_QUANTUM = Decimal("0.001")  # inventory_batches.quantity is NUMERIC(14, 3)


class InventoryDeductionRefused(Exception):
    """A deduction that must not happen; ``detail['reason']`` names why. Nothing is written."""

    def __init__(self, status_code: int, reason: str, **extra: Any) -> None:
        super().__init__(reason)
        self.status_code = status_code
        self.detail = {"reason": reason, **extra}


@dataclass(frozen=True)
class InventoryDeductionLine:
    batch_id: str
    item_id: str | None
    unit: str
    quantity: Decimal


def _unit_key(unit: str | None) -> str:
    return (unit or "").strip().lower()


def inventory_deduction_refusal(
    *, enabled: bool, has_batches: bool, idempotency_key: str | None, status: str, user: Any
) -> tuple[int, dict[str, str]] | None:
    """Why a requested deduction cannot start, before anything is written; ``None`` if it can.

    Flag off or no named batch: nothing to refuse (and nothing is deducted). Otherwise moving
    stock needs ``inventory:manage``: logging an activity (``activity:execute``, which a field
    worker holds) does not grant it. Then the ``Idempotency-Key`` is mandatory (its stored result
    is the receipt, so a retry cannot deduct twice) and only a ``completed`` operation consumed
    stock.
    """
    if not (enabled and has_batches):
        return None
    if not has_permission(user, Permission.INVENTORY_MANAGE):
        return 403, {
            "reason": "inventory_deduction_requires_inventory_manage",
            "permission": Permission.INVENTORY_MANAGE.value,
        }
    if not idempotency_key:
        return 428, {"reason": "inventory_deduction_requires_idempotency_key"}
    if status != "completed":
        return 409, {"reason": "inventory_deduction_requires_completed_operation"}
    return None


def plan_inventory_deduction(inputs: Iterable[Any]) -> list[InventoryDeductionLine]:
    """One line per named batch (sorted, the lock order); inputs without a batch are skipped."""
    lines: dict[str, InventoryDeductionLine] = {}
    for i in inputs:
        batch_id = getattr(i, "inventory_batch_id", None)
        if not batch_id:
            continue
        qty = Decimal(str(i.quantity)).quantize(_STOCK_QUANTUM)
        if qty <= 0:
            raise InventoryDeductionRefused(
                422, "inventory_deduction_quantity_must_be_positive", batch_id=batch_id
            )
        prev = lines.get(batch_id)
        if prev is None:
            lines[batch_id] = InventoryDeductionLine(batch_id, i.inventory_item_id, i.unit, qty)
            continue
        if i.inventory_item_id and prev.item_id and i.inventory_item_id != prev.item_id:
            raise InventoryDeductionRefused(409, "inventory_batch_item_mismatch", batch_id=batch_id)
        if _unit_key(i.unit) != _unit_key(prev.unit):
            raise InventoryDeductionRefused(409, "inventory_batch_unit_mismatch", batch_id=batch_id)
        lines[batch_id] = InventoryDeductionLine(
            batch_id, prev.item_id or i.inventory_item_id, prev.unit, prev.quantity + qty
        )
    return [lines[k] for k in sorted(lines)]


_LOCK_BATCH_SQL = """SELECT b.item_id, b.quantity, COALESCE(b.unit, i.unit) AS unit
   FROM inventory_batches b JOIN inventory_items i ON i.item_id = b.item_id
   WHERE b.batch_id = $1 AND b.tenant_id = $2::uuid AND i.tenant_id = $2::uuid
   FOR UPDATE OF b"""
_DEDUCT_BATCH_SQL = """UPDATE inventory_batches SET quantity = quantity - $3::numeric
   WHERE batch_id = $1 AND tenant_id = $2::uuid AND quantity >= $3::numeric
   RETURNING quantity"""


async def apply_inventory_deduction(
    conn, *, tenant_id: str, operation_id: str, plan: Iterable[InventoryDeductionLine]
) -> list[dict[str, Any]]:
    """Lock, check and deduct each planned batch; return one receipt per batch.

    Must run inside the ledger record's transaction: a refusal raises and rolls back the record,
    its inputs and every earlier deduction together. Another tenant's batch reads as absent.
    """
    receipts: list[dict[str, Any]] = []
    for line in plan:
        row = await conn.fetchrow(_LOCK_BATCH_SQL, line.batch_id, tenant_id)
        if row is None:
            raise InventoryDeductionRefused(
                404, "inventory_batch_not_found_for_tenant", batch_id=line.batch_id
            )
        if line.item_id and line.item_id != row["item_id"]:
            raise InventoryDeductionRefused(
                409, "inventory_batch_item_mismatch", batch_id=line.batch_id
            )
        if _unit_key(line.unit) != _unit_key(row["unit"]):
            raise InventoryDeductionRefused(
                409, "inventory_batch_unit_mismatch", batch_id=line.batch_id, unit=row["unit"]
            )
        before = Decimal(row["quantity"])
        after = await conn.fetchval(_DEDUCT_BATCH_SQL, line.batch_id, tenant_id, line.quantity)
        if after is None:
            raise InventoryDeductionRefused(
                409,
                "inventory_batch_insufficient_stock",
                batch_id=line.batch_id,
                requested=float(line.quantity),
                available=float(before),
            )
        receipts.append(
            {
                "operation_id": operation_id,
                "batch_id": line.batch_id,
                "item_id": row["item_id"],
                "unit": row["unit"],
                "quantity_deducted": float(line.quantity),
                "quantity_before": float(before),
                "quantity_after": float(after),
            }
        )
    return receipts


async def fetch_budget_and_actual(conn, tenant_id: str, season_id: str, currency=None):
    """بنود ميزانيّة الموسم وتكاليفه **الفعليّة** فقط (منجَزة وبتاريخٍ لا يتجاوز اليوم).

    نُقِلت من الراوتر (راتشِت الحجم). المخطَّط/الجاري/الملغى والمؤرَّخ مستقبلاً ليس تكلفةً فعليّة
    فلا يدخل الانحرافَ ولا الربحيّة. ``currency`` (مُطبَّعة) تقصر الطرفين على عملةٍ واحدة.
    """
    scope, args = _currency_scope(tenant_id, season_id, currency)
    budget_rows = await conn.fetch(
        f"""SELECT budget_line_id, season_id, stage, category, planned_quantity, unit,
                  planned_unit_cost, planned_cost, currency, source, editable
           FROM farm_season_budget_lines
           WHERE tenant_id = $1::uuid AND season_id = $2{scope}""",
        *args,
    )
    actual_rows = await conn.fetch(
        f"""SELECT operation_id, season_id, COALESCE(cost_category, operation_type) AS category,
                  'whole_season' AS stage, cost_amount, currency
           FROM farm_operation_ledger
           WHERE tenant_id = $1::uuid AND season_id = $2 AND cost_amount IS NOT NULL
             AND {ACTUAL_OPERATION_SQL}{scope}""",
        *args,
    )
    budgets = [
        SeasonBudgetLine(
            line_id=r["budget_line_id"],
            season_id=r["season_id"],
            category=r["category"],
            stage=r["stage"],
            planned_quantity=r["planned_quantity"],
            unit=r["unit"],
            planned_unit_cost=r["planned_unit_cost"],
            planned_cost=float(r["planned_cost"] or 0.0),
            currency=r["currency"],
            source=r["source"],
            editable=r["editable"],
        )
        for r in budget_rows
    ]
    actuals = [
        ActualCostLine(
            source_id=r["operation_id"],
            season_id=r["season_id"],
            category=r["category"],
            stage=r["stage"],
            actual_cost=float(r["cost_amount"] or 0.0),
            currency=r["currency"],
        )
        for r in actual_rows
    ]
    return budgets, actuals


#: v247: an operation may name one task, and only inside the field it is recorded for.
TASK_IN_FIELD_SQL = (
    "SELECT 1 FROM field_tasks WHERE task_id=$1 AND tenant_id=$2::uuid AND field_id=$3"
)


async def task_link_error(conn, tenant_id: str, task_id, field_id: str | None):
    """Return ``(status, detail)`` when an optional task link is invalid, else ``None``."""
    if task_id is None:
        return None
    if not field_id:
        return 422, "task_link_requires_field"
    if not await conn.fetchval(TASK_IN_FIELD_SQL, task_id, tenant_id, field_id):
        return 404, "task_not_found_in_field"
    return None


#: Tenant-scope lookups of the operations ledger (moved from the router for its size ratchet).
_TENANT_SCOPE_SQL: dict[str, tuple[str, str]] = {
    # W1-14 (business-1): a season is an agronomic season (``seasons``, the table farmers write)
    # or a ledger season project, exactly as the simple farm book accepts it. v281 replaced the
    # foreign keys to farm_season_projects (no writer) with a trigger checking the same union.
    "season": (
        "SELECT 1 FROM seasons WHERE tenant_id = $1::uuid AND season_id = $2"
        " UNION ALL"
        " SELECT 1 FROM farm_season_projects WHERE tenant_id = $1::uuid AND season_id = $2"
        " LIMIT 1",
        "season_not_found_for_tenant",
    ),
    "production_unit": (
        "SELECT 1 FROM farm_production_units WHERE tenant_id = $1::uuid AND production_unit_id = $2",
        "production_unit_not_found_for_tenant",
    ),
    "farm": (
        "SELECT 1 FROM farms WHERE tenant_id = $1::uuid AND farm_id = $2",
        "farm_not_found_for_tenant",
    ),
}


async def missing_tenant_scope(conn, tenant_id: str, kind: str, value: str | None) -> str | None:
    """The 404 detail when ``value`` is set and not owned by the tenant; ``None`` otherwise."""
    if not value:
        return None
    sql, detail = _TENANT_SCOPE_SQL[kind]
    return None if await conn.fetchval(sql, tenant_id, value) == 1 else detail


def normalize_currency(currency: str | None) -> str | None:
    """ISO-like currency code as stored for comparison (``" usd "`` → ``"USD"``); blank → None."""
    text = (currency or "").strip().upper()
    return text or None


class MixedCurrencyError(ValueError):
    """A season (or a summary scope) holds amounts in more than one currency.

    Business-2: amounts in different currencies were summed under one label (``YER`` by
    default). A report is in one currency: the caller names it (``?currency=``) or the scope
    must hold exactly one. The router turns this into HTTP 409 listing the currencies found.
    """

    def __init__(self, currencies: list[str]):
        self.currencies = sorted(currencies)
        super().__init__("mixed_currency")

    def detail(self) -> dict:
        return {
            "code": "mixed_currency",
            "currencies": self.currencies,
            "message": "amounts are recorded in more than one currency: pass ?currency=",
        }


#: Distinct currencies of a season's amounts: budget lines, priced operations, revenue.
#: An unpriced operation carries no amount, so its (default) currency is not counted.
SEASON_CURRENCIES_SQL = """
    SELECT DISTINCT upper(trim(currency)) AS currency FROM (
        SELECT currency FROM farm_season_budget_lines
         WHERE tenant_id = $1::uuid AND season_id = $2
        UNION ALL
        SELECT currency FROM farm_operation_ledger
         WHERE tenant_id = $1::uuid AND season_id = $2 AND cost_amount IS NOT NULL
        UNION ALL
        SELECT currency FROM farm_revenue_records
         WHERE tenant_id = $1::uuid AND season_id = $2
    ) amounts ORDER BY 1"""


def resolve_report_currency(currencies, requested: str | None) -> str | None:
    """The one currency a report is in: the requested one, else the only one recorded.

    ``None`` when nothing is recorded and nothing was requested. More than one recorded and
    none requested raises :class:`MixedCurrencyError`: amounts are never summed across
    currencies.
    """
    requested = normalize_currency(requested)
    if requested is not None:
        return requested
    found = sorted({c for c in (normalize_currency(x) for x in currencies) if c})
    if len(found) > 1:
        raise MixedCurrencyError(found)
    return found[0] if found else None


async def season_report_currency(conn, tenant_id: str, season_id: str, requested=None):
    """:func:`resolve_report_currency` over the season's recorded amounts."""
    if normalize_currency(requested) is not None:
        return normalize_currency(requested)
    rows = await conn.fetch(SEASON_CURRENCIES_SQL, tenant_id, season_id)
    return resolve_report_currency([r["currency"] for r in rows], None)


def _currency_scope(tenant_id: str, season_id: str, currency: str | None):
    if currency is None:
        return "", (tenant_id, season_id)
    return " AND upper(trim(currency)) = $3", (tenant_id, season_id, currency)


async def scope_report_currency(conn, where_sql: str, args, requested=None) -> str | None:
    """One currency for a filtered ledger scope (business-2): the one named, else the only one.

    ``where_sql`` filters ``farm_operation_ledger o`` with ``args``; several currencies and none
    named raise ``MixedCurrencyError`` (409 at the route).
    """
    cur = normalize_currency(requested)
    if cur is not None:
        return cur
    found = await conn.fetch(
        f"""SELECT DISTINCT upper(trim(o.currency)) AS currency
            FROM farm_operation_ledger o
            WHERE {where_sql} AND o.cost_amount IS NOT NULL""",
        *args,
    )
    return resolve_report_currency([r["currency"] for r in found], None)


def planned_totals_by_currency(rows) -> tuple[dict[str, float], str | None]:
    """Budget totals per currency, never one sum across them (business-2), and the single one."""
    totals: dict[str, float] = {}
    for r in rows:
        key = normalize_currency(r["currency"]) or "UNKNOWN"
        totals[key] = totals.get(key, 0.0) + float(r["planned_cost"] or 0.0)
    return totals, (next(iter(totals)) if len(totals) == 1 else None)


def money_filter_sql(param: int) -> str:
    """Business-2: the amounts of a report in one currency, parameter ``$param`` (text).

    Used as ``FILTER (WHERE ...)`` on money sums only, so counts, water, energy and hours keep
    every operation of the scope. A ``NULL`` currency (nothing priced in scope) matches no row.
    """
    return f"upper(trim(currency)) IS NOT DISTINCT FROM ${param}::text"


async def fetch_unpriced_categories(conn, tenant_id: str, season_id: str, currency=None):
    """Completed operations with no recorded cost, per category, in the report's currency.

    Ledger operations carry no budget stage (actuals are keyed ``whole_season``), so an
    unpriced operation makes its whole category incomplete, whatever the budget stage.

    ``currency`` (normalised) keeps the operations recorded in that currency: an unpriced
    operation leaves its category incomplete only in the report of the currency it is recorded
    in. Unpriced work recorded in another currency is listed apart
    (:func:`fetch_unpriced_other_currencies`), never folded into this report's coverage.
    """
    scope, args = _currency_scope(tenant_id, season_id, currency)
    rows = await conn.fetch(
        f"""SELECT 'whole_season' AS stage, COALESCE(cost_category, operation_type) AS category,
                   COUNT(*)::int AS unpriced_operations
            FROM farm_operation_ledger
            WHERE tenant_id = $1::uuid AND season_id = $2 AND cost_amount IS NULL
              AND {ACTUAL_OPERATION_SQL}{scope}
            GROUP BY COALESCE(cost_category, operation_type) ORDER BY category""",
        *args,
    )
    return [dict(row) for row in rows]


async def fetch_unpriced_other_currencies(conn, tenant_id: str, season_id: str, currency):
    """Unpriced completed work recorded in a currency other than the report's ``currency``.

    Shown beside the report so it is not silent, but it does not change this currency's
    coverage or variance: the row says its cost will be in another currency. The database
    cannot tell a currency the writer chose from the column default (``YER``), so a writer that
    omits the currency of an unpriced operation in a non-YER season sees it listed here. With no
    report currency (nothing priced in scope) every unpriced row is already in the report.
    """
    if currency is None:
        return []
    rows = await conn.fetch(
        f"""SELECT upper(trim(currency)) AS currency,
                   COALESCE(cost_category, operation_type) AS category,
                   COUNT(*)::int AS unpriced_operations
            FROM farm_operation_ledger
            WHERE tenant_id = $1::uuid AND season_id = $2 AND cost_amount IS NULL
              AND {ACTUAL_OPERATION_SQL}
              AND upper(trim(currency)) IS DISTINCT FROM $3::text
            GROUP BY 1, 2 ORDER BY 1, 2""",
        tenant_id,
        season_id,
        currency,
    )
    return [dict(row) for row in rows]


async def fetch_unpriced_work(conn, tenant_id: str, season_id: str, currency):
    """``(incomplete, other_currencies)`` for :func:`priced_variance`, in one call."""
    incomplete = await fetch_unpriced_categories(conn, tenant_id, season_id, currency)
    other = await fetch_unpriced_other_currencies(conn, tenant_id, season_id, currency)
    return incomplete, other


def priced_variance(
    budgets, actuals, incomplete: list[dict], other_currencies: list[dict] | None = None
) -> tuple[list, dict]:
    """Drop variance lines whose category has unpriced work: a missing cost is not a saving.

    ``incomplete`` is the report currency's unpriced work only; ``other_currencies`` (unpriced
    work recorded in other currencies) is reported beside it and changes nothing here.
    """
    variance = compute_variances(budgets, actuals)
    categories = {row["category"] for row in incomplete}
    coverage = {
        "cost_coverage": "partial" if incomplete else "recorded_operations",
        "unpriced_operations": sum(row["unpriced_operations"] for row in incomplete),
        "incomplete_categories": incomplete,
    }
    if other_currencies is not None:  # the routes always pass it
        coverage["unpriced_in_other_currencies"] = list(other_currencies)
    return [line for line in variance if line.category not in categories], coverage


async def fetch_season_revenue(conn, tenant_id: str, season_id: str, currency=None) -> float:
    """Recorded season revenue (moved from the router: size ratchet).

    ``currency`` (normalised) restricts the sum to one currency (business-2).
    """
    scope, args = _currency_scope(tenant_id, season_id, currency)
    row = await conn.fetchrow(
        f"""SELECT COALESCE(SUM(amount), 0)::float AS revenue
           FROM farm_revenue_records WHERE tenant_id = $1::uuid AND season_id = $2{scope}""",
        *args,
    )
    return float(row["revenue"] or 0.0)


async def fetch_ledger_summary_for_season(
    conn, tenant_id: str, season_id: str, currency: str | None
) -> LedgerSummary:
    """Season summary; money sums only in ``currency`` (business-2), the rest over every row."""
    money = money_filter_sql(3)
    row = await conn.fetchrow(
        f"""WITH ops AS (
            SELECT * FROM farm_operation_ledger WHERE tenant_id = $1::uuid AND season_id = $2
              AND {ACTUAL_OPERATION_SQL}
        )
        SELECT
            COUNT(*)::int AS operation_count,
            COALESCE(SUM(cost_amount) FILTER (WHERE {money}), 0)::float AS total_cost,
            COALESCE(SUM(cost_amount) FILTER (WHERE {money} AND cost_category IN ('administration','overhead','supervision','security','management')), 0)::float AS indirect_cost,
            COALESCE(SUM(cost_amount) FILTER (WHERE {money} AND sync_status IN ('ready_for_sync','synced','sync_failed')), 0)::float AS syncable_cost,
            (SELECT SUM(water_volume_m3) FROM farm_water_records w JOIN ops ON ops.operation_id = w.operation_id)::float AS water_volume_m3,
            (SELECT COUNT(*) FROM farm_water_records w JOIN ops ON ops.operation_id = w.operation_id)::int AS water_records_total,
            (SELECT COUNT(water_volume_m3) FROM farm_water_records w JOIN ops ON ops.operation_id = w.operation_id)::int AS water_records_measured,
            COALESCE((SELECT SUM(kwh) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS energy_kwh,
            COALESCE((SELECT SUM(diesel_liters) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS diesel_liters,
            COALESCE((SELECT SUM(hours_worked) FROM farm_equipment_records q JOIN ops ON ops.operation_id = q.operation_id), 0)::float AS equipment_hours,
            COALESCE((SELECT SUM(hours) FROM farm_labor_records l JOIN ops ON ops.operation_id = l.operation_id), 0)::float AS labor_hours
        FROM ops""",
        tenant_id,
        season_id,
        currency,
    )
    breakdown_rows = await conn.fetch(
        f"""SELECT COALESCE(cost_category, 'uncategorized') AS category,
                  COALESCE(SUM(cost_amount) FILTER (WHERE {money}), 0)::float AS amount
           FROM farm_operation_ledger
           WHERE tenant_id = $1::uuid AND season_id = $2 AND {ACTUAL_OPERATION_SQL}
           GROUP BY COALESCE(cost_category, 'uncategorized')""",
        tenant_id,
        season_id,
        currency,
    )
    total = float(row["total_cost"] or 0.0)
    indirect = float(row["indirect_cost"] or 0.0)
    return LedgerSummary(
        total_cost=total,
        direct_cost=total - indirect,
        indirect_cost=indirect,
        currency=currency or "YER",  # nothing priced: every sum is 0
        cost_breakdown={r["category"]: float(r["amount"] or 0.0) for r in breakdown_rows},
        **water_summary_from_row(row),
        energy_kwh=float(row["energy_kwh"] or 0.0),
        diesel_liters=float(row["diesel_liters"] or 0.0),
        equipment_hours=float(row["equipment_hours"] or 0.0),
        labor_hours=float(row["labor_hours"] or 0.0),
        input_quantities={},
        record_count=int(row["operation_count"] or 0),
        syncable_cost=float(row["syncable_cost"] or 0.0),
        control_only=float(row["syncable_cost"] or 0.0) == 0.0,
    )


# ─── Governance farm context (W1-12) ──────────────────────────────────────────────────
# Kept in this module (not a new platform module: test_p0_platform_module_growth_guard).
# server-side farm facts for the governance gate (W1-12).
#
# guardrails-engine asks for farm economics and seasonal water before it rules on a spending
# action (``services/guardrails-engine/contracts.py``). Those facts are recorded in the farm
# operations ledger, the revenue records, the water records and ``water_ledger``, and nothing
# read them (findings x-3, airuntime-3). This module reads them, for one tenant, and returns a
# ``farm_context`` whose every value carries its source.
#
# Rules (fail closed: an absent key makes the gate return ``evidence_unavailable``, never a
# guess):
#
# - Amounts are never converted between currencies and never summed across them. The
#   guardrails keys are in USD, so ``annual_*_usd`` / ``season_*_usd`` are emitted only when every
#   amount in their scope is recorded in USD. Other currencies stay in per-currency blocks.
# - No recorded row is not zero: costs or revenue with no rows are unavailable, not ``0``.
# - Costs with unpriced completed work are incomplete, so the cost total is not emitted (a
#   missing cost would read as a lower cost).
# - ``cash_reserve_usd`` has no server source today and is always unavailable.
# - Water: a day's metered volume (``farm_water_records``) wins over the ``water_ledger``
#   irrigation depth for the same day (no double count); a day with an unmeasured record and no
#   ledger depth makes the season total incomplete, so it is not emitted.
#
# The caller passes a connection already scoped to the tenant (``tenant_connection``); every
# query also binds ``tenant_id`` explicitly.
SCHEMA = "sahool.governance_farm_context/v1"
ANNUAL_WINDOW_DAYS = 365
NO_SERVER_SOURCE = "no_server_source"

#: ``fields.water_source`` vocabulary (well/canal/river/rainfed/tank/mixed) to the classes
#: guardrails accepts. Anything else (rainfed, tank, free text) is not mapped.
WATER_SOURCE_CLASS = {
    "well": "groundwater",
    "groundwater": "groundwater",
    "borehole": "groundwater",
    "canal": "surface",
    "river": "surface",
    "surface": "surface",
    "mixed": "mixed",
}

_FIELD_SQL = """SELECT field_id, farm_id, area_ha, water_source
                FROM fields WHERE tenant_id = $1::uuid AND field_id = $2"""

_SEASON_SQL = """
    SELECT 'seasons' AS source, field_id,
           COALESCE(sowing_date, plowing_date, land_leveling_date) AS start_date,
           season_end AS end_date
      FROM seasons WHERE tenant_id = $1::uuid AND season_id = $2
    UNION ALL
    SELECT 'farm_season_projects', NULL, start_date, end_date
      FROM farm_season_projects WHERE tenant_id = $1::uuid AND season_id = $2
    LIMIT 1"""

_SEASON_COSTS_SQL = f"""
    SELECT upper(trim(currency)) AS currency,
           SUM(cost_amount)::float AS amount,
           COUNT(*) FILTER (WHERE cost_amount IS NOT NULL)::int AS priced,
           COUNT(*) FILTER (WHERE cost_amount IS NULL)::int AS unpriced
      FROM farm_operation_ledger
     WHERE tenant_id = $1::uuid AND season_id = $2 AND {ACTUAL_OPERATION_SQL}
     GROUP BY 1 ORDER BY 1"""

_SEASON_REVENUE_SQL = """
    SELECT upper(trim(currency)) AS currency, SUM(amount)::float AS amount, COUNT(*)::int AS rows
      FROM farm_revenue_records WHERE tenant_id = $1::uuid AND season_id = $2
     GROUP BY 1 ORDER BY 1"""

_ANNUAL_COSTS_SQL = f"""
    SELECT upper(trim(currency)) AS currency,
           SUM(cost_amount)::float AS amount,
           COUNT(*) FILTER (WHERE cost_amount IS NOT NULL)::int AS priced,
           COUNT(*) FILTER (WHERE cost_amount IS NULL)::int AS unpriced
      FROM farm_operation_ledger
     WHERE tenant_id = $1::uuid AND operation_date >= $2 AND {ACTUAL_OPERATION_SQL}
     GROUP BY 1 ORDER BY 1"""

_ANNUAL_REVENUE_SQL = """
    SELECT upper(trim(currency)) AS currency, SUM(amount)::float AS amount, COUNT(*)::int AS rows
      FROM farm_revenue_records
     WHERE tenant_id = $1::uuid AND revenue_date >= $2 AND revenue_date <= $3
     GROUP BY 1 ORDER BY 1"""

#: Water records of the field in the season: linked to a completed operation of the season,
#: or unlinked to any season and dated inside the season window. The operation filter is
#: ``ACTUAL_OPERATION_SQL`` qualified by the join alias.
_FARM_WATER_SQL = """
    SELECT w.record_date, w.water_volume_m3
      FROM farm_water_records w
      LEFT JOIN farm_operation_ledger o
        ON o.operation_id = w.operation_id AND o.tenant_id = w.tenant_id
     WHERE w.tenant_id = $1::uuid AND w.field_id = $2
       AND (o.operation_id IS NULL
            OR (o.status = 'completed' AND o.operation_date <= CURRENT_DATE))
       AND (o.season_id = $3
            OR (o.season_id IS NULL AND $4::date IS NOT NULL
                AND w.record_date >= $4::date AND w.record_date <= $5::date))"""

_WATER_LEDGER_SQL = """
    SELECT ledger_date, irrigation_mm
      FROM water_ledger
     WHERE tenant_id = $1::uuid AND field_id = $2
       AND ledger_date >= $3::date AND ledger_date <= $4::date
       AND irrigation_mm IS NOT NULL"""


def _positive_float(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and v == v and v != float("inf") else None


def _by_currency(rows: Iterable[Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        key = normalize_currency(r["currency"]) or "UNKNOWN"
        if r["amount"] is not None:
            out[key] = out.get(key, 0.0) + float(r["amount"])
    return out


def usd_total(
    amounts: dict[str, float], *, rows: int, unpriced: int = 0
) -> tuple[float | None, str]:
    """The USD total of a scope and why it is (not) available.

    Only a scope with recorded rows, all priced, all in USD, has a USD total.
    """
    if rows == 0:
        return None, "no_recorded_rows"
    if unpriced:
        return None, f"unpriced_operations:{unpriced}"
    currencies = sorted(amounts)
    if currencies != ["USD"]:
        return None, "currency_not_usd:" + ",".join(currencies)
    return round(amounts["USD"], 2), "ok"


def merge_season_water(
    farm_records: Iterable[tuple[date, float | None]],
    ledger_days: Iterable[tuple[date, float]],
    area_ha: float | None,
) -> dict[str, Any]:
    """Season water of one field from metered records and ``water_ledger`` depths.

    Per day: the metered volume wins; else the ledger depth (``1 mm × 1 ha = 10 m³``); a day
    whose only record is unmeasured makes the total incomplete. ``m3_ha`` is ``None`` unless the
    area is known and every day with water is measured.
    """
    metered: dict[date, float] = {}
    unmeasured: set[date] = set()
    for day, volume in farm_records:
        if volume is None:
            unmeasured.add(day)
        else:
            metered[day] = metered.get(day, 0.0) + float(volume)
    ledger: dict[date, float] = {}
    for day, mm in ledger_days:
        ledger[day] = ledger.get(day, 0.0) + float(mm)

    ledger_only = {d: mm for d, mm in ledger.items() if d not in metered}
    uncovered = sorted(d for d in unmeasured if d not in metered and d not in ledger)
    total_m3: float | None = sum(metered.values())
    if ledger_only:
        total_m3 = None if area_ha is None else total_m3 + sum(ledger_only.values()) * 10 * area_ha
    days = len(set(metered) | set(ledger_only) | set(uncovered))
    complete = not uncovered and total_m3 is not None
    m3_ha = (
        round(total_m3 / area_ha, 3)
        if complete and days and area_ha is not None and total_m3 is not None
        else None
    )
    reason = "ok"
    if not days:
        reason = "no_water_records"
    elif area_ha is None:
        reason = "field_area_unavailable"
    elif uncovered:
        reason = f"unmeasured_days:{len(uncovered)}"
    return {
        "m3_ha": m3_ha,
        "reason": reason,
        "total_m3": round(total_m3, 3) if total_m3 is not None else None,
        "days": days,
        "metered_days": len(metered),
        "ledger_days": len(ledger_only),
        "unmeasured_days": len(uncovered),
    }


async def build_governance_farm_context(
    conn,
    tenant_id: str,
    *,
    field_id: str | None = None,
    season_id: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Read the tenant's recorded farm facts into a guardrails ``farm_context``.

    Top-level guardrails keys are present only when sourced; ``provenance`` names the source of
    each, and ``unavailable`` the reason for each key that is absent.
    """
    today = today or datetime.now(UTC).date()
    ctx: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    unavailable: dict[str, str] = {}

    def emit(key: str, value: Any, source: dict[str, Any]) -> None:
        ctx[key] = value
        provenance[key] = source

    # ── field: area and water source ───────────────────────────────────────────────
    area: float | None = None
    field_row = None
    if field_id:
        field_row = await conn.fetchrow(_FIELD_SQL, tenant_id, field_id)
        if field_row is None:
            unavailable["field"] = "field_not_found_for_tenant"
    if field_row is not None:
        area = _positive_float(field_row["area_ha"])
        field_src = {"source": "fields", "field_id": field_id, "column": None}
        if area is not None:
            emit("field_area_ha", area, {**field_src, "column": "area_ha"})
        else:
            unavailable["field_area_ha"] = "area_not_recorded"
        raw_source = (field_row["water_source"] or "").strip().lower() or None
        water_class = WATER_SOURCE_CLASS.get(raw_source or "")
        if water_class:
            emit(
                "water_source",
                water_class,
                {**field_src, "column": "water_source", "recorded_value": raw_source},
            )
        else:
            unavailable["water_source"] = (
                f"unmapped_water_source:{raw_source}" if raw_source else "water_source_not_recorded"
            )
    elif not field_id:
        unavailable["field"] = "no_field_in_context"

    # ── season: costs, revenue, water ──────────────────────────────────────────────
    season = None
    if season_id:
        season = await conn.fetchrow(_SEASON_SQL, tenant_id, season_id)
        if season is None:
            unavailable["season"] = "season_not_found_for_tenant"
        elif field_id and season["field_id"] and season["field_id"] != field_id:
            unavailable["season"] = "season_not_for_field"
            season = None
    else:
        unavailable["season"] = "no_season_in_context"

    if season is not None:
        costs = await conn.fetch(_SEASON_COSTS_SQL, tenant_id, season_id)
        revenue = await conn.fetch(_SEASON_REVENUE_SQL, tenant_id, season_id)
        cost_amounts, revenue_amounts = _by_currency(costs), _by_currency(revenue)
        priced = sum(r["priced"] for r in costs)
        unpriced = sum(r["unpriced"] for r in costs)
        revenue_rows = sum(r["rows"] for r in revenue)
        season_src = {
            "season_id": season_id,
            "season_source": season["source"],
            "prediction": False,
        }
        ctx["season_economics"] = {
            **season_src,
            "costs_by_currency": cost_amounts,
            "revenue_by_currency": revenue_amounts,
            "priced_operations": priced,
            "unpriced_operations": unpriced,
            "cost_coverage": "partial" if unpriced else "recorded_operations",
            "revenue_records": revenue_rows,
            "source": ["farm_operation_ledger", "farm_revenue_records"],
        }
        value, why = usd_total(cost_amounts, rows=priced + unpriced, unpriced=unpriced)
        if value is not None:
            emit("season_costs_usd", value, {**season_src, "source": "farm_operation_ledger"})
        else:
            unavailable["season_costs_usd"] = why
        value, why = usd_total(revenue_amounts, rows=revenue_rows)
        if value is not None:
            emit("season_revenue_usd", value, {**season_src, "source": "farm_revenue_records"})
        else:
            unavailable["season_revenue_usd"] = why

        if field_id and field_row is not None:
            start, end = season["start_date"], season["end_date"] or today
            end = min(end, today)
            farm_rows = await conn.fetch(
                _FARM_WATER_SQL, tenant_id, field_id, season_id, start, end
            )
            ledger_rows = (
                await conn.fetch(_WATER_LEDGER_SQL, tenant_id, field_id, start, end)
                if start is not None
                else []
            )
            water = merge_season_water(
                [(r["record_date"], r["water_volume_m3"]) for r in farm_rows],
                [(r["ledger_date"], r["irrigation_mm"]) for r in ledger_rows],
                area,
            )
            window = {
                "from": start.isoformat() if start else None,
                "to": end.isoformat(),
            }
            ctx["season_water"] = {**water, "window": window, "field_id": field_id}
            if water["m3_ha"] is not None:
                emit(
                    "season_water_used_m3_ha",
                    water["m3_ha"],
                    {
                        **season_src,
                        "field_id": field_id,
                        "window": window,
                        "source": ["farm_water_records", "water_ledger", "fields.area_ha"],
                        "method": "metered volume per day, else water_ledger irrigation_mm x 10 x area",
                    },
                )
            else:
                unavailable["season_water_used_m3_ha"] = water["reason"]
        else:
            unavailable["season_water_used_m3_ha"] = "no_field_in_context"
    else:
        unavailable.setdefault("season_water_used_m3_ha", unavailable.get("season", ""))

    # ── trailing year, whole tenant ────────────────────────────────────────────────
    since = today - timedelta(days=ANNUAL_WINDOW_DAYS)
    annual_src = {
        "scope": "tenant",
        "window": {"from": since.isoformat(), "to": today.isoformat()},
        "prediction": False,
    }
    costs = await conn.fetch(_ANNUAL_COSTS_SQL, tenant_id, since)
    revenue = await conn.fetch(_ANNUAL_REVENUE_SQL, tenant_id, since, today)
    cost_amounts, revenue_amounts = _by_currency(costs), _by_currency(revenue)
    priced = sum(r["priced"] for r in costs)
    unpriced = sum(r["unpriced"] for r in costs)
    revenue_rows = sum(r["rows"] for r in revenue)
    ctx["annual_economics"] = {
        **annual_src,
        "costs_by_currency": cost_amounts,
        "revenue_by_currency": revenue_amounts,
        "priced_operations": priced,
        "unpriced_operations": unpriced,
        "revenue_records": revenue_rows,
    }
    value, why = usd_total(cost_amounts, rows=priced + unpriced, unpriced=unpriced)
    if value is not None:
        emit("annual_costs_usd", value, {**annual_src, "source": "farm_operation_ledger"})
    else:
        unavailable["annual_costs_usd"] = why
    value, why = usd_total(revenue_amounts, rows=revenue_rows)
    if value is not None:
        emit("annual_revenue_usd", value, {**annual_src, "source": "farm_revenue_records"})
    else:
        unavailable["annual_revenue_usd"] = why

    unavailable["cash_reserve_usd"] = NO_SERVER_SOURCE
    ctx["provenance"] = provenance
    ctx["unavailable"] = {k: v for k, v in unavailable.items() if v}
    ctx["context_schema"] = SCHEMA
    ctx["built_from"] = "server"
    return ctx


FARM_CONTEXT_TIMEOUT_S = 10.0


def threadsafe_farm_context_fn(
    loop: asyncio.AbstractEventLoop,
    open_connection: Callable[[], Any],
    tenant_id: str,
    season_id: str | None,
    *,
    timeout_s: float = FARM_CONTEXT_TIMEOUT_S,
    sink: dict | None = None,
) -> Callable[[str, str | None], dict[str, Any]]:
    """A synchronous ``farm_context_fn(tenant_id, field_id)`` for a worker thread.

    The pest-escalation workflow runs in a thread (``asyncio.to_thread``) while the database
    pool belongs to the request's event loop, so the builder is scheduled back on that loop.
    ``open_connection()`` returns an async context manager yielding a tenant-scoped connection.
    The function raises on a tenant mismatch, a timeout or a database error; the gate turns
    any exception into a block (fail closed). ``sink["farm_context"]`` keeps what was read so
    the caller can expose it in the workflow state.
    """

    async def _load(field_id: str | None) -> dict[str, Any]:
        async with open_connection() as conn:
            return await build_governance_farm_context(
                conn, tenant_id, field_id=field_id, season_id=season_id
            )

    def farm_context_fn(requested_tenant: str, field_id: str | None) -> dict[str, Any]:
        if str(requested_tenant) != str(tenant_id):
            raise PermissionError("farm_context_tenant_mismatch")
        future = asyncio.run_coroutine_threadsafe(_load(field_id), loop)
        try:
            farm = future.result(timeout=timeout_s)
        except BaseException:
            # A timeout must not leave the load holding its pooled connection: cancelling the
            # future cancels the task on the loop, which releases the connection. Still raises.
            future.cancel()
            raise
        if sink is not None:
            sink["farm_context"] = farm
        return farm

    return farm_context_fn
