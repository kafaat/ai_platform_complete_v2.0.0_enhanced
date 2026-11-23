"""api/routers/farm_operations_ledger.py — Farm Operations Ledger رقابي اختياري.

الميزة خلف FEATURE_FARM_OPERATIONS_LEDGER (OFF افتراضاً). عند تفعيلها تحفظ السجلات
اليومية للأعمال/المياه/الطاقة/المعدات/العمالة/المواد كـ Operational Truth داخل SAHOOL.
لا تزامن ERP ولا قيود محاسبية هنا؛ sync_status يعلن فقط قابلية الترحيل لاحقاً.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date

from core import farm_operations_ledger as ledger_core
from core.erp_projection_contract import build_projection_envelope
from core.farm_closed_loop import (
    OperationEvent,
    ResourceUse,
    build_economic_state,
    build_inventory_projection,
    operation_event_to_ledger_payload,
)
from core.farm_costing import (
    SeasonBudgetLine,
    compute_profitability,
    generate_cost_recommendations,
    normalize_budget_line,
    project_to_erp_lines,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from api import main as api_main
from api.farm_operations_ledger_models import (
    EnergyRecordIn,
    EquipmentRecordIn,
    InputRecordIn,
    LaborRecordIn,
    WaterRecordIn,
    _non_negative_or_none,
)
from api.feature_registry import is_enabled
from api.main import (
    CommandStore,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _idem_key,
    _idempotent,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.water_ledger_auto import AUTO_CREATED_BY
from api.water_ledger_compute import project_farm_water_to_ledger

router = APIRouter()
_FLAG = "FEATURE_FARM_OPERATIONS_LEDGER"


def _enabled() -> bool:
    return is_enabled(_FLAG, os.getenv("FEATURE_FARM_OPERATIONS_LEDGER", ""))


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="farm_operations_ledger_disabled")


async def _assert_owned(conn, tenant_id: str, kind: str, value: str | None) -> None:
    if detail := await ledger_core.missing_tenant_scope(conn, tenant_id, kind, value):
        raise HTTPException(status_code=404, detail=detail)


async def _assert_season_in_tenant(conn, tenant_id: str, season_id: str | None) -> None:
    await _assert_owned(conn, tenant_id, "season", season_id)


async def _assert_production_unit_in_tenant(conn, tenant_id: str, unit_id: str | None) -> None:
    await _assert_owned(conn, tenant_id, "production_unit", unit_id)


async def _assert_farm_in_tenant(conn, tenant_id: str, farm_id: str | None) -> None:
    await _assert_owned(conn, tenant_id, "farm", farm_id)


class OperationLedgerIn(BaseModel):
    operation_date: date
    operation_type: str
    season_id: str | None = None
    production_unit_id: str | None = None
    farm_id: str | None = None
    field_id: str | None = None
    task_id: uuid.UUID | None = None
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

    @model_validator(mode="after")
    def _status_lifecycle(self):  # مخطَّط≠منفَّذ: حالةٌ معدودة ولا «منجَزة» مستقبليّة
        ledger_core.validate_operation_status(self.status, self.operation_date)
        return self


def _request_digest(req: OperationLedgerIn) -> str:
    """بصمةُ الحمولة الكاملة (JSON مرتَّب) — تُميِّز الإعادةَ الصادقة عن إعادة استعمال المفتاح."""
    # Without a task link the digest matches receipts created before the optional task_id.
    payload = req.model_dump(mode="json", exclude={"task_id"} if req.task_id is None else None)
    for row in payload["inputs"]:  # likewise for inputs naming no inventory batch (F-D11)
        if row.get("inventory_batch_id") is None:
            row.pop("inventory_batch_id", None)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/api/v1/farm-ledger/operations", status_code=201)
async def create_operation_ledger_record(
    req: OperationLedgerIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
    idem: str | None = Depends(_idem_key),
):
    """يحفظ سجل عمل يوميّاً ومرفقاته الرقابية. لا يزامن ERP.

    U06: ``Idempotency-Key`` يُسجِّل الأمر مرّةً في ``commands`` (معاملة ``tenant_connection``) ويُعيد النتيجةَ حرفيّاً؛ المفتاحُ نفسه بحمولةٍ مختلفة ⇒ 409 **قبل** كلّ فحوص النطاق (فهي داخل العمل).

    F-D11: an input naming ``inventory_batch_id`` deducts from that batch only when
    ``FEATURE_LEDGER_INVENTORY_DEDUCTION`` is on (OFF by default; off ⇒ ``applied: false`` and no
    stock moves). On: an ``Idempotency-Key`` and a ``completed`` status are required, the batch
    row is locked and reduced in this transaction, and a refusal (another tenant's batch, item or
    unit mismatch, insufficient stock) writes nothing. The stored result is the receipt.
    """
    _require_enabled()
    if api_main._DB_POOL is None:
        raise HTTPException(status_code=503, detail="farm_operations_ledger_database_unavailable")
    deduct = _flag_enabled(_INVENTORY_DEDUCTION_FLAG)
    has_batches = any(i.inventory_batch_id for i in req.inputs)
    if refusal := ledger_core.inventory_deduction_refusal(
        enabled=deduct, has_batches=has_batches, idempotency_key=idem, status=req.status
    ):
        raise HTTPException(status_code=refusal[0], detail=refusal[1])
    try:
        plan = ledger_core.plan_inventory_deduction(req.inputs) if deduct else []
    except ledger_core.InventoryDeductionRefused as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    operation_id = "oplog_" + uuid.uuid4().hex[:12]
    try:
        async with tenant_connection(user) as conn:
            tenant_id = str(user.tenant_id)

            async def _persist() -> dict:
                if not (req.field_id or req.production_unit_id or req.farm_id):
                    raise HTTPException(
                        status_code=422, detail="field_or_production_unit_or_farm_required"
                    )
                if req.field_id:
                    await _assert_field_in_tenant(conn, req.field_id)
                if task_error := await ledger_core.task_link_error(
                    conn, tenant_id, req.task_id, req.field_id
                ):
                    raise HTTPException(status_code=task_error[0], detail=task_error[1])
                await _assert_season_in_tenant(conn, tenant_id, req.season_id)
                await _assert_production_unit_in_tenant(conn, tenant_id, req.production_unit_id)
                await _assert_farm_in_tenant(conn, tenant_id, req.farm_id)
                async with conn.transaction():
                    await conn.execute(
                        """INSERT INTO farm_operation_ledger
                           (operation_id, tenant_id, season_id, production_unit_id, farm_id, field_id,
                            operation_type, operation_date, execution_mode, contractor_id, status,
                            notes, cost_amount, cost_category, currency, sync_status, created_by,
                            task_id, created_at, updated_at)
                           VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                                   $12, $13, $14, $15, $16, $17, $18, now(), now())""",
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
                        req.task_id,
                    )
                    await ledger_core.persist_operation_subrecords(  # داخل المعاملة نفسها
                        conn,
                        tenant_id=str(user.tenant_id),
                        operation_id=operation_id,
                        record_date=req.operation_date,
                        farm_id=req.farm_id,
                        field_id=req.field_id,
                        water=req.water,
                        energy=req.energy,
                        equipment=req.equipment,
                        labor=req.labor,
                        inputs=req.inputs,
                    )
                    # W1-13: the day's measured water reaches the daily water ledger, same txn.
                    water_ledger = (
                        await project_farm_water_to_ledger(
                            conn,
                            tenant_id=tenant_id,
                            field_id=req.field_id,
                            record_date=req.operation_date,
                            reporter=str(user.user_id),
                            auto_created_by=AUTO_CREATED_BY,
                        )
                        if req.water and req.field_id
                        else None
                    )
                    try:  # F-D11: same transaction — a refusal rolls back the record too
                        receipts = await ledger_core.apply_inventory_deduction(
                            conn, tenant_id=tenant_id, operation_id=operation_id, plan=plan
                        )
                    except ledger_core.InventoryDeductionRefused as e:
                        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
                deduction = {
                    "applied": deduct,
                    "flag": _INVENTORY_DEDUCTION_FLAG,
                    **({} if deduct else {"disabled_reason": "feature_flag_off"}),
                    "receipts": receipts,
                }
                return {
                    "operation_id": operation_id,
                    **({"task_id": str(req.task_id)} if req.task_id else {}),
                    "persisted": True,
                    "sync_status": req.sync_status,
                    "message_ar": "حُفظ سجل العملية الزراعية",
                    **({"water_ledger": water_ledger} if water_ledger else {}),
                    **({"inventory_deduction": deduction} if has_batches else {}),
                }

            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _persist,
                    command_type="farm_ledger.operation.create",
                    actor_id=str(user.user_id),
                    tenant_id=tenant_id,
                    payload={"operation_id": operation_id},
                    request_digest=_request_digest(req),
                )
            else:
                result = await _persist()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حفظ سجل العمليات الزراعية", e) from e
    return result


@router.get("/api/v1/farm-ledger/operations")
async def list_operation_ledger_records(
    field_id: str | None = None,
    season_id: str | None = None,
    task_id: uuid.UUID | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    _require_enabled()
    if api_main._DB_POOL is None:
        return {"entries": [], "total": 0, "note_ar": "القاعدة غير مفعلة"}
    clauses = ["tenant_id = $1::uuid"]
    args: list = [str(user.tenant_id)]
    if field_id:
        args.append(field_id)
        clauses.append(f"field_id = ${len(args)}")
    if task_id is not None:
        args.append(task_id)
        clauses.append(f"task_id = ${len(args)}::uuid")
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
                "SELECT operation_id, season_id, production_unit_id, farm_id, field_id, task_id, "
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
    currency: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """ملخّص رقابي/تكلفة مبسّط من السجلات. لا يختلق أرقاماً ولا يزامن ERP.

    التكاليف بعملةٍ واحدة (business-2): ``?currency=`` أو نطاقٌ فيه عملةٌ واحدة، وإلّا 409."""
    _require_enabled()
    if api_main._DB_POOL is None:
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
    money = ledger_core.money_filter_sql(len(args) + 1)  # counts and water keep every operation
    try:
        async with tenant_connection(user) as conn:
            if field_id:
                await _assert_field_in_tenant(conn, field_id)
            cur = await ledger_core.scope_report_currency(conn, where_sql, args, currency)
            margs = [*args, cur]
            row = await conn.fetchrow(
                f"""WITH scoped AS (SELECT * FROM farm_operation_ledger o WHERE {where_sql}),
                ops AS (SELECT * FROM scoped WHERE {ledger_core.ACTUAL_OPERATION_SQL})
                SELECT
                    COUNT(*)::int AS operation_count,
                    (SELECT COUNT(*) FROM scoped WHERE {ledger_core.PLANNED_OPERATION_SQL})::int AS planned_operation_count,
                    (SELECT COALESCE(SUM(cost_amount), 0) FROM scoped WHERE {ledger_core.PLANNED_OPERATION_SQL} AND {money})::float AS planned_cost,
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
                *margs,
            )
            breakdown_rows = await conn.fetch(
                f"""SELECT COALESCE(cost_category, 'uncategorized') AS category,
                           COALESCE(SUM(cost_amount) FILTER (WHERE {money}), 0)::float AS amount
                    FROM farm_operation_ledger o WHERE {where_sql} AND {ledger_core.ACTUAL_OPERATION_SQL}
                    GROUP BY COALESCE(cost_category, 'uncategorized')
                    ORDER BY category""",
                *margs,
            )
    except HTTPException:
        raise
    except ledger_core.MixedCurrencyError as e:
        raise HTTPException(status_code=409, detail=e.detail()) from e  # business-2
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تلخيص سجل العمليات الزراعية", e) from e
    total = float(row["total_cost"] or 0.0)
    indirect = float(row["indirect_cost"] or 0.0)
    return {
        "summary": {
            "currency": cur,
            "operation_count": row["operation_count"],  # منجَزة حتى اليوم فقط
            "total_cost": total,
            "planned_operation_count": row["planned_operation_count"],
            "planned_cost": float(row["planned_cost"] or 0.0),
            "direct_cost": total - indirect,
            "indirect_cost": indirect,
            "cost_breakdown": {r["category"]: float(r["amount"] or 0.0) for r in breakdown_rows},
            **ledger_core.water_summary_payload(row),
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
    user: UserSchema = Depends(require_permission(Permission.FINANCE_MANAGE)),
):
    """يحفظ بنود موازنة الموسم حسب المرحلة والتصنيف. كل القيم قابلة للتعديل ولا تُطبق كقرار تلقائي."""
    _require_enabled()
    if api_main._DB_POOL is None:
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
    except HTTPException:  # 404 season / 403 ownership are answers, not an outage
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حفظ موازنة الموسم", e) from e
    return {"saved": saved, "message_ar": "حُفظت بنود موازنة الموسم"}


@router.get("/api/v1/farm-ledger/budgets/{season_id}")
async def get_season_budget(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if api_main._DB_POOL is None:
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
    totals, single = ledger_core.planned_totals_by_currency(rows)
    return {
        "season_id": season_id,
        "lines": [dict(r) for r in rows],
        "currency": single,
        "total_planned_cost": totals[single] if single else (None if totals else 0.0),
        "totals_by_currency": totals,
    }


@router.post("/api/v1/farm-ledger/revenues", status_code=201)
async def create_revenue_record(
    req: RevenueRecordIn,
    user: UserSchema = Depends(require_permission(Permission.FINANCE_MANAGE)),
):
    _require_enabled()
    if api_main._DB_POOL is None:
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


@router.get("/api/v1/farm-ledger/variance/{season_id}")
async def get_budget_variance(
    season_id: str,
    currency: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if api_main._DB_POOL is None:
        return {
            "season_id": season_id,
            "variance": [],
            "recommendations": [],
            "note_ar": "القاعدة غير مفعلة",
        }
    tenant = str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            cur = await ledger_core.season_report_currency(conn, tenant, season_id, currency)
            budgets, actuals = await ledger_core.fetch_budget_and_actual(
                conn, tenant, season_id, cur
            )
            unpriced = await ledger_core.fetch_unpriced_work(conn, tenant, season_id, cur)
    except ledger_core.MixedCurrencyError as e:
        raise HTTPException(status_code=409, detail=e.detail()) from e  # business-2
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحليل انحرافات الموسم", e) from e
    variance, coverage = ledger_core.priced_variance(budgets, actuals, *unpriced)
    recs = generate_cost_recommendations(variance)
    return {
        "season_id": season_id,
        "currency": cur,
        **coverage,
        "variance": [v.__dict__ for v in variance],
        "recommendations": [r.__dict__ for r in recs],
        "provenance": {"source": "farm_operations_ledger", "prediction": False},
    }


@router.get("/api/v1/farm-ledger/profitability/{season_id}")
async def get_season_profitability(
    season_id: str,
    yield_quantity: float | None = None,
    unit: str | None = None,
    currency: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    _require_enabled()
    if api_main._DB_POOL is None:
        return {"season_id": season_id, "profitability": None, "note_ar": "القاعدة غير مفعلة"}
    tenant = str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            cur = await ledger_core.season_report_currency(conn, tenant, season_id, currency)
            _, actuals = await ledger_core.fetch_budget_and_actual(conn, tenant, season_id, cur)
            revenue = await ledger_core.fetch_season_revenue(conn, tenant, season_id, cur)
    except ledger_core.MixedCurrencyError as e:
        raise HTTPException(status_code=409, detail=e.detail()) from e  # business-2
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحليل ربحية الموسم", e) from e
    profit = compute_profitability(
        season_id,
        revenue=revenue,
        cost_lines=actuals,
        yield_quantity=yield_quantity,
        unit=unit,
        **({"currency": cur} if cur else {}),
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
    currency: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """يعرض إسقاطاً مالياً قابلاً للترحيل لاحقاً؛ لا يرسل شيئاً إلى ERP من هذا endpoint."""
    _require_enabled()
    if api_main._DB_POOL is None:
        return {"season_id": season_id, "lines": [], "note_ar": "القاعدة غير مفعلة"}
    cur, tenant = ledger_core.normalize_currency(currency), str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            _, actuals = await ledger_core.fetch_budget_and_actual(conn, tenant, season_id, cur)
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("إسقاط ERP", e) from e
    try:  # one projection, one currency: mixed-currency actuals are never summed
        lines = project_to_erp_lines(
            actuals, cost_center=cost_center, project=season_id, currency=cur
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=f"{e}: pass ?currency=") from e
    line_payload = [line.__dict__ for line in lines]
    provider = os.getenv("ERP_PROVIDER", "none").strip().lower() or "none"
    envelope = build_projection_envelope(
        season_id=season_id,
        lines=line_payload,
        provider=provider,
        currency=lines[0].currency if lines else (cur or "YER"),
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
_INVENTORY_DEDUCTION_FLAG = "FEATURE_LEDGER_INVENTORY_DEDUCTION"  # F-D11, OFF by default
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

    F-D10: a deliberate preview boundary (ADR-0004). Nothing in the platform consumes this
    payload, so ``would_persist`` stays false even with FEATURE_OPERATION_LEDGER_AUTOWRITE on;
    the write is a human posting ``ledger_payload`` to ``write_path``. Never writes stock.
    """
    _require_enabled()
    if req.field_id and api_main._DB_POOL is not None:
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
    autowrite = _flag_enabled(_AUTOWRITE_FLAG)
    return {
        "autowrite_enabled": autowrite,
        "persisted": False,
        "would_persist": False,
        "autowrite_consumer": None,
        "disabled_reason": "no_autowrite_consumer" if autowrite else "feature_flag_off",
        "write_path": {
            "endpoint": "POST /api/v1/farm-ledger/operations",
            "permission": Permission.ACTIVITY_EXECUTE.value,
            "requires": "a person submits ledger_payload with an Idempotency-Key",
        },
        "ledger_payload": payload,
        "provenance": {"source": "farm_operations_ledger", "persisted": False},
    }


def _inventory_write_path() -> dict:
    """F-D11: the projection never writes; this is the one step that does, and its flag."""
    return {
        "endpoint": "POST /api/v1/farm-ledger/operations",
        "flag": _INVENTORY_DEDUCTION_FLAG,
        "flag_enabled": _flag_enabled(_INVENTORY_DEDUCTION_FLAG),
        "requires": "inputs[].inventory_batch_id, status=completed and an Idempotency-Key",
    }


@router.get("/api/v1/farm-ledger/inventory-projection/{season_id}")
async def get_inventory_projection(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """إسقاط خصم مخزون من سجلات المواد فقط. لا يكتب في inventory-service."""
    _require_enabled()
    if api_main._DB_POOL is None:
        return {
            "season_id": season_id,
            "lines": [],
            "inventory_write": False,
            "write_path": _inventory_write_path(),
            "note_ar": "القاعدة غير مفعلة",
        }
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
        "inventory_write": False,
        "write_path": _inventory_write_path(),
        "provenance": {"source": "farm_operations_ledger", "inventory_write": False},
    }


@router.get("/api/v1/farm-ledger/economic-state/{season_id}")
async def get_economic_state(
    season_id: str,
    area_ha: float | None = None,
    yield_quantity: float | None = None,
    unit: str | None = None,
    currency: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """حالة اقتصادية اختيارية من Farm Ledger. لا تُكتب في CanonicalFieldState إلا لاحقاً خلف علم مستقل.

    بعملةٍ واحدة (business-2): ``?currency=`` أو موسمٌ بعملةٍ واحدة، وإلّا 409 كالربحيّة."""
    _require_enabled()
    if api_main._DB_POOL is None:
        return {"season_id": season_id, "economic_state": None, "note_ar": "القاعدة غير مفعلة"}
    tenant = str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            cur = await ledger_core.season_report_currency(conn, tenant, season_id, currency)
            summary = await ledger_core.fetch_ledger_summary_for_season(
                conn, tenant, season_id, cur
            )
            budgets, actuals = await ledger_core.fetch_budget_and_actual(
                conn, tenant, season_id, cur
            )
            unpriced = await ledger_core.fetch_unpriced_work(conn, tenant, season_id, cur)
            revenue = await ledger_core.fetch_season_revenue(conn, tenant, season_id, cur)
    except ledger_core.MixedCurrencyError as e:
        raise HTTPException(status_code=409, detail=e.detail()) from e  # business-2
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حساب الحالة الاقتصادية", e) from e
    # an unpriced category is not an underspend: its variance line is dropped, as in /variance
    variances, coverage = ledger_core.priced_variance(budgets, actuals, *unpriced)
    profit = compute_profitability(
        season_id,
        revenue=revenue,
        cost_lines=actuals,
        yield_quantity=yield_quantity,
        unit=unit,
        **({"currency": cur} if cur else {}),
    )
    state = build_economic_state(
        season_id, summary, area_ha=area_ha, profitability=profit, variances=variances
    )
    return {
        "season_id": season_id,
        "canonical_economics_enabled": _flag_enabled(_CANONICAL_ECONOMICS_FLAG),
        "would_write_canonical_state": False,
        "disabled_reason": None if _flag_enabled(_CANONICAL_ECONOMICS_FLAG) else "feature_flag_off",
        "currency": cur,
        **coverage,
        "economic_state": {
            **state.__dict__,
            "recommendations": [r.__dict__ for r in state.recommendations],
        },
    }
