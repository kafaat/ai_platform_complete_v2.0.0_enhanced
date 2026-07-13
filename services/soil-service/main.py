"""
SAHOOL v9.1.0 — services/soil-service/main.py
IoT soil sensor data ingestion and analysis.
MED-SOIL-01 FIX: service implementation added.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

import asyncpg
from fastapi import FastAPI, Header, HTTPException
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
_projection_stop: asyncio.Event | None = None
_projection_task: asyncio.Task | None = None


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
        if os.getenv("SOIL_PROJECTION_WORKER_ENABLED", "true").lower() in {"1", "true", "yes"}:
            import projection_jobs

            global _projection_stop, _projection_task
            _projection_stop = asyncio.Event()
            worker_id = os.getenv("HOSTNAME") or socket.gethostname()
            _projection_task = asyncio.create_task(
                projection_jobs.worker_loop(
                    _pool, stop=_projection_stop, worker_id=f"soil:{worker_id}"
                )
            )
    logger.info("✅ soil-service started")
    yield
    if _projection_stop:
        _projection_stop.set()
    if _projection_task:
        await _projection_task
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
    depth_cm: float = Field(30, gt=0, le=500)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)
    # deprecated compatibility only; authoritative tenant comes from X-Tenant-Id/field owner.
    tenant_id: str = ""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


# ─── تسجيل الراوترات المُفكَّكة (في النهاية: بعد app وكلّ الرموز المشتركة) ──────
# يُحلّ الاستيراد الدائريّ — وحدات routers/ تستورد رموزاً من main (app/الحالة/
# المساعِدات/SoilReading)؛ فيُستدعى التسجيل بعد تعريفها جميعاً.
from router_registry import register_routers  # noqa: E402

register_routers(app)

# إعادة تصدير مُعالِجات المسارات من routers/ إلى main (توافق: اختبارات السلوك تستدعي
# ``main.ingest_reading``/``main.get_readings`` مباشرةً وحارس تصادم الأسماء يفحص وجودها).
# ربط اسم فقط — لا يُسجّل مساراً ثانياً (register_routers سجّلها عبر الراوتر).
from routers.readings import get_readings, ingest_reading  # noqa: E402, F401
