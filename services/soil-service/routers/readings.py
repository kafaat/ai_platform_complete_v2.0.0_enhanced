"""routers/readings.py — قراءات مستشعر التربة واستيعابها (Readings/Ingest)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات/
المصادقة مطابقة. النماذج/المساعِدات المشتركة (``SoilReading``/``_require_*``)
تبقى في ``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا
الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.get("/soil/readings/{field_id}")
async def get_readings(field_id: str, limit: int = 100, x_agent_token: str = Header(None)):
    """Get soil sensor readings for a field.

    أمان (طبقتان):
    ١) توكن الخدمة (يمنع المجهول).
    ٢) تفويض ملكيّة الحقل للمستأجِر عبر المصدر الموثوق (جدول fields، دالّة SECURITY
       DEFINER): مالكٌ معروف ≠ مستأجِر الطلب (X-Tenant-Id الموثوق) ⇒ 403 (إغلاق
       IDOR / تسريب عبر المستأجرين بمعرفة field_id). fail-closed: قاعدة مُهيّأة لكن
       تعذّر إثبات الملكيّة ⇒ 503. بلا قاعدة (DB-less مقصود) أو الحقل غير موجود ⇒
       لا حجب من القاعدة (يبقى توكن الخدمة، لا تُسرَّب بيانات حقل مجهول).
    """
    main._require_service_token(x_agent_token)
    # تفويض ملكيّة الحقل (قبل أيّ استعلام قراءة) — fail-closed عند تعذّر الإثبات.
    await main._require_field_tenant(field_id)
    if not main._pool:
        # fail-closed: قاعدة البيانات غير موصولة ⇒ 503 (لا 200 بجسم خطأ يخدع
        # المستدعي ويُمرَّر للمكوّنات كأنّه نجاح). متّسق مع بقيّة الخدمات.
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")
    async with main._pool.acquire() as conn:
        # H5 FIX: أعمدة soil_readings الفعليّة (init_v8.sql) هي
        # temperature_c/ph/ec_ds_m/nitrogen_mg_kg/... — نُسمّيها بأسماء الـAPI
        # عبر alias. السابق كان يقرأ أعمدة غير موجودة (temperature/humidity/
        # ph_level/ec_level/n_ppm...) ⇒ UndefinedColumnError على كلّ قراءة.
        rows = await conn.fetch(
            """SELECT sensor_id,
                      temperature_c     AS temperature,
                      moisture_pct,
                      ph                AS ph_level,
                      ec_ds_m           AS ec_level,
                      nitrogen_mg_kg    AS n_ppm,
                      phosphorus_mg_kg  AS p_ppm,
                      potassium_mg_kg   AS k_ppm,
                      recorded_at
               FROM soil_readings
               WHERE field_id = $1
               ORDER BY recorded_at DESC LIMIT $2""",
            field_id,
            limit,
        )
    return [dict(r) for r in rows]


@router.post("/soil/ingest")
async def ingest_reading(reading: main.SoilReading, x_agent_token: str = Header(None)):
    """Ingest IoT soil sensor data — يتطلّب توكن خدمة + تحقّق Pydantic.

    أمان: لا نثق بـtenant_id من جسم الطلب أبداً (قابل للتزوير). نشتقّه من المالك
    المُثبَت للحقل (جدول fields عبر دالّة SECURITY DEFINER) أو من X-Tenant-Id
    الموثوق. مالكٌ معروف ≠ مستأجِر الطلب ⇒ 403 (منع كتابة عبر المستأجرين). إن حمل
    الجسم tenant_id يخالف المالك المُثبَت ⇒ نرفض (409). fail-closed عند تعذّر إثبات
    الملكيّة (قاعدة مُهيّأة) ⇒ 503."""
    main._require_service_token(x_agent_token)
    # تفويض ملكيّة الحقل + اشتقاق المالك الموثوق (لا من الجسم). owner=None يعني
    # DB-less مقصود/الحقل غير موجود (لا حجب — يُحفَظ السلوك ليبقى CI أخضر).
    owner = await main._require_field_tenant(reading.field_id)
    # اشتقاق tenant_id الموثوق: المالك المُثبَت أوّلاً، وإلّا X-Tenant-Id الموثوق.
    # لا يُؤخَذ tenant_id من الجسم إطلاقاً (يُتجاهَل، ويُرفَض إن خالف المالك المُثبَت).
    resolved_tenant = owner or main._REQ_TENANT.get()
    body_tenant = (reading.tenant_id or "").strip() or None
    if owner and body_tenant and body_tenant != owner:
        # الجسم يحمل tenant_id يخالف المالك الحقيقيّ للحقل ⇒ محاولة انتحال ⇒ رفض.
        raise HTTPException(409, "tenant_id في الجسم يخالف مالك الحقل — مرفوض")
    if not main._pool:
        # fail-closed: قاعدة البيانات غير موصولة ⇒ 503 (لا 200 بجسم خطأ يخدع
        # المستدعي ويُمرَّر للمكوّنات كأنّه نجاح). متّسق مع بقيّة الخدمات.
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")
    async with main._pool.acquire() as conn:
        # H5 FIX: نكتب الأعمدة الفعليّة بما فيها NPK. tenant_id عمود UUID
        # nullable ⇒ نحوّل "" إلى NULL لتفادي فشل الإدخال. نكتب المالك المُشتقّ
        # الموثوق لا قيمة الجسم (إغلاق ثقة المُدخَل).
        await conn.execute(
            """
            INSERT INTO soil_readings
            (field_id, sensor_id, temperature_c, moisture_pct,
             ph, ec_ds_m, nitrogen_mg_kg, phosphorus_mg_kg, potassium_mg_kg,
             recorded_at, tenant_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),$10)
            ON CONFLICT DO NOTHING
        """,
            reading.field_id,
            reading.sensor_id,
            reading.temperature,
            reading.moisture_pct,
            reading.ph_level,
            reading.ec_level,
            reading.n_ppm,
            reading.p_ppm,
            reading.k_ppm,
            resolved_tenant,  # مالك الحقل المُثبَت/الترويسة الموثوقة — لا قيمة الجسم
        )
    return {"status": "ingested"}
