"""api/routers/devices.py — أجهزة IoT والقياسات (Devices & Telemetry)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/الثوابت/المساعِدات) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    _DEVICE_ONLINE_WINDOW_MIN,
    DeviceRequest,
    Permission,
    TelemetryRequest,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/devices", status_code=201)
async def register_device(
    req: DeviceRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يسجّل جهاز IoT جديد في سجلّ المستأجر."""
    import uuid as _uuid

    device_id = "dev_" + _uuid.uuid4().hex[:12]
    # تحقّق غير كاسر (best-effort): إن لم يكن نوع الجهاز معرّفاً في سجلّ الأنواع
    # (api/device_registry) نُسجّل تحذيراً فقط — لا نرفض (السلوك دون تغيير). مغلّف
    # بـtry/except كي لا يكسر أيّ خطأ في السجلّ نقطة التسجيل. ربط النوع/الرفض متابعة.
    try:
        from api.device_registry import get_device_type

        if get_device_type(req.type) is None:
            logging.warning("سُجّل جهاز بنوع غير مُعرَّف في سجلّ الأنواع: %s", req.type)
    except Exception:  # noqa: BLE001 — تحذير اختياريّ لا يجوز أن يُفشل التسجيل
        pass
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO iot_devices
                (device_id, tenant_id, name, type, field_id, firmware_version)
               VALUES ($1, $2::uuid, $3, $4, $5, $6)""",
            device_id,
            str(user.tenant_id),
            req.name,
            req.type,
            req.field_id,
            req.firmware_version,
        )
    return {"device_id": device_id, "name": req.name, "message_ar": "سُجّل الجهاز"}


@router.get("/api/v1/devices")
async def list_devices(user: UserSchema = Depends(require_permission(Permission.DEVICE_VIEW))):
    """قائمة الأجهزة مع حالة الصحّة المحسوبة (online إن ظهر مؤخّراً)."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            """SELECT device_id, name, type, field_id, status, last_seen_at, firmware_version,
                      (last_seen_at IS NOT NULL
                       AND last_seen_at > NOW() - make_interval(mins => $1)) AS online
               FROM iot_devices ORDER BY type, name""",
            _DEVICE_ONLINE_WINDOW_MIN,
        )
    return [
        {
            "device_id": r["device_id"],
            "name": r["name"],
            "type": r["type"],
            "field_id": r["field_id"],
            "status": r["status"],
            "online": r["online"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
            "firmware_version": r["firmware_version"],
        }
        for r in rows
    ]


@router.post("/api/v1/devices/{device_id}/telemetry", status_code=201)
async def ingest_telemetry(
    device_id: str,
    req: TelemetryRequest,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """يبتلع قراءة من جهاز ويحدّث آخر ظهوره (= نبضة صحّة). تسجيل القراءة من
    صلاحية observation:record (العامل يدفع قراءات الميدان)."""
    recorded = None
    if req.recorded_at:
        # ندعم لاحقة "Z" (Zulu/UTC) الشائعة، ونطبّع الـnaive إلى UTC قبل
        # إدخاله في عمود TIMESTAMPTZ (لئلّا يُرفَض مدخل صحيح أو يُخزَّن توقيت ملتبس).
        raw = req.recorded_at.strip().replace("Z", "+00:00").replace("z", "+00:00")
        try:
            recorded = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail="recorded_at غير صالح — استخدم ISO 8601"
            ) from None
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=UTC)
    async with tenant_connection(user) as conn:
        exists = await conn.fetchval("SELECT 1 FROM iot_devices WHERE device_id = $1", device_id)
        if not exists:
            raise HTTPException(status_code=404, detail="الجهاز غير مسجّل")
        await conn.execute(
            """INSERT INTO device_telemetry
                (tenant_id, device_id, sensor_type, value, unit, recorded_at)
               VALUES ($1::uuid, $2, $3, $4, $5, COALESCE($6, NOW()))""",
            str(user.tenant_id),
            device_id,
            req.sensor_type,
            req.value,
            req.unit,
            recorded,
        )
        # القراءة = نبضة صحّة: حدّث آخر ظهور والحالة online
        await conn.execute(
            "UPDATE iot_devices SET last_seen_at = NOW(), status = 'online' WHERE device_id = $1",
            device_id,
        )
    return {"device_id": device_id, "message_ar": "سُجّلت القراءة"}


@router.get("/api/v1/devices/{device_id}/telemetry")
async def list_telemetry(
    device_id: str,
    limit: int = Query(100, ge=1, le=1000),
    user: UserSchema = Depends(require_permission(Permission.DEVICE_VIEW)),
):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            """SELECT sensor_type, value, unit, recorded_at
               FROM device_telemetry WHERE device_id = $1
               ORDER BY recorded_at DESC LIMIT $2""",
            device_id,
            limit,
        )
    return [
        {
            "sensor_type": r["sensor_type"],
            "value": float(r["value"]),
            "unit": r["unit"],
            "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
        }
        for r in rows
    ]


@router.get("/api/v1/devices/fleet-health")
async def devices_fleet_health(
    user: UserSchema = Depends(require_permission(Permission.DEVICE_VIEW)),
):
    """صحّة أسطول الأجهزة — كشف استباقي للأجهزة الصامتة مرتّباً بالخطورة.

    يُكمّل GET /devices (العرض) بإنذار استباقي: أيّ جهاز صامت، ما خطورته، هل
    يعتمده حقل نشط. مُستلهَم من مبدأ MDM (الإنذار المبكر). RLS عبر tenant_connection.
    """
    from api.fleet_health import DeviceHealthRecord, assess_fleet

    rows: list = []
    active_fields: set[str] = set()
    try:
        async with tenant_connection(user) as conn:
            devs = await conn.fetch(
                """SELECT device_id, name, type, field_id,
                          EXTRACT(EPOCH FROM (NOW() - last_seen_at)) / 60 AS mins_since
                   FROM iot_devices"""
            )
            for d in devs:
                rows.append(
                    DeviceHealthRecord(
                        device_id=d["device_id"],
                        name=d["name"],
                        device_type=d["type"],
                        field_id=d["field_id"],
                        minutes_since_seen=(
                            float(d["mins_since"]) if d["mins_since"] is not None else None
                        ),
                    )
                )
            import asyncpg as _asyncpg  # لتضييق الالتقاط على غياب الجدول فقط

            try:
                # SAVEPOINT يعزل فشل الاستعلام الاختياري عن المعاملة الخارجيّة (RLS)،
                # فلا يُجهضها غياب الجدول (نمط _emit_domain_event نفسه).
                async with conn.transaction():
                    af = await conn.fetch(
                        "SELECT DISTINCT field_id FROM field_lifecycle WHERE status = 'active'"
                    )
                    active_fields = {r["field_id"] for r in af if r["field_id"]}
            except _asyncpg.UndefinedTableError:
                # غياب جدول دورة الحياة لا يكسر المراقبة (يسقط رفع الحرجيّة فقط).
                # أيّ خطأ DB آخر (صلاحيّة/SQL/انقطاع) يُترك ليُترجَم إلى 503 خارجيّاً
                # بدل إخفائه بصمت وإعطاء «صحّة» مضلّلة.
                active_fields = set()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("صحّة الأسطول", e) from e

    return assess_fleet(rows, active_field_ids=active_fields)
