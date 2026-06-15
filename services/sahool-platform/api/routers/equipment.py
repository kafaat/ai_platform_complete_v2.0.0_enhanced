"""api/routers/equipment.py — المعدّات والصيانة (Equipment & Maintenance)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    EquipmentRequest,
    MaintenanceRequest,
    Permission,
    UserSchema,
    _emit_domain_event,
    _parse_date,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/equipment", status_code=201)
async def create_equipment(
    req: EquipmentRequest,
    user: UserSchema = Depends(require_permission(Permission.EQUIPMENT_MANAGE)),
):
    import uuid as _uuid

    equipment_id = "eqp_" + _uuid.uuid4().hex[:12]
    purchase = _parse_date(req.purchase_date, "purchase_date")
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO equipment
                (equipment_id, tenant_id, name, type, operating_hours, purchase_date, notes)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)""",
            equipment_id,
            str(user.tenant_id),
            req.name,
            req.type,
            req.operating_hours,
            purchase,
            req.notes,
        )
        await _emit_domain_event(
            conn,
            user,
            "EQUIPMENT_CREATED",
            "equipment",
            equipment_id,
            {"name": req.name, "type": req.type},
        )
    return {"equipment_id": equipment_id, "name": req.name, "message_ar": "سُجّلت المعدّة"}


@router.get("/api/v1/equipment")
async def list_equipment(user: UserSchema = Depends(require_permission(Permission.EQUIPMENT_VIEW))):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT equipment_id, name, type, status, operating_hours, purchase_date "
            "FROM equipment ORDER BY type, name"
        )
    return [
        {
            "equipment_id": r["equipment_id"],
            "name": r["name"],
            "type": r["type"],
            "status": r["status"],
            "operating_hours": float(r["operating_hours"]),
            "purchase_date": r["purchase_date"].isoformat() if r["purchase_date"] else None,
        }
        for r in rows
    ]


@router.post("/api/v1/equipment/{equipment_id}/maintenance", status_code=201)
async def log_maintenance(
    equipment_id: str,
    req: MaintenanceRequest,
    user: UserSchema = Depends(require_permission(Permission.EQUIPMENT_MANAGE)),
):
    import uuid as _uuid

    maintenance_id = "mnt_" + _uuid.uuid4().hex[:12]
    sched = _parse_date(req.scheduled_date, "scheduled_date")
    performed = _parse_date(req.performed_date, "performed_date")
    async with tenant_connection(user) as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM equipment WHERE equipment_id = $1", equipment_id
        )
        if not exists:
            raise HTTPException(status_code=404, detail="المعدّة غير موجودة")
        await conn.execute(
            """INSERT INTO equipment_maintenance
                (maintenance_id, tenant_id, equipment_id, kind, status,
                 scheduled_date, performed_date, cost_usd, notes)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)""",
            maintenance_id,
            str(user.tenant_id),
            equipment_id,
            req.kind,
            req.status,
            sched,
            performed,
            req.cost_usd,
            req.notes,
        )
        # عطل قيد التنفيذ ⇒ حدّث حالة المعدّة (تتبّع تشغيليّ)
        if req.kind == "breakdown" and req.status != "done":
            await conn.execute(
                "UPDATE equipment SET status = 'broken' WHERE equipment_id = $1", equipment_id
            )
        await _emit_domain_event(
            conn,
            user,
            "MAINTENANCE_LOGGED",
            "equipment_maintenance",
            maintenance_id,
            {"equipment_id": equipment_id, "kind": req.kind, "status": req.status},
        )
    return {"maintenance_id": maintenance_id, "message_ar": "سُجّلت الصيانة"}


@router.get("/api/v1/equipment/{equipment_id}/maintenance")
async def list_maintenance(
    equipment_id: str,
    user: UserSchema = Depends(require_permission(Permission.EQUIPMENT_VIEW)),
):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT maintenance_id, kind, status, scheduled_date, performed_date, cost_usd, notes "
            "FROM equipment_maintenance WHERE equipment_id = $1 "
            "ORDER BY COALESCE(performed_date, scheduled_date) DESC NULLS LAST",
            equipment_id,
        )
    return [
        {
            "maintenance_id": r["maintenance_id"],
            "kind": r["kind"],
            "status": r["status"],
            "scheduled_date": r["scheduled_date"].isoformat() if r["scheduled_date"] else None,
            "performed_date": r["performed_date"].isoformat() if r["performed_date"] else None,
            "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
            "notes": r["notes"],
        }
        for r in rows
    ]
