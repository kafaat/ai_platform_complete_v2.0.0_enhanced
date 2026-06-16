"""api/routers/harvest_traceability.py — تتبّع سلسلة الإمداد (farm-to-market) — v65.

دفعات الحصاد (harvest_lots) + سلسلة الحيازة append-only (custody_chain_events).
يكمّل input-traceability (تتبّع مدخلات الحقل) بالتتبّع من الحصاد إلى السوق. المنطق
النقيّ في core/engines/harvest_traceability؛ هنا المسارات + القاعدة (العزل عبر
tenant_connection/RLS). النماذج مركزيّة في api.main كبقيّة الميزات.

ملاحظة MVP: الإنشاء يولّد المعرّف خادم-جانبيّاً بلا غلاف idempotency (لا عميل موبايل
يستهلكه بعد) — يُضاف لاحقاً عند الحاجة كما في create_season/create_activity.
"""

from __future__ import annotations

import json as _json
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.harvest_models import (
    _CUSTODY_EVENT_SELECT,
    _HARVEST_LOT_SELECT,
    CustodyEventCreateRequest,
    CustodyEventSummary,
    HarvestLotCreateRequest,
    HarvestLotSummary,
    _row_to_custody_event,
    _row_to_harvest_lot,
)
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _clamp_list_window,
    _db_unavailable,
    _emit_domain_event,
    _parse_date,
    require_permission,
    tenant_connection,
)

router = APIRouter()


def _parse_dt(value: str, field: str) -> datetime:
    """ISO datetime → datetime؛ 422 واضحة على قيمة غير صالحة (لا 500 من القاعدة)."""
    try:
        return datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=422, detail=f"{field}: زمن ISO غير صالح") from e


