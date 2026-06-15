"""api/routers/farms.py — المزارع (Farms — أب الحقول)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسارات/الأذونات/المخرجات/الأحداث المُصدَرة/مخطّط OpenAPI
مطابقة تماماً لما كان في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app``
إلى ``@router`` (بما فيها إصدار FARM_CREATED حرفيّاً عبر ``_emit_domain_event``).

النموذج ``FarmCreateRequest`` والمساعِدات (_emit_domain_event/_db_unavailable …) تبقى
مُعرَّفة في ``api.main`` وتُستورَد من هنا. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    FarmCreateRequest,
    Permission,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/farms", status_code=201)
async def create_farm(
    req: FarmCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FARM_CREATE)),
):
    """ينشئ مزرعة جديدة (أب الحقول). مُبوّب بصلاحية farm:create."""
    import uuid as _uuid

    farm_id = "frm_" + _uuid.uuid4().hex[:12]
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO farms
                    (farm_id, tenant_id, name, location, area_ha, centroid_lat, centroid_lon,
                     country, region, timezone, units, currency, description, activity_type)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                farm_id,
                str(user.tenant_id),
                req.name,
                req.location,
                req.area_ha,
                req.centroid_lat,
                req.centroid_lon,
                req.country,
                req.region,
                req.timezone,
                req.units,
                req.currency,
                req.description,
                req.activity_type,
            )
            # حدث إنشاء المزرعة (معلَم تأهيل): يُمكّن مستهلكي الأحداث من التفاعل
            # (إشعار/تهيئة لاحقة). نفس المعاملة (outbox) — فشل الإصدار لا يكسر الحفظ.
            await _emit_domain_event(
                conn,
                user,
                "FARM_CREATED",
                "farm",
                farm_id,
                {"name": req.name, "region": req.region},
            )
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً — مرّره كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ المزرعة", e) from e
    return {"farm_id": farm_id, "name": req.name, "message_ar": "أُنشئت المزرعة"}


@router.get("/api/v1/farms")
async def list_farms(user: UserSchema = Depends(require_permission(Permission.FARM_VIEW))):
    """قائمة مزارع المستأجر (مُرشّحة بـRLS تلقائيّاً)."""
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT farm_id, name, location, area_ha, centroid_lat, centroid_lon, "
                "country, region, timezone, units, currency, description, activity_type, "
                "created_at FROM farms ORDER BY created_at DESC"
            )
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً — مرّره كما هو
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة المزارع", e) from e
    return [
        {
            "farm_id": r["farm_id"],
            "name": r["name"],
            "location": r["location"],
            "area_ha": float(r["area_ha"]) if r["area_ha"] is not None else None,
            "centroid_lat": float(r["centroid_lat"]) if r["centroid_lat"] is not None else None,
            "centroid_lon": float(r["centroid_lon"]) if r["centroid_lon"] is not None else None,
            "country": r["country"],
            "region": r["region"],
            "timezone": r["timezone"],
            "units": r["units"],
            "currency": r["currency"],
            "description": r["description"],
            "activity_type": r["activity_type"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/api/v1/farms/{farm_id}/fields")
async def list_farm_fields(
    farm_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """حقول مزرعة محدّدة (هرميّة المزرعة→الحقل)."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT field_id, name, area_ha, crop, soil_type FROM fields "
            "WHERE farm_id = $1 ORDER BY name",
            farm_id,
        )
    return [
        {
            "field_id": r["field_id"],
            "name": r["name"],
            "area_ha": float(r["area_ha"]) if r["area_ha"] is not None else None,
            "crop": r["crop"],
            "soil_type": r["soil_type"],
        }
        for r in rows
    ]
