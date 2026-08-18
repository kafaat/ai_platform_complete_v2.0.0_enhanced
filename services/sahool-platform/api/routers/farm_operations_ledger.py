"""api/routers/farm_operations_ledger.py — Farm Operations Ledger رقابي اختياري.

الميزة خلف FEATURE_FARM_OPERATIONS_LEDGER (OFF افتراضاً). عند تفعيلها تحفظ السجلات
اليومية للأعمال/المياه/الطاقة/المعدات/العمالة/المواد كـ Operational Truth داخل SAHOOL.
لا تزامن ERP ولا قيود محاسبية هنا؛ sync_status يعلن فقط قابلية الترحيل لاحقاً.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

from core.farm_closed_loop import (
    OperationEvent,
    ResourceUse,
    build_economic_state,
    build_inventory_projection,
    operation_event_to_ledger_payload,
)
from core.farm_costing import (
    ActualCostLine,
    SeasonBudgetLine,
    compute_profitability,
    compute_variances,
    generate_cost_recommendations,
    normalize_budget_line,
    project_to_erp_lines,
)
from core.erp_projection_contract import build_projection_envelope
from core.farm_operations_ledger import LedgerSummary
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.feature_registry import is_enabled
from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()
_FLAG = "FEATURE_FARM_OPERATIONS_LEDGER"


def _enabled() -> bool:
    return is_enabled(_FLAG, os.getenv("FEATURE_FARM_OPERATIONS_LEDGER", ""))


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="farm_operations_ledger_disabled")


async def _assert_season_in_tenant(conn, tenant_id: str, season_id: str | None) -> None:
    if not season_id:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM farm_season_projects WHERE tenant_id = $1::uuid AND season_id = $2",
        tenant_id,
        season_id,
    )
    if ok != 1:
        raise HTTPException(status_code=404, detail="season_not_found_for_tenant")


async def _assert_production_unit_in_tenant(
    conn, tenant_id: str, production_unit_id: str | None
) -> None:
    if not production_unit_id:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM farm_production_units WHERE tenant_id = $1::uuid AND production_unit_id = $2",
        tenant_id,
        production_unit_id,
    )
    if ok != 1:
        raise HTTPException(status_code=404, detail="production_unit_not_found_for_tenant")


async def _assert_farm_in_tenant(conn, tenant_id: str, farm_id: str | None) -> None:
    if not farm_id:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM farms WHERE tenant_id = $1::uuid AND farm_id = $2",
        tenant_id,
        farm_id,
    )
    if ok != 1:
        raise HTTPException(status_code=404, detail="farm_not_found_for_tenant")


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
    quantity: float
    unit: str
    estimated_cost: float | None = None
    notes: str | None = None

    @field_validator("quantity", "estimated_cost")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class OperationLedgerIn(BaseModel):
    operation_date: date
    operation_type: str
    season_id: str | None = None
    production_unit_id: str | None = None
    farm_id: str | None = None
    field_id: str | None = None
    execution_mode: str = "self"
    contractor_id: str | None = None
    status: str = "completed"
    notes: str | None = None
    cost_amount: float | None = None
    cost_category: str | None = None
    currency: str = "YER"
    sync_status: str = "control_only"
    water: WaterRecordIn | None = None
    energy: EnergyRecordIn | None = None
    equipment: list[EquipmentRecordIn] = Field(default_factory=list)
    labor: list[LaborRecordIn] = Field(default_factory=list)
    inputs: list[InputRecordIn] = Field(default_factory=list)

    @field_validator("cost_amount")
    @classmethod
    def _cost_positive(cls, v):
        return _non_negative_or_none(v, "cost_amount")


@router.post("/api/v1/farm-ledger/operations", status_code=201)
async def create_operation_ledger_record(
    req: OperationLedgerIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    """يحفظ سجل عمل يوميّاً ومرفقاته الرقابية. لا يزامن ERP ولا يخصم مخزوناً هنا."""
    _require_enabled()
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="farm_operations_ledger_database_unavailable")
    if not (req.field_id or req.production_unit_id or req.farm_id):
        raise HTTPException(status_code=422, detail="field_or_production_unit_or_farm_required")
    operation_id = "oplog_" + uuid.uuid4().hex[:12]
    try:
        async with tenant_connection(user) as conn:
            tenant_id = str(user.tenant_id)
            if req.field_id:
                await _assert_field_in_tenant(conn, req.field_id)
            await _assert_season_in_tenant(conn, tenant_id, req.season_id)
            await _assert_production_unit_in_tenant(conn, tenant_id, req.production_unit_id)
            await _assert_farm_in_tenant(conn, tenant_id, req.farm_id)
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO farm_operation_ledger
                       (operation_id, tenant_id, season_id, production_unit_id, farm_id, field_id,
                        operation_type, operation_date, execution_mode, contractor_id, status,
                        notes, cost_amount, cost_category, currency, sync_status, created_by,
                        created_at, updated_at)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                               $12, $13, $14, $15, $16, $17, now(), now())""",
                    operation_id,
                    str(user.tenant_id),
                    req.season_id,
                    req.production_unit_id,
                    req.farm_id,
                    req.field_id,
                    req.operation_type,
                    req.operation_date,
                    req.execution_mode,
                    req.contractor_id,
                    req.status,
                    req.notes,
                    req.cost_amount,
                    req.cost_category,
                    req.currency,
                    req.sync_status,
                    user.user_id,
                )
                if req.water:
                    await conn.execute(
                        """INSERT INTO farm_water_records
                           (tenant_id, operation_id, record_date, farm_id, field_id, well_id, pump_id,
                            pivot_id, hours_operated, water_volume_m3, measurement_method, notes)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                        str(user.tenant_id),
                        operation_id,
                        req.operation_date,
                        req.farm_id,
                        req.field_id,
                        req.water.well_id,
                        req.water.pump_id,
                        req.water.pivot_id,
                        req.water.hours_operated,
                        req.water.water_volume_m3,
                        req.water.measurement_method,
                        req.water.notes,
                    )
                if req.energy:
                    await conn.execute(
                        """INSERT INTO farm_energy_records
                           (tenant_id, operation_id, record_date, energy_source, kwh, diesel_liters,
                            hours_operated, equipment_id, well_id, pivot_id, notes)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                        str(user.tenant_id),
                        operation_id,
                        req.operation_date,
                        req.energy.energy_source,
                        req.energy.kwh,
                        req.energy.diesel_liters,
                        req.energy.hours_operated,
                        req.energy.equipment_id,
                        req.energy.well_id,
                        req.energy.pivot_id,
                        req.energy.notes,
                    )
                for e in req.equipment:
                    await conn.execute(
                        """INSERT INTO farm_equipment_records
                           (tenant_id, operation_id, record_date, equipment_id, operator_id, hours_worked,
                            fuel_liters, maintenance_cost, notes)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)""",
                        str(user.tenant_id),
                        operation_id,
                        req.operation_date,
                        e.equipment_id,
                        e.operator_id,
                        e.hours_worked,
                        e.fuel_liters,
                        e.maintenance_cost,
                        e.notes,
                    )
                for labor in req.labor:
                    await conn.execute(
                        """INSERT INTO farm_labor_records
                           (tenant_id, operation_id, record_date, worker_id, workers_count, hours,
                            wage_amount, notes)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)""",
                        str(user.tenant_id),
                        operation_id,
                        req.operation_date,
                        labor.worker_id,
                        labor.workers_count,
                        labor.hours,
                        labor.wage_amount,
                        labor.notes,
                    )
                for i in req.inputs:
                    await conn.execute(
                        """INSERT INTO farm_input_records
                           (tenant_id, operation_id, record_date, input_type, inventory_item_id, quantity,
                            unit, estimated_cost, notes)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)""",
                        str(user.tenant_id),
                        operation_id,
                        req.operation_date,
                        i.input_type,
                        i.inventory_item_id,
                        i.quantity,
                        i.unit,
                        i.estimated_cost,
                        i.notes,
                    )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حفظ سجل العمليات الزراعية", e) from e
    return {
        "operation_id": operation_id,
        "persisted": True,
        "sync_status": req.sync_status,
        "message_ar": "حُفظ سجل العملية الزراعية",
    }