@router.post("/api/v1/harvest-lots", status_code=201, response_model=HarvestLotSummary)
async def create_harvest_lot(
    req: HarvestLotCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ دفعة حصاد مربوطة بحقل (إلزاميّ) وموسم (اختياريّ، يخصّ الحقل). يُصدِر
    HARVEST_LOT_CREATED. 404 إن لم يكن الحقل/الموسم للمستأجِر. 503 عند تعذّر القاعدة."""
    harvest_date = _parse_date(req.harvest_date, "تاريخ الحصاد")
    if harvest_date is None:
        raise HTTPException(status_code=422, detail="تاريخ الحصاد مطلوب (ISO YYYY-MM-DD)")
    lot_id = "hl_" + _uuid.uuid4().hex[:16]
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, req.field_id)  # 404 لو الحقل ليس للمستأجِر
            if req.season_id is not None:
                ok = await conn.fetchval(
                    "SELECT 1 FROM seasons WHERE season_id = $1 AND field_id = $2",
                    req.season_id,
                    req.field_id,
                )
                if not ok:
                    raise HTTPException(status_code=404, detail="الموسم غير موجود لهذا الحقل")
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO harvest_lots
                       (harvest_lot_id, tenant_id, field_id, season_id, crop,
                        harvest_date, quantity_kg, moisture_pct, quality_grade, notes_ar)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    lot_id,
                    str(user.tenant_id),
                    req.field_id,
                    req.season_id,
                    req.crop,
                    harvest_date,
                    req.quantity_kg,
                    req.moisture_pct,
                    req.quality_grade,
                    req.notes_ar,
                )
                await _emit_domain_event(
                    conn,
                    user,
                    "HARVEST_LOT_CREATED",
                    "harvest_lot",
                    lot_id,
                    {
                        "field_id": req.field_id,
                        "season_id": req.season_id,
                        "quantity_kg": req.quantity_kg,
                    },
                )
            row = await conn.fetchrow(
                f"SELECT {_HARVEST_LOT_SELECT} FROM harvest_lots WHERE harvest_lot_id = $1",
                lot_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء دفعة الحصاد", e) from e
    return _row_to_harvest_lot(row)


@router.get("/api/v1/harvest-lots", response_model=list[HarvestLotSummary])
async def list_harvest_lots(
    field_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int | None = Query(default=None, ge=0),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """دفعات حصاد المستأجِر (الأحدث أولاً) — عزل بـRLS + ترشيح حقل/حالة اختياريّ +
    ترقيم (limit/offset، افتراضيّ أحدث 100). 503 عند تعذّر القاعدة."""
    lim, off = _clamp_list_window(limit, offset)
    conds: list[str] = []
    args: list = []
    if field_id is not None:
        args.append(field_id)
        conds.append(f"field_id = ${len(args)}")
    if status is not None:
        args.append(status)
        conds.append(f"status = ${len(args)}")
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    args.append(lim)
    lim_ph = f"${len(args)}"
    args.append(off)
    off_ph = f"${len(args)}"
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                f"SELECT {_HARVEST_LOT_SELECT} FROM harvest_lots{where} "
                f"ORDER BY harvest_date DESC, harvest_lot_id DESC LIMIT {lim_ph} OFFSET {off_ph}",
                *args,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة دفعات الحصاد", e) from e
    return [_row_to_harvest_lot(r) for r in rows]


@router.get("/api/v1/harvest-lots/{harvest_lot_id}", response_model=HarvestLotSummary)
async def get_harvest_lot(
    harvest_lot_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفاصيل دفعة (RLS). 404 إن لم تكن للمستأجِر. 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"SELECT {_HARVEST_LOT_SELECT} FROM harvest_lots WHERE harvest_lot_id = $1",
                harvest_lot_id,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة دفعة الحصاد", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="دفعة الحصاد غير موجودة ضمن هذا المستأجِر")
    return _row_to_harvest_lot(row)


@router.post(
    "/api/v1/harvest-lots/{harvest_lot_id}/custody-events",
    status_code=201,
    response_model=CustodyEventSummary,
)
async def add_custody_event(
    harvest_lot_id: str,
    req: CustodyEventCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يسجّل حدث حيازة (append-only) على دفعة + يحرّك حالتها تطبيقيّاً (status_for_event)
    + content_hash للتدقيق. يُصدِر CUSTODY_EVENT_RECORDED. القفل (FOR UPDATE) يُسلسِل
    التسجيلات المتزامنة على نفس الدفعة. 404 إن لم تكن الدفعة للمستأجِر. 503 عند تعذّر القاعدة."""
    from core.engines.harvest_traceability import compute_event_hash, status_for_event

    occurred = _parse_dt(req.occurred_at, "occurred_at")
    content_hash = compute_event_hash(
        harvest_lot_id, req.event_type, occurred.isoformat(), req.event_details
    )
    try:
        async with tenant_connection(user) as conn:
            lot = await conn.fetchrow(
                "SELECT status FROM harvest_lots WHERE harvest_lot_id = $1 FOR UPDATE",
                harvest_lot_id,
            )
            if lot is None:
                raise HTTPException(
                    status_code=404, detail="دفعة الحصاد غير موجودة ضمن هذا المستأجِر"
                )
            new_status = status_for_event(req.event_type, lot["status"])
            async with conn.transaction():
                ev_id = await conn.fetchval(
                    """INSERT INTO custody_chain_events
                       (tenant_id, harvest_lot_id, event_type, handler, handler_role,
                        location_name, quantity_kg, event_details, occurred_at, content_hash)
                       VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                       RETURNING custody_event_id""",
                    str(user.tenant_id),
                    harvest_lot_id,
                    req.event_type,
                    req.handler,
                    req.handler_role,
                    req.location_name,
                    req.quantity_kg,
                    _json.dumps(req.event_details),
                    occurred,
                    content_hash,
                )
                if new_status != lot["status"]:
                    await conn.execute(
                        "UPDATE harvest_lots SET status = $1 WHERE harvest_lot_id = $2",
                        new_status,
                        harvest_lot_id,
                    )
                await _emit_domain_event(
                    conn,
                    user,
                    "CUSTODY_EVENT_RECORDED",
                    "harvest_lot",
                    harvest_lot_id,
                    {
                        "event_type": req.event_type,
                        "custody_event_id": ev_id,
                        "new_status": new_status,
                    },
                )
            row = await conn.fetchrow(
                f"SELECT {_CUSTODY_EVENT_SELECT} FROM custody_chain_events "
                "WHERE custody_event_id = $1",
                ev_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تسجيل حدث الحيازة", e) from e
    return _row_to_custody_event(row)


@router.get("/api/v1/harvest-lots/{harvest_lot_id}/traceability")
async def get_traceability(
    harvest_lot_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الأثر الكامل لدفعة: الدفعة + سلسلة الحيازة مرتّبة + المنشأ + تقييم الاكتمال
    (دالّة نقيّة assemble_traceability). 404 إن لم تكن الدفعة للمستأجِر. 503 عند تعذّر القاعدة."""
    from core.engines.harvest_traceability import assemble_traceability

    try:
        async with tenant_connection(user) as conn:
            lot_row = await conn.fetchrow(
                f"SELECT {_HARVEST_LOT_SELECT} FROM harvest_lots WHERE harvest_lot_id = $1",
                harvest_lot_id,
            )
            if lot_row is None:
                raise HTTPException(
                    status_code=404, detail="دفعة الحصاد غير موجودة ضمن هذا المستأجِر"
                )
            ev_rows = await conn.fetch(
                f"SELECT {_CUSTODY_EVENT_SELECT} FROM custody_chain_events "
                "WHERE harvest_lot_id = $1 ORDER BY occurred_at ASC, custody_event_id ASC",
                harvest_lot_id,
            )
            field_row = await conn.fetchrow(
                "SELECT field_id, name, area_ha FROM fields WHERE field_id = $1",
                lot_row["field_id"],
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة أثر الدفعة", e) from e
    lot = _row_to_harvest_lot(lot_row).model_dump()
    chain = [_row_to_custody_event(r).model_dump() for r in ev_rows]
    origin: dict = {}
    if field_row is not None:
        origin = {
            "field_id": field_row["field_id"],
            "field_name": field_row["name"],
            "area_ha": float(field_row["area_ha"]) if field_row["area_ha"] is not None else None,
        }
    return assemble_traceability(lot, chain, origin)
