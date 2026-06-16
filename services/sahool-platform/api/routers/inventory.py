"""api/routers/inventory.py — المخزون (Inventory: items/batches/expiring)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.inventory_models import (
    InventoryBatchRequest,
    InventoryItemRequest,
)
from api.main import (
    CommandStore,
    Permission,
    UserSchema,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    _parse_date,
    get_pool,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/inventory/items", status_code=201)
async def create_inventory_item(
    req: InventoryItemRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_MANAGE)),
):
    import uuid as _uuid

    item_id = "inv_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:

        async def _work():
            await conn.execute(
                """INSERT INTO inventory_items
                    (item_id, tenant_id, category, name, unit, reorder_level, notes)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)""",
                item_id,
                str(user.tenant_id),
                req.category,
                req.name,
                req.unit,
                req.reorder_level,
                req.notes,
            )
            await _emit_domain_event(
                conn,
                user,
                "INVENTORY_ITEM_CREATED",
                "inventory_item",
                item_id,
                {"category": req.category, "name": req.name},
            )
            return {"item_id": item_id, "name": req.name, "message_ar": "أُضيف عنصر المخزون"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="inventory.item.create",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"item_id": item_id},
            )
        else:
            result = await _work()
    return result


@router.get("/api/v1/inventory/items")
async def list_inventory_items(
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_VIEW)),
):
    """عناصر المخزون مع الكمّيّة الكلّيّة (مجموع الدفعات) — مُرشّحة بـRLS."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            """SELECT i.item_id, i.category, i.name, i.unit, i.reorder_level,
                      COALESCE(SUM(b.quantity), 0) AS total_quantity
               FROM inventory_items i
               LEFT JOIN inventory_batches b ON b.item_id = i.item_id
               GROUP BY i.item_id, i.category, i.name, i.unit, i.reorder_level
               ORDER BY i.category, i.name"""
        )
    return [
        {
            "item_id": r["item_id"],
            "category": r["category"],
            "name": r["name"],
            "unit": r["unit"],
            "reorder_level": float(r["reorder_level"]) if r["reorder_level"] is not None else None,
            "total_quantity": float(r["total_quantity"]),
            "low_stock": (
                r["reorder_level"] is not None
                and float(r["total_quantity"]) <= float(r["reorder_level"])
            ),
        }
        for r in rows
    ]


@router.post("/api/v1/inventory/items/{item_id}/batches", status_code=201)
async def add_inventory_batch(
    item_id: str,
    req: InventoryBatchRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_MANAGE)),
):
    import uuid as _uuid

    batch_id = "bat_" + _uuid.uuid4().hex[:12]
    expiry = _parse_date(req.expiry_date, "expiry_date")
    received = _parse_date(req.received_at, "received_at") or date.today()
    async with tenant_connection(user) as conn:

        async def _work():
            # تأكّد من وجود العنصر ضمن المستأجر (RLS يمنع عنصر مستأجر آخر)
            exists = await conn.fetchval(
                "SELECT 1 FROM inventory_items WHERE item_id = $1", item_id
            )
            if not exists:
                raise HTTPException(status_code=404, detail="عنصر المخزون غير موجود")
            await conn.execute(
                """INSERT INTO inventory_batches
                    (batch_id, tenant_id, item_id, quantity, unit, batch_code,
                     expiry_date, received_at, supplier, notes)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10)""",
                batch_id,
                str(user.tenant_id),
                item_id,
                req.quantity,
                req.unit,
                req.batch_code,
                expiry,
                received,
                req.supplier,
                req.notes,
            )
            await _emit_domain_event(
                conn,
                user,
                "INVENTORY_BATCH_ADDED",
                "inventory_batch",
                batch_id,
                {"item_id": item_id, "quantity": req.quantity},
            )
            return {"batch_id": batch_id, "item_id": item_id, "message_ar": "أُضيفت الدفعة"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="inventory.batch.add",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"batch_id": batch_id, "item_id": item_id},
            )
        else:
            result = await _work()
    return result


@router.get("/api/v1/inventory/expiring")
async def list_expiring_batches(
    days: int = Query(30, ge=1, le=3650),  # مقيّد 1..10 سنوات (لا سالب/ضخم)
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_VIEW)),
):
    """دفعات تنتهي خلال N يوماً (تنبيه قبل تلف المبيدات/الأسمدة)."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            """SELECT b.batch_id, b.item_id, i.name, b.quantity, b.unit, b.expiry_date
               FROM inventory_batches b
               JOIN inventory_items i ON i.item_id = b.item_id
               WHERE b.expiry_date IS NOT NULL
                 AND b.expiry_date <= CURRENT_DATE + make_interval(days => $1)
                 AND b.quantity > 0
               ORDER BY b.expiry_date ASC""",
            days,
        )
    return [
        {
            "batch_id": r["batch_id"],
            "item_id": r["item_id"],
            "name": r["name"],
            "quantity": float(r["quantity"]),
            "unit": r["unit"],
            "expiry_date": r["expiry_date"].isoformat() if r["expiry_date"] else None,
        }
        for r in rows
    ]
