"""
SAHOOL v9.1.0 — services/soil-service/main.py
IoT soil sensor data ingestion and analysis.
MED-SOIL-01 FIX: service implementation added.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar

import asyncpg
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("soil-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"soil","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("soil-service")

DATABASE_URL = os.getenv("DATABASE_URL", "")
NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
# مصادقة خدمة-لخدمة: استيعاب بيانات المستشعرات يكتب للقاعدة — يتطلّب توكناً
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    """يمنع حقن بيانات مستشعرات مزوّرة. فشل آمن لو التوكن غير مضبوط."""
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الاستيعاب معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


VERSION = "9.1.0"

_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if DATABASE_URL:
        # FIX: statement_cache_size معامل عميل asyncpg لا إعداد خادم — في
        # server_settings يفشل الاتصال بـ"unrecognized configuration parameter".
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0
        )
        # FINDING-001: ارفض الإقلاع إن تجاوز دور الاتّصال RLS (fail-closed افتراضيّاً).
        from shared.db_role_guard import assert_db_role_rls_safe

        await assert_db_role_rls_safe(_pool, service="soil-service")
    logger.info("✅ soil-service started")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="SAHOOL Soil Service", version=VERSION, lifespan=lifespan)


# ─── سياق المستأجِر للطلب (تفويض ملكيّة الحقل — عزل متعدّد المستأجرين) ──────
# قراءة/استيعاب قراءات التربة بمعرّف الحقل كانت بلا فحص ملكيّة ⇒ أيّ حامل توكن
# خدمة يقرأ قراءات أيّ مستأجِر بمعرفة field_id (IDOR / تسريب عبر المستأجرين). نلتقط
# الترويسة الموثوقة X-Tenant-Id (تحقنها البوّابة بعد التحقّق من JWT؛ proxy_params
# يُفرّغ أيّ ترويسة منتحَلة من العميل) ونفرض عبرها ملكيّة الحقل. غيابها ⇒ None ⇒
# مالكٌ معروف ≠ None ⇒ حجب (fail-closed)، نفس نمط raster-service.
_REQ_TENANT: ContextVar[str | None] = ContextVar("req_tenant", default=None)


def _tenant_from_header(value: str | None) -> str | None:
    """يطبّع ترويسة X-Tenant-Id: فراغ/None ⇒ None (لا مستأجِر)."""
    if not value:
        return None
    return value.strip() or None


@app.middleware("http")
async def _tenant_context_mw(request, call_next):
    """يضبط سياق المستأجِر لكلّ طلب من الترويسة الموثوقة، ويُعيده بعد الطلب."""
    token = _REQ_TENANT.set(_tenant_from_header(request.headers.get("X-Tenant-Id")))
    try:
        return await call_next(request)
    finally:
        _REQ_TENANT.reset(token)


async def _field_owner(field_id: str) -> str | None:
    """مالك الحقل (tenant_id) من المصدر الموثوق (جدول fields عبر دالّة SECURITY
    DEFINER). None ⇒ غير محسوم (بلا قاعدة DB-less مقصود/الحقل غير موجود) ⇒ لا حجب.
    يرفع OwnerLookupUnavailable إن كانت القاعدة مُهيّأة لكن تعذّر الإثبات (يُترَك
    للمنادي ليُقرّر fail-closed ⇒ 503). لا نُخبّئ النتيجة (الملكيّة ثابتة لكن مسار
    القراءة نادر نسبيّاً ولا حاجة لذاكرة TTL هنا)."""
    import db_persist

    # OwnerLookupUnavailable يُمرَّر (لا يُلتقَط) ⇒ يقرّر المنادي الحجب 503. None هنا =
    # بلا قاعدة (DB-less مقصود) أو الحقل غير موجود ⇒ لا حجب.
    return await db_persist.field_owner_tenant(field_id)


async def _require_field_tenant(field_id: str) -> str | None:
    """تفويض ملكيّة الحقل للمستأجِر (عزل متعدّد المستأجرين على قراءات التربة).

    المصادقة مفروضة عند البوّابة (تتحقّق JWT وتحقن X-Tenant-Id موثوقاً)، لكنّ توكن
    الخدمة وحده لا يربط القراءة بمستأجِر ⇒ بلا فحص ملكيّة يقرأ مستأجِرٌ حقلَ آخر
    بتخمين/معرفة المعرّف (IDOR). نحسم من المصدر الموثوق (جدول fields) عبر دالّة
    SECURITY DEFINER. field_id مفتاح أساسيّ ⇒ مالك واحد عالميّاً.

    العائد: المالك المُثبَت (tenant_id) إن وُجد، وإلّا None (DB-less/الحقل غير موجود)
    — يستخدمه الاستيعاب لاشتقاق tenant_id من المصدر الموثوق لا من جسم الطلب.

    fail-closed: قاعدة مُهيّأة + تعذّر إثبات الملكيّة ⇒ 503 (لا نخدم بلا إثبات). أمّا
    «بلا قاعدة» أو «الحقل غير موجود» ⇒ المالك None ⇒ لا حجب (تجنّب رفض زائف عند
    التشغيل المقصود بلا قاعدة — CI/تطوير — وعند الحقل المجهول لا تُسرَّب بيانات)."""
    import db_persist

    req_tenant = _REQ_TENANT.get()
    try:
        owner = await _field_owner(field_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الحقل — أعد المحاولة لاحقاً") from e
    if owner and owner != req_tenant:
        # مالكٌ معروف ≠ مستأجِر الطلب (أو غياب المستأجِر) ⇒ إغلاق IDOR.
        raise HTTPException(403, "الحقل لا يخصّ مستأجِرك")
    return owner


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "soil-service", "version": VERSION}


@app.get("/readyz")
async def readyz():
    try:
        if _pool:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        # لا نُرجِع str(e) (يسرّب DSN/تفاصيل اتّصال) — رسالة عامّة + تسجيل داخليّ
        logger.warning("readyz فشل: %s", e)
        raise HTTPException(503, "not ready") from e


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/soil/readings/{field_id}")
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
    _require_service_token(x_agent_token)
    # تفويض ملكيّة الحقل (قبل أيّ استعلام قراءة) — fail-closed عند تعذّر الإثبات.
    await _require_field_tenant(field_id)
    if not _pool:
        # fail-closed: قاعدة البيانات غير موصولة ⇒ 503 (لا 200 بجسم خطأ يخدع
        # المستدعي ويُمرَّر للمكوّنات كأنّه نجاح). متّسق مع بقيّة الخدمات.
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")
    async with _pool.acquire() as conn:
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


class SoilReading(BaseModel):
    """نموذج تحقّق لقراءة مستشعر التربة — يرفض البيانات المشوّهة."""

    field_id: str = Field(min_length=1, max_length=64)
    sensor_id: str = Field(min_length=1, max_length=64)
    temperature: float | None = Field(None, ge=-50, le=80)
    moisture_pct: float | None = Field(None, ge=0, le=100)
    ph_level: float | None = Field(None, ge=0, le=14)
    ec_level: float | None = Field(None, ge=0, le=50)
    # H5 FIX: NPK كان يُقرأ ولا يُكتب ولا حقل له — أُضيف ليُدخَل فعلاً.
    n_ppm: float | None = Field(None, ge=0)
    p_ppm: float | None = Field(None, ge=0)
    k_ppm: float | None = Field(None, ge=0)
    tenant_id: str = ""


@app.post("/soil/ingest")
async def ingest_reading(reading: SoilReading, x_agent_token: str = Header(None)):
    """Ingest IoT soil sensor data — يتطلّب توكن خدمة + تحقّق Pydantic.

    أمان: لا نثق بـtenant_id من جسم الطلب أبداً (قابل للتزوير). نشتقّه من المالك
    المُثبَت للحقل (جدول fields عبر دالّة SECURITY DEFINER) أو من X-Tenant-Id
    الموثوق. مالكٌ معروف ≠ مستأجِر الطلب ⇒ 403 (منع كتابة عبر المستأجرين). إن حمل
    الجسم tenant_id يخالف المالك المُثبَت ⇒ نرفض (409). fail-closed عند تعذّر إثبات
    الملكيّة (قاعدة مُهيّأة) ⇒ 503."""
    _require_service_token(x_agent_token)
    # تفويض ملكيّة الحقل + اشتقاق المالك الموثوق (لا من الجسم). owner=None يعني
    # DB-less مقصود/الحقل غير موجود (لا حجب — يُحفَظ السلوك ليبقى CI أخضر).
    owner = await _require_field_tenant(reading.field_id)
    # اشتقاق tenant_id الموثوق: المالك المُثبَت أوّلاً، وإلّا X-Tenant-Id الموثوق.
    # لا يُؤخَذ tenant_id من الجسم إطلاقاً (يُتجاهَل، ويُرفَض إن خالف المالك المُثبَت).
    resolved_tenant = owner or _REQ_TENANT.get()
    body_tenant = (reading.tenant_id or "").strip() or None
    if owner and body_tenant and body_tenant != owner:
        # الجسم يحمل tenant_id يخالف المالك الحقيقيّ للحقل ⇒ محاولة انتحال ⇒ رفض.
        raise HTTPException(409, "tenant_id في الجسم يخالف مالك الحقل — مرفوض")
    if not _pool:
        # fail-closed: قاعدة البيانات غير موصولة ⇒ 503 (لا 200 بجسم خطأ يخدع
        # المستدعي ويُمرَّر للمكوّنات كأنّه نجاح). متّسق مع بقيّة الخدمات.
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")
    async with _pool.acquire() as conn:
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