@router.get("/api/v1/farm-ledger/operations")
async def list_operation_ledger_records(
    field_id: str | None = None,
    season_id: str | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    _require_enabled()
    if _DB_POOL is None:
        return {"entries": [], "total": 0, "note_ar": "القاعدة غير مفعلة"}
    clauses = ["tenant_id = $1::uuid"]
    args: list = [str(user.tenant_id)]
    if field_id:
        args.append(field_id)
        clauses.append(f"field_id = ${len(args)}")
    if season_id:
        args.append(season_id)
        clauses.append(f"season_id = ${len(args)}")
    if date_from:
        args.append(date_from)
        clauses.append(f"operation_date >= ${len(args)}")
    if date_to:
        args.append(date_to)
        clauses.append(f"operation_date <= ${len(args)}")
    try:
        async with tenant_connection(user) as conn:
            if field_id:
                await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                "SELECT operation_id, season_id, production_unit_id, farm_id, field_id, "
                "operation_type, operation_date, execution_mode, contractor_id, status, "
                "cost_amount, cost_category, currency, sync_status, notes "
                "FROM farm_operation_ledger WHERE "
                + " AND ".join(clauses)
                + " ORDER BY operation_date DESC, created_at DESC LIMIT 500",
                *args,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("جلب سجل العمليات الزراعية", e) from e
    return {
        "entries": [dict(r) | {"operation_date": r["operation_date"].isoformat()} for r in rows],
        "total": len(rows),
    }


@router.get("/api/v1/farm-ledger/summary")
async def farm_ledger_summary(
    field_id: str | None = None,
    season_id: str | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """ملخّص رقابي/تكلفة مبسّط من السجلات. لا يختلق أرقاماً ولا يزامن ERP."""
    _require_enabled()
    if _DB_POOL is None:
        return {"summary": None, "note_ar": "القاعدة غير مفعلة"}
    clauses = ["o.tenant_id = $1::uuid"]
    args: list = [str(user.tenant_id)]
    if field_id:
        args.append(field_id)
        clauses.append(f"o.field_id = ${len(args)}")
    if season_id:
        args.append(season_id)
        clauses.append(f"o.season_id = ${len(args)}")
    if date_from:
        args.append(date_from)
        clauses.append(f"o.operation_date >= ${len(args)}")
    if date_to:
        args.append(date_to)
        clauses.append(f"o.operation_date <= ${len(args)}")
    where_sql = " AND ".join(clauses)
    try:
        async with tenant_connection(user) as conn:
            if field_id:
                await _assert_field_in_tenant(conn, field_id)
            row = await conn.fetchrow(
                f"""WITH ops AS (
                    SELECT * FROM farm_operation_ledger o WHERE {where_sql}
                )
                SELECT
                    COUNT(*)::int AS operation_count,
                    COALESCE(SUM(cost_amount), 0)::float AS total_cost,
                    COALESCE(SUM(cost_amount) FILTER (WHERE cost_category IN ('administration','overhead','supervision','security','management')), 0)::float AS indirect_cost,
                    COALESCE(SUM(cost_amount) FILTER (WHERE sync_status IN ('ready_for_sync','synced','sync_failed')), 0)::float AS syncable_cost,
                    COALESCE((SELECT SUM(water_volume_m3) FROM farm_water_records w JOIN ops ON ops.operation_id = w.operation_id), 0)::float AS water_volume_m3,
                    COALESCE((SELECT SUM(kwh) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS energy_kwh,
                    COALESCE((SELECT SUM(diesel_liters) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS diesel_liters,
                    COALESCE((SELECT SUM(hours_worked) FROM farm_equipment_records q JOIN ops ON ops.operation_id = q.operation_id), 0)::float AS equipment_hours,
                    COALESCE((SELECT SUM(hours) FROM farm_labor_records l JOIN ops ON ops.operation_id = l.operation_id), 0)::float AS labor_hours
                FROM ops""",
                *args,
            )
            breakdown_rows = await conn.fetch(
                f"""SELECT COALESCE(cost_category, 'uncategorized') AS category,
                           COALESCE(SUM(cost_amount), 0)::float AS amount
                    FROM farm_operation_ledger o WHERE {where_sql}
                    GROUP BY COALESCE(cost_category, 'uncategorized')
                    ORDER BY category""",
                *args,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تلخيص سجل العمليات الزراعية", e) from e
    total = float(row["total_cost"] or 0.0)
    indirect = float(row["indirect_cost"] or 0.0)
    return {
        "summary": {
            "operation_count": row["operation_count"],
            "total_cost": total,
            "direct_cost": total - indirect,
            "indirect_cost": indirect,
            "cost_breakdown": {r["category"]: float(r["amount"] or 0.0) for r in breakdown_rows},
            "water_volume_m3": float(row["water_volume_m3"] or 0.0),
            "energy_kwh": float(row["energy_kwh"] or 0.0),
            "diesel_liters": float(row["diesel_liters"] or 0.0),
            "equipment_hours": float(row["equipment_hours"] or 0.0),
            "labor_hours": float(row["labor_hours"] or 0.0),
            "syncable_cost": float(row["syncable_cost"] or 0.0),
            "control_only": float(row["syncable_cost"] or 0.0) == 0.0,
            "provenance": {"source": "farm_operations_ledger", "erp_synced": False},
        }
    }


class BudgetLineIn(BaseModel):
    budget_line_id: str | None = None
    season_id: str
    stage: str = "whole_season"
    category: str
    planned_quantity: float | None = None
    unit: str | None = None
    planned_unit_cost: float | None = None
    planned_cost: float = 0.0
    currency: str = "YER"
    source: str = "manual"
    editable: bool = True
    notes: str | None = None

    @field_validator("planned_quantity", "planned_unit_cost", "planned_cost")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class BudgetLinesIn(BaseModel):
    lines: list[BudgetLineIn]


class RevenueRecordIn(BaseModel):
    revenue_id: str | None = None
    season_id: str
    production_unit_id: str | None = None
    field_id: str | None = None
    revenue_date: date
    product_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    amount: float = 0.0
    currency: str = "YER"
    source: str = "manual"
    notes: str | None = None

    @field_validator("quantity", "unit_price", "amount")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


@router.post("/api/v1/farm-ledger/budgets", status_code=201)
async def upsert_season_budget_lines(
    req: BudgetLinesIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    """يحفظ بنود موازنة الموسم حسب المرحلة والتصنيف. كل القيم قابلة للتعديل ولا تُطبق كقرار تلقائي."""
    _require_enabled()
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="farm_operations_ledger_database_unavailable")
    if not req.lines:
        raise HTTPException(status_code=422, detail="budget_lines_required")
    try:
        async with tenant_connection(user) as conn:
            tenant_id = str(user.tenant_id)
            async with conn.transaction():
                saved = []
                for item in req.lines:
                    await _assert_season_in_tenant(conn, tenant_id, item.season_id)
                    line_id = item.budget_line_id or "bud_" + uuid.uuid4().hex[:12]
                    normalized = normalize_budget_line(
                        SeasonBudgetLine(
                            line_id=line_id,
                            season_id=item.season_id,
                            category=item.category,
                            stage=item.stage,
                            planned_quantity=item.planned_quantity,
                            unit=item.unit,
                            planned_unit_cost=item.planned_unit_cost,
                            planned_cost=item.planned_cost,
                            currency=item.currency,
                            source=item.source,
                            editable=item.editable,
                        )
                    )
                    row = await conn.fetchrow(
                        """INSERT INTO farm_season_budget_lines
                           (budget_line_id, tenant_id, season_id, stage, category, planned_quantity,
                            unit, planned_unit_cost, planned_cost, currency, source, editable,
                            notes, created_by, created_at, updated_at)
                           VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, now(), now())
                           ON CONFLICT (budget_line_id) DO UPDATE SET
                             stage = EXCLUDED.stage,
                             category = EXCLUDED.category,
                             planned_quantity = EXCLUDED.planned_quantity,
                             unit = EXCLUDED.unit,
                             planned_unit_cost = EXCLUDED.planned_unit_cost,
                             planned_cost = EXCLUDED.planned_cost,
                             currency = EXCLUDED.currency,
                             source = EXCLUDED.source,
                             editable = EXCLUDED.editable,
                             notes = EXCLUDED.notes,
                             updated_at = now()
                           WHERE farm_season_budget_lines.tenant_id = EXCLUDED.tenant_id
                           RETURNING budget_line_id""",
                        line_id,
                        str(user.tenant_id),
                        item.season_id,
                        normalized.stage,
                        normalized.category,
                        normalized.planned_quantity,
                        normalized.unit,
                        normalized.planned_unit_cost,
                        normalized.planned_cost,
                        normalized.currency,
                        normalized.source,
                        normalized.editable,
                        item.notes,
                        user.user_id,
                    )
                    if row is None:
                        raise HTTPException(
                            status_code=403, detail="budget_line_not_owned_by_tenant"
                        )
                    saved.append(
                        {"budget_line_id": line_id, "planned_cost": normalized.planned_cost}
                    )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حفظ موازنة الموسم", e) from e
    return {"saved": saved, "message_ar": "حُفظت بنود موازنة الموسم"}


@router.get("/api/v1/farm-ledger/budgets/{season_id}")
async def get_season_budget(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if _DB_POOL is None:
        return {"season_id": season_id, "lines": [], "note_ar": "القاعدة غير مفعلة"}
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """SELECT budget_line_id, season_id, stage, category, planned_quantity, unit,
                          planned_unit_cost, planned_cost, currency, source, editable, notes
                   FROM farm_season_budget_lines
                   WHERE tenant_id = $1::uuid AND season_id = $2
                   ORDER BY stage, category""",
                str(user.tenant_id),
                season_id,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("جلب موازنة الموسم", e) from e
    return {
        "season_id": season_id,
        "lines": [dict(r) for r in rows],
        "total_planned_cost": sum(float(r["planned_cost"] or 0.0) for r in rows),
    }


@router.post("/api/v1/farm-ledger/revenues", status_code=201)
async def create_revenue_record(
    req: RevenueRecordIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    _require_enabled()
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="farm_operations_ledger_database_unavailable")
    revenue_id = req.revenue_id or "rev_" + uuid.uuid4().hex[:12]
    amount = req.amount or ((req.quantity or 0.0) * (req.unit_price or 0.0))
    try:
        async with tenant_connection(user) as conn:
            tenant_id = str(user.tenant_id)
            if req.field_id:
                await _assert_field_in_tenant(conn, req.field_id)
            await _assert_season_in_tenant(conn, tenant_id, req.season_id)
            await _assert_production_unit_in_tenant(conn, tenant_id, req.production_unit_id)
            await conn.execute(
                """INSERT INTO farm_revenue_records
                   (revenue_id, tenant_id, season_id, production_unit_id, field_id, revenue_date,
                    product_name, quantity, unit, unit_price, amount, currency, source, notes, created_by, created_at)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, now())""",
                revenue_id,
                str(user.tenant_id),
                req.season_id,
                req.production_unit_id,
                req.field_id,
                req.revenue_date,
                req.product_name,
                req.quantity,
                req.unit,
                req.unit_price,
                amount,
                req.currency,
                req.source,
                req.notes,
                user.user_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حفظ إيراد الموسم", e) from e
    return {"revenue_id": revenue_id, "amount": amount, "message_ar": "حُفظ سجل الإيراد"}


async def _fetch_budget_and_actual(conn, tenant_id: str, season_id: str):
    budget_rows = await conn.fetch(
        """SELECT budget_line_id, season_id, stage, category, planned_quantity, unit,
                  planned_unit_cost, planned_cost, currency, source, editable
           FROM farm_season_budget_lines
           WHERE tenant_id = $1::uuid AND season_id = $2""",
        tenant_id,
        season_id,
    )
    actual_rows = await conn.fetch(
        """SELECT operation_id, season_id, COALESCE(cost_category, operation_type) AS category,
                  'whole_season' AS stage, cost_amount, currency
           FROM farm_operation_ledger
           WHERE tenant_id = $1::uuid AND season_id = $2 AND cost_amount IS NOT NULL""",
        tenant_id,
        season_id,
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


@router.get("/api/v1/farm-ledger/variance/{season_id}")
async def get_budget_variance(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if _DB_POOL is None:
        return {
            "season_id": season_id,
            "variance": [],
            "recommendations": [],
            "note_ar": "القاعدة غير مفعلة",
        }
    try:
        async with tenant_connection(user) as conn:
            budgets, actuals = await _fetch_budget_and_actual(conn, str(user.tenant_id), season_id)
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحليل انحرافات الموسم", e) from e
    variance = compute_variances(budgets, actuals)
    recs = generate_cost_recommendations(variance)
    return {
        "season_id": season_id,
        "variance": [v.__dict__ for v in variance],
        "recommendations": [r.__dict__ for r in recs],
        "provenance": {"source": "farm_operations_ledger", "prediction": False},
    }


@router.get("/api/v1/farm-ledger/profitability/{season_id}")
async def get_season_profitability(
    season_id: str,
    yield_quantity: float | None = None,
    unit: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if _DB_POOL is None:
        return {"season_id": season_id, "profitability": None, "note_ar": "القاعدة غير مفعلة"}
    try:
        async with tenant_connection(user) as conn:
            _, actuals = await _fetch_budget_and_actual(conn, str(user.tenant_id), season_id)
            rev = await conn.fetchrow(
                """SELECT COALESCE(SUM(amount), 0)::float AS revenue
                   FROM farm_revenue_records WHERE tenant_id = $1::uuid AND season_id = $2""",
                str(user.tenant_id),
                season_id,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحليل ربحية الموسم", e) from e
    profit = compute_profitability(
        season_id,
        revenue=float(rev["revenue"] or 0.0),
        cost_lines=actuals,
        yield_quantity=yield_quantity,
        unit=unit,
    )
    return {
        "season_id": season_id,
        "profitability": profit.__dict__,
        "provenance": {"source": "farm_operations_ledger", "prediction": False},
    }


@router.get("/api/v1/farm-ledger/erp-projection/{season_id}")
async def get_erp_projection(
    season_id: str,
    cost_center: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """يعرض إسقاطاً مالياً قابلاً للترحيل لاحقاً؛ لا يرسل شيئاً إلى ERP من هذا endpoint."""
    _require_enabled()
    if _DB_POOL is None:
        return {"season_id": season_id, "lines": [], "note_ar": "القاعدة غير مفعلة"}
    try:
        async with tenant_connection(user) as conn:
            _, actuals = await _fetch_budget_and_actual(conn, str(user.tenant_id), season_id)
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("إسقاط ERP", e) from e
    lines = project_to_erp_lines(actuals, cost_center=cost_center, project=season_id)
    line_payload = [line.__dict__ for line in lines]
    provider = os.getenv("ERP_PROVIDER", "none").strip().lower() or "none"
    envelope = build_projection_envelope(
        season_id=season_id,
        lines=line_payload,
        provider=provider,
        currency="YER",
    )
    return {
        **envelope,
        "synced": False,
        "provenance": {
            "source": "farm_operations_ledger",
            "erp_write": False,
            "projection_digest": envelope["projection_digest"],
        },
    }


_AUTOWRITE_FLAG = "FEATURE_OPERATION_LEDGER_AUTOWRITE"
_INVENTORY_SYNC_FLAG = "FEATURE_LEDGER_INVENTORY_SYNC"
_CANONICAL_ECONOMICS_FLAG = "FEATURE_CANONICAL_ECONOMICS"


def _flag_enabled(name: str) -> bool:
    return is_enabled(name, os.getenv(name, ""))


class ResourceUseIn(BaseModel):
    resource_type: str
    quantity: float
    unit: str
    estimated_cost: float | None = None
    inventory_item_id: str | None = None

    @field_validator("quantity", "estimated_cost")
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


class OperationEventIn(BaseModel):
    event_id: str | None = None
    occurred_on: date
    operation_type: str
    season_id: str | None = None
    farm_id: str | None = None
    field_id: str | None = None
    production_unit_id: str | None = None
    execution_mode: str = "self"
    cost_category: str | None = None
    cost_amount: float | None = None
    water_m3: float | None = None
    energy_kwh: float | None = None
    diesel_liters: float | None = None
    equipment_hours: float | None = None
    labor_hours: float | None = None
    inputs: list[ResourceUseIn] = Field(default_factory=list)

    @field_validator(
        "cost_amount", "water_m3", "energy_kwh", "diesel_liters", "equipment_hours", "labor_hours"
    )
    @classmethod
    def _positive(cls, v, info):
        return _non_negative_or_none(v, info.field_name)


@router.post("/api/v1/farm-ledger/autowrite-preview")
async def operation_autowrite_preview(
    req: OperationEventIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    """يعرض كيف سيتحوّل حدث عملية إلى سجل رقابي. لا يحفظ شيئاً.

    الكتابة التلقائية الحقيقية تبقى خلف FEATURE_OPERATION_LEDGER_AUTOWRITE، وهذا
    endpoint يساعد على الاختبار والاعتماد دون تغيير سلوك الإنتاج.
    """
    _require_enabled()
    if req.field_id and _DB_POOL is not None:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, req.field_id)
    event = OperationEvent(
        event_id=req.event_id or "evt_" + uuid.uuid4().hex[:12],
        tenant_id=str(user.tenant_id),
        occurred_on=req.occurred_on,
        operation_type=req.operation_type,
        season_id=req.season_id,
        farm_id=req.farm_id,
        field_id=req.field_id,
        production_unit_id=req.production_unit_id,
        execution_mode=req.execution_mode,
        cost_category=req.cost_category,
        cost_amount=req.cost_amount,
        water_m3=req.water_m3,
        energy_kwh=req.energy_kwh,
        diesel_liters=req.diesel_liters,
        equipment_hours=req.equipment_hours,
        labor_hours=req.labor_hours,
        inputs=tuple(
            ResourceUse(i.resource_type, i.quantity, i.unit, i.estimated_cost, i.inventory_item_id)
            for i in req.inputs
        ),
        source="api.autowrite_preview",
    )
    payload = operation_event_to_ledger_payload(event)
    return {
        "autowrite_enabled": _flag_enabled(_AUTOWRITE_FLAG),
        "would_persist": _flag_enabled(_AUTOWRITE_FLAG)
        and payload.get("autowrite_eligible") is True,
        "disabled_reason": None if _flag_enabled(_AUTOWRITE_FLAG) else "feature_flag_off",
        "ledger_payload": payload,
        "provenance": {"source": "farm_operations_ledger", "persisted": False},
    }


@router.get("/api/v1/farm-ledger/inventory-projection/{season_id}")
async def get_inventory_projection(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """إسقاط خصم مخزون من سجلات المواد فقط. لا يكتب في inventory-service."""
    _require_enabled()
    if _DB_POOL is None:
        return {"season_id": season_id, "lines": [], "note_ar": "القاعدة غير مفعلة"}
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """SELECT i.input_type, i.inventory_item_id, SUM(i.quantity)::float AS quantity,
                          i.unit, SUM(COALESCE(i.estimated_cost, 0))::float AS estimated_cost
                   FROM farm_input_records i
                   JOIN farm_operation_ledger o ON o.operation_id = i.operation_id
                   WHERE o.tenant_id = $1::uuid AND i.tenant_id = $1::uuid AND o.season_id = $2
                   GROUP BY i.input_type, i.inventory_item_id, i.unit
                   ORDER BY i.input_type, i.inventory_item_id NULLS LAST""",
                str(user.tenant_id),
                season_id,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("إسقاط المخزون", e) from e
    resources = [
        ResourceUse(
            resource_type=r["input_type"],
            inventory_item_id=r["inventory_item_id"],
            quantity=float(r["quantity"] or 0.0),
            unit=r["unit"],
            estimated_cost=float(r["estimated_cost"] or 0.0),
        )
        for r in rows
    ]
    lines = build_inventory_projection(resources, sync_enabled=_flag_enabled(_INVENTORY_SYNC_FLAG))
    return {
        "season_id": season_id,
        "sync_enabled": _flag_enabled(_INVENTORY_SYNC_FLAG),
        "lines": [line.__dict__ for line in lines],
        "provenance": {"source": "farm_operations_ledger", "inventory_write": False},
    }


async def _fetch_ledger_summary_for_season(conn, tenant_id: str, season_id: str) -> LedgerSummary:
    row = await conn.fetchrow(
        """WITH ops AS (
            SELECT * FROM farm_operation_ledger WHERE tenant_id = $1::uuid AND season_id = $2
        )
        SELECT
            COUNT(*)::int AS operation_count,
            COALESCE(SUM(cost_amount), 0)::float AS total_cost,
            COALESCE(SUM(cost_amount) FILTER (WHERE cost_category IN ('administration','overhead','supervision','security','management')), 0)::float AS indirect_cost,
            COALESCE(SUM(cost_amount) FILTER (WHERE sync_status IN ('ready_for_sync','synced','sync_failed')), 0)::float AS syncable_cost,
            COALESCE((SELECT SUM(water_volume_m3) FROM farm_water_records w JOIN ops ON ops.operation_id = w.operation_id), 0)::float AS water_volume_m3,
            COALESCE((SELECT SUM(kwh) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS energy_kwh,
            COALESCE((SELECT SUM(diesel_liters) FROM farm_energy_records e JOIN ops ON ops.operation_id = e.operation_id), 0)::float AS diesel_liters,
            COALESCE((SELECT SUM(hours_worked) FROM farm_equipment_records q JOIN ops ON ops.operation_id = q.operation_id), 0)::float AS equipment_hours,
            COALESCE((SELECT SUM(hours) FROM farm_labor_records l JOIN ops ON ops.operation_id = l.operation_id), 0)::float AS labor_hours
        FROM ops""",
        tenant_id,
        season_id,
    )
    breakdown_rows = await conn.fetch(
        """SELECT COALESCE(cost_category, 'uncategorized') AS category,
                  COALESCE(SUM(cost_amount), 0)::float AS amount
           FROM farm_operation_ledger
           WHERE tenant_id = $1::uuid AND season_id = $2
           GROUP BY COALESCE(cost_category, 'uncategorized')""",
        tenant_id,
        season_id,
    )
    total = float(row["total_cost"] or 0.0)
    indirect = float(row["indirect_cost"] or 0.0)
    return LedgerSummary(
        total_cost=total,
        direct_cost=total - indirect,
        indirect_cost=indirect,
        currency="YER",
        cost_breakdown={r["category"]: float(r["amount"] or 0.0) for r in breakdown_rows},
        water_volume_m3=float(row["water_volume_m3"] or 0.0),
        energy_kwh=float(row["energy_kwh"] or 0.0),
        diesel_liters=float(row["diesel_liters"] or 0.0),
        equipment_hours=float(row["equipment_hours"] or 0.0),
        labor_hours=float(row["labor_hours"] or 0.0),
        input_quantities={},
        record_count=int(row["operation_count"] or 0),
        syncable_cost=float(row["syncable_cost"] or 0.0),
        control_only=float(row["syncable_cost"] or 0.0) == 0.0,
    )


@router.get("/api/v1/farm-ledger/economic-state/{season_id}")
async def get_economic_state(
    season_id: str,
    area_ha: float | None = None,
    yield_quantity: float | None = None,
    unit: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """حالة اقتصادية اختيارية من Farm Ledger. لا تُكتب في CanonicalFieldState إلا لاحقاً خلف علم مستقل."""
    _require_enabled()
    if _DB_POOL is None:
        return {"season_id": season_id, "economic_state": None, "note_ar": "القاعدة غير مفعلة"}
    try:
        async with tenant_connection(user) as conn:
            summary = await _fetch_ledger_summary_for_season(conn, str(user.tenant_id), season_id)
            budgets, actuals = await _fetch_budget_and_actual(conn, str(user.tenant_id), season_id)
            variances = compute_variances(budgets, actuals)
            rev = await conn.fetchrow(
                """SELECT COALESCE(SUM(amount), 0)::float AS revenue
                   FROM farm_revenue_records WHERE tenant_id = $1::uuid AND season_id = $2""",
                str(user.tenant_id),
                season_id,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حساب الحالة الاقتصادية", e) from e
    profit = compute_profitability(
        season_id,
        revenue=float(rev["revenue"] or 0.0),
        cost_lines=actuals,
        yield_quantity=yield_quantity,
        unit=unit,
    )
    state = build_economic_state(
        season_id, summary, area_ha=area_ha, profitability=profit, variances=variances
    )
    return {
        "season_id": season_id,
        "canonical_economics_enabled": _flag_enabled(_CANONICAL_ECONOMICS_FLAG),
        "would_write_canonical_state": False,
        "disabled_reason": None if _flag_enabled(_CANONICAL_ECONOMICS_FLAG) else "feature_flag_off",
        "economic_state": {
            **state.__dict__,
            "recommendations": [r.__dict__ for r in state.recommendations],
        },
    }
