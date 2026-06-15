"""
api/main.py — FastAPI application للنواة سهول
================================================
يربط api_adapter (المحايد عن الإطار) بـHTTP routes حقيقية.

النمط Hexagonal:
  HTTP Request → FastAPI route → ApiRequest dict →
  api_adapter.handle_*() → ApiResponse → HTTP Response

ما يُقدّمه:
  GET  /healthz                    → liveness (لا dependency)
  GET  /readyz                     → readiness (يفحص النواة)
  POST /api/v1/recommendations     → توصية جديدة (uses recommendation_engine)
  POST /api/v1/observations        → تسجيل مشاهدة (يدخل في offline queue إن offline)
  POST /api/v1/sync                → دفعة sync من العميل offline-first
  POST /api/v1/auth/login          → JWT issue (dev mode: HS256، لا RS256)
  GET  /api/v1/me                  → معلومات المستخدم

ما لم يُبنَ هنا (مُؤجَّل بمبرّر):
  • DB integration (in-memory للـMVP، PostgreSQL لاحقاً)
  • RS256 JWT keys (HS256 dev secret حالياً)
  • Rate limiting بـRedis (في-memory الآن، يتغذّى من api_adapter)
  • OAuth2/SSO
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

# جعل النواة قابلة للاستيراد
sys.path.insert(0, str(Path(__file__).parent.parent))

import jwt  # PyJWT
from core.api_adapter import (
    ApiRequest,
    handle_healthz,
    handle_readyz,
    handle_recommendation_request,
)
from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema
from core.offline_first import (
    OfflineQueue,
    OperationKind,
    SyncStatus,
    apply_supersession,
    record_operation_offline,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field

logger = logging.getLogger("sahool.api")

# ─── إعدادات ──────────────────────────────────────────────────────
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن لرفض توكن
# من مُصدِر مجهول رغم صحّة التوقيع/الجمهور (تدقيق B: لم يكن iss يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# سياسة أمنيّة: لا سرّ افتراضيّ معروف. السرّ الحرفيّ المنشور سابقاً
# ("dev-secret-CHANGE-IN-PRODUCTION") كان يسمح لأيّ مَن يعرفه بتزوير توكن لأيّ
# مستأجِر/دور (owner). الآن:
#   • الإنتاج (SAHOOL_ENV=production): يجب ضبط سرّ قويّ (≥32) وإلّا توقّف (fail-closed).
#   • التطوير: إن غاب/ضعف نولّد سرّاً عشوائيّاً لهذه العمليّة فقط — لا يُزوَّر عبر
#     سرّ منشور، والتوكنات تُمنَح وتُتحقَّق داخل العمليّة نفسها (يكفي للاختبار/dev).
_IS_PRODUCTION = os.getenv("SAHOOL_ENV", "development").lower() == "production"
# strip: مسافات/أسطر لاحقة لا تُحوّل سرّاً ضعيفاً/افتراضيّاً إلى «قويّ» (التفاف على الفحص).
_ENV_SECRET = os.getenv("SAHOOL_JWT_SECRET", "").strip()
_WEAK_SECRET = (
    not _ENV_SECRET or _ENV_SECRET == "dev-secret-CHANGE-IN-PRODUCTION" or len(_ENV_SECRET) < 32
)
if _WEAK_SECRET and _IS_PRODUCTION:
    logger.error(
        "🛑 SAHOOL_JWT_SECRET غير مضبوط/ضعيف في الإنتاج — توقّف. "
        "عيّن سرّاً قويّاً (≥32 محرفاً) واستخدم RS256."
    )
    sys.exit(1)
if _WEAK_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)  # عشوائيّ لكلّ عمليّة (تطوير فقط)
    logger.warning(
        "⚠️ SAHOOL_JWT_SECRET غير مضبوط/ضعيف — وُلِّد سرّ تطوير عشوائيّ لهذه العمليّة "
        "فقط. عيّن سرّاً قويّاً (≥32) واستخدم RS256 قبل أيّ نشر."
    )
else:
    JWT_SECRET = _ENV_SECRET

# دخول dev بلا كلمة مرور (/api/v1/auth/{login,signup}) يُصدِر توكناً كامل الصلاحيّة
# من جسم الطلب — تجاوز مصادقة لو وصلته الطلبات. لا يُفعَّل إلّا بإقرار صريح
# (SAHOOL_DEV_AUTH=1) وفي غير الإنتاج. الافتراض **مُعطَّل**: staging/فارغ/غير مضبوط
# لا يكشفه (المصادقة الحقيقيّة عبر خدمة sahool-auth بـbcrypt).
_DEV_AUTH_ENABLED = (
    os.getenv("SAHOOL_DEV_AUTH", "").strip().lower() in ("1", "true", "yes") and not _IS_PRODUCTION
)
if _DEV_AUTH_ENABLED:
    logger.warning("⚠️ SAHOOL_DEV_AUTH مُفعَّل — دخول dev بلا كلمة مرور (تطوير فقط).")

# Offline queue واحد على مستوى التطبيق.
# ⚠️ N2: حالة في الذاكرة → يتطلّب --workers 1. عاملان = طابوران منفصلان =
# تضارب بيانات. قبل رفع العمّال: انقله لـRedis (LIST/Stream لكلّ مستأجر).
_OFFLINE_QUEUE = OfflineQueue(max_per_tenant=1000)


# ─── FastAPI app ─────────────────────────────────────────────────
app = FastAPI(
    title="SAHOOL Core API",
    description="API للنواة سهول — decision-system زراعي offline-first",
    version="1.0.0",
)

# ─── PostgreSQL pool (lifespan) ─────────────────────────────────
# يُنشأ pool واحد عند الإقلاع لو DATABASE_URL مضبوط؛ وإلّا يبقى None
# (الـendpoints المعتمدة على DB تُرجع 503 بوضوح بدل التعطّل).
# لتشغيل القاعدة: migrations/bootstrap_postgres.sh ثم ضبط DATABASE_URL.
_DB_POOL = None  # asyncpg.Pool | None


@app.on_event("startup")
async def _init_db_pool():
    global _DB_POOL
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        logging.warning("DATABASE_URL غير مضبوط — endpoints القاعدة معطّلة (503)")
        return
    try:
        import asyncpg

        # statement_cache_size=0 لتوافق PgBouncer (مبدأ موثّق)
        _DB_POOL = await asyncpg.create_pool(dsn, statement_cache_size=0, min_size=1, max_size=10)
        logging.info("✓ pool القاعدة جاهز")
    except Exception as e:  # noqa: BLE001
        logging.error("فشل إنشاء pool القاعدة: %s", e)
        _DB_POOL = None


@app.on_event("startup")
async def _start_scheduler():
    """يبدأ جدولة المهامّ الدوريّة (أتمتة داخليّة).

    صدق: المهامّ تُسجَّل فقط إن توفّر منطقها الفعلي. fetch_weather مربوط
    بـOpen-Meteo عبر weather_automation (يسحب فقط للإحداثيّات المسجّلة).
    فحص النضارة لا يحتاج تبعيّات. لا نسجّل مهمّة فارغة تدّعي عملاً.
    """
    from api.agronomic_consistency import check_decision_freshness
    from api.imagery_automation import imagery_automation
    from api.scheduler import register_default_tasks, scheduler
    from api.weather_automation import weather_automation

    # اربط pool القاعدة للاستمرار الدائم + حمّل ما سبق تسجيله (إن توفّر)
    if _DB_POOL is not None:
        weather_automation.set_pool(_DB_POOL)
        imagery_automation.set_pool(_DB_POOL)
        try:
            wn = await weather_automation.load_from_db()
            inum = await imagery_automation.load_from_db()
            logging.info("أتمتة: حُمّل %s إحداثيّة طقس و%s حقل صور من القاعدة", wn, inum)
        except Exception as e:  # noqa: BLE001
            logging.warning("فشل تحميل حالة الأتمتة من القاعدة: %s", e)

    async def _freshness_sweep():
        check_decision_freshness(ndvi_age_days=0, soil_age_days=0, weather_age_hours=0)

    async def _weather_sweep():
        # سحب الطقس دوريّاً للإحداثيّات المسجّلة (Open-Meteo، مجّاني).
        # لو لا إحداثيّات → لا يضرب المصدر (صدق).
        result = await weather_automation.refresh_all()
        if result.get("refreshed"):
            logging.info("أتمتة الطقس: حُدّثت %s إحداثيّة", result["refreshed"])

    async def _imagery_sweep():
        # فحص صور Sentinel الجديدة للحقول المتابَعة + حساب المؤشّرات.
        # لو لا حقول → لا يضرب raster-service (صدق).
        result = await imagery_automation.scan_all()
        if result.get("new_images"):
            logging.info(
                "أتمتة الصور: %s صورة جديدة، فُحص %s حقل", result["new_images"], result["scanned"]
            )

    async def _alerts_sweep():
        # تقييم تنبيهات كلّ الحقول دوريّاً لكلّ مستأجِر. لا واجهة/مستخدم هنا،
        # لذا نبني مبدأً نظاميّاً (OWNER) لكلّ tenant من جدول fields ونمرّره
        # لنفس مسار التقييم/الحفظ (المُعاد استخدامه في endpoint عند الطلب).
        # معزول: فشل حقل/مستأجِر لا يُسقط البقيّة. صدق: لو لا حقول → لا عمل.
        if _DB_POOL is None:
            return
        from core.canonical_schemas import UserRole, UserSchema

        try:
            async with _DB_POOL.acquire() as conn:
                trows = await conn.fetch(
                    "SELECT DISTINCT tenant_id FROM fields WHERE tenant_id IS NOT NULL"
                )
        except Exception as e:  # noqa: BLE001 — تعذّر سرد المستأجرين ⇒ تخطٍّ صامت
            logging.warning("أتمتة التنبيهات: تعذّر سرد المستأجرين: %s", type(e).__name__)
            return

        total_created = 0
        for tr in trows:
            tid = str(tr["tenant_id"])
            sys_user = UserSchema(
                user_id="system-scheduler",
                tenant_id=tid,
                role=UserRole.OWNER,
                name_ar="نظام الجدولة",
            )
            try:
                async with tenant_connection(sys_user) as conn:
                    frows = await conn.fetch(
                        "SELECT field_id FROM fields WHERE tenant_id = $1::uuid", tid
                    )
                for fr in frows:
                    try:
                        created, _ = await _evaluate_field_alerts_persist(sys_user, fr["field_id"])
                        total_created += len(created)
                    except Exception as fe:  # noqa: BLE001 — عزل لكلّ حقل
                        logging.debug(
                            "أتمتة التنبيهات: تخطّي حقل %s: %s",
                            fr["field_id"],
                            type(fe).__name__,
                        )
            except Exception as te:  # noqa: BLE001 — عزل لكلّ مستأجِر
                logging.warning("أتمتة التنبيهات: تخطّي مستأجِر %s: %s", tid, type(te).__name__)
        if total_created:
            logging.info("أتمتة التنبيهات: أُنشئ %s تنبيهاً عبر كلّ الحقول", total_created)

    register_default_tasks(
        fetch_weather=_weather_sweep,
        scan_new_imagery=_imagery_sweep,
        check_decision_freshness=_freshness_sweep,
        run_alerts_evaluation=_alerts_sweep,
        alerts_evaluation_interval_seconds=int(
            os.getenv("SAHOOL_ALERTS_EVAL_INTERVAL_SECONDS", "21600")
        ),
    )
    scheduler.start()


# ── OutboxWorker: relay الأحداث من event_outbox إلى NATS (نمط outbox الموثوق) ──
# يُغلق فجوة «الأحداث تُكتب ولا تُنشَر»: emit_event يكتب الحدث + صفّ outbox ذرّيّاً
# مع تغيير الحالة، وهذا العامل يقرأ المعلّق ويُنشره لـNATS (backoff/retry).
_OUTBOX_WORKER = None  # OutboxWorker | None
_OUTBOX_TASK = None  # asyncio.Task | None
_NATS_CONN = None  # nats client | None


@app.on_event("startup")
async def _start_outbox_worker():
    """يبدأ relay الأحداث (outbox → NATS). تدهور رشيق: لو غاب NATS/القاعدة، نتخطّى
    بتحذير دون إسقاط الإقلاع — الأحداث تبقى في outbox لتُنشَر عند توفّر NATS لاحقاً."""
    global _OUTBOX_WORKER, _OUTBOX_TASK, _NATS_CONN
    if _DB_POOL is None:
        logging.warning("OutboxWorker: لا pool قاعدة — relay الأحداث معطّل")
        return
    try:
        import nats

        from api.event_bus import OutboxWorker

        nats_url = os.getenv("NATS_URL", "nats://sahool-nats:4222")
        _NATS_CONN = await nats.connect(nats_url, max_reconnect_attempts=-1)

        async def _publish(subject: str, payload: bytes) -> None:
            await _NATS_CONN.publish(subject, payload)

        _OUTBOX_WORKER = OutboxWorker(_DB_POOL, _publish)
        _OUTBOX_TASK = asyncio.create_task(_OUTBOX_WORKER.run())
        logging.info("✓ OutboxWorker بدأ — relay الأحداث إلى %s", nats_url)
    except Exception as e:  # noqa: BLE001 — غياب NATS لا يُسقط المنصّة
        logging.warning("OutboxWorker معطّل (NATS؟): %s — الأحداث تبقى في outbox", e)


@app.on_event("shutdown")
async def _stop_outbox_worker():
    global _OUTBOX_WORKER, _OUTBOX_TASK, _NATS_CONN
    if _OUTBOX_WORKER is not None:
        _OUTBOX_WORKER.stop()
    if _OUTBOX_TASK is not None:
        _OUTBOX_TASK.cancel()
        try:
            await _OUTBOX_TASK
        except asyncio.CancelledError:
            pass
    if _NATS_CONN is not None:
        # drain قد يرمي لو انقطع الاتّصال — لا نُفشِل الإيقاف بسببه.
        try:
            await _NATS_CONN.drain()
        except Exception as e:  # noqa: BLE001
            logging.warning("NATS drain أثناء الإيقاف: %s", e)
    _OUTBOX_WORKER = _OUTBOX_TASK = _NATS_CONN = None


@app.on_event("shutdown")
async def _stop_scheduler():
    from api.scheduler import scheduler

    await scheduler.stop()


@app.on_event("shutdown")
async def _close_db_pool():
    global _DB_POOL
    if _DB_POOL is not None:
        await _DB_POOL.close()
        _DB_POOL = None


def get_pool():
    """اعتماديّة: تُرجع الـpool أو 503 لو القاعدة غير مفعّلة."""
    if _DB_POOL is None:
        raise HTTPException(
            status_code=503,
            detail="قاعدة البيانات غير مفعّلة. شغّل migrations/bootstrap_postgres.sh واضبط DATABASE_URL.",
        )
    return _DB_POOL


from contextlib import asynccontextmanager as _asynccontextmanager  # noqa: E402


@_asynccontextmanager
async def tenant_connection(user):
    """يفتح اتّصالاً ضمن معاملة ويضبط سياق المستأجر لتفعيل RLS فعليّاً.

    إصلاح ثغرة عزل المستأجرين: سياسات RLS تعتمد على
    current_setting('app.current_tenant'). بدون ضبطه على الاتّصال، إمّا
    تُرفض الاستعلامات (لو فُرض RLS) أو يقرأ المستأجر بيانات غيره (IDOR).

    الاستخدام:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(...)   # مُرشّحة تلقائيّاً بـRLS
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # SET LOCAL — يدوم ضمن المعاملة فقط (آمن مع connection pooling)
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "       set_config('app.current_user_id', $2, true), "
                "       set_config('app.current_role', $3, true)",
                str(user.tenant_id),
                str(user.user_id),
                user.role.value if hasattr(user.role, "value") else str(user.role),
            )
            yield conn


async def _apply_tenant_guc(conn, tenant_id: str) -> None:
    """يضبط سياق المستأجِر على اتّصال خام (يُحاكي main.py:346 حرفيّاً).

    `true` ⇒ transaction-local (SET LOCAL — آمن مع connection pooling). يُستخدَم
    على المسارات التي تكتسب اتّصالها الخاصّ من الـpool (لا عبر tenant_connection)
    لكنّها مع ذلك مُنطّقة بمستأجِر واحد، فتفعّل RLS فعليّاً تحت الدور المُقيَّد
    (sahool_app: NOBYPASSRLS, FORCE RLS). يجب استدعاؤه داخل معاملة قبل أيّ
    استعلام مُنطّق بمستأجِر.
    """
    await conn.execute(
        "SELECT set_config('app.current_tenant', $1, true)",
        str(tenant_id),
    )


async def _emit_domain_event(conn, user, event_type_name, entity_type, entity_id, payload):
    """يُصدر حدث domain ضمن نفس معاملة الكتابة (نمط outbox: الحدث + صفّ outbox
    يُكتبان ذرّيّاً مع تغيير الحالة)، لكن داخل **savepoint** — نجاحه ذرّيّ مع
    الحالة، وفشله (مثلاً غياب جداول الأحداث v11) يُسجَّل ولا يُجهض الكتابة. هكذا
    نُغلق فجوة «كتابة بلا حدث» دون جعل مسار الكتابة قابلاً للكسر."""
    from api.event_bus import EventBus, EventSource, EventType

    # اسم حدث غير معروف = خطأ مطوّر (لا فشل قاعدة) — يُكشَف فوراً (KeyError) لا يُبتلَع
    # صامتاً؛ خارج try حتى لا يُخفيه التقاط فشل الإصدار التالي.
    et = EventType[event_type_name]
    try:
        async with conn.transaction():  # SAVEPOINT داخل معاملة tenant_connection
            await EventBus(get_pool(), conn=conn).emit(
                event_type=et,
                entity_type=entity_type,
                entity_id=str(entity_id),
                tenant_id=str(user.tenant_id),
                payload=payload,
                source=EventSource.WEB,
                actor_id=str(user.user_id),
            )
    except Exception as e:  # noqa: BLE001 — فشل الإصدار (غياب جداول/DB) لا يكسر الكتابة (تصميم متعمّد)
        logger.warning("emit %s تخطّي: %s", event_type_name, e)


# ─── idempotency لنقاط الموبايل (إعادات offline لا تُكرّر الكتابة) ──────────────
# الموبايل قد يُعيد POST نفسه (شبكة ضعيفة/مزامنة batch بعد انقطاع). بمفتاح
# Idempotency-Key (UUID) يُسجَّل الأمر مرّة واحدة في جدول commands؛ الإعادة تُعيد
# النتيجة المخزّنة بلا إعادة تنفيذ. كلّ شيء داخل معاملة tenant_connection (RLS +
# ذرّيّة): فشل العمل ⇒ ارتداد كامل (بما فيه أثر الأمر) ⇒ إعادة آمنة. بلا مفتاح ⇒
# تنفيذ عاديّ (توافق خلفيّ كامل — لا يتغيّر سلوك العملاء القائمين).
def _idem_key(idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> str | None:
    """يستخرج مفتاح الإيدمبوتنسي (UUID) ويتحقّق من شكله.

    فارغ/مسافات ⇒ يُعامَل كغياب (None، تنفيذ عاديّ)؛ قيمة غير فارغة غير صالحة ⇒ 400
    (لا تضيع idempotency بصمت لمفتاح مُشوَّه). يُعيد المفتاح بعد strip.
    """
    if idempotency_key is None:
        return None
    key = idempotency_key.strip()
    if not key:
        return None
    import uuid as _uuid

    try:
        _uuid.UUID(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Idempotency-Key يجب أن يكون UUID") from e
    return key


async def _idempotent(store, command_id, do_work, *, command_type, actor_id, tenant_id, payload):
    """منطق idempotency نقيّ (store مُحقَن ⇒ قابل للاختبار). يُرجِع نتيجة العمل (JSON).

    أوّل مرّة: يُدرِج الأمر، ينفّذ do_work، يسجّل النتيجة. الإعادة الناجحة: يُعيد
    النتيجة المخزّنة بلا تنفيذ. الإعادة بينما الأصل قيد المعالجة/فشل: 409 (أعد لاحقاً).

    قيد تصميميّ مهمّ: يجب استدعاؤه **داخل معاملة تَرتدّ عند الفشل** (مثل
    tenant_connection). الاعتماد على الارتداد هو ما يجعله سليماً: فشل do_work ⇒
    ارتداد إدراج الأمر أيضاً ⇒ لا أمر «pending» يتيم، والإعادة اللاحقة تُنفَّذ من
    جديد بأمان (لا تعلّق على 409 أبديّ). لذا لا نُعلّم processing/failed صراحةً —
    الارتداد يتكفّل، والتعليم داخل المعاملة سيُرتَدّ بلا فائدة. لا تستخدمه خارج معاملة.
    """
    from api.command_store import Command, CommandSource, CommandStatus

    cmd = Command.new(
        command_type,
        actor_id,
        tenant_id,
        payload,
        source=CommandSource.MOBILE,
        command_id=command_id,
    )
    if await store.insert(cmd):  # أُدرِج الآن ⇒ تنفيذ أوّل
        result = await do_work()
        await store.mark_succeeded(command_id, result)
        return result
    existing = await store.get(command_id)  # موجود مسبقاً
    if existing is not None and existing.status == CommandStatus.SUCCEEDED:
        return existing.result  # نتيجة مخزّنة — لا إعادة تنفيذ (idempotent)
    raise HTTPException(status_code=409, detail="الأمر قيد المعالجة — أعد المحاولة لاحقاً")


# المتغيّر: SAHOOL_CORS_ORIGINS = "https://app.sahool.ye,https://www.sahool.ye"
# للتطوير: SAHOOL_CORS_ORIGINS = "http://localhost:3000,http://10.0.2.2:8000"
_cors_raw = os.getenv("SAHOOL_CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

if not _cors_origins:
    # في غياب الـENV — fallback آمن (dev مفتوح، prod مغلق)
    if os.getenv("SAHOOL_ENV", "development") == "production":
        _cors_origins = []  # ❌ لا يقبل أيّ origin (يجب ضبط SAHOOL_CORS_ORIGINS)
    else:
        _cors_origins = ["http://localhost:3000", "http://10.0.2.2:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ─── حدّ المعدّل (Rate Limiting) ─────────────────────────────────
# الفجوة المسدودة (تدقيق التغطية، الأمن): platform API كان بلا أيّ حدّ معدّل
# (خدمة auth تملك check_ip_rate، لكن النواة لا). نافذة ثابتة في الذاكرة لكلّ IP.
# ⚠ N: الحالة في الذاكرة (لكلّ worker). كافٍ كحاجز DoS أساسيّ في MVP؛ قبل توزيع
# العمّال انقله لـRedis (INCR+EXPIRE، نفس نمط auth) لعدّاد مشترك دقيق.
_RATE_LIMIT_PER_MIN = int(os.getenv("SAHOOL_RATE_LIMIT_PER_MIN", "120"))
_RATE_EXEMPT_PATHS = {"/healthz", "/readyz", "/metrics"}
_RATE_MAX_BUCKETS = 50000  # سقف المفاتيح — يمنع نموّ الذاكرة بلا حدّ من IPs فريدة
_rate_buckets: dict[str, tuple[int, float]] = {}  # client → (count, window_start_epoch)


def _rate_client_key(request) -> str:
    """العميل الحقيقي خلف البروكسي: X-Forwarded-For (أوّل قفزة) ثمّ X-Real-IP،
    وإلّا عنوان الاتّصال المباشر. nginx يضبطهما؛ بدونهما يُبكَّت الكلّ تحت IP
    البروكسي ⇒ خنق عامّ خاطئ (ملاحظة المراجعة)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )


def _prune_rate_buckets(now: float) -> None:
    """تنظيف كسول: يحذف النوافذ المنتهية حين يتضخّم القاموس (لا مؤقّت خلفيّ)."""
    for k in [k for k, (_, start) in _rate_buckets.items() if now - start >= 60.0]:
        _rate_buckets.pop(k, None)


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """حاجز DoS أساسيّ: يحدّ طلبات كلّ عميل في نافذة دقيقة (fail-open عند الشكّ)."""
    if _RATE_LIMIT_PER_MIN <= 0 or request.url.path in _RATE_EXEMPT_PATHS:
        return await call_next(request)
    import time as _t

    now = _t.time()
    # تنظيف كسول عند التضخّم (burst من IPs فريدة لا يُنمّي الذاكرة بلا حدّ)
    if len(_rate_buckets) > _RATE_MAX_BUCKETS:
        _prune_rate_buckets(now)
    key = _rate_client_key(request)
    count, start = _rate_buckets.get(key, (0, now))
    if now - start >= 60.0:  # نافذة جديدة
        count, start = 0, now
    count += 1
    _rate_buckets[key] = (count, start)
    if count > _RATE_LIMIT_PER_MIN:
        retry = max(1, int(60.0 - (now - start)))
        return JSONResponse(
            status_code=429,
            content={"detail": "طلبات كثيرة — تجاوزت الحدّ المسموح، حاول لاحقاً"},
            headers={"Retry-After": str(retry)},
        )
    return await call_next(request)


# ─── Pydantic models للـrequest/response ─────────────────────────


class LoginRequest(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "agronomist"
    name_ar: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RecommendationRequest(BaseModel):
    tenant_id: str
    farm_id: str
    field_id: str
    crop: str
    validation: dict
    current_indicators: dict = Field(default_factory=dict)
    district_id: str | None = None


class ObservationRequest(BaseModel):
    tenant_id: str
    farm_id: str | None = None
    field_id: str | None = None
    observable_id: str
    value: float
    unit: str = ""
    source: str = "manual"  # manual/sensor/lab/satellite
    confidence: str = "medium"
    measured_at: str  # ISO datetime
    method: str | None = None


class SyncBatchRequest(BaseModel):
    """دفعة عمليات من العميل offline-first."""

    tenant_id: str
    operations: list[dict]


class FieldSummary(BaseModel):
    """ملخّص حقل للقائمة (HomeScreen)."""

    field_id: str
    farm_id: str
    name_ar: str
    crop: str
    area_ha: float
    quality_grade: str  # READY/LIMITED/PENDING_LAB/BLOCKED
    last_observation_at: str | None = None
    pending_activities: int = 0
    health_summary_ar: str  # "صحّي" / "يحتاج ريّ" / "إجهاد ملحي"
    soil_type: str | None = None  # نوع التربة (يُمرَّر للواجهة بدل ضياعه)
    manager: str | None = None  # المسؤول عن الحقل
    # حقول مُثراة (v33): كود الحقل + مصدر الماء + الملكيّة + الكشف الآلي للموقع.
    field_code: str | None = None  # كود الحقل (مرجع المزارع)
    description: str | None = None  # وصف حرّ
    water_source: str | None = None  # well/canal/river/rainfed/tank/mixed
    ownership_type: str | None = None  # نوع الملكيّة
    country: str | None = None  # الدولة (مكتشفة آليّاً من المركز)
    region: str | None = None  # الإقليم/المحافظة (مكتشفة آليّاً من المركز)
    # حقول الخريطة (اختياريّة، توافق خلفيّ): مركز الحقل وهندسته لرسم المضلّع.
    lat: float | None = None
    lon: float | None = None
    geometry: dict | None = None


# ─── تفاصيل الحقل المتقدّمة (v37) — ملء تدريجيّ بعد الإنشاء ────────
# القائمة (list_fields) تبقى رشيقة؛ هذه الأعمدة تُقرأ عبر GET /fields/{id}
# وتُحدَّث جزئيّاً عبر PATCH /fields/{id}. مصدر واحد لأسماء الأعمدة (يُعاد
# استخدامه في SELECT التفصيليّ وفي بنّاء التحديث الجزئيّ + الاختبارات).
_FIELD_ADVANCED_COLUMNS: tuple[str, ...] = (
    "soil_ph",
    "soil_ec",
    "soil_om",
    "soil_n",
    "soil_p",
    "soil_k",
    "elevation_m",
    "slope_pct",
    "aspect",
    "climate_zone",
    "zone_key",  # v49: مفتاح الإقليم القانوني (agro_climate_zones) — يُفعّل تحليل السوق الإقليمي
    "annual_rainfall_mm",
    "owner_name",
    "lease_years",
    "registry_no",
    # نموذج الريّ/المياه التفصيليّ (v41) — ملء تدريجيّ عبر PATCH (Progressive Profiling)
    "irrigation_type",
    "irrigation_efficiency_pct",
    "flow_rate_m3h",
    "pump_type",
    "well_depth_m",
    "water_ec",
    # ربط المدير بمستخدم حقيقيّ (v41) — إضافيّ بجانب manager النصّيّ
    "manager_user_id",
)

# حدّ التداخل المعتبَر (م²) — أكبر منه ⇒ تداخل حقيقيّ لا مجرّد ملامسة حدود/انزياح GPS.
_MIN_FIELD_OVERLAP_M2 = 25.0


def _significant_overlaps(overlaps, min_m2: float = _MIN_FIELD_OVERLAP_M2) -> list:
    """يُرشّح صفوف التداخل بحيث يبقى ما تجاوزت مساحة تقاطعه الحدّ — دالّة نقيّة (لا DB).

    يقبل صفوف asyncpg.Record أو dict (كلاهما يدعم o["overlap_m2"]). قيمة None تُعامَل
    كصفر. يُستخدَم لتحويل قرار «تداخل معتبَر» إلى منطق قابل للاختبار offline.
    """
    return [o for o in overlaps if (o["overlap_m2"] or 0.0) > min_m2]


class FieldDetail(FieldSummary):
    """تفاصيل حقل كاملة (لوحة التفاصيل) — يرث الملخّص ويضيف الأعمدة المتقدّمة.

    كلّها اختياريّة (ملء تدريجيّ): كيمياء التربة + المناخ الدقيق + الملكيّة.
    """

    # كيمياء التربة (نتائج مختبر)
    soil_ph: float | None = None
    soil_ec: float | None = None
    soil_om: float | None = None  # المادّة العضويّة %
    soil_n: float | None = None
    soil_p: float | None = None
    soil_k: float | None = None
    # المناخ الدقيق / التضاريس
    elevation_m: float | None = None
    slope_pct: float | None = None
    aspect: str | None = None
    climate_zone: str | None = None
    zone_key: str | None = None
    annual_rainfall_mm: float | None = None
    # تفاصيل الملكيّة
    owner_name: str | None = None
    lease_years: int | None = None
    registry_no: str | None = None
    # الريّ/المياه التفصيليّ (v41)
    irrigation_type: str | None = None  # drip/pivot/flood/sprinkler/rainfed/subsurface
    irrigation_efficiency_pct: float | None = None
    flow_rate_m3h: float | None = None  # تدفّق المضخّة م³/ساعة
    pump_type: str | None = None
    well_depth_m: float | None = None
    water_ec: float | None = None  # ملوحة الماء dS/m
    manager_user_id: int | None = None  # FK إلى users(id) (v47)


class FieldUpdateRequest(BaseModel):
    """طلب تحديث جزئيّ لتفاصيل حقل — كلّ الحقول اختياريّة (ملء تدريجيّ).

    تُحدَّث الأعمدة المُرسَلة فقط (الموجودة في الـpayload) — لا تُمسح غير المُرسَلة.
    التمييز بين «لم يُرسَل» و«أُرسِل null» عبر model_fields_set (انظر _build_field_update).
    """

    soil_ph: float | None = Field(default=None, ge=0, le=14)
    soil_ec: float | None = Field(default=None, ge=0)
    soil_om: float | None = Field(default=None, ge=0)  # المادّة العضويّة %
    soil_n: float | None = Field(default=None, ge=0)
    soil_p: float | None = Field(default=None, ge=0)
    soil_k: float | None = Field(default=None, ge=0)
    elevation_m: float | None = None
    slope_pct: float | None = Field(default=None, ge=0)
    aspect: str | None = Field(default=None, max_length=20)
    climate_zone: str | None = Field(default=None, max_length=40)
    zone_key: str | None = Field(default=None, max_length=64)
    annual_rainfall_mm: float | None = Field(default=None, ge=0)
    owner_name: str | None = Field(default=None, max_length=100)
    lease_years: int | None = Field(default=None, ge=0)
    registry_no: str | None = Field(default=None, max_length=50)
    # الريّ/المياه التفصيليّ (v41)
    irrigation_type: str | None = Field(default=None, max_length=20)
    irrigation_efficiency_pct: float | None = Field(default=None, ge=0, le=100)
    flow_rate_m3h: float | None = Field(default=None, ge=0)
    pump_type: str | None = Field(default=None, max_length=30)
    well_depth_m: float | None = Field(default=None, ge=0)
    water_ec: float | None = Field(default=None, ge=0)
    manager_user_id: int | None = Field(default=None, ge=1)  # FK users(id) (v47)


def _build_field_update(req: FieldUpdateRequest) -> tuple[str, list]:
    """يبني جملة SET للتحديث الجزئيّ من الحقول المُرسَلة فقط — دالّة نقيّة (لا DB).

    يُرجِع (set_clause, values) حيث set_clause = "col1 = $1, col2 = $2 …" والقيم
    بالترتيب نفسه. تُستخدَم القيم لاحقاً بعد إلحاق معرّف الحقل ($N) في WHERE.
    يُميّز «لم يُرسَل» (يُتجاهَل) عن «أُرسِل null» (يُمسح العمود) عبر model_fields_set.

    يرفع ValueError لو لم تُرسَل أيّ حقول — لا UPDATE فارغ (يعالجه الـendpoint 422).
    """
    sent = req.model_fields_set
    data = req.model_dump()
    assignments: list[str] = []
    values: list = []
    idx = 1
    for col in _FIELD_ADVANCED_COLUMNS:
        if col in sent:
            assignments.append(f"{col} = ${idx}")
            values.append(data[col])
            idx += 1
    if not assignments:
        raise ValueError("no fields to update")
    return ", ".join(assignments), values


# ─── Auth helpers ────────────────────────────────────────────────


# تطبيع الأدوار عبر حدود الخدمات: خدمة auth تُصدر admin/expert/farmer، والنواة
# تستخدم النموذج الخماسي (owner/manager/agronomist/worker/viewer). يطابق
# frontend/src/lib/permissions.ts (ROLE_ALIASES) حتى لا يهبط 'admin' صامتاً إلى
# أدنى صلاحية. fail-closed: المجهول/الناقص ⇒ viewer (أقلّ صلاحية، مبدأ "شكّ = منع").
_ROLE_ALIASES: dict[str, UserRole] = {
    "owner": UserRole.OWNER,
    "admin": UserRole.OWNER,
    "manager": UserRole.MANAGER,
    "agronomist": UserRole.AGRONOMIST,
    "expert": UserRole.AGRONOMIST,
    "worker": UserRole.WORKER,
    "farmer": UserRole.WORKER,
    "viewer": UserRole.VIEWER,
}


def _normalize_role(raw: str | None) -> UserRole:
    """يطبّع دور الـJWT للنموذج الخماسي. fail-closed: مجهول/ناقص ⇒ viewer."""
    if not raw:
        return UserRole.VIEWER
    return _ROLE_ALIASES.get(str(raw).strip().lower(), UserRole.VIEWER)


def create_token(user: UserSchema) -> str:
    payload = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "name_ar": user.name_ar,
        "aud": "sahool",  # توحيد: يطابق auth ويُقبل عبر كلّ الخدمات
        "iss": "sahool-platform",  # المُصدِر — تفرضه الخدمات للتحقّق من مصدر التوكن
        "jti": secrets.token_hex(16),  # معرّف توكن فريد — يتيح الإبطال (denylist)
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ─── إبطال JWT (denylist) — يُغلق فجوة: تسجيل الخروج لم يكن يُبطِل التوكن فعليّاً ──
# يُبنى backend مشترك مع خدمة auth (نفس مفتاح Redis sahool:jti:revoked:{jti}) كي
# يرى المنصّة إبطالات auth أيضاً؛ وإلّا ذاكرة (dev/offline — إبطال داخل العمليّة).
from core.jwt_denylist import (  # noqa: E402
    InMemoryDenylist,
    RedisDenylist,
    is_token_revoked,
)


def _build_denylist():
    """backend الإبطال: Redis (مشترك مع auth) إن توفّر REDIS_URL وحيّ، وإلّا ذاكرة.

    fail-safe: أيّ تعذّر اتّصال/استيراد ⇒ ذاكرة (يُبطِل داخل العمليّة على الأقلّ، مع
    fail-open على الفحص). الإنتاج متعدّد العمّال يحتاج Redis لمشاركة الإبطال.
    """
    url = os.getenv("REDIS_URL", "")
    if url:
        try:
            import redis as _redis

            client = _redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            logger.info("denylist: Redis مفعّل (إبطال مشترك مع auth)")
            return RedisDenylist(client)
        except Exception as e:  # noqa: BLE001 — تعذّر Redis ⇒ ذاكرة (fail-safe)
            logger.warning("denylist: تعذّر Redis (%s) — fallback ذاكرة داخل العمليّة", e)
    return InMemoryDenylist()


_DENYLIST = _build_denylist()


def get_current_user(authorization: str = Header(None)) -> UserSchema:
    """يستخرج المستخدم من JWT. fail-closed."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience="sahool")
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e

    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — توكن من مُصدِر مجهول يُرفَض كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    # إبطال التوكن (denylist): توكن مُبطَل (سُجّل خروجه/أُلغي) ⇒ 401 رغم سريانه.
    # fail-open: تعذّر فحص القائمة (Redis ساقط) لا يقفل المستخدمين (داخل is_token_revoked).
    if is_token_revoked(_DENYLIST, payload.get("jti")):
        raise HTTPException(status_code=401, detail="التوكن مُبطَل — سجّل الدخول من جديد")

    role = _normalize_role(payload.get("role"))

    # توكن ناقص الحقول الأساسيّة → 401 (لا 500). استخدم .get ثمّ تحقّق.
    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not sub or not tenant_id:
        raise HTTPException(status_code=401, detail="Token missing required claims")

    return UserSchema(
        user_id=sub,
        tenant_id=tenant_id,
        role=role,
        name_ar=payload.get("name_ar", ""),
    )


def require_permission(permission: Permission):
    """تبعيّة FastAPI: تُصادِق (JWT) ثمّ تفرض صلاحية الدور — fail-closed 403.

    تربط طبقة HTTP بمحرّك الصلاحيات (core.authorization) الذي كان مفروضاً في خطّ
    التوصيات فقط لا عند نقاط الـHTTP. تُرجِع المستخدم فيبقى جسد الـendpoint بلا
    تغيير:
        user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD))

    العزل بين المستأجرين يبقى على RLS + tenant_id؛ هذه الطبقة تفصل الصلاحيات
    *داخل* المستأجر (الفجوة المعياريّة: RBAC غير مفروض في platform).
    """

    def _dep(user: UserSchema = Depends(get_current_user)) -> UserSchema:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"الدور '{user.role.value}' لا يملك صلاحية '{permission.value}'",
            )
        return user

    return _dep


# ─── Endpoints ────────────────────────────────────────────────────


@app.get("/healthz")
def healthz():
    """Liveness — لا dependency، فقط أنّ التطبيق يعمل."""
    resp = handle_healthz()
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@app.get("/readyz")
def readyz():
    """Readiness — يفحص النواة (skills_registry، canonical_schemas، ...)."""
    resp = handle_readyz()
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """تسجيل دخول dev-mode (بلا كلمة مرور). مُعطَّل افتراضيّاً في كلّ البيئات؛
    لا يُفعَّل إلّا بـSAHOOL_DEV_AUTH=1 وفي غير الإنتاج. غير ذلك ⇒ 403.
    المصادقة الحقيقيّة عبر خدمة sahool-auth (/auth/login بـbcrypt)."""
    # C1 FIX: هذه نقطة تطوير تُصدر JWT بلا كلمة مرور. مُعطَّلة افتراضيّاً (وفي
    # الإنتاج دائماً) — لا تُفعَّل إلّا بإقرار صريح SAHOOL_DEV_AUTH=1 في غير الإنتاج.
    # يمنع تجاوز المصادقة وانهيار عزل المستأجرين لو أصابت الطلبات هذه النقطة.
    if not _DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة — استخدم خدمة المصادقة (/auth/login).",
        )
    # هنا: dev-mode فقط، نقبل أيّ user_id صالح
    try:
        role = UserRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from None

    user = UserSchema(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=role,
        name_ar=req.name_ar,
    )
    token = create_token(user)

    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRY_HOURS * 3600,
        user={
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        },
    )


@app.get("/api/v1/me")
def me(user: UserSchema = Depends(get_current_user)):
    """بيانات المستخدم الحالي (الهوية + المستأجر + الدور)."""
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "name_ar": user.name_ar,
    }


# ─── auth endpoints التي يطلبها التطبيق (مطابقة contract) ─────────
# جلسة المطابقة: الموبايل (authService.ts) يستدعي /api/v1/auth/{me,logout,signup}
# لكنّها لم تكن موجودة → تسجيل الدخول/الخروج كان يفشل بـ404.


@app.get("/api/v1/auth/me")
def auth_me(user: UserSchema = Depends(get_current_user)):
    """alias لـ/api/v1/me — التطبيق يستدعي هذا المسار."""
    return {
        "user": {
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        }
    }


@app.post("/api/v1/auth/logout")
def auth_logout(
    authorization: str = Header(None),
    user: UserSchema = Depends(get_current_user),
):
    """تسجيل خروج — يُبطِل التوكن فعليّاً عبر denylist (jti) لا على الجهاز فقط.

    يُضيف jti التوكن للقائمة بمهلة = ما تبقّى حتى انتهائه، فيُرفَض في الطلبات اللاحقة
    (get_current_user يستشير القائمة). fail-safe: فشل الإبطال لا يكسر الخروج.
    """
    token = (authorization or "").replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience="sahool")
        # تدقيق B: افرض المُصدِر — توكن من مُصدِر مجهول يُعامَل كغير صالح (لا إبطال له).
        if payload.get("iss") not in _ALLOWED_ISS:
            raise InvalidTokenError("Invalid token issuer")
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(1, int(exp) - int(time.time()))
            _DENYLIST.revoke(jti, ttl)
    except Exception as e:  # noqa: BLE001 — فشل الإبطال لا يكسر الخروج (العميل يحذف التوكن)
        logger.warning("logout: تعذّر إبطال التوكن: %s", e)
    return {"status": "logged_out", "message_ar": "تمّ تسجيل الخروج"}


@app.post("/api/v1/auth/signup", response_model=TokenResponse)
def auth_signup(req: LoginRequest):
    """تسجيل مستخدم جديد (dev-mode — نفس منطق login بلا كلمة مرور).

    مُعطَّل افتراضيّاً في كلّ البيئات؛ لا يُفعَّل إلّا بـSAHOOL_DEV_AUTH=1 وفي غير
    الإنتاج. غير ذلك ⇒ 403. التسجيل الحقيقيّ عبر خدمة auth (DB + bcrypt).
    """
    # C1 FIX: نفس منطق login بلا كلمة مرور → مُعطَّل افتراضيّاً وفي الإنتاج دائماً.
    if not _DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة — استخدم خدمة المصادقة.",
        )
    try:
        role = UserRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from None
    user = UserSchema(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=role,
        name_ar=req.name_ar,
    )
    token = create_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRY_HOURS * 3600,
        user={
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        },
    )


@app.post("/api/v1/recommendations")
def recommendations(
    req: RecommendationRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """نقطة التوصية الجوهرية — تستخدم api_adapter كاملاً."""
    # تحقّق tenant isolation
    if req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant recommendation request forbidden")

    api_req = ApiRequest(
        user=user,
        payload=req.model_dump(),
        path="/api/v1/recommendations",
        method="POST",
    )
    resp = handle_recommendation_request(api_req)
    return JSONResponse(status_code=resp.status_code, content=resp.body)


class FieldRecommendationRequest(BaseModel):
    field_id: str
    farm_id: str = ""
    crop: str
    current_indicators: dict = Field(default_factory=dict)
    growth_stage: str | None = None
    district_id: str | None = None


@app.post("/api/v1/recommendations/for-field")
def recommendations_for_field(
    req: FieldRecommendationRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """توصية لحقل دون أن يبني العميل «شهادة الجودة» (validation) يدويّاً.

    الواجهة كانت تعجز عن استدعاء /api/v1/recommendations لأنّه يتطلّب dict
    validation معقّداً (خرج بوّابة الجودة). هنا نبنيه خادميّاً من ملاحظات
    المستأجر عبر validate_observations ثمّ نستدعي المحرّك الحقيقيّ نفسه. صدق:
    عند نقص الملاحظات تُعاد توصية «محجوبة/محدودة» تُبيّن ما يلزم قياسه — لا
    سيناريو مفبرَك، وهو السلوك المُصمَّم لبوّابة الجودة."""
    import os as _os
    from pathlib import Path as _Path

    import validate_observations as _vo

    # جذر بيانات المستأجر (قابل للضبط). غيابه ⇒ شهادة منخفضة الجودة بصدق
    # (لا اختراع ملاحظات)، فيُعيد المحرّك توصية محدودة تُرشد لما يجب قياسه.
    root = _os.getenv(
        "SAHOOL_TENANT_DATA_ROOT",
        _os.path.join(_os.path.dirname(__file__), "..", "tenants"),
    )
    # تقوية: نُطبّع المسار ونتأكّد أنّ مجلّد المستأجر داخل الجذر (دفاع ضدّ "../"
    # أو فواصل مسار في tenant_id — تجنّب قراءة بيانات خارج عزل المستأجر).
    root_path = _Path(root).resolve()
    tenant_dir = (root_path / str(user.tenant_id)).resolve()
    if not tenant_dir.is_relative_to(root_path):
        raise HTTPException(status_code=400, detail="معرّف مستأجر غير صالح")
    try:
        validation = _vo.validate(tenant_dir)
    except Exception as e:  # noqa: BLE001 — صدق: لا توصية بلا شهادة جودة
        raise HTTPException(status_code=503, detail=f"تعذّر بناء شهادة الجودة: {e}") from e

    api_req = ApiRequest(
        user=user,
        payload={
            "tenant_id": user.tenant_id,
            # لا نخلط farm_id بـfield_id (كيانان مختلفان؛ authorize يفحص
            # farm_ids_access). نمرّره كما هو؛ المستخدم محدود الصلاحيّة يُرسله،
            # وذو الوصول الشامل (farm_ids_access فارغة) يمرّ بـ"".
            "farm_id": req.farm_id,
            "field_id": req.field_id,
            "crop": req.crop,
            "validation": validation,
            "current_indicators": req.current_indicators,
            "growth_stage": req.growth_stage,
            "district_id": req.district_id,
        },
        path="/api/v1/recommendations/for-field",
        method="POST",
    )
    resp = handle_recommendation_request(api_req)
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@app.post("/api/v1/observations")
def observations(
    req: ObservationRequest,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """تسجيل مشاهدة جديدة. في الإنتاج: يدخل DB. الآن: offline queue."""
    if req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    op = record_operation_offline(
        _OFFLINE_QUEUE,
        tenant_id=req.tenant_id,
        user_id=user.user_id,
        kind=OperationKind.OBSERVATION_CREATE,
        payload=req.model_dump(),
    )
    return {
        "status": "recorded",
        "op_id": op.op_id,
        "queued_for_sync": True,
        "message_ar": "سُجّلت محلّياً، ستُحفظ عند الاتصال",
    }


@app.post("/api/v1/sync")
async def sync(
    req: SyncBatchRequest,
    user: UserSchema = Depends(get_current_user),
):
    """دفعة عمليات من العميل offline-first.

    العميل أنشأ ops محلّياً، يرسلها هنا حين يعود الاتصال.
    لكلّ عملية: تُكتب للقاعدة فعليّاً (idempotent على op_id)، ثم تُسجَّل النتيجة.

    fail-safe: لو فشلت كتابة عملية، تبقى في الـqueue للمحاولة لاحقاً (لا نُعلن
    نجاحاً زائفاً). إن لم تكن القاعدة مفعّلة (DATABASE_URL غير مضبوط) تبقى الكلّ
    في الـqueue.
    """
    if req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # ١) نُسجّل عمليّات هذا الطلب في الـqueue. نوع غير معروف ⇒ 400 صريح (لا 500):
    #    OperationKind(قيمة مجهولة) يرفع ValueError، فنتحقّق قبل الإدخال.
    op_ids = []
    for raw_op in req.operations:
        raw_kind = raw_op.get("kind", "observation_create")
        try:
            kind = OperationKind(raw_kind)
        except ValueError:
            valid = ", ".join(k.value for k in OperationKind)
            raise HTTPException(
                status_code=400,
                detail=f"نوع عمليّة غير معروف: {raw_kind!r}. المسموح: {valid}",
            ) from None
        op = record_operation_offline(
            _OFFLINE_QUEUE,
            tenant_id=req.tenant_id,
            user_id=user.user_id,
            kind=kind,
            payload=raw_op.get("payload", {}),
        )
        op_ids.append(op.op_id)

    # ٢) supersession أوّلاً (لا نُثبّت عمليّات قديمة حلّت محلّها أحدث منها)
    superseded = apply_supersession(_OFFLINE_QUEUE, req.tenant_id)

    # ٣) نأخذ الدفعة الفعليّة من رأس الـqueue (FIFO، QUEUED فقط) — نفس ما كان
    #     sync_cycle سيعالجه — لنُثبّت بالضبط ما نعالج (إصلاح: كانت الكتابة تخصّ
    #     عمليّات هذا الطلب فقط بينما الـqueue قد يحوي أقدم، فتُعلَّم FAILED بلا رجعة).
    batch = _OFFLINE_QUEUE.peek_pending(req.tenant_id, limit=max(len(req.operations), 1))

    # ٤) نُثبّت كلّ عمليّة في الدفعة بمتانة ضمن سياق RLS. الناجح ⇒ SYNCED؛ الفاشل
    #    يبقى QUEUED (لا FAILED) ليُعاد في الدورة التالية (peek_pending يُرجع QUEUED
    #    فقط). إن لم تكن القاعدة مفعّلة، تبقى الكلّ QUEUED.
    started = datetime.now(UTC)
    synced = 0
    pending_retry = 0
    if _DB_POOL is not None:
        from api.offline_sync_db import persist_synced_operation

        async with tenant_connection(user) as conn:
            for op in batch:
                try:
                    async with conn.transaction():  # savepoint لكلّ عمليّة
                        await persist_synced_operation(conn, op=op, tenant_id=req.tenant_id)
                    _OFFLINE_QUEUE.mark_status(req.tenant_id, op.op_id, SyncStatus.SYNCED)
                    synced += 1
                except Exception as exc:  # noqa: BLE001 — تبقى QUEUED لإعادة المحاولة
                    _OFFLINE_QUEUE.mark_status(
                        req.tenant_id, op.op_id, SyncStatus.QUEUED, error=str(exc)[:200]
                    )
                    pending_retry += 1
                    logging.warning("sync: persist failed for op %s: %s", op.op_id, exc)
    else:
        pending_retry = len(batch)
        logging.warning(
            "sync: DATABASE_URL غير مضبوط — بقيت %d عمليّة QUEUED لإعادة المحاولة", pending_retry
        )

    duration_ms = round((datetime.now(UTC) - started).total_seconds() * 1000, 2)
    if not batch:
        reason = "✅ لا عمليّات معلّقة للـsync"
    elif pending_retry == 0:
        reason = f"✅ {synced} عمليّة sync بنجاح"
    else:
        reason = f"⚠️ {synced} sync، {pending_retry} بقيت معلّقة لإعادة المحاولة"
    if superseded:
        reason += f" (+{superseded} مُلغاة بـsupersession)"

    return {
        "status": "completed",
        "synced": synced,
        # العمليّات غير المُثبّتة تبقى QUEUED لإعادة المحاولة (لا FAILED). نفصل
        # العدّين: failed=الفشل النهائي الفعلي (0 هنا)، queued=ما سيُعاد.
        "failed": 0,
        "queued": pending_retry,
        "conflicted": 0,
        "superseded": superseded,
        "duration_ms": duration_ms,
        "reason_ar": reason,
        "op_ids": op_ids,
    }


@app.get("/api/v1/queue/status")
def queue_status(user: UserSchema = Depends(get_current_user)):
    """حالة الـoffline queue للـtenant الحالي."""
    from core.offline_first import queue_summary

    return queue_summary(_OFFLINE_QUEUE, user.tenant_id)


@app.get("/api/v1/capabilities")
def list_capabilities(user: UserSchema = Depends(get_current_user)):
    """بوّابة القدرات المشروطة: أيّ قدرة مؤجَّلة مُفعَّلة/خاملة وكيف تُشغَّل.
    لا يكشف أسراراً — قِيَم منطقيّة + تعليمات تفعيل فقط (شفافيّة تشغيليّة)."""
    from core.capabilities import capabilities_report

    return capabilities_report()


def _centroid_from_bbox(bbox: dict | None) -> tuple[float | None, float | None]:
    """مركز تقريبيّ من bbox {min_lat,max_lat,min_lng,max_lng}. (lat, lon).

    مفاتيح lng (لا lon) لمطابقة compute_bbox في geospatial_integrity.
    """
    if not bbox:
        return None, None
    try:
        lat = round((bbox["min_lat"] + bbox["max_lat"]) / 2, 6)
        lon = round((bbox["min_lng"] + bbox["max_lng"]) / 2, 6)
    except (KeyError, TypeError):
        return None, None
    return lat, lon


def _reverse_geocode(lat: float | None, lon: float | None) -> tuple[str | None, str | None]:
    """يكشف آليّاً الدولة + الإقليم (المحافظة) من مركز الحقل — دالّة نقيّة offline.

    الدولة = "اليمن" إن وقعت النقطة داخل YEMEN_BBOX (geospatial_integrity)، وإلّا
    "غير محدّد". الإقليم = المحافظة اليمنيّة عبر geo_zone_locator (صناديق إحداثيّة
    + الأصغر/الأدقّ عند التداخل). تُعاد (country, region)؛ region قد يكون None خارج
    اليمن أو خارج المحافظات المعرّفة. لا I/O — قابلة للاختبار دون قاعدة/شبكة.
    """
    from api.geo_zone_locator import locate_field
    from api.geospatial_integrity import YEMEN_BBOX

    if lat is None or lon is None:
        return None, None

    inside_yemen = (
        YEMEN_BBOX["min_lat"] <= lat <= YEMEN_BBOX["max_lat"]
        and YEMEN_BBOX["min_lng"] <= lon <= YEMEN_BBOX["max_lng"]
    )
    country = "اليمن" if inside_yemen else "غير محدّد"

    region: str | None = None
    if inside_yemen:
        loc = locate_field(lat, lon)
        if loc.get("supported"):
            gov = loc.get("governorate_ar")
            # locate_field يُرجع نصّاً افتراضيّاً عند تعذّر المطابقة الدقيقة
            if gov and gov != "غير محدّدة بدقّة":
                region = gov
    return country, region


def _row_to_field_summary(r) -> FieldSummary:
    """صفّ DB → FieldSummary (يفكّ geometry لو رجعت نصّاً من JSONB)."""
    import json as _json

    def _opt(key):
        # عمود اختياري قد يغيب (صفّ قديم/اختبار) — None بدل KeyError
        try:
            return r[key]
        except (KeyError, IndexError):
            return None

    geom = r["geometry"]
    if isinstance(geom, str):
        try:
            geom = _json.loads(geom)
        except (ValueError, TypeError):
            geom = None
    return FieldSummary(
        field_id=r["field_id"],
        farm_id=r["farm_id"] or "",
        name_ar=r["name"],
        crop=r["crop"] or "—",
        area_ha=float(r["area_ha"]) if r["area_ha"] is not None else 0.0,
        quality_grade="READY",
        health_summary_ar="—",
        soil_type=r["soil_type"],
        manager=r["manager"],
        field_code=_opt("field_code"),
        description=_opt("description"),
        water_source=_opt("water_source"),
        ownership_type=_opt("ownership_type"),
        country=_opt("country"),
        region=_opt("region"),
        lat=float(r["lat"]) if r["lat"] is not None else None,
        lon=float(r["lon"]) if r["lon"] is not None else None,
        geometry=geom,
    )


def _db_unavailable(action_ar: str, exc: Exception) -> HTTPException:
    """يحوّل خطأ DB (انقطاع اتّصال، عمود/هجرة غير مطبّقة…) إلى 503 صريح بدل 500.

    يُبقي الـendpoint مطابقاً للموثَّق (والواجهة تعرض فشلاً صادقاً لا «خطأ غير
    متوقّع»). يُعاد استخدامه في قراءة/كتابة الحقول.
    """
    logging.warning("fields DB error during %s: %s", action_ar, type(exc).__name__)
    return HTTPException(
        status_code=503,
        detail=f"تعذّر {action_ar} (القاعدة غير متاحة أو الهجرات غير مطبّقة). حاول لاحقاً.",
    )


@app.get("/api/v1/fields", response_model=list[FieldSummary])
async def list_fields(user: UserSchema = Depends(get_current_user)):
    """قائمة حقول المستأجر من القاعدة — للـHomeScreen/الخريطة.

    تُرشَّح بـtenant_id (دفاع عميق) + RLS، وتُرجع المركز + الهندسة (GeoJSON)
    لرسم المضلّع على الخريطة. عند تعذّر القاعدة ⇒ 503 صريح — لا بيانات وهميّة.
    """
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT field_id, farm_id, name, area_ha, crop, soil_type, manager, "
                "field_code, description, water_source, ownership_type, country, region, "
                "lat, lon, geometry "
                "FROM fields WHERE tenant_id = $1::uuid ORDER BY name",
                str(user.tenant_id),
            )
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً — مرّره كما هو
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة الحقول", e) from e
    return [_row_to_field_summary(r) for r in rows]


class FieldCreateRequest(BaseModel):
    """طلب إنشاء حقل من مضلّع مرسوم على الخريطة."""

    name: str = Field(min_length=1, max_length=100)
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    geometry: dict  # GeoJSON Polygon: {"type":"Polygon","coordinates":[[[lon,lat],...]]}
    farm_id: str | None = None
    gov: str | None = None
    # حقول مُثراة (v33): اختياريّة. country/region تُكتشف آليّاً إن لم تُرسَل.
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)


async def _persist_field(req: FieldCreateRequest, user: UserSchema) -> FieldSummary:
    """مسار التحقّق + الإدراج المشترك للحقل (مرسوم أو مستورَد).

    يتحقّق من الهندسة (CRS 4326، تقاطع ذاتي، مساحة معقولة، داخل اليمن) ويحسب
    المساحة + المركز منها، يكشف الدولة/الإقليم آليّاً إن لم يُرسَلا، ثمّ يُدرج
    ضمن سياق المستأجر (RLS). يردّ الحقل المُنشأ بهندسته. مصدر واحد للحقيقة
    يُعيد استخدامه create_field و import_field — لا تكرار للتحقّق/الإدراج.
    """
    import json as _json
    import uuid as _uuid

    import asyncpg  # لتضييق التقاط أخطاء PostGIS الغائب في فحص التداخل

    validation = validate_field_geometry(req.geometry)
    if not validation.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة.",
                "issues": [
                    {"code": i.code, "severity": i.severity.value, "message_ar": i.message_ar}
                    for i in validation.issues
                ],
            },
        )
    area_ha = round(validation.computed_area_ha or 0.0, 2)
    lat, lon = _centroid_from_bbox(validation.computed_bbox)
    # الكشف الآلي للدولة + الإقليم من مركز المضلّع (إن لم يُرسلهما العميل)
    country, region = req.country, req.region
    if country is None or region is None:
        auto_country, auto_region = _reverse_geocode(lat, lon)
        country = country or auto_country
        region = region or auto_region
    field_id = "fld_" + _uuid.uuid4().hex[:12]
    geom_json = _json.dumps(req.geometry)
    try:
        async with tenant_connection(user) as conn:
            # التحقّق أنّ المزرعة المرتبطة موجودة وتخصّ المستأجِر الحالي (إن أُرسلت).
            # farm_id يبقى اختياريّاً (ملف تعريف تدريجي)؛ نتحقّق فقط عند توفّره.
            # RLS يحصر farms أصلاً — لكن نضيف الفحص الصريح (دفاع + خطأ واضح).
            if req.farm_id:
                farm_ok = await conn.fetchrow(
                    "SELECT 1 FROM farms WHERE farm_id = $1 AND tenant_id = $2::uuid",
                    req.farm_id,
                    str(user.tenant_id),
                )
                if farm_ok is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "message_ar": "المزرعة غير موجودة أو ليست لك",
                            "code": "farm_not_found",
                        },
                    )
            # منع تكرار اسم الحقل داخل نفس المزرعة/المستأجر (تطبيع حالة الأحرف).
            dup = await conn.fetchrow(
                "SELECT field_id FROM fields WHERE tenant_id = $1::uuid "
                "AND farm_id IS NOT DISTINCT FROM $2 AND lower(name) = lower($3) LIMIT 1",
                str(user.tenant_id),
                req.farm_id,
                req.name,
            )
            if dup is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message_ar": f"يوجد حقل بالاسم نفسه «{req.name}» في هذه المزرعة.",
                        "code": "duplicate_field_name",
                        "existing_field_id": dup["field_id"],
                    },
                )
            # منع تداخل الهندسة مع حقول المستأجِر (ST_Intersects على عمود geom المفهرس
            # GiST — v43) — يكشف أيضاً «النسخ» الهندسيّة ولو اختلف الاسم. يتطلّب PostGIS؛
            # تدهور رشيق فقط عند غيابه (دالّة/نوع غير معرّف)؛ أيّ خطأ DB آخر ⇒ 503.
            try:
                overlaps = await conn.fetch(
                    """
                    SELECT field_id, name,
                           ST_Area(ST_Intersection(
                               ST_GeomFromGeoJSON($1), geom
                           )::geography) AS overlap_m2
                    FROM fields
                    WHERE tenant_id = $2::uuid AND geom IS NOT NULL
                      AND ST_Intersects(ST_GeomFromGeoJSON($1), geom)
                    ORDER BY overlap_m2 DESC NULLS LAST
                    LIMIT 5
                    """,
                    geom_json,
                    str(user.tenant_id),
                )
            except (asyncpg.UndefinedFunctionError, asyncpg.UndefinedObjectError) as ovl_err:
                # PostGIS غير مُثبَّت (دوال/نوع geometry غير معرّفة) — تخطٍّ رشيق فقط هنا.
                logger.warning("تخطّي فحص تداخل الحقول — PostGIS غير متاح: %s", ovl_err)
                overlaps = []
            significant = _significant_overlaps(overlaps, _MIN_FIELD_OVERLAP_M2)
            if significant:
                top = significant[0]
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message_ar": (
                            f"حدود الحقل تتداخل مع «{top['name']}» "
                            f"(~{top['overlap_m2']:.0f} م²). صحّح الحدود."
                        ),
                        "code": "field_geometry_overlap",
                        "overlaps": [
                            {
                                "field_id": o["field_id"],
                                "name": o["name"],
                                "overlap_m2": round(o["overlap_m2"] or 0.0, 1),
                            }
                            for o in significant
                        ],
                    },
                )
            await conn.execute(
                """INSERT INTO fields
                    (field_id, tenant_id, farm_id, name, crop, soil_type, manager,
                     area_ha, lat, lon, gov, geometry,
                     field_code, description, water_source, ownership_type,
                     country, region)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb,
                     $13, $14, $15, $16, $17, $18)""",
                field_id,
                str(user.tenant_id),
                req.farm_id,
                req.name,
                req.crop,
                req.soil_type,
                req.manager,
                area_ha,
                lat,
                lon,
                req.gov or region,  # المحافظة المكتشفة؛ خارج اليمن ⇒ NULL (لا تلفيق «البيضاء»)
                _json.dumps(req.geometry),
                req.field_code,
                req.description,
                req.water_source,
                req.ownership_type,
                country,
                region,
            )
            # حدث domain ضمن نفس المعاملة (نمط outbox) — يُغلق فجوة «كتابة بلا حدث».
            await _emit_domain_event(
                conn,
                user,
                "FIELD_CREATED",
                "field",
                field_id,
                {
                    "name": req.name,
                    "crop": req.crop,
                    "area_ha": area_ha,
                    "farm_id": req.farm_id,
                    "soil_type": req.soil_type,
                },
            )
    except HTTPException:
        raise  # get_pool() يرفع 503 أصلاً
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("حفظ الحقل", e) from e
    return FieldSummary(
        field_id=field_id,
        farm_id=req.farm_id or "",
        name_ar=req.name,
        crop=req.crop or "—",
        area_ha=area_ha,
        quality_grade="PENDING_LAB",
        health_summary_ar="حقل جديد — بانتظار قياسات",
        soil_type=req.soil_type,
        manager=req.manager,
        field_code=req.field_code,
        description=req.description,
        water_source=req.water_source,
        ownership_type=req.ownership_type,
        country=country,
        region=region,
        lat=lat,
        lon=lon,
        geometry=req.geometry,
    )


@app.post("/api/v1/fields", status_code=201, response_model=FieldSummary)
async def create_field(
    req: FieldCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
):
    """ينشئ حقلاً من مضلّع مرسوم — يُخزَّن فعليّاً في القاعدة (لا تلفيق).

    يتحقّق من الهندسة ويحسب المساحة + المركز، ثمّ يُدرج ضمن سياق المستأجر (RLS).
    يردّ الحقل المُنشأ بهندسته كي ترسمه الواجهة فوراً.
    """
    return await _persist_field(req, user)


class FieldImportRequest(BaseModel):
    """طلب استيراد حدّ حقل من ملفّ (GeoJSON/KML) أو نقاط GPS بدل الرسم اليدويّ.

    format يحدّد المصدر: 'geojson'/'kml' يستخدمان content (نصّ الملفّ)؛ 'gps'
    يستخدم points ([[lon,lat],...] مسار المشي). بقيّة الحقول كـFieldCreateRequest
    (تُمرَّر لنفس مسار الحفظ المشترك).
    """

    format: Literal["geojson", "kml", "gps"]
    content: str | None = None
    points: list[list[float]] | None = None
    name: str = Field(min_length=1, max_length=100)
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    farm_id: str | None = None
    gov: str | None = None
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)


@app.post("/api/v1/fields/import", status_code=201, response_model=FieldSummary)
async def import_field(
    req: FieldImportRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_CREATE)),
):
    """يستورد حدّ حقل من GeoJSON/KML/نقاط GPS → GeoJSON Polygon ثمّ يُخزّنه.

    يحلّل المصدر إلى Polygon (geo_import: نقيّ offline) ثمّ يعيد استخدام نفس
    مسار التحقّق + الإدراج كـcreate_field. خطأ التحليل ⇒ 400 (مدخل تالف)؛ هندسة
    غير صالحة ⇒ 422 (من المسار المشترك). لا تلفيق — الفشل يُعرَض بصدق.
    """
    from api import geo_import

    fmt = req.format
    try:
        if fmt == "geojson":
            if not req.content:
                raise ValueError("استيراد GeoJSON يتطلّب محتوى الملفّ (content).")
            geometry = geo_import.parse_geojson(req.content)
        elif fmt == "kml":
            if not req.content:
                raise ValueError("استيراد KML يتطلّب محتوى الملفّ (content).")
            geometry = geo_import.parse_kml(req.content)
        else:  # gps
            if not req.points:
                raise ValueError("استيراد GPS يتطلّب نقاطاً (points).")
            geometry = geo_import.points_to_polygon(req.points)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"message_ar": f"تعذّر تحليل ملفّ الاستيراد: {e}"},
        ) from e

    create_req = FieldCreateRequest(
        name=req.name,
        crop=req.crop,
        soil_type=req.soil_type,
        manager=req.manager,
        geometry=geometry,
        farm_id=req.farm_id,
        gov=req.gov,
        field_code=req.field_code,
        description=req.description,
        water_source=req.water_source,
        ownership_type=req.ownership_type,
        country=req.country,
        region=req.region,
    )
    return await _persist_field(create_req, user)


def _row_to_field_detail(r) -> FieldDetail:
    """صفّ DB (مع الأعمدة المتقدّمة) → FieldDetail. يعيد استخدام تطبيع الملخّص ثمّ
    يضيف الأعمدة المتقدّمة (v37). NUMERIC من asyncpg يأتي Decimal ⇒ float للـJSON."""
    base = _row_to_field_summary(r)

    def _f(key):
        try:
            v = r[key]
        except (KeyError, IndexError):
            return None
        return float(v) if v is not None else None

    def _s(key):
        try:
            return r[key]
        except (KeyError, IndexError):
            return None

    def _i(key):
        try:
            v = r[key]
        except (KeyError, IndexError):
            return None
        return int(v) if v is not None else None

    return FieldDetail(
        **base.model_dump(),
        soil_ph=_f("soil_ph"),
        soil_ec=_f("soil_ec"),
        soil_om=_f("soil_om"),
        soil_n=_f("soil_n"),
        soil_p=_f("soil_p"),
        soil_k=_f("soil_k"),
        elevation_m=_f("elevation_m"),
        slope_pct=_f("slope_pct"),
        aspect=_s("aspect"),
        climate_zone=_s("climate_zone"),
        zone_key=_s("zone_key"),
        annual_rainfall_mm=_f("annual_rainfall_mm"),
        owner_name=_s("owner_name"),
        lease_years=_i("lease_years"),
        registry_no=_s("registry_no"),
        irrigation_type=_s("irrigation_type"),
        irrigation_efficiency_pct=_f("irrigation_efficiency_pct"),
        flow_rate_m3h=_f("flow_rate_m3h"),
        pump_type=_s("pump_type"),
        well_depth_m=_f("well_depth_m"),
        water_ec=_f("water_ec"),
        manager_user_id=_i("manager_user_id"),
    )


# أعمدة SELECT لقراءة الحقل التفصيليّة: أساس الملخّص + الأعمدة المتقدّمة (v37).
_FIELD_DETAIL_SELECT = (
    "field_id, farm_id, name, area_ha, crop, soil_type, manager, "
    "field_code, description, water_source, ownership_type, country, region, "
    "lat, lon, geometry, " + ", ".join(_FIELD_ADVANCED_COLUMNS)
)


@app.get("/api/v1/fields/{field_id}", response_model=FieldDetail)
async def get_field(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفاصيل حقل كاملة (لوحة التفاصيل) — الأساسيّات + الأعمدة المتقدّمة (v37).

    مُرشَّحة بالمستأجِر (RLS). 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة تفاصيل الحقل", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    return _row_to_field_detail(row)


@app.get("/api/v1/fields/{field_id}/terrain")
async def get_field_terrain(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفسير تضاريسيّ للحقل (ارتفاع/منحدر/اتّجاه → دلالة زراعيّة) — طبقة استرشاد/عرض.

    يقرأ أعمدة التضاريس (v37) ويُرجِع enrich_terrain: تدريج/انجراف/صقيع/تعرّض
    شمسي/صرف. يعمل فوراً على القيم المخزّنة (يدويّة أو من DEM). صادق عند غيابها.

    ⚠ التعبئة التلقائيّة من DEM (SRTM/Copernicus) بند مؤجَّل (POST_DEPLOYMENT_ROADMAP):
    تحتاج مزوّد DEM حيّاً غير مضبوط هنا — حتى ذلك تُملأ يدويّاً عبر
    PATCH /api/v1/fields/{field_id}.
    """
    from core.engines.dem_enrichment import enrich_terrain

    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT elevation_m, slope_pct, aspect FROM fields WHERE field_id = $1",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة تضاريس الحقل", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")

    result = enrich_terrain(
        elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
        slope_pct=float(row["slope_pct"]) if row["slope_pct"] is not None else None,
        aspect=row["aspect"],
    )
    result["field_id"] = field_id
    result["dem_auto_fill"] = {
        "available": False,
        "note_ar": (
            "التعبئة التلقائيّة من DEM مؤجَّلة (تحتاج مزوّد SRTM/Copernicus حيّاً). "
            "حتى ذلك: أدخِل elevation_m/slope_pct/aspect عبر "
            "PATCH /api/v1/fields/{field_id}، والتفسير أعلاه يعمل فوراً على القيم المخزّنة."
        ),
    }
    return result


@app.get("/api/v1/fields/{field_id}/workspace")
async def get_field_workspace(
    field_id: str,
    timeline_limit: int = 50,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مساحة عمل الحقل: ملخّص + طبقات قابلة للتبديل + خطّ زمنيّ (عرض صرف).

    مستلهَمة من نمط FieldView/John Deere (الخريطة محور + طبقات + خطّ زمنيّ) بنمط
    سهول الصادق: كلّ طبقة تُعلن توفّرها (متاحة/عند الطلب/غير متوفّرة)، والخطّ الزمنيّ
    من أحداث مسجّلة فقط (لا اختراع). 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر القاعدة.
    """
    from core.engines.dem_enrichment import enrich_terrain
    from core.engines.field_workspace import assemble_workspace

    events: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            field = await conn.fetchrow(
                "SELECT field_id, name, crop, area_ha, soil_type, elevation_m, slope_pct, "
                "aspect, water_ec, irrigation_type FROM fields WHERE field_id = $1",
                field_id,
            )
            if field is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            rows = await conn.fetch(
                """SELECT event_type, occurred_at FROM events
                   WHERE entity_type = 'field' AND entity_id = $1
                   ORDER BY occurred_at DESC LIMIT $2""",
                field_id,
                max(1, min(timeline_limit, 500)),
            )
            events = [
                {
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                }
                for r in rows
            ]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("مساحة عمل الحقل", e) from e

    field_d = dict(field)
    terrain = enrich_terrain(
        elevation_m=float(field_d["elevation_m"])
        if field_d.get("elevation_m") is not None
        else None,
        slope_pct=float(field_d["slope_pct"]) if field_d.get("slope_pct") is not None else None,
        aspect=field_d.get("aspect"),
    )
    return assemble_workspace(field_d, terrain, events)


@app.patch("/api/v1/fields/{field_id}", response_model=FieldDetail)
async def update_field(
    field_id: str,
    req: FieldUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """تحديث جزئيّ لتفاصيل حقل (ملء تدريجيّ) — يُحدِّث الأعمدة المُرسَلة فقط.

    يتأكّد أنّ الحقل يخصّ المستأجِر (404) ضمن سياق المستأجِر (RLS)، يبني UPDATE
    من الحقول المُرسَلة فقط (دالّة نقيّة _build_field_update)، ويردّ الحقل المُحدَّث.
    422 لو لم تُرسَل أيّ حقول (لا UPDATE فارغ). 503 عند تعذّر القاعدة.
    """
    try:
        set_clause, values = _build_field_update(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث") from e
    # معرّف الحقل يأخذ آخر رقم placeholder في WHERE.
    field_idx = len(values) + 1
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            await conn.execute(
                f"UPDATE fields SET {set_clause} WHERE field_id = ${field_idx}",
                *values,
                field_id,
            )
            row = await conn.fetchrow(
                f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1",
                field_id,
            )
            if row is None:
                # سُحب الحقل بين التأكيد والقراءة (نادر) ⇒ نرفع 404 **داخل** المعاملة
                # قبل إصدار الحدث، فتتراجع المعاملة ولا يُكتب حدث لتحديث لم يقع فعلاً.
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            # حدث domain ضمن نفس المعاملة — الحقول المُرسَلة فقط في الـpayload.
            await _emit_domain_event(
                conn,
                user,
                "FIELD_UPDATED",
                "field",
                field_id,
                req.model_dump(exclude_unset=True),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("تحديث تفاصيل الحقل", e) from e
    return _row_to_field_detail(row)


@app.delete("/api/v1/fields/{field_id}")
async def delete_field(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_DELETE)),
):
    """يحذف حقلاً ويُصدِر FIELD_DELETED — حذف متتالٍ لتبعيّاته (مواسم/عمليّات/تنبيهات).

    حارس صدق: يُرفض (409) إن كان للحقل موسم نشط — أغلِقه أوّلاً (يمنع محو حقل قيد
    الاستخدام بالخطأ). الحدث يُصدَر قبل الحذف ضمن المعاملة (نمط outbox)، وentity_id
    نصّيّ (events منذ v18) فيبقى الحدث بعد حذف الحقل (لا FK من events إلى fields).
    404 لو الحقل ليس للمستأجِر؛ 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT field_id, name, crop, farm_id FROM fields WHERE field_id = $1",
                field_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM seasons WHERE field_id = $1 AND status = 'active'",
                field_id,
            )
            if active and int(active) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="للحقل موسم نشط — أغلِقه قبل الحذف (تفادي محو بيانات قيد الاستخدام).",
                )
            # الحدث قبل الحذف (يحفظ ما حُذف)؛ ثمّ DELETE المتتالي.
            await _emit_domain_event(
                conn,
                user,
                "FIELD_DELETED",
                "field",
                field_id,
                {"name": row["name"], "crop": row["crop"], "farm_id": row["farm_id"]},
            )
            await conn.execute("DELETE FROM fields WHERE field_id = $1", field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حذف الحقل", e) from e
    return {"field_id": field_id, "deleted": True}


@app.get("/api/v1/geo/reverse")
def geo_reverse_endpoint(
    lat: float,
    lon: float,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كشف عكسي خفيف: مركز الحقل → {country, region} — لعرض الموقع المكتشف آليّاً
    في الواجهة فور رسم المضلّع (قبل الحفظ). دالّة نقيّة (لا قاعدة)."""
    country, region = _reverse_geocode(lat, lon)
    return {"country": country, "region": region}


# ─── المواسم الزراعيّة (Seasons) — نمط FieldView (v32) ────────────
_IRRIGATION_TYPES = {"drip", "pivot", "flood", "sprinkler", "rainfed", "subsurface"}


class StageItem(BaseModel):
    name: str = ""
    date: str = ""
    notes: str = ""


class SeasonCreateRequest(BaseModel):
    """طلب إنشاء موسم زراعيّ لحقل (محاصيل/صنف/ريّ/تواريخ/مراحل)."""

    crops: list[str] = Field(default_factory=list)
    cultivar: str | None = Field(default=None, max_length=100)
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = Field(default=None, ge=0)
    land_leveling_date: str | None = None
    plowing_date: str | None = None
    sowing_date: str | None = None
    season_end: str | None = None
    custom_stages: list[StageItem] = Field(default_factory=list)
    # KPIs زراعيّة (v42) — أساس التحليلات، كلّها اختياريّة (ملء تدريجيّ)
    target_yield_kg_ha: float | None = Field(default=None, ge=0)
    plant_density: float | None = Field(default=None, ge=0)  # نبات/م²
    row_spacing_cm: float | None = Field(default=None, ge=0)
    seed_variety_source: str | None = Field(default=None, max_length=100)
    # حقول أغرونوميّة (v52، نمط FieldView) — كلّها اختياريّة
    maturity: str | None = Field(default=None, max_length=40)  # early/medium/late
    tillage_type: str | None = Field(default=None, max_length=40)
    actual_yield_kg_ha: float | None = Field(default=None, ge=0)  # الغلّة الفعليّة بعد الحصاد
    notes_ar: str | None = Field(default=None, max_length=2000)


class SeasonSummary(BaseModel):
    season_id: str
    field_id: str
    crops: list[str]
    cultivar: str | None = None
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = None
    land_leveling_date: str | None = None
    plowing_date: str | None = None
    sowing_date: str | None = None
    season_end: str | None = None
    stages: list[dict]
    status: str
    created_at: str | None = None
    # ─── KPIs زراعيّة (v42) — اختياريّة، ملء تدريجيّ ─
    target_yield_kg_ha: float | None = None
    plant_density: float | None = None
    row_spacing_cm: float | None = None
    seed_variety_source: str | None = None
    # ─── حقول أغرونوميّة (v52، نمط FieldView) — اختياريّة ─
    maturity: str | None = None
    tillage_type: str | None = None
    actual_yield_kg_ha: float | None = None
    notes_ar: str | None = None
    # ─── نتائج محاكاة الموسم (v39) — تُملأ عند تشغيل /simulate، تقديريّة ─
    sim_yield_kg_ha: float | None = None
    sim_biomass_kg_ha: float | None = None
    sim_gdd_total: float | None = None
    sim_lai_max: float | None = None
    sim_water_mm: float | None = None
    sim_ran_at: str | None = None


def _row_to_season(r) -> SeasonSummary:
    import json as _json

    keys = set(r.keys())

    def _arr(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return []
        return v or []

    def _d(v):
        return v.isoformat() if v is not None else None

    def _num(col):  # عمود sim_* قد لا يكون في SELECT (مثلاً list_seasons) — None بأمان
        v = r[col] if col in keys else None
        return float(v) if v is not None else None

    return SeasonSummary(
        season_id=r["season_id"],
        field_id=r["field_id"],
        crops=_arr(r["crops"]),
        cultivar=r["cultivar"],
        irrigation_type=r["irrigation_type"],
        seed_rate_kg_ha=float(r["seed_rate_kg_ha"]) if r["seed_rate_kg_ha"] is not None else None,
        land_leveling_date=_d(r["land_leveling_date"]),
        plowing_date=_d(r["plowing_date"]),
        sowing_date=_d(r["sowing_date"]),
        season_end=_d(r["season_end"]),
        stages=_arr(r["stages"]),
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
        target_yield_kg_ha=_num("target_yield_kg_ha"),
        plant_density=_num("plant_density"),
        row_spacing_cm=_num("row_spacing_cm"),
        seed_variety_source=(r["seed_variety_source"] if "seed_variety_source" in keys else None),
        # v52 (محروسة بالمفاتيح — None إن لم تُحدَّد في SELECT)
        maturity=(r["maturity"] if "maturity" in keys else None),
        tillage_type=(r["tillage_type"] if "tillage_type" in keys else None),
        actual_yield_kg_ha=_num("actual_yield_kg_ha"),
        notes_ar=(r["notes_ar"] if "notes_ar" in keys else None),
        sim_yield_kg_ha=_num("sim_yield_kg_ha"),
        sim_biomass_kg_ha=_num("sim_biomass_kg_ha"),
        sim_gdd_total=_num("sim_gdd_total"),
        sim_lai_max=_num("sim_lai_max"),
        sim_water_mm=_num("sim_water_mm"),
        sim_ran_at=(
            r["sim_ran_at"].isoformat()
            if "sim_ran_at" in keys and r["sim_ran_at"] is not None
            else None
        ),
    )


async def _assert_field_in_tenant(conn, field_id: str) -> None:
    """يتأكّد أنّ الحقل يخصّ المستأجِر (RLS) قبل ربط موسم به — 404 وإلّا."""
    exists = await conn.fetchval("SELECT 1 FROM fields WHERE field_id = $1", field_id)
    if not exists:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")


@app.post(
    "/api/v1/fields/{field_id}/seasons",
    status_code=201,
    response_model=SeasonSummary,
)
async def create_season(
    field_id: str,
    req: SeasonCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ موسماً زراعيّاً للحقل — يُخزَّن فعليّاً (بدل /seasons المُبتلَع).

    يتحقّق من نوع الريّ وترتيب التواريخ، ويربط الموسم بالحقل ضمن سياق المستأجِر
    (RLS) بعد تأكيد أنّ الحقل يخصّه (404)، ويردّ الموسم المُنشأ. idempotent:
    Idempotency-Key (UUID) يمنع تكرار الإنشاء عند إعادة الموبايل (offline).
    """
    import json as _json
    import uuid as _uuid

    if req.irrigation_type and req.irrigation_type not in _IRRIGATION_TYPES:
        raise HTTPException(status_code=422, detail="نوع ريّ غير معروف")
    # التواريخ: تُحوَّل/تُتحقَّق (400 على صيغة غير صالحة) قبل القاعدة.
    land = _parse_date(req.land_leveling_date, "تسوية الأرض")
    plow = _parse_date(req.plowing_date, "الحراثة")
    sow = _parse_date(req.sowing_date, "البذار")
    end = _parse_date(req.season_end, "نهاية الموسم")
    if plow and land and plow < land:
        raise HTTPException(status_code=422, detail="تاريخ الحراثة قبل تسوية الأرض")
    if sow and plow and sow < plow:
        raise HTTPException(status_code=422, detail="تاريخ البذار قبل الحراثة")
    if end and sow and end < sow:
        raise HTTPException(status_code=422, detail="نهاية الموسم قبل البذار")
    season_id = "ssn_" + _uuid.uuid4().hex[:12]
    # تصفية المراحل الفارغة كليّاً (name/date/notes فارغة) — لا تلوّث JSONB
    # بمدخلات غير مفيدة (مرحلة أُضيفت ثمّ تُركت فارغة في الواجهة).
    clean_stages = [
        s for s in req.custom_stages if (s.name.strip() or s.date.strip() or s.notes.strip())
    ]
    stages_json = _json.dumps([s.model_dump() for s in clean_stages])
    crops_json = _json.dumps(req.crops)

    import asyncpg as _asyncpg  # لالتقاط سباق الموسم النشط (UniqueViolation → 409)

    try:
        async with tenant_connection(user) as conn:

            async def _work():
                await _assert_field_in_tenant(conn, field_id)
                # ثابت v44: حقل واحد ⇒ موسم نشط واحد على الأكثر. بدل رفض الإنشاء (409)،
                # نُغلق آليّاً أيّ موسم نشط سابق لهذا الحقل ثمّ نُدرج الجديد ضمن نفس
                # المعاملة — فيكون «إنشاء موسم» انتقالاً نظيفاً للموسم النشط. الفهرس
                # الفريد الجزئي (uq_seasons_one_active) هو الضمانة النهائيّة للثابت.
                async with conn.transaction():
                    closed = await conn.fetch(
                        "UPDATE seasons SET status = 'closed' "
                        "WHERE field_id = $1 AND status = 'active' RETURNING season_id",
                        field_id,
                    )
                    # حدث SEASON_CLOSED لكلّ موسم نشط أُغلق آليّاً (توسيع تغطية الأحداث).
                    for cr in closed:
                        await _emit_domain_event(
                            conn,
                            user,
                            "SEASON_CLOSED",
                            "season",
                            cr["season_id"],
                            {
                                "field_id": field_id,
                                "reason": "superseded_by_new_season",
                                "superseded_by": season_id,
                            },
                        )
                    await conn.execute(
                        """INSERT INTO seasons
                        (season_id, tenant_id, field_id, crops, cultivar, irrigation_type,
                         seed_rate_kg_ha, land_leveling_date, plowing_date, sowing_date,
                         season_end, stages, status,
                         target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source,
                         maturity, tillage_type, actual_yield_kg_ha, notes_ar)
                       VALUES ($1, $2::uuid, $3, $4::jsonb, $5, $6, $7,
                               $8, $9, $10, $11, $12::jsonb, 'active',
                               $13, $14, $15, $16,
                               $17, $18, $19, $20)""",
                        season_id,
                        str(user.tenant_id),
                        field_id,
                        crops_json,
                        req.cultivar,
                        req.irrigation_type,
                        req.seed_rate_kg_ha,
                        land,
                        plow,
                        sow,
                        end,
                        stages_json,
                        req.target_yield_kg_ha,
                        req.plant_density,
                        req.row_spacing_cm,
                        req.seed_variety_source,
                        req.maturity,
                        req.tillage_type,
                        req.actual_yield_kg_ha,
                        req.notes_ar,
                    )
                    # حدث domain ضمن نفس معاملة إنشاء الموسم (نمط outbox).
                    await _emit_domain_event(
                        conn,
                        user,
                        "SEASON_CREATED",
                        "season",
                        season_id,
                        {
                            "field_id": field_id,
                            "crops": req.crops,
                            "cultivar": req.cultivar,
                            "irrigation_type": req.irrigation_type,
                            "sowing_date": req.sowing_date,
                        },
                    )
                    # Canonical Field State: إنشاء موسم يغيّر سياق القرار ⇒ أعِد حساب
                    # الإسقاط، وأصدِر field.state_changed إن تبدّلت صلاحيّة القرار/التنفيذ
                    # (تغذية حيّة لوكيل الإشعارات، نفس معاملة الكتابة — نمط outbox).
                    from api.field_state_projection import recompute_field_state

                    _fs = await recompute_field_state(conn, field_id)
                    if _fs["changed"]:
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_STATE_CHANGED",
                            "field",
                            field_id,
                            {
                                "validity": _fs["state"]["validity"],
                                "execution_mode": _fs["state"]["execution_mode"],
                                "trigger": "season.created",
                            },
                        )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ season_id الأصليّ) — response_model يتحقّق منه.
                return SeasonSummary(
                    season_id=season_id,
                    field_id=field_id,
                    crops=req.crops,
                    cultivar=req.cultivar,
                    irrigation_type=req.irrigation_type,
                    seed_rate_kg_ha=req.seed_rate_kg_ha,
                    land_leveling_date=land.isoformat() if land else None,
                    plowing_date=plow.isoformat() if plow else None,
                    sowing_date=sow.isoformat() if sow else None,
                    season_end=end.isoformat() if end else None,
                    stages=[s.model_dump() for s in clean_stages],  # نفس ما خُزّن (لا بناء)
                    status="active",
                    target_yield_kg_ha=req.target_yield_kg_ha,
                    plant_density=req.plant_density,
                    row_spacing_cm=req.row_spacing_cm,
                    seed_variety_source=req.seed_variety_source,
                    maturity=req.maturity,
                    tillage_type=req.tillage_type,
                    actual_yield_kg_ha=req.actual_yield_kg_ha,
                    notes_ar=req.notes_ar,
                ).model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="season.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "season_id": season_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except _asyncpg.UniqueViolationError as e:
        # 409 فقط لانتهاك uq_seasons_one_active (سباق الموسم النشط)؛ أيّ تفرّد آخر
        # (أو قيد مستقبليّ) يسلك مسار 503 الموثّق بدل إخفائه كـactive_season_conflict.
        if getattr(e, "constraint_name", None) != "uq_seasons_one_active":
            raise _db_unavailable("حفظ الموسم", e) from e
        raise HTTPException(
            status_code=409,
            detail={
                "message_ar": "يوجد موسم نشط لهذا الحقل بالفعل (محاولة متزامنة) — أعد المحاولة.",
                "code": "active_season_conflict",
            },
        ) from e
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ الموسم", e) from e
    return result


@app.get("/api/v1/fields/{field_id}/seasons", response_model=list[SeasonSummary])
async def list_seasons(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مواسم الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو الحقل ليس للمستأجِر
            rows = await conn.fetch(
                "SELECT season_id, field_id, crops, cultivar, irrigation_type, "
                "seed_rate_kg_ha, land_leveling_date, plowing_date, sowing_date, "
                "season_end, stages, status, created_at, "
                "target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source, "
                "maturity, tillage_type, actual_yield_kg_ha, notes_ar, "
                "sim_yield_kg_ha, sim_biomass_kg_ha, sim_gdd_total, sim_lai_max, "
                "sim_water_mm, sim_ran_at "
                "FROM seasons WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة المواسم", e) from e
    return [_row_to_season(r) for r in rows]


class SeasonUpdateRequest(BaseModel):
    """تحديث موسم قائم (تحديث جزئيّ — الحقول الممرَّرة فقط). status بانتقال محقَّق."""

    status: str | None = None
    crops: list[str] | None = None
    cultivar: str | None = Field(default=None, max_length=100)
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = Field(default=None, ge=0)
    sowing_date: str | None = None
    season_end: str | None = None
    target_yield_kg_ha: float | None = Field(default=None, ge=0)
    plant_density: float | None = Field(default=None, ge=0)
    row_spacing_cm: float | None = Field(default=None, ge=0)
    seed_variety_source: str | None = Field(default=None, max_length=100)
    # حقول أغرونوميّة (v52، نمط FieldView) — اختياريّة
    maturity: str | None = Field(default=None, max_length=40)
    tillage_type: str | None = Field(default=None, max_length=40)
    actual_yield_kg_ha: float | None = Field(default=None, ge=0)
    notes_ar: str | None = Field(default=None, max_length=2000)


_SEASON_SELECT_COLS = (
    "season_id, field_id, crops, cultivar, irrigation_type, seed_rate_kg_ha, "
    "land_leveling_date, plowing_date, sowing_date, season_end, stages, status, "
    "created_at, target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source, "
    "maturity, tillage_type, actual_yield_kg_ha, notes_ar, "
    "sim_yield_kg_ha, sim_biomass_kg_ha, sim_gdd_total, sim_lai_max, sim_water_mm, sim_ran_at"
)


@app.patch("/api/v1/fields/{field_id}/seasons/{season_id}", response_model=SeasonSummary)
async def update_season(
    field_id: str,
    season_id: str,
    req: SeasonUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحدّث موسماً قائماً (تحديث جزئيّ) — يُصدِر SEASON_UPDATED (+SEASON_CLOSED عند الإغلاق).

    حالة الموسم تتغيّر بانتقال محقَّق فقط (season_lifecycle): planned→active/closed،
    active→closed، والمُغلَق نهائيّ (422 لغيره). تأكيد ملكيّة الحقل (404)؛ والموسم
    يخصّ الحقل (404). انتقال planned→active وهناك نشط ⇒ 409. 503 عند تعذّر القاعدة.
    """
    import asyncpg as _asyncpg

    from api.season_lifecycle import SeasonTransitionError, validate_status_transition

    if req.irrigation_type is not None and req.irrigation_type not in _IRRIGATION_TYPES:
        raise HTTPException(status_code=422, detail="نوع ريّ غير معروف")
    sow = _parse_date(req.sowing_date, "البذار") if req.sowing_date is not None else None
    end = _parse_date(req.season_end, "نهاية الموسم") if req.season_end is not None else None
    if end and sow and end < sow:
        raise HTTPException(status_code=422, detail="نهاية الموسم قبل البذار")

    # أعمدة قابلة للتحديث (column, value) — الحقول الممرَّرة فقط، JSONB مُعلَّم.
    fields_set = req.model_fields_set
    updates: list[tuple[str, object, bool]] = []  # (col, value, is_jsonb)
    if "crops" in fields_set:
        import json as _json

        updates.append(("crops", _json.dumps(req.crops or []), True))
    if "cultivar" in fields_set:
        updates.append(("cultivar", req.cultivar, False))
    if req.irrigation_type is not None:
        updates.append(("irrigation_type", req.irrigation_type, False))
    if "seed_rate_kg_ha" in fields_set:
        updates.append(("seed_rate_kg_ha", req.seed_rate_kg_ha, False))
    if req.sowing_date is not None:
        updates.append(("sowing_date", sow, False))
    if req.season_end is not None:
        updates.append(("season_end", end, False))
    for kpi in (
        "target_yield_kg_ha",
        "plant_density",
        "row_spacing_cm",
        "seed_variety_source",
        # حقول v52 الأغرونوميّة
        "maturity",
        "tillage_type",
        "actual_yield_kg_ha",
        "notes_ar",
    ):
        if kpi in fields_set:
            updates.append((kpi, getattr(req, kpi), False))

    if not updates and req.status is None:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث")

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT status FROM seasons WHERE season_id = $1 AND field_id = $2 FOR UPDATE",
                    season_id,
                    field_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="الموسم غير موجود لهذا الحقل")

                status_changed = False
                if req.status is not None:
                    try:
                        status_changed = validate_status_transition(current["status"], req.status)
                    except SeasonTransitionError as te:
                        raise HTTPException(
                            status_code=te.http_status, detail=te.message_ar
                        ) from te
                    if status_changed:
                        updates.append(("status", req.status, False))

                if updates:
                    set_parts, params = [], []
                    for col, value, is_jsonb in updates:
                        params.append(value)
                        cast = "::jsonb" if is_jsonb else ""
                        set_parts.append(f"{col} = ${len(params)}{cast}")
                    params.extend([season_id, field_id])
                    await conn.execute(
                        f"UPDATE seasons SET {', '.join(set_parts)} "
                        f"WHERE season_id = ${len(params) - 1} AND field_id = ${len(params)}",
                        *params,
                    )

                # حدث التحديث + حدث الإغلاق المخصَّص عند الانتقال إلى closed.
                changed_fields = [c for c, _, _ in updates]
                await _emit_domain_event(
                    conn,
                    user,
                    "SEASON_UPDATED",
                    "season",
                    season_id,
                    {"field_id": field_id, "changed_fields": changed_fields},
                )
                if status_changed and req.status == "closed":
                    await _emit_domain_event(
                        conn,
                        user,
                        "SEASON_CLOSED",
                        "season",
                        season_id,
                        {"field_id": field_id, "reason": "explicit_update"},
                    )

                row = await conn.fetchrow(
                    f"SELECT {_SEASON_SELECT_COLS} FROM seasons WHERE season_id = $1",
                    season_id,
                )
    except HTTPException:
        raise
    except _asyncpg.UniqueViolationError as e:
        if getattr(e, "constraint_name", None) != "uq_seasons_one_active":
            raise _db_unavailable("تحديث الموسم", e) from e
        raise HTTPException(
            status_code=409,
            detail={
                "message_ar": "يوجد موسم نشط لهذا الحقل بالفعل — أغلقه قبل تفعيل آخر.",
                "code": "active_season_conflict",
            },
        ) from e
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("تحديث الموسم", e) from e
    return _row_to_season(row)


# ─── محاكاة الموسم (Crop-model simulation) — v39 ─────────────────
# نموذج محصولي حقيقي خفيف (RUE/FAO-56، نقيّ ومُختبَر في api.season_simulation):
# تراكم GDD + كتلة حيويّة عبر كفاءة استخدام الإشعاع + مؤشّر LAI + احتياج الماء،
# ثمّ الإنتاج = الكتلة × مؤشّر الحصاد، مُحجَّماً بإجهاد مائي. النواة تجمع السياق
# (الموسم من القاعدة، الطقس التاريخي من Open-Meteo) وتكتب الناتج على صفّ الموسم.
# تقديرات نموذجيّة بنطاق وثقة صريحة — لا أرقام قاطعة. تعذّر الطقس ⇒ 503.

# سقف نافذة المحاكاة (يوم) حين يغيب season_end — دورة موسميّة معقولة.
_SIM_MAX_WINDOW_DAYS = 160


class SeasonSimResponse(BaseModel):
    """ناتج محاكاة الموسم — تقديرات نموذجيّة بنطاق وثقة وافتراضات صريحة."""

    season_id: str
    crop: str
    crop_recognized: bool
    days_simulated: int
    gdd_total: float
    gdd_to_maturity: float
    maturity_reached: bool
    lai_max: float
    biomass_kg_ha: float
    yield_kg_ha: float
    yield_low_kg_ha: float
    yield_high_kg_ha: float
    water_need_mm: float
    water_supply_mm: float | None
    water_stress_factor: float
    confidence: float
    rationale_ar: str
    assumptions_ar: list[str]
    warnings_ar: list[str]
    sim_ran_at: str


@app.post("/api/v1/seasons/{season_id}/simulate", response_model=SeasonSimResponse)
async def simulate_season_endpoint(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يشغّل محاكاة محصوليّة (RUE/FAO-56) للموسم ويحفظ الناتج على صفّه.

    يؤكّد أنّ الموسم يخصّ المستأجِر (404 وإلّا)، يجمع المحصول/التواريخ من القاعدة
    والطقس التاريخي من Open-Meteo لنافذة الموسم (sowing→end أو آخر ~160 يوماً)،
    يستدعي api.season_simulation.simulate_season (نقيّ)، يكتب sim_* + sim_ran_at،
    ويردّ النتيجة (تقديرات بنطاق وثقة). 503 إن تعذّرت القاعدة أو الطقس.
    """
    import json as _json

    from api.connectors.openmeteo import fetch_historical
    from api.season_simulation import DayWeather, SimContext, simulate_season

    # ١) سياق الموسم من القاعدة (+ تأكيد المستأجِر عبر RLS ⇒ 404 إن غاب).
    try:
        async with tenant_connection(user) as conn:
            srow = await conn.fetchrow(
                "SELECT s.season_id, s.field_id, s.crops, s.sowing_date, s.season_end, "
                "f.lat, f.lon FROM seasons s JOIN fields f ON f.field_id = s.field_id "
                "WHERE s.season_id = $1",
                season_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الموسم للمحاكاة", e) from e
    if srow is None:
        raise HTTPException(status_code=404, detail="الموسم غير موجود ضمن هذا المستأجِر")
    if srow["lat"] is None or srow["lon"] is None:
        raise HTTPException(
            status_code=422,
            detail="حقل الموسم بلا إحداثيّات (lat/lon) — لا يمكن جلب الطقس للمحاكاة.",
        )

    crops = srow["crops"]
    if isinstance(crops, str):
        try:
            crops = _json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    crop = str(crops[0]) if isinstance(crops, list) and crops else None

    # ٢) نافذة المحاكاة: من البذار إلى نهاية الموسم (أو اليوم)، بحدّ أقصى.
    today = datetime.now(UTC).date()
    sow = srow["sowing_date"]
    end = srow["season_end"]
    start = sow if sow is not None else (today - timedelta(days=_SIM_MAX_WINDOW_DAYS))
    win_end = min(end, today) if end is not None else today
    if win_end <= start:
        win_end = min(start + timedelta(days=_SIM_MAX_WINDOW_DAYS), today)
    if (win_end - start).days > _SIM_MAX_WINDOW_DAYS:
        win_end = start + timedelta(days=_SIM_MAX_WINDOW_DAYS)
    # ERA5 التاريخي يتأخّر ~5 أيّام — لا نطلب أحدث من ذلك.
    win_end = min(win_end, today - timedelta(days=5))
    if win_end <= start:
        raise HTTPException(
            status_code=422,
            detail="نافذة الموسم قصيرة جدّاً أو في المستقبل — لا بيانات طقس تاريخيّة كافية للمحاكاة.",
        )

    # ٣) الطقس التاريخي (ERA5) من Open-Meteo — تعذّره ⇒ 503 صريح.
    try:
        days = await fetch_historical(
            float(srow["lat"]),
            float(srow["lon"]),
            start.isoformat(),
            win_end.isoformat(),
        )
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس التاريخي (Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    weather = [
        DayWeather(
            t_min_c=d.temp_min_c,
            t_max_c=d.temp_max_c,
            solar_mj_m2=None,  # غير مطلوب من المصدر الحالي — يُقدَّر في النموذج
            et0_mm=d.et0_mm,
            rain_mm=d.precipitation_mm or 0.0,
        )
        for d in days
    ]

    # ٤) المحاكاة النقيّة.
    result = simulate_season(
        SimContext(crop=crop, sowing_date=sow, season_end=end, weather=weather)
    )

    # ٥) حفظ النتائج على صفّ الموسم (+ وقت التشغيل).
    ran_at = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                "UPDATE seasons SET sim_yield_kg_ha = $2, sim_biomass_kg_ha = $3, "
                "sim_gdd_total = $4, sim_lai_max = $5, sim_water_mm = $6, sim_ran_at = $7 "
                "WHERE season_id = $1",
                season_id,
                result.yield_kg_ha,
                result.biomass_kg_ha,
                result.gdd_total,
                result.lai_max,
                result.water_need_mm,
                ran_at,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حفظ نتائج المحاكاة", e) from e

    return SeasonSimResponse(
        season_id=season_id,
        crop=result.crop,
        crop_recognized=result.crop_recognized,
        days_simulated=result.days_simulated,
        gdd_total=result.gdd_total,
        gdd_to_maturity=result.gdd_to_maturity,
        maturity_reached=result.maturity_reached,
        lai_max=result.lai_max,
        biomass_kg_ha=result.biomass_kg_ha,
        yield_kg_ha=result.yield_kg_ha,
        yield_low_kg_ha=result.yield_low_kg_ha,
        yield_high_kg_ha=result.yield_high_kg_ha,
        water_need_mm=result.water_need_mm,
        water_supply_mm=result.water_supply_mm,
        water_stress_factor=result.water_stress_factor,
        confidence=result.confidence,
        rationale_ar=result.rationale_ar,
        assumptions_ar=result.assumptions_ar,
        warnings_ar=result.warnings_ar,
        sim_ran_at=ran_at.isoformat(),
    )


# ─── الطقس والريّ (Weather-driven advice) — Sprint 5a ────────────
# نقطتان للحقل: توصية ريّ (FAO-56) + مخاطر أمراض، تُحسبان من الطقس الحيّ
# (نفس مصدر /api/v1/weather: Open-Meteo) ومحصول الموسم النشط إن وُجد.
# منطق التهديف نقيّ في api.weather_advice (مُختبَر offline). تعذّر الطقس ⇒ 503.

# مراحل النموّ التقريبيّة بالأيّام منذ البذار (FAO-56 — initial/dev/mid/late).
# ⚠ تقدير عامّ يحتاج معايرة لكلّ محصول؛ يُستخدم فقط لاختيار Kc حين توفّر sowing_date.
_STAGE_DAY_BOUNDS = ((30, "initial"), (60, "development"), (120, "mid"))


def _growth_stage(days_since_sowing: int | None) -> str:
    """يُرجع مرحلة النموّ من عدد الأيّام منذ البذار. None/غير معروف ⇒ 'mid'."""
    if days_since_sowing is None or days_since_sowing < 0:
        return "mid"
    for bound, stage in _STAGE_DAY_BOUNDS:
        if days_since_sowing <= bound:
            return stage
    return "late"


async def _field_weather_context(conn, field_id: str) -> tuple[float, float, str | None, str]:
    """يجلب (lat, lon, crop, stage) للحقل + موسمه النشط بعد تأكيد المُستأجِر (404).

    المحصول من الموسم النشط (أحدث active) إن وُجد، وإلّا من عمود fields.crop.
    المرحلة من sowing_date للموسم النشط إن توفّر، وإلّا 'mid'.
    يرفع 404 إن غاب الحقل، و422 إن لم تتوفّر إحداثيّات الحقل (الطقس يحتاجها).
    """
    row = await conn.fetchrow("SELECT lat, lon, crop FROM fields WHERE field_id = $1", field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    if row["lat"] is None or row["lon"] is None:
        raise HTTPException(
            status_code=422,
            detail="الحقل بلا إحداثيّات (lat/lon) — لا يمكن جلب الطقس. حدّد موقع الحقل أوّلاً.",
        )
    season = await conn.fetchrow(
        "SELECT crops, sowing_date FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    crop: str | None = row["crop"]
    stage = "mid"
    if season is not None:
        import json as _json

        crops = season["crops"]
        if isinstance(crops, str):
            try:
                crops = _json.loads(crops)
            except (ValueError, TypeError):
                crops = []
        if isinstance(crops, list) and crops:
            crop = str(crops[0])
        if season["sowing_date"] is not None:
            days = (date.today() - season["sowing_date"]).days
            stage = _growth_stage(days)
    return float(row["lat"]), float(row["lon"]), crop, stage


async def _latest_soil_moisture(conn, field_id: str):
    """أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل، أو None إن لا قراءة صالحة.

    يجلب قراءات soil_moisture من device_telemetry للأجهزة المرتبطة بالحقل
    (iot_devices.field_id) ضمن سياق المستأجِر (RLS)، ثمّ يلتقط أحدثها الصالحة عبر
    المنطق النقيّ pick_latest_soil_moisture (يتجاهل القيم خارج النطاق المعقول).
    يُعيد كائن SoilMoistureReading أو None — لا يرفع استثناء عند غياب البيانات
    (القرار يتدبّر None برشاقة: يعتمد احتياج الريّ بدلاً منها).
    """
    from api.soil_telemetry import pick_latest_soil_moisture

    rows = await conn.fetch(
        """SELECT t.value, t.unit, t.recorded_at, t.device_id
             FROM device_telemetry t
             JOIN iot_devices d ON d.device_id = t.device_id
            WHERE d.field_id = $1 AND t.sensor_type = 'soil_moisture'
            ORDER BY t.recorded_at DESC
            LIMIT 50""",
        field_id,
    )
    return pick_latest_soil_moisture([dict(r) for r in rows])


@app.get("/api/v1/fields/{field_id}/soil-moisture")
async def field_soil_moisture(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل من telemetry الحيّ، أو null.

    يقرأ من device_telemetry (الأجهزة المرتبطة بالحقل عبر iot_devices.field_id)
    ضمن سياق المستأجِر (RLS) بعد تأكيد أنّ الحقل يخصّه (404). يردّ القراءة + زمنها
    + الجهاز المصدر، أو reading=null إن لا قراءة صالحة (لا بيانات وهميّة). 503 إن
    تعذّرت القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة رطوبة التربة", e) from e
    return {
        "field_id": field_id,
        "reading": reading.as_dict() if reading is not None else None,
    }


@app.get("/api/v1/fields/{field_id}/weather/irrigation-advice")
async def field_irrigation_advice(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """توصية ريّ بنمط FAO-56 للحقل من الطقس الحيّ ومحصول الموسم النشط.

    يحسب ET₀ × Kc − المطر الفعّال (api.weather_advice، نقيّ ومُختبَر). يجلب ET₀
    والمطر من Open-Meteo (نفس مصدر /api/v1/weather). 404 إن غاب الحقل، 503 إن
    تعذّر الطقس (لا بيانات وهميّة).
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage = await _field_weather_context(conn, field_id)
            # رطوبة تربة حيّة من telemetry الأجهزة (إن وُجدت) — تُغذّي إلحاح التوصية.
            soil_reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        forecast = await fetch_daily_forecast(lat, lon, days=3)
        current = await fetch_current(lat, lon)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    today = forecast[0] if forecast else None
    et0 = today.et0_mm if today and today.et0_mm is not None else None
    if et0 is None:
        raise HTTPException(
            status_code=503,
            detail="بيانات ET₀ غير متوفّرة من مصدر الطقس حاليّاً. حاول لاحقاً.",
        )
    # المطر المتوقّع خلال ٤٨ ساعة القادمة (يومان قادمان من التوقّع).
    forecast_rain = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
    soil_pct = soil_reading.value_pct if soil_reading is not None else None
    advice = irrigation_advice(
        et0_mm=et0,
        crop=crop,
        stage=stage,
        rain_recent_mm=current.precipitation_mm or 0.0,
        forecast_rain_mm=forecast_rain,
        soil_moisture_pct=soil_pct,
    )
    advice.update(
        {
            "field_id": field_id,
            "crop": crop,
            "stage": stage,
            "source": "open-meteo",
            "soil_moisture_pct": soil_pct,
            "soil_moisture_at": (
                soil_reading.recorded_at.isoformat() if soil_reading is not None else None
            ),
        }
    )
    return advice


@app.get("/api/v1/fields/{field_id}/weather/disease-risk")
async def field_disease_risk(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مخاطر أمراض فطريّة (agro-met) للحقل من الرطوبة/الحرارة/المطر.

    منطق التهديف نقيّ (api.weather_advice، مُختبَر offline). يجلب الطقس الحالي +
    مطر آخر ٣ أيّام من Open-Meteo. 404 إن غاب الحقل، 503 إن تعذّر الطقس.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import disease_risk

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, _stage = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        current = await fetch_current(lat, lon)
        forecast = await fetch_daily_forecast(lat, lon, days=3)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    rain_3d = sum(f.precipitation_mm or 0.0 for f in forecast[:3])
    risk = disease_risk(
        temp_c=current.temperature_c,
        humidity_pct=current.humidity_pct,
        rain_mm_3d=rain_3d,
        crop=crop,
    )
    risk.update(
        {
            "field_id": field_id,
            "crop": crop,
            "temperature_c": round(current.temperature_c, 1),
            "humidity_pct": round(current.humidity_pct, 1),
            "rain_mm_3d": round(rain_3d, 1),
            "source": "open-meteo",
        }
    )
    return risk


# ─── التوصيات الموحَّدة لكلّ حقل (Unified per-field recommendations) ─
# عمود توصيات واحد يجمع: الريّ + التسميد + الأمراض + الحصاد/الإنتاج. منطق
# التجميع نقيّ في api.recommendations_hub (مُختبَر offline). النواة تجمع السياق
# (الموسم من القاعدة، الطقس من Open-Meteo) ثمّ تمرّره. تدهور رشيق: عند تعذّر
# الطقس نُرجع التوصيات التي لا تحتاجه (تسميد/حصاد) بدل التلفيق؛ 503 فقط إن لم
# يبقَ شيء (القاعدة نفسها متعذّرة).


async def _field_season_context(conn, field_id: str):
    """يجلب (lat, lon, crop, stage, sowing_date) للحقل + موسمه النشط (404 إن غاب).

    يوسّع _field_weather_context بإرجاع sowing_date (لنافذة الحصاد). يرفع 404 إن
    غاب الحقل. lat/lon قد يكونان None هنا (الطقس اختياريّ في التوصيات الموحَّدة).
    """
    row = await conn.fetchrow("SELECT lat, lon, crop FROM fields WHERE field_id = $1", field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    season = await conn.fetchrow(
        "SELECT crops, sowing_date FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    crop: str | None = row["crop"]
    stage = "mid"
    sowing_date = None
    if season is not None:
        import json as _json

        crops = season["crops"]
        if isinstance(crops, str):
            try:
                crops = _json.loads(crops)
            except (ValueError, TypeError):
                crops = []
        if isinstance(crops, list) and crops:
            crop = str(crops[0])
        sowing_date = season["sowing_date"]
        if sowing_date is not None:
            stage = _growth_stage((date.today() - sowing_date).days)
    lat = float(row["lat"]) if row["lat"] is not None else None
    lon = float(row["lon"]) if row["lon"] is not None else None
    return lat, lon, crop, stage, sowing_date


async def _historical_rain_3d_mm(lat: float, lon: float, forecast_fallback: float) -> float:
    """مطر تراكمي آخر ٣ أيام (تاريخيّ ERA5) — لمخاطر الأمراض تُعدّ رطوبة الأيام
    السابقة لا المطر المستقبليّ. fallback لمجموع التوقّع إن تعذّر التاريخيّ."""
    from datetime import timedelta as _td

    from api.connectors.openmeteo import fetch_historical

    try:
        today = datetime.now(UTC).date()
        hist = await fetch_historical(
            lat, lon, (today - _td(days=3)).isoformat(), (today - _td(days=1)).isoformat()
        )
        return round(sum(d.precipitation_mm or 0.0 for d in hist), 1)
    except Exception:  # noqa: BLE001 — تعذّر التاريخيّ ⇒ fallback للتوقّع
        logging.exception("historical 3-day rain fetch failed; using forecast fallback")
        return round(forecast_fallback, 1)


@app.get("/api/v1/fields/{field_id}/recommendations")
async def field_recommendations(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عمود التوصيات الموحَّد للحقل: ريّ + تسميد + أمراض + حصاد، مفروز بالأولويّة.

    التجميع نقيّ (api.recommendations_hub، مُختبَر offline). يجمع سياق الموسم من
    القاعدة (404 إن غاب الحقل، 503 إن تعذّرت القاعدة) والطقس من Open-Meteo. تدهور
    رشيق: عند تعذّر الطقس (أو غياب إحداثيّات الحقل) نُرجع توصيات التسميد/الحصاد
    فقط — لا بيانات وهميّة. 503 فقط إن لم تتوفّر أيّة توصية.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.field_state_projection import recompute_field_state
    from api.recommendations_hub import RecommendationContext, build_recommendations

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, sowing_date = await _field_season_context(conn, field_id)
            # Canonical Field State: التوصيات تمرّ عبر الحالة القانونيّة الموحّدة —
            # نُحدِّث الإسقاط ونرفق صلاحيّة القرار + نمط التنفيذ بالاستجابة (مصدر حقيقة
            # واحد يحكم: تلقائيّ أم مراجعة بشريّة)، بدل قرار متفرّق لكلّ توصية.
            field_state = (await recompute_field_state(conn, field_id))["state"]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل للتوصيات", e) from e

    ctx = RecommendationContext(
        field_id=field_id,
        crop=crop,
        stage=stage,
        today=date.today(),
        sowing_date=sowing_date,
    )
    # Stage F (تغذية آمنة): مرّر مرجعيّة النواة الزراعيّة الموحّدة للمُجمِّع — تصعيد/
    # تنبيه فقط (تنبيه ملوحة حرجة) لا استبدال أرقام. صدق: غياب الحقائق ⇒ لا تصعيد.
    _agro_truths = (field_state.get("agronomic") or {}).get("operational_truths") or {}
    ctx.salinity_class = _agro_truths.get("salinity_class")
    ctx.crop_vigor = _agro_truths.get("crop_vigor")

    # الطقس اختياريّ: نملأ سياقه إن توفّرت الإحداثيّات والمصدر. تعذّره لا يُسقط
    # الطلب — نكتفي بالتوصيات التي لا تحتاجه (تدهور رشيق، لا تلفيق).
    weather_available = False
    if lat is not None and lon is not None:
        try:
            forecast = await fetch_daily_forecast(lat, lon, days=3)
            current = await fetch_current(lat, lon)
            today = forecast[0] if forecast else None
            et0 = today.et0_mm if today and today.et0_mm is not None else None
            ctx.et0_mm = et0
            ctx.rain_recent_mm = current.precipitation_mm or 0.0
            ctx.forecast_rain_mm = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
            ctx.temp_c = current.temperature_c
            ctx.humidity_pct = current.humidity_pct
            ctx.rain_mm_3d = await _historical_rain_3d_mm(
                lat, lon, sum(f.precipitation_mm or 0.0 for f in forecast[:3])
            )
            weather_available = True
        except Exception:  # noqa: BLE001 — تعذّر الطقس ⇒ تدهور رشيق لا فشل
            logging.exception("recommendations: weather unavailable for %s", field_id)

    recs = build_recommendations(ctx)
    if not recs:
        # لا توصية أمكن توليدها (لا طقس، لا محصول، لا بذار) — فشل صادق.
        raise HTTPException(
            status_code=503,
            detail="تعذّر توليد توصيات (لا طقس ولا سياق موسم كافٍ). حدّد موقع الحقل وموسمه.",
        )

    return {
        "field_id": field_id,
        "crop": crop,
        "stage": stage,
        "weather_available": weather_available,
        # الحالة القانونيّة الموحّدة تحكم تطبيق التوصيات (مصدر حقيقة واحد): نمط
        # التنفيذ != auto ⇒ requires_review (تحتاج تأكيد المهندس/المزارع قبل التنفيذ).
        "field_state": {
            "validity": field_state["validity"],
            "execution_mode": field_state["execution_mode"],
            "confidence_level": field_state.get("confidence_level"),
            "reasons_ar": field_state.get("reasons_ar", []),
        },
        "requires_review": field_state["execution_mode"] != "auto",
        "recommendations": [r.to_dict() for r in recs],
    }


# ─── العمليّات الزراعيّة (Activities) — نمط seasons (v35) ─────────
_ACTIVITY_TYPES = {
    "planting",
    "fertilization",
    "irrigation",
    "spraying",
    "pruning",
    "harvest",
    "scouting",
}


def _activity_event_type(activity_type: str, status: str) -> str:
    """يربط نوع النشاط + حالته (done/planned) بحدث عمليّة محدَّد (operation.*) حين
    ينطبق، وإلّا ACTIVITY_RECORDED العامّ — لإثراء سجلّ الأحداث بدلالة أدقّ.

    يفوّض إلى `field_aggregate.activity_event_for` (مصدر واحد للدلالة) ويُرجِع اسم
    العضو (لتوافق `_emit_domain_event` الذي يستقبل الاسم)."""
    from api.field_aggregate import activity_event_for

    return activity_event_for(activity_type, status).name


class ActivityCreateRequest(BaseModel):
    """طلب تسجيل عمليّة زراعيّة لحقل (نوع/عنوان/تفاصيل/تواريخ/موسم اختياريّ)."""

    activity_type: str
    title_ar: str | None = Field(default=None, max_length=200)
    details: dict = Field(default_factory=dict)
    scheduled_for: str | None = None
    performed_on: str | None = None
    season_id: str | None = None


class ActivitySummary(BaseModel):
    activity_id: str
    field_id: str
    season_id: str | None = None
    activity_type: str
    title_ar: str | None = None
    details: dict
    scheduled_for: str | None = None
    performed_on: str | None = None
    status: str
    created_at: str | None = None


def _row_to_activity(r) -> ActivitySummary:
    import json as _json

    def _obj(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return {}
        return v or {}

    def _d(v):
        return v.isoformat() if v is not None else None

    return ActivitySummary(
        activity_id=r["activity_id"],
        field_id=r["field_id"],
        season_id=r["season_id"],
        activity_type=r["activity_type"],
        title_ar=r["title_ar"],
        details=_obj(r["details"]),
        scheduled_for=_d(r["scheduled_for"]),
        performed_on=_d(r["performed_on"]),
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
    )


@app.post(
    "/api/v1/fields/{field_id}/activities",
    status_code=201,
    response_model=ActivitySummary,
)
async def create_activity(
    field_id: str,
    req: ActivityCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يسجّل عمليّة زراعيّة للحقل — تُخزَّن فعليّاً ضمن سياق المستأجِر (RLS).

    يتحقّق من نوع العمليّة (422)، ويحوّل التواريخ (400)، ويؤكّد أنّ الحقل
    يخصّ المستأجِر (404) قبل الإدراج، ثمّ يردّ العمليّة المُنشأة. idempotent:
    Idempotency-Key (UUID) يمنع تكرار التسجيل عند إعادة الموبايل (offline).
    """
    import json as _json
    import uuid as _uuid

    if req.activity_type not in _ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="نوع عمليّة غير معروف")
    scheduled = _parse_date(req.scheduled_for, "التاريخ المُجدوَل")
    performed = _parse_date(req.performed_on, "تاريخ التنفيذ")
    activity_id = "act_" + _uuid.uuid4().hex[:12]
    status = "done" if performed else "planned"
    try:
        details_json = _json.dumps(req.details or {})
    except (TypeError, ValueError) as e:
        # محتوى details غير قابل للتسلسل ⇒ خطأ إدخال صريح (422) لا 500/503.
        raise HTTPException(
            status_code=422, detail="تفاصيل العمليّة غير قابلة للتسلسل (JSON)"
        ) from e
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                await _assert_field_in_tenant(conn, field_id)
                if req.season_id is not None:
                    # الموسم اختياريّ، لكن إن مُرّر فيجب أن يوجد ويخصّ الحقل نفسه
                    # (لا FK صلب على القاعدة؛ تحقّق تطبيقيّ + فهرس داعم — v45).
                    season_ok = await conn.fetchval(
                        "SELECT 1 FROM seasons WHERE season_id = $1 AND field_id = $2",
                        req.season_id,
                        field_id,
                    )
                    if season_ok is None:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "message_ar": "الموسم غير موجود لهذا الحقل",
                                "code": "invalid_season_for_field",
                            },
                        )
                await conn.execute(
                    """INSERT INTO activities
                        (activity_id, tenant_id, field_id, season_id, activity_type,
                         title_ar, details, scheduled_for, performed_on, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)""",
                    activity_id,
                    str(user.tenant_id),
                    field_id,
                    req.season_id,
                    req.activity_type,
                    req.title_ar,
                    details_json,
                    scheduled,
                    performed,
                    status,
                )
                # حدث domain ضمن نفس معاملة تسجيل العمليّة (نمط outbox) — بحدث عمليّة
                # محدَّد (operation.*) حسب النوع/الحالة، وإلّا ACTIVITY_RECORDED العامّ.
                await _emit_domain_event(
                    conn,
                    user,
                    _activity_event_type(req.activity_type, status),
                    "activity",
                    activity_id,
                    {
                        "field_id": field_id,
                        "season_id": req.season_id,
                        "activity_type": req.activity_type,
                        "status": status,
                    },
                )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ activity_id الأصليّ) — response_model يتحقّق منه.
                return ActivitySummary(
                    activity_id=activity_id,
                    field_id=field_id,
                    season_id=req.season_id,
                    activity_type=req.activity_type,
                    title_ar=req.title_ar,
                    details=req.details or {},
                    scheduled_for=scheduled.isoformat() if scheduled else None,
                    performed_on=performed.isoformat() if performed else None,
                    status=status,
                ).model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="activity.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": field_id, "activity_id": activity_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ العمليّة", e) from e
    return result


@app.get("/api/v1/fields/{field_id}/activities", response_model=list[ActivitySummary])
async def list_field_activities(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عمليّات الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو الحقل ليس للمستأجِر
            rows = await conn.fetch(
                "SELECT activity_id, field_id, season_id, activity_type, title_ar, "
                "details, scheduled_for, performed_on, status, created_at "
                "FROM activities WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة العمليّات", e) from e
    return [_row_to_activity(r) for r in rows]


# ─── المهامّ الميدانيّة (field_tasks) — كانت الواجهة تنادي /tasks بلا خلفيّة ─
# تُسلسِل قائمة مهامّ المستأجِر + تحديث الحالة، مدعومة بجدول field_tasks (RLS).
class TaskSummary(BaseModel):
    task_id: str
    field_id: str
    task_type: str
    priority: int = 3
    status: str
    recommended_date: str | None = None
    estimated_duration_min: int | None = None
    estimated_cost_usd: float | None = None
    assigned_to: str | None = None
    notes: str | None = None
    photo_url: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class TaskListResponse(BaseModel):
    """غلاف {tasks:[...]} — يطابق عقد الواجهة (useTasks يقرأ data.tasks)."""

    tasks: list[TaskSummary]


class TaskUpdateRequest(BaseModel):
    """تحديث مهمّة (جزئيّ): الحالة و/أو صورة و/أو ملاحظة."""

    status: str | None = None
    photo_url: str | None = None
    notes: str | None = None


_TASK_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
_TASK_COLS = (
    "task_id, field_id, task_type, priority, status, recommended_date, "
    "estimated_duration_min, estimated_cost_usd, assigned_to, notes, photo_url, "
    "completed_at, created_at"
)


def _row_to_task(r) -> TaskSummary:
    return TaskSummary(
        task_id=str(r["task_id"]),
        field_id=r["field_id"],
        task_type=r["task_type"],
        priority=r["priority"] if r["priority"] is not None else 3,
        status=r["status"],
        recommended_date=r["recommended_date"].isoformat()
        if r["recommended_date"] is not None
        else None,
        estimated_duration_min=r["estimated_duration_min"],
        estimated_cost_usd=float(r["estimated_cost_usd"])
        if r["estimated_cost_usd"] is not None
        else None,
        assigned_to=r["assigned_to"],
        notes=r["notes"],
        photo_url=r["photo_url"],
        completed_at=r["completed_at"].isoformat() if r["completed_at"] is not None else None,
        created_at=r["created_at"].isoformat() if r["created_at"] is not None else None,
    )


@app.get("/api/v1/tasks", response_model=TaskListResponse)
async def list_tasks(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مهامّ المستأجِر (مُرشَّحة بـRLS، واختياريّاً بحقل). الأعلى أولويّةً ثمّ الأقرب
    موعداً. يُرجِع {tasks:[...]} (عقد الواجهة). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            if field_id:
                rows = await conn.fetch(
                    f"SELECT {_TASK_COLS} FROM field_tasks WHERE field_id = $1 "
                    "ORDER BY priority ASC, recommended_date ASC NULLS LAST, created_at DESC",
                    field_id,
                )
            else:
                rows = await conn.fetch(
                    f"SELECT {_TASK_COLS} FROM field_tasks "
                    "ORDER BY priority ASC, recommended_date ASC NULLS LAST, created_at DESC"
                )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة المهامّ", e) from e
    return TaskListResponse(tasks=[_row_to_task(r) for r in rows])


@app.patch("/api/v1/tasks/{task_id}", response_model=TaskSummary)
async def update_task(
    task_id: str,
    req: TaskUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """تحديث مهمّة (الحالة/صورة/ملاحظة) — مُرشَّح بالمستأجِر (RLS). 404 لو ليست
    للمستأجِر؛ 422 على حالة غير معروفة أو لا حقول للتحديث."""
    if req.status is not None and req.status not in _TASK_STATUSES:
        raise HTTPException(status_code=422, detail="حالة مهمّة غير معروفة")
    sets: list[str] = []
    vals: list[object] = []
    if req.status is not None:
        vals.append(req.status)
        sets.append(f"status = ${len(vals)}")
        if req.status == "completed":
            sets.append("completed_at = NOW()")
    if req.photo_url is not None:
        vals.append(req.photo_url)
        sets.append(f"photo_url = ${len(vals)}")
    if req.notes is not None:
        vals.append(req.notes)
        sets.append(f"notes = ${len(vals)}")
    if not sets:
        raise HTTPException(status_code=422, detail="لا حقول للتحديث")
    sets.append("updated_at = NOW()")
    vals.append(task_id)
    query = (
        f"UPDATE field_tasks SET {', '.join(sets)} "
        f"WHERE task_id::TEXT = ${len(vals)} RETURNING {_TASK_COLS}"
    )
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(query, *vals)
            # حدث تحديث المهمّة (تفاعليّ): يبثّه وكيل الإشعارات للواجهة حيّاً. داخل
            # المعاملة وفقط عند وجود الصفّ (مرشَّح بالمستأجِر عبر RLS).
            if row is not None:
                await _emit_domain_event(
                    conn,
                    user,
                    "TASK_UPDATED",
                    "task",
                    task_id,
                    # القيم الفعليّة من الصفّ المُحدَّث (RETURNING) لا من req — req.status
                    # قد تكون None عند تحديث photo/notes فقط (ملاحظة Copilot).
                    {"status": row.get("status"), "field_id": row.get("field_id")},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("تحديث المهمّة", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="المهمّة غير موجودة ضمن هذا المستأجِر")
    return _row_to_task(row)


@app.get("/api/v1/fields/{field_id}/input-traceability")
async def field_input_traceability(
    field_id: str,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تتبّع مدخلات الإنتاج (بذرة→حصاد) per حقل/موسم + الاقتصاد — يركّب القائم.

    يجمع تطبيقات المدخلات من activities (بذر/تسميد/رشّ/ريّ مع كلفة في details)
    ويربطها بناتج الحصاد من recommendation_outcomes ومساحة الحقل، فيبني دفتر
    مدخلات صادقاً: كلفة/هكتار، كلفة/طنّ، ومدى اكتمال النَسَب. الكلفة الغائبة
    تُعلَن لا تُؤلَّف. المخزون والشراء يبقيان في ERPNext (لا نقل WareMap).
    """
    from decimal import Decimal as _Decimal

    import asyncpg as _asyncpg
    from core.engines.input_traceability import (
        ACTIVITY_TO_INPUT,
        InputApplication,
        build_input_ledger,
    )

    _json = __import__("json")

    def _details(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return {}
        return v or {}

    def _num(v):
        # يقبل int/float/Decimal (NUMERIC من asyncpg) — يرفض bool/None/نصّ.
        if isinstance(v, bool) or v is None:
            return None
        return float(v) if isinstance(v, (int, float, _Decimal)) else None

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو ليس للمستأجِر
            area_ha = _num(
                await conn.fetchval("SELECT area_ha FROM fields WHERE field_id = $1", field_id)
            )

            q = (
                "SELECT activity_type, details, performed_on, scheduled_for FROM activities "
                "WHERE field_id = $1 AND activity_type = ANY($2::text[])"
            )
            params: list = [field_id, list(ACTIVITY_TO_INPUT.keys())]
            if season_id is not None:
                q += " AND season_id = $3"
                params.append(season_id)
            rows = await conn.fetch(q, *params)

            # ناتج الحصاد من recommendation_outcomes (savepoint — قد لا يكون مفعَّلاً).
            harvest_yield = None
            try:
                async with conn.transaction():
                    oq = (
                        "SELECT MAX(actual_yield_t_ha) AS y FROM recommendation_outcomes "
                        "WHERE field_id = $1 AND actual_yield_t_ha IS NOT NULL"
                    )
                    oparams: list = [field_id]
                    if season_id is not None:
                        oq += " AND season_id = $2"
                        oparams.append(season_id)
                    orow = await conn.fetchrow(oq, *oparams)
                    harvest_yield = _num(orow["y"]) if orow else None
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                harvest_yield = None
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تتبّع المدخلات", e) from e

    apps = []
    for r in rows:
        d = _details(r["details"])
        apps.append(
            InputApplication(
                activity_type=r["activity_type"],
                product_name=d.get("product_name") or d.get("product"),
                quantity=_num(d.get("quantity")),
                unit=d.get("unit"),
                cost=_num(d.get("cost")),
                applied_on=(
                    (r["performed_on"] or r["scheduled_for"]).isoformat()
                    if (r["performed_on"] or r["scheduled_for"])
                    else None
                ),
            )
        )
    return build_input_ledger(
        apps,
        field_id=field_id,
        season_id=season_id,
        area_ha=area_ha,
        harvest_yield_t_ha=harvest_yield,
    )


class NDVIObservationIn(BaseModel):
    """مشاهدة NDVI زمنيّة واحدة (من سلسلة Sentinel-2)."""

    date: str = Field(min_length=4, max_length=32)
    ndvi: float
    days_after_planting: int | None = Field(default=None, ge=0)


class GrowthNarrativeRequest(BaseModel):
    """سرد نموّ فينولوجي من سلسلة NDVI + مظروف متوقَّع اختياريّ."""

    observations: list[NDVIObservationIn]
    crop: str = Field(min_length=1, max_length=50)
    peak_ndvi_floor: float | None = Field(default=None, ge=-1, le=1)
    expected_peak_dap_min: int | None = Field(default=None, ge=0)


@app.post("/api/v1/fields/{field_id}/growth-narrative")
async def field_growth_narrative(
    field_id: str,
    req: GrowthNarrativeRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """سرد نموّ الحقل الفينولوجي من سلسلة NDVI القمريّة — بديل صادق للتايم‑لابس بلا عتاد.

    يصنّف الطور (إنبات/خضري/ذروة/شيخوخة) من شكل المنحنى، ويكشف شذوذ النموّ
    (ذروة ضعيفة/شيخوخة مبكّرة) **فقط مقابل مظروف متوقَّع مُمرَّر** — لا قيم أجنبيّة
    مُقحَمة. دون حدّ أدنى من المشاهد: لا سرد (لا لقطة تُقدَّم كمنحنى). 503 عند تعذّر
    القاعدة. السلسلة تُمرَّر في الطلب (من raster-service) — الجلب الحيّ بند تشغيليّ.
    """
    from core.engines.phenology_narrative import (
        NDVIObservation,
        build_growth_narrative,
    )

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)  # 404 لو ليس للمستأجِر
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("سرد النموّ", e) from e

    obs = [
        NDVIObservation(date=o.date, ndvi=o.ndvi, days_after_planting=o.days_after_planting)
        for o in req.observations
    ]
    result = build_growth_narrative(
        obs,
        crop=req.crop,
        peak_ndvi_floor=req.peak_ndvi_floor,
        expected_peak_dap_min=req.expected_peak_dap_min,
    )
    result["field_id"] = field_id
    return result


# ─── Workflow مخبري للتربة (Soil lab tests) — دورة حياة v50 ──────────
_SOIL_TEST_SELECT = (
    "test_id, field_id, status, lab_name, sampled_on, result, notes_ar, "
    "approved_by, published_at, created_at"
)


class SoilLabTestCreateRequest(BaseModel):
    """طلب فحص تربة جديد (يبدأ بحالة requested)."""

    lab_name: str | None = Field(default=None, max_length=120)
    sampled_on: str | None = None
    notes_ar: str | None = None
    result: dict | None = None


class SoilLabTestUpdateRequest(BaseModel):
    """تحديث فحص تربة (انتقال حالة محقَّق + بيانات اختياريّة)."""

    status: str | None = None
    lab_name: str | None = Field(default=None, max_length=120)
    sampled_on: str | None = None
    notes_ar: str | None = None
    result: dict | None = None


class SoilLabTestSummary(BaseModel):
    test_id: str
    field_id: str
    status: str
    lab_name: str | None = None
    sampled_on: str | None = None
    result: dict = Field(default_factory=dict)
    notes_ar: str | None = None
    approved_by: str | None = None
    published_at: str | None = None
    created_at: str | None = None


def _row_to_soil_test(r) -> SoilLabTestSummary:
    import json as _json

    def _obj(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return {}
        return v or {}

    def _d(v):
        return v.isoformat() if v is not None else None

    return SoilLabTestSummary(
        test_id=r["test_id"],
        field_id=r["field_id"],
        status=r["status"],
        lab_name=r["lab_name"],
        sampled_on=_d(r["sampled_on"]),
        result=_obj(r["result"]),
        notes_ar=r["notes_ar"],
        approved_by=r["approved_by"],
        published_at=_d(r["published_at"]),
        created_at=_d(r["created_at"]),
    )


@app.post(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    status_code=201,
    response_model=SoilLabTestSummary,
)
async def create_soil_lab_test(
    field_id: str,
    req: SoilLabTestCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ فحص تربة (حالة requested) — بداية دورة الحياة المخبريّة. يُصدِر SOIL_SAMPLE_RECORDED."""
    import json as _json
    import uuid as _uuid

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة")
    test_id = "soil_" + _uuid.uuid4().hex[:12]
    try:
        result_json = _json.dumps(req.result or {})
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل (JSON)") from e
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO soil_lab_tests "
                    "(test_id, tenant_id, field_id, status, lab_name, sampled_on, result, notes_ar) "
                    "VALUES ($1, $2::uuid, $3, 'requested', $4, $5, $6::jsonb, $7)",
                    test_id,
                    str(user.tenant_id),
                    field_id,
                    req.lab_name,
                    sampled,
                    result_json,
                    req.notes_ar,
                )
                await _emit_domain_event(
                    conn,
                    user,
                    "SOIL_SAMPLE_RECORDED",
                    "soil_lab_test",
                    test_id,
                    {"field_id": field_id, "status": "requested"},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء فحص التربة", e) from e
    return SoilLabTestSummary(
        test_id=test_id,
        field_id=field_id,
        status="requested",
        lab_name=req.lab_name,
        sampled_on=sampled.isoformat() if sampled else None,
        result=req.result or {},
        notes_ar=req.notes_ar,
    )


@app.get(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    response_model=list[SoilLabTestSummary],
)
async def list_soil_lab_tests(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """فحوص تربة الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests "
                "WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة فحوص التربة", e) from e
    return [_row_to_soil_test(r) for r in rows]


@app.patch(
    "/api/v1/fields/{field_id}/soil-lab-tests/{test_id}",
    response_model=SoilLabTestSummary,
)
async def update_soil_lab_test(
    field_id: str,
    test_id: str,
    req: SoilLabTestUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحدّث فحص تربة (انتقال حالة محقَّق + بيانات) — يُصدِر SOIL_LAB_RESULT_PUBLISHED عند النشر.

    الانتقال عبر `soil_lab_workflow` (عيّنة→مختبر→نتيجة→اعتماد→نشر؛ المنشور/الملغى
    نهائيّان؛ لا اعتماد/نشر بلا نتيجة — 422). تأكيد ملكيّة الحقل (404)؛ الفحص يخصّ
    الحقل (404). 503 عند تعذّر القاعدة.
    """
    import json as _json

    from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة") if req.sampled_on is not None else None
    if req.result is not None:
        try:
            result_json = _json.dumps(req.result)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل") from e

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                cur = await conn.fetchrow(
                    "SELECT status, result FROM soil_lab_tests "
                    "WHERE test_id = $1 AND field_id = $2 FOR UPDATE",
                    test_id,
                    field_id,
                )
                if cur is None:
                    raise HTTPException(status_code=404, detail="فحص التربة غير موجود لهذا الحقل")

                set_parts, params = [], []

                def _add(col, value, cast=""):
                    params.append(value)
                    set_parts.append(f"{col} = ${len(params)}{cast}")

                if req.lab_name is not None:
                    _add("lab_name", req.lab_name)
                if req.sampled_on is not None:
                    _add("sampled_on", sampled)
                if req.notes_ar is not None:
                    _add("notes_ar", req.notes_ar)
                if req.result is not None:
                    _add("result", result_json, "::jsonb")

                status_changed = False
                if req.status is not None:
                    # توفّر نتيجة = نتيجة موجودة سابقاً (JSONB غير فارغ) أو ممرَّرة الآن.
                    existing = cur["result"]
                    existing_obj = (
                        _json.loads(existing) if isinstance(existing, str) else (existing or {})
                    )
                    has_result = bool(req.result) or bool(existing_obj)
                    try:
                        status_changed = validate_soil_transition(
                            cur["status"], req.status, has_result=has_result
                        )
                    except SoilWorkflowError as se:
                        raise HTTPException(
                            status_code=se.http_status, detail=se.message_ar
                        ) from se
                    if status_changed:
                        _add("status", req.status)
                        if req.status == "approved":
                            _add("approved_by", str(user.user_id))
                        if req.status == "published":
                            set_parts.append("published_at = now()")  # وقت القاعدة (لا param)

                if not set_parts:
                    raise HTTPException(status_code=422, detail="لا حقول للتحديث")

                params.extend([test_id, field_id])
                await conn.execute(
                    f"UPDATE soil_lab_tests SET {', '.join(set_parts)} "
                    f"WHERE test_id = ${len(params) - 1} AND field_id = ${len(params)}",
                    *params,
                )
                if status_changed and req.status == "published":
                    await _emit_domain_event(
                        conn,
                        user,
                        "SOIL_LAB_RESULT_PUBLISHED",
                        "soil_lab_test",
                        test_id,
                        {"field_id": field_id},
                    )
                    # نشر نتيجة التربة يُدخِل EC جديداً (تقرؤه gather_field_freshness من
                    # soil_lab_tests المنشورة) ⇒ قد تتبدّل الملوحة فالحالة القانونيّة
                    # (نمط التنفيذ/الصلاحيّة). أعِد حساب الإسقاط وأصدِر field.state_changed
                    # إن تبدّل — تغذية حيّة لمستهلكي الحالة، نفس معاملة الكتابة (outbox).
                    from api.field_state_projection import recompute_field_state

                    _fs = await recompute_field_state(conn, field_id)
                    if _fs["changed"]:
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_STATE_CHANGED",
                            "field",
                            field_id,
                            {
                                "validity": _fs["state"]["validity"],
                                "execution_mode": _fs["state"]["execution_mode"],
                                "trigger": "soil_lab.published",
                            },
                        )
                row = await conn.fetchrow(
                    f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests WHERE test_id = $1",
                    test_id,
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تحديث فحص التربة", e) from e
    return _row_to_soil_test(row)


# ─── التنبيهات الزراعيّة (Alerts) — نمط activities (v36) ──────────
_ALERT_TYPES = {
    "low_moisture",
    "heavy_rain",
    "disease_risk",
    "heat_stress",
    "frost_risk",
    "other",
}
_ALERT_SEVERITIES = {"info", "warning", "critical"}
_ALERT_STATUSES = {"active", "acknowledged", "resolved"}


class AlertCreateRequest(BaseModel):
    """طلب إنشاء تنبيه زراعيّ (نوع/خطورة/عنوان/نصّ/حقل اختياريّ)."""

    alert_type: str
    severity: str
    title_ar: str | None = Field(default=None, max_length=200)
    message_ar: str | None = None
    field_id: str | None = None


class AlertSummary(BaseModel):
    alert_id: str
    field_id: str | None = None
    alert_type: str
    severity: str
    title_ar: str | None = None
    message_ar: str | None = None
    status: str
    created_at: str | None = None


def _row_to_alert(r) -> AlertSummary:
    return AlertSummary(
        alert_id=r["alert_id"],
        field_id=r["field_id"],
        alert_type=r["alert_type"],
        severity=r["severity"],
        title_ar=r["title_ar"],
        message_ar=r["message_ar"],
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
    )


@app.get("/api/v1/alerts", response_model=list[AlertSummary])
async def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تنبيهات المستأجِر (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS) + حالة/خطورة اختياريّة.

    تُتحقَّق قيم الترشيح (422 على قيمة غير معروفة) قبل الاستعلام. 503 عند تعذّر القاعدة.
    """
    if status is not None and status not in _ALERT_STATUSES:
        raise HTTPException(status_code=422, detail="حالة تنبيه غير معروفة")
    if severity is not None and severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    conds = ["tenant_id = $1::uuid"]
    args: list = [str(user.tenant_id)]
    if status is not None:
        args.append(status)
        conds.append(f"status = ${len(args)}")
    if severity is not None:
        args.append(severity)
        conds.append(f"severity = ${len(args)}")
    where = " AND ".join(conds)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at "
                f"FROM alerts WHERE {where} ORDER BY created_at DESC",
                *args,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة التنبيهات", e) from e
    return [_row_to_alert(r) for r in rows]


@app.post("/api/v1/alerts", status_code=201, response_model=AlertSummary)
async def create_alert(
    req: AlertCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ تنبيهاً زراعيّاً للمستأجِر — يُخزَّن فعليّاً ضمن سياق المستأجِر (RLS).

    يتحقّق من النوع والخطورة (422)، ويؤكّد أنّ الحقل (إن مُرِّر) يخصّ المستأجِر
    (404) قبل الإدراج، ثمّ يردّ التنبيه المُنشأ. idempotent: Idempotency-Key
    (UUID) يمنع تكرار الإنشاء عند إعادة الموبايل (offline).
    """
    import uuid as _uuid

    if req.alert_type not in _ALERT_TYPES:
        raise HTTPException(status_code=422, detail="نوع تنبيه غير معروف")
    if req.severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    alert_id = "alr_" + _uuid.uuid4().hex[:12]
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                if req.field_id is not None:
                    await _assert_field_in_tenant(conn, req.field_id)
                await conn.execute(
                    """INSERT INTO alerts
                        (alert_id, tenant_id, field_id, alert_type, severity,
                         title_ar, message_ar, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'active')""",
                    alert_id,
                    str(user.tenant_id),
                    req.field_id,
                    req.alert_type,
                    req.severity,
                    req.title_ar,
                    req.message_ar,
                )
                created = AlertSummary(
                    alert_id=alert_id,
                    field_id=req.field_id,
                    alert_type=req.alert_type,
                    severity=req.severity,
                    title_ar=req.title_ar,
                    message_ar=req.message_ar,
                    status="active",
                )
                # تسجيل قنوات التسليم المقصودة (بلا إرسال فعليّ) — غير كاسر.
                await _log_alert_deliveries(conn, user, created)
                # حدث إنشاء التنبيه (تفاعليّ): يستهلكه وكيل الإشعارات للبثّ الفوريّ بدل
                # المسح الدوريّ. نفس معاملة الكتابة (outbox) — فشل الإصدار لا يكسر الحفظ.
                await _emit_domain_event(
                    conn,
                    user,
                    "ALERT_CREATED",
                    "alert",
                    alert_id,
                    {
                        "severity": req.severity,
                        "alert_type": req.alert_type,
                        "field_id": req.field_id,
                    },
                )
                # Canonical Field State: تنبيه على حقل قد يعكس تبدّل قراره ⇒ أعِد حساب
                # الإسقاط وأصدِر field.state_changed إن تبدّلت الصلاحيّة (نفس نمط الموسم،
                # نفس معاملة الكتابة). التنبيهات تمرّ عبر مصدر الحقيقة الواحد.
                if req.field_id is not None:
                    from api.field_state_projection import recompute_field_state

                    _fs = await recompute_field_state(conn, req.field_id)
                    if _fs["changed"]:
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_STATE_CHANGED",
                            "field",
                            req.field_id,
                            {
                                "validity": _fs["state"]["validity"],
                                "execution_mode": _fs["state"]["execution_mode"],
                                "trigger": "alert.created",
                            },
                        )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ alert_id الأصليّ) — response_model يتحقّق منه.
                return created.model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="alert.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": req.field_id, "alert_id": alert_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ التنبيه", e) from e
    return result


@app.patch("/api/v1/alerts/{alert_id}/acknowledge", response_model=AlertSummary)
async def acknowledge_alert(
    alert_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُقِرّ تنبيهاً (status='acknowledged') للمستأجِر — مُرشَّح بالمستأجِر (RLS).

    404 لو التنبيه ليس ضمن المستأجِر؛ 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "UPDATE alerts SET status = 'acknowledged' WHERE alert_id = $1 "
                "RETURNING alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at",
                alert_id,
            )
            # حدث الإقرار (تفاعليّ): يُمكّن المستهلكين من تتبّع دورة حياة التنبيه.
            # داخل المعاملة وفقط عند وجود الصفّ (مرشَّح بالمستأجِر عبر RLS).
            if row is not None:
                await _emit_domain_event(
                    conn,
                    user,
                    "ALERT_ACKNOWLEDGED",
                    "alert",
                    alert_id,
                    {"field_id": row["field_id"], "severity": row["severity"]},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("إقرار التنبيه", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="التنبيه غير موجود ضمن هذا المستأجِر")
    return _row_to_alert(row)


# ─── تفضيلات الإشعار + قنوات التسليم (notification_preferences v9 + v38) ──
# تخزّن قنوات المستخدم (بريد/SMS/Push/واتساب) + عناوينها + أنواع الأحداث المُشترَك
# بها لكلّ (مستأجِر، مستخدم) — تُقرأ/تُحدَّث عبر GET/PUT /api/v1/notifications/
# preferences (FIELD_VIEW/FIELD_EDIT). نُعيد استخدام جدول v9 (لا جدول جديد) مع
# توسعة v38 (sms/whatsapp/user_ref/min_severity). UPSERT على (tenant_id, user_ref)
# ⇒ صفّ واحد لكلّ مستخدم لكلّ مستأجِر (tenant-isolated عبر RLS + شرط tenant صريح).
# منطق التوجيه (أيّ قناة تتلقّى أيّ تنبيه) صرف في api.alert_delivery (مُختبَر offline).

_NOTIF_EVENT_TYPES = {
    "satellite",
    "weather_alert",
    "pest_alert",
    "irrigation_rec",
    "fertilizer_rec",
    "low_stock",
    "task_assigned",
    "economic_analysis",
    # أنواع تنبيهات الحقل (v36) — لتطابق التوجيه مع alert_type الفعليّ.
    "low_moisture",
    "heavy_rain",
    "disease_risk",
    "heat_stress",
    "frost_risk",
    "other",
}


class NotificationPreferences(BaseModel):
    """تفضيلات إشعار المستخدم — القنوات المُفعَّلة + عناوينها + أنواع الأحداث.

    تُستخدم للقراءة والتحديث (PUT يستبدل الصفّ كاملاً — upsert). العناوين/الأرقام
    اختياريّة؛ القناة المُفعَّلة بلا عنوان تُسجَّل كغير قابلة للتسليم (صدق، لا ابتلاع).
    """

    email_enabled: bool = False
    email_address: str | None = Field(default=None, max_length=255)
    sms_enabled: bool = False
    sms_number: str | None = Field(default=None, max_length=32)
    push_enabled: bool = False
    push_token: str | None = None
    whatsapp_enabled: bool = False
    whatsapp_number: str | None = Field(default=None, max_length=32)
    event_types: list[str] = Field(default_factory=list)
    min_severity: str | None = None


def _row_to_prefs(r) -> NotificationPreferences:
    """يطبّع صفّ notification_preferences إلى نموذج الاستجابة (event_types قائمة)."""
    raw_events = r["event_types"]
    if isinstance(raw_events, str):
        import json as _json

        try:
            raw_events = _json.loads(raw_events)
        except (ValueError, TypeError):
            raw_events = []
    return NotificationPreferences(
        email_enabled=bool(r["email_enabled"]),
        email_address=r["email_address"],
        sms_enabled=bool(r["sms_enabled"]),
        sms_number=r["sms_number"],
        push_enabled=bool(r["push_enabled"]),
        push_token=r["push_token"],
        whatsapp_enabled=bool(r["whatsapp_enabled"]),
        whatsapp_number=r["whatsapp_number"],
        event_types=list(raw_events) if raw_events else [],
        min_severity=r["min_severity"],
    )


_PREF_SELECT_COLS = (
    "email_enabled, email_address, sms_enabled, sms_number, "
    "push_enabled, push_token, whatsapp_enabled, whatsapp_number, "
    "event_types, min_severity"
)


@app.get(
    "/api/v1/notifications/preferences",
    response_model=NotificationPreferences,
)
async def get_notification_preferences(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفضيلات إشعار المستخدم الحاليّ ضمن مستأجِره — قنوات + عناوين + أنواع أحداث.

    تُرشَّح بـ(tenant_id, user_ref) (عزل مستأجِر + لكلّ مستخدم). لا صفّ ⇒ تفضيلات
    افتراضيّة (كلّ القنوات مُعطَّلة) لا 404 (الواجهة تعرض نموذجاً فارغاً صادقاً).
    503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"SELECT {_PREF_SELECT_COLS} FROM notification_preferences "
                "WHERE tenant_id = $1::uuid AND user_ref = $2",
                str(user.tenant_id),
                str(user.user_id),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة تفضيلات الإشعار", e) from e
    if row is None:
        return NotificationPreferences()
    return _row_to_prefs(row)


@app.put(
    "/api/v1/notifications/preferences",
    response_model=NotificationPreferences,
)
async def update_notification_preferences(
    req: NotificationPreferences,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُحدِّث (UPSERT) تفضيلات إشعار المستخدم الحاليّ — صفّ واحد لكلّ (مستأجِر، مستخدم).

    يتحقّق من أنواع الأحداث ودرجة الخطورة (422 على قيمة غير معروفة)، ثمّ يُدرِج/
    يُحدِّث عبر تعارض (tenant_id, user_ref). tenant-isolated. 503 عند تعذّر القاعدة.
    """
    import json as _json

    bad_events = [e for e in req.event_types if e not in _NOTIF_EVENT_TYPES]
    if bad_events:
        raise HTTPException(status_code=422, detail="نوع حدث إشعار غير معروف")
    if req.min_severity is not None and req.min_severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO notification_preferences
                    (tenant_id, user_ref, email_enabled, email_address,
                     sms_enabled, sms_number, push_enabled, push_token,
                     whatsapp_enabled, whatsapp_number, event_types, min_severity)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                           $11::jsonb, $12)
                   ON CONFLICT (tenant_id, user_ref)
                   DO UPDATE SET
                     email_enabled    = EXCLUDED.email_enabled,
                     email_address    = EXCLUDED.email_address,
                     sms_enabled      = EXCLUDED.sms_enabled,
                     sms_number       = EXCLUDED.sms_number,
                     push_enabled     = EXCLUDED.push_enabled,
                     push_token       = EXCLUDED.push_token,
                     whatsapp_enabled = EXCLUDED.whatsapp_enabled,
                     whatsapp_number  = EXCLUDED.whatsapp_number,
                     event_types      = EXCLUDED.event_types,
                     min_severity     = EXCLUDED.min_severity,
                     updated_at       = NOW()
                   RETURNING email_enabled, email_address, sms_enabled,
                     sms_number, push_enabled, push_token, whatsapp_enabled,
                     whatsapp_number, event_types, min_severity""",
                str(user.tenant_id),
                str(user.user_id),
                req.email_enabled,
                req.email_address,
                req.sms_enabled,
                req.sms_number,
                req.push_enabled,
                req.push_token,
                req.whatsapp_enabled,
                req.whatsapp_number,
                _json.dumps(req.event_types),
                req.min_severity,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ تفضيلات الإشعار", e) from e
    return _row_to_prefs(row)


async def _log_alert_deliveries(conn, user, alert: AlertSummary) -> None:
    """يحسب قنوات تسليم تنبيه مُنشأ ويُسلّمه عبر مُرسِل حقيقيّ، ثمّ يُسجّل النتيجة.

    يقرأ تفضيلات المستخدم، يبني NotificationPrefs/AlertInput، ويستدعي
    alert_delivery.deliver بمُرسِل حقيقيّ (real_channel_sender): إرسال فعليّ
    عبر القنوات المهيّأة (بريد/SMS/واتساب/تلغرام/Push)، و'logged_not_sent' لغير
    المهيّأة (لا ادّعاء إرسال). غير كاسر: أيّ خطأ (قراءة التفضيلات أو التسليم)
    يُبتلَع ويُسجَّل تحذيراً فلا يفشل إنشاء التنبيه.
    """
    from api.alert_delivery import AlertInput, NotificationPrefs, deliver
    from api.alert_senders import real_channel_sender

    try:
        row = await conn.fetchrow(
            f"SELECT {_PREF_SELECT_COLS} FROM notification_preferences "
            "WHERE tenant_id = $1::uuid AND user_ref = $2",
            str(user.tenant_id),
            str(user.user_id),
        )
    except Exception as e:  # noqa: BLE001 — تسجيل تسليم لا يكسر إنشاء التنبيه
        logger.warning("تعذّر قراءة تفضيلات الإشعار للتسليم: %s", e)
        return
    if row is None:
        return
    prefs_model = _row_to_prefs(row)
    prefs = NotificationPrefs(
        email_enabled=prefs_model.email_enabled,
        email_address=prefs_model.email_address,
        sms_enabled=prefs_model.sms_enabled,
        sms_number=prefs_model.sms_number,
        push_enabled=prefs_model.push_enabled,
        push_token=prefs_model.push_token,
        whatsapp_enabled=prefs_model.whatsapp_enabled,
        whatsapp_number=prefs_model.whatsapp_number,
        event_types=prefs_model.event_types or None,
        min_severity=prefs_model.min_severity,
    )
    alert_input = AlertInput(
        alert_type=alert.alert_type,
        severity=alert.severity,
        title_ar=alert.title_ar,
        message_ar=alert.message_ar,
        field_id=alert.field_id,
    )
    # مُرسِل حقيقيّ (بريد/SMS/واتساب/تلغرام/Push عند تهيئتها، وإلّا logged_not_sent).
    # متزامن (I/O) فنشغّله في خيط كي لا يحجب حلقة الأحداث. غير كاسر: أيّ استثناء
    # تسليم (شبكة/SMTP) يُبتلَع ويُسجَّل — لا يفشل إنشاء التنبيه.
    try:
        plan = await asyncio.to_thread(deliver, prefs, alert_input, real_channel_sender)
    except Exception as e:  # noqa: BLE001 — تسليم لا يكسر الإنشاء
        logger.warning("تعذّر تسليم التنبيه %s عبر القنوات: %s", alert.alert_id, e)
        return
    for channel, ok, detail in plan.results:
        logger.info(
            "تسليم تنبيه %s ← قناة=%s نجَح=%s (%s)",
            alert.alert_id,
            channel,
            ok,
            detail,
        )


# ─── توليد التنبيهات التلقائيّ (Alert engine) — يكتب في جدول alerts (v36) ──
# يبني سياق الحقل من مساعِدات الطقس/الحقل الموجودة (_field_weather_context +
# Open-Meteo + توصية الريّ FAO-56)، يُشغّل قواعد alert_rules النقيّة، ثمّ يُدرِج
# التنبيهات المُولَّدة في نفس جدول v36 — بحذف تكرار (dedupe) لكلّ نوع نشط في الحقل.
# لا جدول/هجرة جديدة. تعذّر الطقس/القاعدة ⇒ 503 صريح.


class AlertEvaluateResponse(BaseModel):
    """ناتج تقييم تنبيهات حقل: المُنشأ + عدد المُتجاوَز (موجود نشط مسبقاً)."""

    created: list[AlertSummary]
    skipped_existing: int


async def _evaluate_field_alerts_persist(
    user: UserSchema, field_id: str
) -> tuple[list[AlertSummary], int]:
    """ينفّذ تقييم تنبيهات حقل واحد ويُدرِج الجديد منها في alerts (v36).

    منطق مشترك بين endpoint الحقل المفرد (/fields/{id}/alerts/evaluate) وتشغيل
    «كلّ الحقول» الدوريّ (/automation/alerts/run) — لتفادي التكرار. يبني السياق
    من الطقس الحيّ (Open-Meteo) ومحصول/مرحلة الموسم النشط، يُشغّل قواعد التنبيه
    النقيّة (api.alert_rules)، ثمّ يُدرِج النتائج مع تجاوز أيّ نوع تنبيه له تنبيه
    'active' قائم (dedupe).

    يُرجع (created, skipped_existing). يرفع HTTPException عند تعذّر القاعدة/الطقس
    أو غياب الحقل (404/422/503) — المُستدعي المفرد يُمرّره؛ تشغيل «كلّ الحقول»
    يلتقطه ليتدهور رشيقاً (يتخطّى الحقل، لا 500).
    """
    import uuid as _uuid

    from api.alert_rules import FieldAlertContext, evaluate_field_alerts
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage = await _field_weather_context(conn, field_id)
            # رطوبة تربة حيّة من telemetry الأجهزة (إن وُجدت) — تُغذّي قاعدة low_moisture.
            soil_reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        forecast = await fetch_daily_forecast(lat, lon, days=3)
        current = await fetch_current(lat, lon)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    soil_pct = soil_reading.value_pct if soil_reading is not None else None
    today = forecast[0] if forecast else None
    # احتياج الريّ الصافي (FAO-56) — يُستخدم لقاعدة low_moisture حين لا قراءة تربة.
    irrigation_need_mm: float | None = None
    if today is not None and today.et0_mm is not None:
        forecast_rain_48h = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
        advice = irrigation_advice(
            et0_mm=today.et0_mm,
            crop=crop,
            stage=stage,
            rain_recent_mm=current.precipitation_mm or 0.0,
            forecast_rain_mm=forecast_rain_48h,
            soil_moisture_pct=soil_pct,
        )
        irrigation_need_mm = advice.get("recommended_mm")

    rain_fc_3d = sum(f.precipitation_mm or 0.0 for f in forecast[:3])  # مطر متوقّع (heavy_rain)
    # مطر آخر ٣ أيام تاريخيّاً (disease_risk = رطوبة سابقة)؛ fallback للتوقّع.
    rain_hist_3d = await _historical_rain_3d_mm(lat, lon, rain_fc_3d)
    ctx = FieldAlertContext(
        field_id=field_id,
        soil_moisture_pct=soil_pct,  # رطوبة تربة حيّة من telemetry إن وُجدت، وإلّا None.
        irrigation_need_mm=irrigation_need_mm,
        forecast_rain_mm=rain_fc_3d,
        temp_c=current.temperature_c,
        humidity_pct=current.humidity_pct,
        rain_mm_3d=rain_hist_3d,
        tmax_c=today.temp_max_c if today is not None else None,
        tmin_c=today.temp_min_c if today is not None else None,
        crop=crop,
    )
    generated = evaluate_field_alerts(ctx)

    created: list[AlertSummary] = []
    skipped = 0
    try:
        async with tenant_connection(user) as conn:
            # أنواع التنبيهات النشطة القائمة لهذا الحقل (dedupe على (field_id, type)).
            existing_rows = await conn.fetch(
                "SELECT DISTINCT alert_type FROM alerts WHERE field_id = $1 AND status = 'active'",
                field_id,
            )
            existing_types = {r["alert_type"] for r in existing_rows}
            for ga in generated:
                if ga.alert_type in existing_types:
                    skipped += 1
                    continue
                alert_id = "alr_" + _uuid.uuid4().hex[:12]
                await conn.execute(
                    """INSERT INTO alerts
                        (alert_id, tenant_id, field_id, alert_type, severity,
                         title_ar, message_ar, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'active')""",
                    alert_id,
                    str(user.tenant_id),
                    field_id,
                    ga.alert_type,
                    ga.severity,
                    ga.title_ar,
                    ga.message_ar,
                )
                # نمنع تكراراً ضمن نفس التشغيل أيضاً (قاعدة واحدة لكلّ نوع).
                existing_types.add(ga.alert_type)
                created.append(
                    AlertSummary(
                        alert_id=alert_id,
                        field_id=field_id,
                        alert_type=ga.alert_type,
                        severity=ga.severity,
                        title_ar=ga.title_ar,
                        message_ar=ga.message_ar,
                        status="active",
                    )
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ التنبيهات المُولَّدة", e) from e

    return created, skipped


@app.post(
    "/api/v1/fields/{field_id}/alerts/evaluate",
    response_model=AlertEvaluateResponse,
)
async def evaluate_field_alerts_endpoint(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُقيّم ظروف الحقل الحاليّة ويُنشئ تنبيهات مُصنَّفة في جدول alerts (v36).

    يؤكّد أنّ الحقل يخصّ المستأجِر (404)، يبني السياق من الطقس الحيّ (Open-Meteo،
    نفس مصدر /api/v1/weather) ومحصول/مرحلة الموسم النشط، يُشغّل قواعد التنبيه
    النقيّة (api.alert_rules)، ثمّ يُدرِج النتائج — مع تجاوز أيّ نوع تنبيه له
    تنبيه 'active' قائم لهذا الحقل (dedupe). 503 إن تعذّر الطقس/القاعدة.
    """
    created, skipped = await _evaluate_field_alerts_persist(user, field_id)
    return AlertEvaluateResponse(created=created, skipped_existing=skipped)


# ─── المزارع (Farms) — هرميّة المزرعة→الحقل (v19) ─────────────────
class FarmCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str | None = None
    area_ha: float | None = None
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    # تنظيم المزرعة (v34) — حقول اختياريّة لشاشة «إنشاء مزرعة».
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=40)
    # غير اختياريّ بقيمة افتراضيّة 'metric' — يطابق DEFAULT في الـmigration ويمنع
    # إدراج NULL صريح، ومُقيَّد بالقيم المسموحة (تحقّق ساكن للواجهة أيضاً).
    units: Literal["metric", "imperial"] = "metric"
    currency: str | None = Field(default=None, max_length=10)
    description: str | None = None
    activity_type: str | None = Field(default=None, max_length=40)


@app.post("/api/v1/farms", status_code=201)
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


@app.get("/api/v1/farms")
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


@app.get("/api/v1/farms/{farm_id}/fields")
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


def _parse_date(value: str | None, field: str) -> date | None:
    """يحوّل سلسلة ISO (YYYY-MM-DD) إلى date؛ يرفع 400 واضحة على قيمة غير صالحة
    بدل تمريرها للقاعدة فتُسقِط 500 (ملاحظة المراجعة). فارغة/None ⇒ None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail=f"تاريخ غير صالح في {field} — استخدم صيغة YYYY-MM-DD"
        ) from None


# ─── المخزون (Inventory) — الطبقة ١٠ (v22) ───────────────────────
class InventoryItemRequest(BaseModel):
    category: str = Field(pattern="^(fertilizer|pesticide|seed|spare_part|other)$")
    name: str = Field(min_length=1, max_length=120)
    unit: str = "unit"
    reorder_level: float | None = Field(default=None, ge=0)
    notes: str | None = None


class InventoryBatchRequest(BaseModel):
    quantity: float = Field(ge=0)
    unit: str | None = None
    batch_code: str | None = None
    expiry_date: str | None = None  # ISO date
    received_at: str | None = None
    supplier: str | None = None
    notes: str | None = None


@app.post("/api/v1/inventory/items", status_code=201)
async def create_inventory_item(
    req: InventoryItemRequest,
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_MANAGE)),
):
    import uuid as _uuid

    item_id = "inv_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
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


@app.get("/api/v1/inventory/items")
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


@app.post("/api/v1/inventory/items/{item_id}/batches", status_code=201)
async def add_inventory_batch(
    item_id: str,
    req: InventoryBatchRequest,
    user: UserSchema = Depends(require_permission(Permission.INVENTORY_MANAGE)),
):
    import uuid as _uuid

    batch_id = "bat_" + _uuid.uuid4().hex[:12]
    expiry = _parse_date(req.expiry_date, "expiry_date")
    received = _parse_date(req.received_at, "received_at") or date.today()
    async with tenant_connection(user) as conn:
        # تأكّد من وجود العنصر ضمن المستأجر (RLS يمنع عنصر مستأجر آخر)
        exists = await conn.fetchval("SELECT 1 FROM inventory_items WHERE item_id = $1", item_id)
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


@app.get("/api/v1/inventory/expiring")
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


# ─── المعدّات (Equipment) — الطبقة ١١ (v23) ──────────────────────
class EquipmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(tractor|pump|harvester|sprayer|other)$")
    operating_hours: float = Field(default=0, ge=0)
    purchase_date: str | None = None
    notes: str | None = None


class MaintenanceRequest(BaseModel):
    kind: str = Field(pattern="^(scheduled|repair|breakdown|inspection)$")
    status: str = Field(default="planned", pattern="^(planned|done|cancelled)$")
    scheduled_date: str | None = None
    performed_date: str | None = None
    cost_usd: float | None = None
    notes: str | None = None


@app.post("/api/v1/equipment", status_code=201)
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


@app.get("/api/v1/equipment")
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


@app.post("/api/v1/equipment/{equipment_id}/maintenance", status_code=201)
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


@app.get("/api/v1/equipment/{equipment_id}/maintenance")
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


# ─── أجهزة IoT (سجلّ + صحّة + telemetry) — الطبقة ٤ (v24) ─────────
class DeviceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(soil_moisture|weather_station|water_meter|camera|actuator|other)$")
    field_id: str | None = None
    firmware_version: str | None = None


class TelemetryRequest(BaseModel):
    sensor_type: str = Field(min_length=1, max_length=40)
    value: float
    unit: str | None = None
    recorded_at: str | None = None  # ISO datetime اختياري (افتراض: الآن)


_DEVICE_ONLINE_WINDOW_MIN = 15  # جهاز يُعتبر online إن ظهر خلال هذه المدّة


@app.post("/api/v1/devices", status_code=201)
async def register_device(
    req: DeviceRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يسجّل جهاز IoT جديد في سجلّ المستأجر."""
    import uuid as _uuid

    device_id = "dev_" + _uuid.uuid4().hex[:12]
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


@app.get("/api/v1/devices")
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


@app.post("/api/v1/devices/{device_id}/telemetry", status_code=201)
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


@app.get("/api/v1/devices/{device_id}/telemetry")
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


# ─── الري التشغيلي (صمامات + جداول) — الطبقة ٣ (v25) ─────────────
class ValveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    device_id: str | None = None
    valve_type: str = Field(default="solenoid", pattern="^(solenoid|manual|drip_header|gate)$")
    flow_rate_lpm: float | None = Field(default=None, ge=0)


class ValveStateRequest(BaseModel):
    status: str = Field(pattern="^(open|closed)$")


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    valve_id: str | None = None
    start_time: str  # HH:MM أو HH:MM:SS
    duration_min: int = Field(ge=1, le=1440)
    days_of_week: list[int] | None = None
    water_target_mm: float | None = Field(default=None, ge=0)
    enabled: bool = True


def _parse_time(value: str):
    """يحوّل HH:MM[:SS] إلى time؛ 400 على قيمة غير صالحة (لا 500)."""
    from datetime import time as _time

    try:
        return _time.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail="start_time غير صالح — استخدم HH:MM أو HH:MM:SS"
        ) from None


@app.post("/api/v1/irrigation/valves", status_code=201)
async def register_valve(
    req: ValveRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    """يسجّل صمّام ريّ ضمن المستأجِر (RLS). idempotent: Idempotency-Key (UUID)
    يمنع تكرار التسجيل عند إعادة الموبايل (offline)."""
    import uuid as _uuid

    valve_id = "vlv_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:

        async def _work():
            await conn.execute(
                """INSERT INTO irrigation_valves
                    (valve_id, tenant_id, name, field_id, device_id, valve_type, flow_rate_lpm)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)""",
                valve_id,
                str(user.tenant_id),
                req.name,
                req.field_id,
                req.device_id,
                req.valve_type,
                req.flow_rate_lpm,
            )
            # نُعيد النتيجة لتُخزَّن كنتيجة أمر idempotent وتُعاد حرفيّاً عند الإعادة
            # (مع حفظ valve_id الأصليّ).
            return {"valve_id": valve_id, "name": req.name, "message_ar": "سُجّل الصمّام"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="valve.register",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"valve_id": valve_id, "field_id": req.field_id},
            )
        else:
            result = await _work()
    return result


@app.get("/api/v1/irrigation/valves")
async def list_valves(user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW))):
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT valve_id, name, field_id, device_id, valve_type, status, flow_rate_lpm, "
            "last_changed_at FROM irrigation_valves ORDER BY name"
        )
    return [
        {
            "valve_id": r["valve_id"],
            "name": r["name"],
            "field_id": r["field_id"],
            "device_id": r["device_id"],
            "valve_type": r["valve_type"],
            "status": r["status"],
            "flow_rate_lpm": float(r["flow_rate_lpm"]) if r["flow_rate_lpm"] is not None else None,
            "last_changed_at": r["last_changed_at"].isoformat() if r["last_changed_at"] else None,
        }
        for r in rows
    ]


@app.post("/api/v1/irrigation/valves/{valve_id}/state")
async def set_valve_state(
    valve_id: str,
    req: ValveStateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    """يسجّل نيّة فتح/إغلاق الصمّام + الحالة. التشغيل الفيزيائي الفعلي يمرّ عبر
    actuator-service/automation مع موافقة بشريّة (HIL) — هذه النقطة لا تُشغّل
    العتاد مباشرةً (مبدأ: لا تشغيل آليّ بلا ضابط). idempotent: Idempotency-Key
    (UUID) يمنع تكرار أمر التشغيل عند إعادة الموبايل (offline)."""
    async with tenant_connection(user) as conn:

        async def _work():
            updated = await conn.fetchval(
                "UPDATE irrigation_valves SET status = $1, last_changed_at = NOW() "
                "WHERE valve_id = $2 RETURNING valve_id",
                req.status,
                valve_id,
            )
            if not updated:
                # 404 داخل _work ⇒ يرتدّ إدراج الأمر معه (لا أمر «ناجح» يتيم على صمّام
                # غير موجود)، فإعادة لاحقة بعد إنشاء الصمّام تُنفَّذ من جديد بأمان.
                raise HTTPException(status_code=404, detail="الصمّام غير موجود")
            return {"valve_id": valve_id, "status": req.status, "message_ar": "سُجّلت حالة الصمّام"}

        # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
        if idem:
            result = await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="valve.set_state",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={"valve_id": valve_id, "status": req.status},
            )
        else:
            result = await _work()
    return result


@app.post("/api/v1/irrigation/schedules", status_code=201)
async def create_schedule(
    req: ScheduleRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    import uuid as _uuid

    schedule_id = "sch_" + _uuid.uuid4().hex[:12]
    start = _parse_time(req.start_time)
    dows = req.days_of_week
    if dows is not None and any(d < 0 or d > 6 for d in dows):
        raise HTTPException(status_code=400, detail="days_of_week يجب أن تكون 0..6")
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO irrigation_schedules
                (schedule_id, tenant_id, field_id, valve_id, name, start_time,
                 duration_min, days_of_week, water_target_mm, enabled)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10)""",
            schedule_id,
            str(user.tenant_id),
            req.field_id,
            req.valve_id,
            req.name,
            start,
            req.duration_min,
            dows,
            req.water_target_mm,
            req.enabled,
        )
        # حدث إنشاء جدول الريّ (تفاعليّ): يبثّه وكيل الإشعارات. نفس المعاملة (outbox)؛
        # _emit_domain_event آمن (يبتلع أخطاءه) فلا يكسر النقطة.
        await _emit_domain_event(
            conn,
            user,
            "IRRIGATION_SCHEDULE_CREATED",
            "irrigation_schedule",
            schedule_id,
            {"field_id": req.field_id, "valve_id": req.valve_id},
        )
    return {"schedule_id": schedule_id, "name": req.name, "message_ar": "أُنشئ جدول الريّ"}


@app.get("/api/v1/irrigation/schedules")
async def list_schedules(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
):
    async with tenant_connection(user) as conn:
        if field_id:
            rows = await conn.fetch(
                "SELECT schedule_id, field_id, valve_id, name, start_time, duration_min, "
                "days_of_week, water_target_mm, enabled, last_run_at FROM irrigation_schedules "
                "WHERE field_id = $1 ORDER BY start_time",
                field_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT schedule_id, field_id, valve_id, name, start_time, duration_min, "
                "days_of_week, water_target_mm, enabled, last_run_at FROM irrigation_schedules "
                "ORDER BY start_time"
            )
    return [
        {
            "schedule_id": r["schedule_id"],
            "field_id": r["field_id"],
            "valve_id": r["valve_id"],
            "name": r["name"],
            "start_time": r["start_time"].isoformat() if r["start_time"] else None,
            "duration_min": r["duration_min"],
            "days_of_week": (list(r["days_of_week"]) if r["days_of_week"] is not None else None),
            "water_target_mm": (
                float(r["water_target_mm"]) if r["water_target_mm"] is not None else None
            ),
            "enabled": r["enabled"],
            "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
        }
        for r in rows
    ]


@app.delete("/api/v1/irrigation/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    async with tenant_connection(user) as conn:
        deleted = await conn.fetchval(
            "DELETE FROM irrigation_schedules WHERE schedule_id = $1 RETURNING schedule_id",
            schedule_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="جدول الريّ غير موجود")
    return {"schedule_id": schedule_id, "message_ar": "حُذف جدول الريّ"}


# ─── البيانات المرجعيّة (Master Data) + الدورات الزراعيّة — (v26) ─
class MasterDataRequest(BaseModel):
    category: str = Field(
        pattern="^(crop|soil_type|fertilizer|pesticide|seed_variety|equipment_type|other)$"
    )
    code: str = Field(min_length=1, max_length=60)
    name_ar: str = Field(min_length=1, max_length=160)
    name_en: str | None = None
    metadata: dict | None = None


class RotationRequest(BaseModel):
    crop: str = Field(min_length=1, max_length=80)
    season_label: str | None = None
    sequence_order: int | None = None
    planted_at: str | None = None
    harvested_at: str | None = None
    notes: str | None = None


@app.post("/api/v1/master-data", status_code=201)
async def create_master_data(
    req: MasterDataRequest,
    user: UserSchema = Depends(require_permission(Permission.MASTER_DATA_MANAGE)),
):
    import json as _json
    import uuid as _uuid

    md_id = "md_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        # نعتمد على قيد UNIQUE(tenant, category, code) لا SELECT-ثمّ-INSERT (سباق):
        # طلبان متزامنان قد يمرّان الفحص ثم يفشل الثاني — نلتقط unique_violation
        # (SQLSTATE 23505) ونُعيد 409 دائماً (لا 500). ملاحظة المراجعة.
        try:
            await conn.execute(
                """INSERT INTO master_data
                    (md_id, tenant_id, category, code, name_ar, name_en, metadata)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb)""",
                md_id,
                str(user.tenant_id),
                req.category,
                req.code,
                req.name_ar,
                req.name_en,
                _json.dumps(req.metadata or {}),
            )
            await _emit_domain_event(
                conn,
                user,
                "MASTER_DATA_CREATED",
                "master_data",
                md_id,
                {"category": req.category, "code": req.code},
            )
        except Exception as e:  # noqa: BLE001 — نميّز unique_violation فقط
            if getattr(e, "sqlstate", None) == "23505":
                raise HTTPException(
                    status_code=409, detail="الرمز موجود مسبقاً في هذه الفئة"
                ) from None
            raise
    return {"md_id": md_id, "code": req.code, "message_ar": "أُضيف عنصر مرجعيّ"}


@app.get("/api/v1/master-data")
async def list_master_data(
    category: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.MASTER_DATA_VIEW)),
):
    """كتالوج البيانات المرجعيّة (مُرشَّح اختياريّاً بالفئة)."""
    async with tenant_connection(user) as conn:
        if category:
            rows = await conn.fetch(
                "SELECT md_id, category, code, name_ar, name_en, metadata, active "
                "FROM master_data WHERE category = $1 AND active ORDER BY name_ar",
                category,
            )
        else:
            rows = await conn.fetch(
                "SELECT md_id, category, code, name_ar, name_en, metadata, active "
                "FROM master_data WHERE active ORDER BY category, name_ar"
            )
    return [
        {
            "md_id": r["md_id"],
            "category": r["category"],
            "code": r["code"],
            "name_ar": r["name_ar"],
            "name_en": r["name_en"],
            "metadata": r["metadata"] if isinstance(r["metadata"], dict) else {},
        }
        for r in rows
    ]


@app.post("/api/v1/fields/{field_id}/rotations", status_code=201)
async def add_crop_rotation(
    field_id: str,
    req: RotationRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """يسجّل محصولاً في تعاقب الحقل (الدورة الزراعيّة + التتبّع)."""
    import uuid as _uuid

    rotation_id = "rot_" + _uuid.uuid4().hex[:12]
    planted = _parse_date(req.planted_at, "planted_at")
    harvested = _parse_date(req.harvested_at, "harvested_at")
    async with tenant_connection(user) as conn:
        exists = await conn.fetchval("SELECT 1 FROM fields WHERE field_id = $1", field_id)
        if not exists:
            raise HTTPException(status_code=404, detail="الحقل غير موجود")
        await conn.execute(
            """INSERT INTO crop_rotations
                (rotation_id, tenant_id, field_id, crop, season_label,
                 sequence_order, planted_at, harvested_at, notes)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)""",
            rotation_id,
            str(user.tenant_id),
            field_id,
            req.crop,
            req.season_label,
            req.sequence_order,
            planted,
            harvested,
            req.notes,
        )
        await _emit_domain_event(
            conn,
            user,
            "CROP_ROTATION_ADDED",
            "crop_rotation",
            rotation_id,
            {"field_id": field_id, "crop": req.crop},
        )
    return {"rotation_id": rotation_id, "message_ar": "سُجّل تعاقب المحصول"}


@app.get("/api/v1/fields/{field_id}/rotations")
async def list_crop_rotations(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تاريخ تعاقب المحاصيل للحقل (للدورة الزراعيّة وتتبّع المحصول)."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT rotation_id, crop, season_label, sequence_order, planted_at, harvested_at, notes "
            "FROM crop_rotations WHERE field_id = $1 "
            "ORDER BY sequence_order NULLS LAST, planted_at",
            field_id,
        )
    return [
        {
            "rotation_id": r["rotation_id"],
            "crop": r["crop"],
            "season_label": r["season_label"],
            "sequence_order": r["sequence_order"],
            "planted_at": r["planted_at"].isoformat() if r["planted_at"] else None,
            "harvested_at": r["harvested_at"].isoformat() if r["harvested_at"] else None,
            "notes": r["notes"],
        }
        for r in rows
    ]


# ─── الإعدادات (Settings) — منصّة/مزرعة/ريّ/إشعارات — (v28) ───────
class SettingRequest(BaseModel):
    scope: str = Field(pattern="^(platform|farm|irrigation|notification)$")
    key: str = Field(min_length=1, max_length=80)
    value: dict | None = None


@app.put("/api/v1/settings")
async def upsert_setting(
    req: SettingRequest,
    user: UserSchema = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    """يحفظ/يحدّث إعداداً (upsert idempotent لكلّ مستأجر+نطاق+مفتاح)."""
    import json as _json
    import uuid as _uuid

    setting_id = "set_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO settings
                (setting_id, tenant_id, scope, key, value, updated_by)
               VALUES ($1, $2::uuid, $3, $4, $5::jsonb, $6)
               ON CONFLICT (tenant_id, scope, key) DO UPDATE
                 SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by
               RETURNING setting_id, scope, key""",
            setting_id,
            str(user.tenant_id),
            req.scope,
            req.key,
            _json.dumps(req.value or {}),
            str(user.user_id),
        )
    return {
        "setting_id": row["setting_id"],
        "scope": row["scope"],
        "key": row["key"],
        "message_ar": "حُفِظ الإعداد",
    }


@app.get("/api/v1/settings")
async def list_settings(
    scope: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.SETTINGS_VIEW)),
):
    """إعدادات المستأجر (مُرشَّحة اختياريّاً بالنطاق)."""
    async with tenant_connection(user) as conn:
        if scope:
            rows = await conn.fetch(
                "SELECT setting_id, scope, key, value, updated_by "
                "FROM settings WHERE scope = $1 ORDER BY key",
                scope,
            )
        else:
            rows = await conn.fetch(
                "SELECT setting_id, scope, key, value, updated_by FROM settings ORDER BY scope, key"
            )
    return [
        {
            "setting_id": r["setting_id"],
            "scope": r["scope"],
            "key": r["key"],
            "value": r["value"] if isinstance(r["value"], dict) else {},
            "updated_by": r["updated_by"],
        }
        for r in rows
    ]


# ─── تحليلات التكاليف الفعليّة (Cost Analytics) ──────────────────
# يستبدل ملخّص التكاليف الثابت في ReportsPage. يُجمّع تكاليف حقيقيّة من جداول
# قائمة: field_tasks.actual_cost_usd + equipment_maintenance.cost_usd. لا ترحيل.
@app.get("/api/v1/analytics/costs")
async def analytics_costs(
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """تكاليف فعليّة مُجمَّعة من الجداول القائمة (لا أرقام ثابتة)."""
    async with tenant_connection(user) as conn:
        tasks_total = await conn.fetchval(
            "SELECT COALESCE(SUM(actual_cost_usd), 0) FROM field_tasks "
            "WHERE actual_cost_usd IS NOT NULL"
        )
        tasks_count = await conn.fetchval(
            "SELECT COUNT(*) FROM field_tasks WHERE actual_cost_usd IS NOT NULL"
        )
        maint_total = await conn.fetchval(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM equipment_maintenance WHERE cost_usd IS NOT NULL"
        )
    tasks_total_f = float(tasks_total or 0)
    maint_total_f = float(maint_total or 0)
    return {
        "by_source": [
            {"source": "field_tasks", "total_usd": tasks_total_f},
            {"source": "maintenance", "total_usd": maint_total_f},
        ],
        "total_usd": tasks_total_f + maint_total_f,
        "task_count": int(tasks_count or 0),
    }


@app.get("/api/v1/analytics/costs/by-field")
async def analytics_costs_by_field(
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """إجماليّات تكلفة المهامّ لكلّ حقل."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT field_id, COALESCE(SUM(actual_cost_usd), 0) AS total_usd "
            "FROM field_tasks WHERE actual_cost_usd IS NOT NULL "
            "GROUP BY field_id ORDER BY total_usd DESC"
        )
    return [{"field_id": r["field_id"], "total_usd": float(r["total_usd"] or 0)} for r in rows]


# ─── التقارير والتحليلات (Reports & Analytics) — تجميع جداول قائمة، لا ترحيل ─
# يُجمّع ملخّصات (مزرعة/حقل/موسم) من fields/seasons/activities/alerts/farms عبر
# COUNT/SUM/GROUP BY مُرشَّحة بالمستأجِر (RLS + tenant_id). تشكيل الصفوف نقيّ
# (دوالّ _shape_* مُختبَرة offline) كي يبقى المنطق قابلاً للاختبار بلا قاعدة.


def _count_by_key(rows, key: str) -> dict[str, int]:
    """صفوف GROUP BY ({key, count}) → قاموس {قيمة: عدد}.

    دالّة نقيّة (لا قاعدة): تتجاهل القيم None (تجمعها تحت 'unknown')، وتحوّل
    العدّ إلى int. تُعاد استخدامها لتجميع العمليّات حسب الحالة/النوع.
    """
    out: dict[str, int] = {}
    for r in rows:
        raw = r[key]
        label = str(raw) if raw is not None else "unknown"
        out[label] = out.get(label, 0) + int(r["count"] or 0)
    return out


def _shape_area_by_crop(rows) -> list[dict]:
    """صفوف ({crop, total_area_ha}) → قائمة مُرتّبة تنازليّاً بالمساحة.

    دالّة نقيّة: المحصول None/فارغ ⇒ 'غير محدّد'، المساحة → float مُدوّرة (٢ منزلة).
    تُغذّي مخطّط «المساحة حسب المحصول» في الواجهة.
    """
    shaped = [
        {
            "crop": (r["crop"] or "غير محدّد"),
            "area_ha": round(float(r["total_area_ha"] or 0), 2),
        }
        for r in rows
    ]
    shaped.sort(key=lambda x: x["area_ha"], reverse=True)
    return shaped


def _shape_farm_summary(
    *,
    farms_count: int,
    fields_count: int,
    total_area_ha,
    active_seasons_count: int,
    activities_by_status: dict[str, int],
    open_alerts_count: int,
    area_by_crop: list[dict],
) -> dict:
    """يبني جسم ملخّص المزرعة من العدّادات المُجمَّعة — نقيّ (لا قاعدة).

    يُطبّع المساحة إلى float (٢ منزلة) ويضمن أعداداً صحيحة موجبة. activities_total
    مُشتقّ من مجموع القاموس كي يطابق التفصيل (مصدر واحد للحقيقة).
    """
    return {
        "farms_count": int(farms_count or 0),
        "fields_count": int(fields_count or 0),
        "total_area_ha": round(float(total_area_ha or 0), 2),
        "active_seasons_count": int(active_seasons_count or 0),
        "activities_total": sum(activities_by_status.values()),
        "activities_by_status": activities_by_status,
        "open_alerts_count": int(open_alerts_count or 0),
        "area_by_crop": area_by_crop,
    }


@app.get("/api/v1/reports/farm-summary")
async def report_farm_summary(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص المزرعة على مستوى المستأجِر — عدّادات حيّة من الجداول القائمة.

    يُجمّع: عدد المزارع/الحقول، إجماليّ المساحة، المواسم النشطة، العمليّات حسب
    الحالة، التنبيهات المفتوحة (active)، والمساحة حسب المحصول. مُرشَّح بالمستأجِر
    (RLS + tenant_id). 503 عند تعذّر القاعدة — لا أرقام مُلفَّقة.
    """
    try:
        async with tenant_connection(user) as conn:
            tid = str(user.tenant_id)
            farms_count = await conn.fetchval(
                "SELECT COUNT(*) FROM farms WHERE tenant_id = $1::uuid", tid
            )
            fields_count = await conn.fetchval(
                "SELECT COUNT(*) FROM fields WHERE tenant_id = $1::uuid", tid
            )
            total_area = await conn.fetchval(
                "SELECT COALESCE(SUM(area_ha), 0) FROM fields WHERE tenant_id = $1::uuid", tid
            )
            active_seasons = await conn.fetchval(
                "SELECT COUNT(*) FROM seasons WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            activity_rows = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM activities "
                "WHERE tenant_id = $1::uuid GROUP BY status",
                tid,
            )
            open_alerts = await conn.fetchval(
                "SELECT COUNT(*) FROM alerts WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            crop_rows = await conn.fetch(
                "SELECT crop, COALESCE(SUM(area_ha), 0) AS total_area_ha FROM fields "
                "WHERE tenant_id = $1::uuid GROUP BY crop",
                tid,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة ملخّص المزرعة", e) from e
    return _shape_farm_summary(
        farms_count=farms_count,
        fields_count=fields_count,
        total_area_ha=total_area,
        active_seasons_count=active_seasons,
        activities_by_status=_count_by_key(activity_rows, "status"),
        open_alerts_count=open_alerts,
        area_by_crop=_shape_area_by_crop(crop_rows),
    )


@app.get("/api/v1/reports/field/{field_id}/summary")
async def report_field_summary(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص حقل واحد — مساحته/محصوله/تربته + موسمه النشط + عمليّاته + تنبيهاته.

    يؤكّد أنّ الحقل يخصّ المستأجِر (404) قبل التجميع. العمليّات تُعدّ حسب النوع
    والحالة، والتنبيهات الأخيرة تُعرض (٥). مُرشَّح بالمستأجِر (RLS). 503 عند تعذّر
    القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            field = await conn.fetchrow(
                "SELECT field_id, name, area_ha, crop, soil_type FROM fields WHERE field_id = $1",
                field_id,
            )
            if field is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            season = await conn.fetchrow(
                "SELECT season_id, crops, cultivar, sowing_date, season_end, status "
                "FROM seasons WHERE field_id = $1 AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                field_id,
            )
            by_type_rows = await conn.fetch(
                "SELECT activity_type, COUNT(*) AS count FROM activities "
                "WHERE field_id = $1 GROUP BY activity_type",
                field_id,
            )
            by_status_rows = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM activities "
                "WHERE field_id = $1 GROUP BY status",
                field_id,
            )
            recent_alert_rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at FROM alerts "
                "WHERE field_id = $1 ORDER BY created_at DESC LIMIT 5",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة ملخّص الحقل", e) from e

    import json as _json

    current_season = None
    if season is not None:
        crops = season["crops"]
        if isinstance(crops, str):
            try:
                crops = _json.loads(crops)
            except (ValueError, TypeError):
                crops = []
        current_season = {
            "season_id": season["season_id"],
            "crops": crops if isinstance(crops, list) else [],
            "cultivar": season["cultivar"],
            "sowing_date": season["sowing_date"].isoformat() if season["sowing_date"] else None,
            "season_end": season["season_end"].isoformat() if season["season_end"] else None,
            "status": season["status"],
        }
    by_status = _count_by_key(by_status_rows, "status")
    return {
        "field_id": field["field_id"],
        "name": field["name"],
        "area_ha": float(field["area_ha"]) if field["area_ha"] is not None else 0.0,
        "crop": field["crop"],
        "soil_type": field["soil_type"],
        "current_season": current_season,
        "activities_total": sum(by_status.values()),
        "activities_by_type": _count_by_key(by_type_rows, "activity_type"),
        "activities_by_status": by_status,
        "recent_alerts": [_row_to_alert(r).model_dump() for r in recent_alert_rows],
    }


@app.get("/api/v1/reports/season/{season_id}/summary")
async def report_season_summary(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملخّص موسم واحد — محصوله/صنفه/تواريخه + عدد المراحل + العمليّات المرتبطة.

    يؤكّد أنّ الموسم يخصّ المستأجِر (404). عدد المراحل من مصفوفة stages (JSONB)،
    والعمليّات المرتبطة تُعدّ بـseason_id. مُرشَّح بالمستأجِر (RLS). 503 عند تعذّر
    القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            season = await conn.fetchrow(
                "SELECT season_id, field_id, crops, cultivar, irrigation_type, "
                "sowing_date, season_end, stages, status FROM seasons "
                "WHERE season_id = $1",
                season_id,
            )
            if season is None:
                raise HTTPException(status_code=404, detail="الموسم غير موجود ضمن هذا المستأجِر")
            activities_count = await conn.fetchval(
                "SELECT COUNT(*) FROM activities WHERE season_id = $1", season_id
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة ملخّص الموسم", e) from e

    import json as _json

    def _arr(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return []
        return v or []

    crops = _arr(season["crops"])
    stages = _arr(season["stages"])
    return {
        "season_id": season["season_id"],
        "field_id": season["field_id"],
        "crops": crops if isinstance(crops, list) else [],
        "cultivar": season["cultivar"],
        "irrigation_type": season["irrigation_type"],
        "sowing_date": season["sowing_date"].isoformat() if season["sowing_date"] else None,
        "season_end": season["season_end"].isoformat() if season["season_end"] else None,
        "status": season["status"],
        "stage_count": len(stages) if isinstance(stages, list) else 0,
        "activities_count": int(activities_count or 0),
    }


# ═══════════════════════════════════════════════════════════════════
# INDICATORS DASHBOARD — لوحة المؤشّرات المُجمَّعة (tenant-scoped, FIELD_VIEW)
# ───────────────────────────────────────────────────────────────────
# صدق المصدر: indicators-service خدمة stub صحّيّة فقط (لا منطق). كانت الواجهة
# تطلب :8091/indicators/dashboard|catalog فتسقط على mock أو فراغ. هنا نوفّر
# لوحة *حقيقيّة* مُجمَّعة من الجداول القائمة (fields/seasons/alerts) عبر البوّابة
# الموحّدة /api/v1/. لا نخترع قيم NDVI/طقس (تلك في vegetation/weather/raster) —
# نُجمّع ما هو محفوظ فعلاً ونصنّف الحقول حسب وجود/غياب موسم نشط. أيّ خطأ DB ⇒ 503.
# ═══════════════════════════════════════════════════════════════════

# كتالوج المؤشّرات التي تحسبها المنصّة فعلاً (مصدر كلٍّ موثّق بصدق). ليس 33
# مؤشّراً مُلفَّقاً — بل ما هو مُنفَّذ ومخدوم عبر خدمات حقيقيّة (vegetation/raster
# للطيفيّة، weather للمناخيّة، soil للتربة). الواجهة تعرضه كدليل + فلترة بالفئة.
# renderable=True ⇒ طبقة بلاطات/شبكة مكانيّة يرسمها raster-service (band_math)
# فتظهر في مبدّل طبقات الخريطة. renderable=False ⇒ قيمة قياسيّة (طقس/تربة) غير
# مكانيّة (لا تُرسَم كطبقة) — مرجعيّة فقط. الواجهة تقود مبدّل الخريطة بـrenderable
# لا بقائمة مُبرمَجة (مصدر حقيقة واحد). كلّ renderable مؤكَّد في raster band_math.
_INDICATOR_CATALOG: list[dict] = [
    {
        "id": "ndvi",
        "category": "vegetation",
        "name_ar": "NDVI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "evi",
        "category": "vegetation",
        "name_ar": "EVI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "ndre",
        "category": "vegetation",
        "name_ar": "NDRE",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "msavi",
        "category": "vegetation",
        "name_ar": "MSAVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "savi",
        "category": "vegetation",
        "name_ar": "SAVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "gndvi",
        "category": "vegetation",
        "name_ar": "GNDVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "ndwi",
        "category": "water",
        "name_ar": "NDWI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "ndmi",
        "category": "water",
        "name_ar": "NDMI (الرطوبة)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "msi",
        "category": "water",
        "name_ar": "MSI (الإجهاد المائي)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "et0",
        "category": "water",
        "name_ar": "ET₀",
        "unit": "mm/d",
        "source": "weather-service (FAO-56)",
        "renderable": False,
    },
    {
        "id": "water_deficit",
        "category": "water",
        "name_ar": "عجز المياه",
        "unit": "mm",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "gdd",
        "category": "weather",
        "name_ar": "GDD المتراكم",
        "unit": "°C·يوم",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "temperature",
        "category": "weather",
        "name_ar": "الحرارة",
        "unit": "°C",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "humidity",
        "category": "weather",
        "name_ar": "الرطوبة النسبيّة",
        "unit": "%",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "salinity",
        "category": "soil",
        "name_ar": "الملوحة (SI)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "soil_ph",
        "category": "soil",
        "name_ar": "pH التربة",
        "unit": "",
        "source": "soil-service",
        "renderable": False,
    },
    {
        "id": "soil_ec",
        "category": "soil",
        "name_ar": "EC التربة",
        "unit": "dS/m",
        "source": "soil-service",
        "renderable": False,
    },
    {
        "id": "nitrogen",
        "category": "soil",
        "name_ar": "النيتروجين المتاح",
        "unit": "mg/kg",
        "source": "soil-service",
        "renderable": False,
    },
]


def _shape_indicator_catalog() -> dict:
    """يبني جسم الكتالوج من _INDICATOR_CATALOG — نقيّ (لا قاعدة).

    يحسب categories = {فئة: عدد} ليطابق ما تتوقّعه الواجهة (total + categories).
    """
    categories: dict[str, int] = {}
    for ind in _INDICATOR_CATALOG:
        cat = ind["category"]
        categories[cat] = categories.get(cat, 0) + 1
    renderable_total = sum(1 for ind in _INDICATOR_CATALOG if ind.get("renderable"))
    return {
        "total": len(_INDICATOR_CATALOG),
        "renderable_total": renderable_total,
        "categories": categories,
        "indicators": _INDICATOR_CATALOG,
        "note_ar": "المؤشّرات المُنفَّذة فعلاً ومصادرها — لا قيم مُلفَّقة. "
        "renderable=طبقة بلاطات مكانيّة (تظهر في مبدّل الخريطة)؛ غيرها قيمة قياسيّة مرجعيّة.",
    }


def _shape_indicators_dashboard(
    *,
    fields_rows,
    active_field_ids: set[str],
    alert_rows,
) -> dict:
    """يبني لوحة المؤشّرات المُجمَّعة من صفوف الحقول/المواسم/التنبيهات — نقيّ.

    - fields_summary: صفّ لكلّ حقل (id/name/crop/area + has_active_season).
    - kpis: عدّادات حقيقيّة (إجماليّ الحقول/المساحة/الحقول النشطة/التنبيهات المفتوحة).
      لا NDVI مخترع — قيم المؤشّرات الطيفيّة تأتي من vegetation/raster لكلّ حقل.
    - alerts: قائمة التنبيهات النشطة كما هي (تُمرَّر للّوحة بلا تلفيق).
    """
    import json as _json

    fields_summary = []
    total_area = 0.0
    for r in fields_rows:
        area = float(r["area_ha"]) if r["area_ha"] is not None else 0.0
        total_area += area
        # geometry (GeoJSON) يُمرَّر كما هو ليرسم العميل (موبايل/ويب) حدّ الحقل
        # ويضبط مركز/تكبير الخريطة على حقل المستخدم. JSONB قد يعود نصّاً ⇒ نفكّه.
        # غيابه لا يكسر شيئاً: العميل يحرس على غياب geometry (حقل اختياريّ).
        geom = None
        try:
            geom = r["geometry"]
        except (KeyError, IndexError):
            geom = None
        if isinstance(geom, str):
            try:
                geom = _json.loads(geom)
            except (ValueError, TypeError):
                geom = None
        fields_summary.append(
            {
                "field_id": r["field_id"],
                "field_name": r["name"],
                "crop": r["crop"],
                "area_ha": round(area, 2),
                "has_active_season": r["field_id"] in active_field_ids,
                "geometry": geom,
            }
        )
    active_count = len(active_field_ids)
    kpis = [
        {
            "id": "fields_total",
            "category": "operations",
            "name_ar": "إجماليّ الحقول",
            "value": len(fields_summary),
            "unit": "حقل",
            "status": "good",
        },
        {
            "id": "area_total",
            "category": "operations",
            "name_ar": "إجماليّ المساحة",
            "value": round(total_area, 2),
            "unit": "هـ",
            "status": "good",
        },
        {
            "id": "active_seasons",
            "category": "operations",
            "name_ar": "حقول بموسم نشط",
            "value": active_count,
            "unit": "حقل",
            "status": "good" if active_count else "fair",
        },
        {
            "id": "open_alerts",
            "category": "operations",
            "name_ar": "تنبيهات مفتوحة",
            "value": len(alert_rows),
            "unit": "تنبيه",
            "status": "critical" if alert_rows else "good",
        },
    ]
    return {
        "kpis": kpis,
        "alerts": [_row_to_alert(r).model_dump() for r in alert_rows],
        "fields_summary": fields_summary,
        "note_ar": "عدّادات حيّة من جداولك — المؤشّرات الطيفيّة لكلّ حقل من شاشة الأقمار.",
    }


@app.get("/api/v1/indicators/catalog")
async def indicators_catalog(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كتالوج المؤشّرات المُنفَّذة فعلاً + مصادرها (بديل indicators-service الـstub).

    ثابت (لا قاعدة) لكنّه صادق: يصف ما تحسبه المنصّة حقّاً عبر خدماتها، لا ٣٣
    مؤشّراً وهميّاً. مُقيَّد بالدور (FIELD_VIEW) للاتّساق مع بقيّة لوحات الحقل.
    """
    return _shape_indicator_catalog()


@app.get("/api/v1/indicators/dashboard")
async def indicators_dashboard(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """لوحة المؤشّرات المُجمَّعة للمستأجِر — عدّادات + تنبيهات + ملخّص الحقول.

    تجميع حيّ من fields/seasons/alerts (RLS + tenant_id). لا قيم NDVI/طقس مُلفَّقة:
    المؤشّرات الطيفيّة لكلّ حقل تُجلب من vegetation/raster في شاشة الأقمار. 503 عند
    تعذّر القاعدة — لا أرقام مخترعة.
    """
    try:
        async with tenant_connection(user) as conn:
            tid = str(user.tenant_id)
            fields_rows = await conn.fetch(
                "SELECT field_id, name, crop, area_ha, geometry FROM fields "
                "WHERE tenant_id = $1::uuid ORDER BY name",
                tid,
            )
            active_season_rows = await conn.fetch(
                "SELECT DISTINCT field_id FROM seasons "
                "WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            alert_rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at FROM alerts "
                "WHERE tenant_id = $1::uuid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 50",
                tid,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة لوحة المؤشّرات", e) from e
    active_field_ids = {r["field_id"] for r in active_season_rows}
    return _shape_indicators_dashboard(
        fields_rows=fields_rows,
        active_field_ids=active_field_ids,
        alert_rows=alert_rows,
    )


# ─── إدارة المستندات (Document Management — سجلّ بيانات وصفيّة) — (v29) ─
# ⚠️ سجلّ بيانات وصفيّة فقط: لا يخزّن الملفّ الثنائيّ (blob). تخزين الكائنات
#    الفعليّ (PDF/صورة/...) يحتاج S3/MinIO — نحفظ هنا storage_ref فقط.
class DocumentRequest(BaseModel):
    category: str = Field(pattern="^(contract|report|image|map|lab_result|other)$")
    title: str = Field(min_length=1, max_length=200)
    storage_ref: str | None = None
    content_type: str | None = Field(default=None, max_length=80)
    size_bytes: int | None = Field(default=None, ge=0)
    field_id: str | None = Field(default=None, max_length=50)  # يطابق fields.field_id VARCHAR(50)


@app.post("/api/v1/documents", status_code=201)
async def register_document(
    req: DocumentRequest,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
):
    """يسجّل بيانات مستند وصفيّة (لا blob — storage_ref يشير لتخزين الكائنات)."""
    import uuid as _uuid

    doc_id = "doc_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO documents
                (doc_id, tenant_id, category, field_id, title, storage_ref,
                 content_type, size_bytes, uploaded_by)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)""",
            doc_id,
            str(user.tenant_id),
            req.category,
            req.field_id,
            req.title,
            req.storage_ref,
            req.content_type,
            req.size_bytes,
            user.user_id,
        )
    return {"doc_id": doc_id, "title": req.title, "message_ar": "سُجّل المستند"}


@app.get("/api/v1/documents")
async def list_documents(
    category: str | None = None,
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_VIEW)),
):
    """سجلّ المستندات (مُرشَّح اختياريّاً بالفئة و/أو الحقل) — معزول بالمستأجر."""
    clauses: list[str] = []
    params: list = []
    if category:
        params.append(category)
        clauses.append(f"category = ${len(params)}")
    if field_id:
        params.append(field_id)
        clauses.append(f"field_id = ${len(params)}")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT doc_id, category, field_id, title, storage_ref, content_type, "
            "size_bytes, version, uploaded_by, created_at "
            f"FROM documents{where} ORDER BY created_at DESC",
            *params,
        )
    return [
        {
            "doc_id": r["doc_id"],
            "category": r["category"],
            "field_id": r["field_id"],
            "title": r["title"],
            "storage_ref": r["storage_ref"],
            "content_type": r["content_type"],
            "size_bytes": r["size_bytes"],
            "version": r["version"],
            "uploaded_by": r["uploaded_by"],
        }
        for r in rows
    ]


@app.get("/api/v1/documents/{doc_id}")
async def get_document(
    doc_id: str,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_VIEW)),
):
    """بيانات مستند مفرد (404 إن غير موجود) — معزول بالمستأجر."""
    async with tenant_connection(user) as conn:
        r = await conn.fetchrow(
            "SELECT doc_id, category, field_id, title, storage_ref, content_type, "
            "size_bytes, version, uploaded_by, created_at "
            "FROM documents WHERE doc_id = $1",
            doc_id,
        )
    if r is None:
        raise HTTPException(status_code=404, detail="المستند غير موجود")
    return {
        "doc_id": r["doc_id"],
        "category": r["category"],
        "field_id": r["field_id"],
        "title": r["title"],
        "storage_ref": r["storage_ref"],
        "content_type": r["content_type"],
        "size_bytes": r["size_bytes"],
        "version": r["version"],
        "uploaded_by": r["uploaded_by"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


# ═══════════════════════════════════════════════════════════════════
#   Open-Meteo Weather Integration (مجاني، بدون مفتاح)
# ═══════════════════════════════════════════════════════════════════


@app.get("/api/v1/weather/current")
async def weather_current(lat: float, lon: float):
    """الطقس الحالي من Open-Meteo. مفتوح بدون auth."""
    try:
        from api.connectors.openmeteo import describe_weather_ar, fetch_current

        data = await fetch_current(lat, lon)
        return {
            "temperature_c": data.temperature_c,
            "humidity_pct": data.humidity_pct,
            "wind_speed_ms": data.wind_speed_ms,
            "precipitation_mm": data.precipitation_mm,
            "cloud_cover_pct": data.cloud_cover_pct,
            "weather_code": data.weather_code,
            "weather_ar": describe_weather_ar(data.weather_code),
            "is_day": data.is_day,
            "timestamp": data.timestamp,
            "source": "open-meteo",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


@app.get("/api/v1/weather/forecast")
async def weather_forecast(lat: float, lon: float, days: int = 7):
    """توقّعات ١-١٦ يوم + ET₀ (FAO-56) + spraying conditions."""
    try:
        from api.connectors.openmeteo import (
            describe_weather_ar,
            fetch_daily_forecast,
            spraying_condition_score,
        )

        forecast = await fetch_daily_forecast(lat, lon, days=days)
        return {
            "location": {"lat": lat, "lon": lon},
            "days": [
                {
                    "date": f.date,
                    "temp_max_c": f.temp_max_c,
                    "temp_min_c": f.temp_min_c,
                    "precipitation_mm": f.precipitation_mm,
                    "et0_mm": f.et0_mm,
                    "sunshine_hours": f.sunshine_hours,
                    # شمسيّ/نهاريّ — لجدولة الريّ بالطاقة الشمسيّة وتقدير الإنتاج
                    "sunrise": f.sunrise,
                    "sunset": f.sunset,
                    "daylight_hours": f.daylight_hours,
                    "solar_radiation_mj_m2": f.solar_radiation_mj_m2,
                    "wind_max_ms": f.wind_max_ms,
                    "weather_code": f.weather_code,
                    "weather_ar": describe_weather_ar(f.weather_code),
                    "spraying": (
                        lambda s: {
                            "status": s[0],
                            "reason_ar": s[1],
                        }
                    )(spraying_condition_score(f)),
                }
                for f in forecast
            ],
            "source": "open-meteo",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


@app.get("/api/v1/weather/historical")
async def weather_historical(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
):
    """ERA5 reanalysis — تاريخي من ١٩٤٠. مفيد لـGDD."""
    try:
        from api.connectors.openmeteo import fetch_historical

        days = await fetch_historical(lat, lon, start_date, end_date)
        return {
            "location": {"lat": lat, "lon": lon},
            "range": {"start": start_date, "end": end_date},
            "days": [
                {
                    "date": d.date,
                    "temp_max_c": d.temp_max_c,
                    "temp_min_c": d.temp_min_c,
                    "precipitation_mm": d.precipitation_mm,
                    "et0_mm": d.et0_mm,
                }
                for d in days
            ],
            "source": "open-meteo-archive",
            "model": "ERA5",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


# ─── TrueUp (yield calibration) — موصَّل end-to-end ──────────────
# جلسة التصحيح الذاتي: بند ١ — توصيل وحدة واحدة فعلاً بدل الجزر المعزولة.
# TrueUpEngine.compute هو pure logic (مُختبَر في test_v12_modules.py: 23/23).
# هنا نوصّله بـendpoint حقيقي. الـpersist (apply) يحتاج DB pool — يُفعّل
# عند توفّر PostgreSQL؛ حتّى ذلك الحين الـendpoint يحسب ويُرجع النتيجة.

from api.trueup import TrueUpEngine, TrueUpInput, TrueUpStatus  # noqa: E402

_trueup_engine = TrueUpEngine()  # pure-compute mode (pool=None)


class TrueUpRequest(BaseModel):
    field_id: str
    operation_id: str
    crop: str
    actual_weight_kg: float
    actual_moisture_pct: float
    measured_weight_kg: float
    measured_yield_kg_ha: float
    sample_area_ha: float | None = None
    notes_ar: str | None = None


@app.post("/api/v1/fields/{field_id}/trueup")
def apply_trueup(
    field_id: str,
    req: TrueUpRequest,
    user: UserSchema = Depends(require_permission(Permission.CALIBRATION_RUN)),
):
    """معايرة الإنتاج (TrueUp) — يحسب k_new + الإنتاج المُعدَّل.

    المرجع: المستند ٩ (FieldView TrueUp).
    الرياضيّات في trueup.py (pure، مُختبَرة). هذا الـendpoint يوصّلها.
    """
    if req.field_id != field_id:
        raise HTTPException(status_code=400, detail="field_id mismatch بين المسار والجسم")

    inp = TrueUpInput(
        field_id=req.field_id,
        operation_id=req.operation_id,
        actual_weight_kg=req.actual_weight_kg,
        actual_moisture_pct=req.actual_moisture_pct,
        measured_weight_kg=req.measured_weight_kg,
        sample_area_ha=req.sample_area_ha,
        notes_ar=req.notes_ar,
    )

    result = _trueup_engine.compute(
        input_data=inp,
        crop=req.crop,
        measured_yield_kg_ha=req.measured_yield_kg_ha,
        k_old=1.0,
    )

    if result.status == TrueUpStatus.REJECTED:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "rejected",
                "rationale_ar": result.rationale_ar,
                "warnings": result.warnings,
            },
        )

    return {
        "status": result.status.value,
        "field_id": result.field_id,
        "operation_id": result.operation_id,
        "k_new": result.k_new,
        "k_change_pct": result.k_change_pct,
        "measured_yield_kg_ha": result.measured_yield_kg_ha,
        "adjusted_yield_kg_ha": result.adjusted_yield_kg_ha,
        "error_pct": result.error_pct,
        "moisture_correction_applied": result.moisture_correction_applied,
        "standard_moisture_pct": result.standard_moisture_pct,
        "rationale_ar": result.rationale_ar,
        "warnings": result.warnings,
        "applied_at": result.applied_at,
        "persisted": False,
    }


# ─── Geometry validation — موصَّل end-to-end ─────────────────────
# جلسة التصحيح الذاتي: توصيل وحدة ثانية. geospatial_integrity.py مُختبَر
# (test_geospatial.py: 29/29). هذا الـendpoint يستخدمه للتحقّق من حدود الحقل
# قبل الحفظ — يمنع CRS mismatch + self-intersection + إحداثيّات خارج اليمن.

from api.geospatial_integrity import validate_field_geometry  # noqa: E402


class GeometryValidateRequest(BaseModel):
    geojson: dict
    declared_crs: str | None = None


@app.post("/api/v1/fields/validate-geometry")
def validate_geometry(
    req: GeometryValidateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من صلاحيّة حدود حقل قبل الحفظ.

    يكشف: CRS غير 4326، تقاطع ذاتي، مساحة غير معقولة، إحداثيّات خارج اليمن،
    ترتيب lng/lat معكوس. يُرجع المساحة المحسوبة + الـbbox عند النجاح.
    """
    result = validate_field_geometry(req.geojson, declared_crs=req.declared_crs)

    issues = [
        {
            "severity": i.severity.value,
            "code": i.code,
            "message_ar": i.message_ar,
            "hint": i.hint,
        }
        for i in result.issues
    ]

    return {
        "valid": result.valid,
        "canonical_crs": result.canonical_crs,
        "computed_area_ha": result.computed_area_ha,
        "computed_bbox": result.computed_bbox,
        "issues": issues,
        "has_errors": result.has_errors,
        "has_warnings": result.has_warnings,
    }


# ═══════════════════════════════════════════════════════════════
# توصيل الوحدات pure-logic المتبقّية (جلسة "بناء الكل")
# كلّها مُختبَرة كـpure logic؛ هنا نوصّلها بـendpoints حقيقيّة.
# الوحدات التي تحتاج DB (command_store, event_bus, event_replay, sharing,
# data_lineage) تبقى غير موصَّلة حتّى توفّر PostgreSQL — لا نزيّف توصيلها.
# ═══════════════════════════════════════════════════════════════

# ─── ١. Prescriptions (variable-rate N) ──────────────────────────
from api.prescriptions import (  # noqa: E402
    PrescriptionGenerator,
    ZoneCharacteristics,
    ZoneClass,
    prescription_to_dict,
)

_rx_generator = PrescriptionGenerator()


class ZoneInput(BaseModel):
    zone_id: str
    zone_class: str  # "low" | "medium" | "high" | "problem"
    area_ha: float
    ndvi_mean: float | None = None
    soil_ph: float | None = None
    soil_ec: float | None = None
    soil_om: float | None = None
    soil_n_ppm: float | None = None
    soil_texture: str | None = None
    soil_depth_cm: int | None = None


class NitrogenRxRequest(BaseModel):
    field_id: str
    season_id: str
    crop: str
    zones: list[ZoneInput]


@app.post("/api/v1/fields/{field_id}/prescriptions/nitrogen")
def prescribe_nitrogen(
    field_id: str,
    req: NitrogenRxRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """توصية تسميد نيتروجيني متغيّر المعدّل (Variable-Rate N) حسب الزون."""
    try:
        zones = [
            ZoneCharacteristics(
                zone_id=z.zone_id,
                zone_class=ZoneClass(z.zone_class),
                area_ha=z.area_ha,
                ndvi_mean=z.ndvi_mean,
                soil_ph=z.soil_ph,
                soil_ec=z.soil_ec,
                soil_om=z.soil_om,
                soil_n_ppm=z.soil_n_ppm,
                soil_texture=z.soil_texture,
                soil_depth_cm=z.soil_depth_cm,
            )
            for z in req.zones
        ]
        rx = _rx_generator.generate_nitrogen(field_id, req.season_id, req.crop, zones)
        return prescription_to_dict(rx)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ─── ٢. Yield estimate ───────────────────────────────────────────
from api.yield_heuristics import (  # noqa: E402
    LifecycleFeatures,
    detect_anomalies,
    estimate_yield,
)


class YieldEstimateRequest(BaseModel):
    field_id: str
    crop: str
    days_in_growing: int = 0
    irrigation_count: int = 0
    moisture_stress_events: int = 0
    pest_alerts: int = 0
    fertilizer_applications: int = 0
    avg_ndvi_growing: float | None = None
    drought_streak_days: int = 0
    rain_events: int = 0


@app.post("/api/v1/fields/{field_id}/yield-estimate")
async def estimate_field_yield(
    field_id: str,
    req: YieldEstimateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقدير الإنتاج (heuristic — ليس AI) + كشف الشذوذ."""
    features = LifecycleFeatures(
        field_id=field_id,
        crop=req.crop,
        days_in_growing=req.days_in_growing,
        irrigation_count=req.irrigation_count,
        moisture_stress_events=req.moisture_stress_events,
        pest_alerts=req.pest_alerts,
        fertilizer_applications=req.fertilizer_applications,
        avg_ndvi_growing=req.avg_ndvi_growing,
        drought_streak_days=req.drought_streak_days,
        rain_events=req.rain_events,
    )
    est = estimate_yield(features)
    anomalies = detect_anomalies(features)
    result = {
        "field_id": est.field_id,
        "crop": est.crop,
        "estimated_yield_kg_ha": est.estimated_yield_kg_ha,
        "yield_score": est.yield_score,
        "confidence": est.confidence,
        "stress_level": est.stress_level.value,
        "rationale_ar": est.rationale_ar,
        "contributors": est.contributors,
        "warnings": est.warnings,
        "anomalies": [
            {
                "type": a.type,
                "severity": a.severity,
                "message_ar": a.message_ar,
                "action_ar": a.suggested_action_ar,
            }
            for a in anomalies
        ],
    }

    # Stage F (تغذية آمنة): نرفق الحالة القانونيّة الموحّدة (Canonical Field State)
    # كمرجعيّة/ثقة فقط — **لا نغيّر رقم التقدير إطلاقاً** (تغيير أرقام زراعيّة يحتاج
    # تحقّقاً ميدانيّاً). نمط التنفيذ != auto ⇒ requires_review (يحتاج تأكيد المهندس
    # قبل الاعتماد على التقدير). صدق + fail-safe: أيّ تعذّر في جلب الحالة لا يكسر
    # التقدير (نتابع بلا الحالة)؛ غياب الحالة ⇒ لا تُرفَق كتلة field_state.
    try:
        # الاستيراد ضمن try أيضاً: أيّ ImportError يُعامَل كتعذّر جلب الحالة (لا
        # يكسر التقدير) — تحقيقاً للـfail-safe المعلن (مراجعة Copilot).
        from api.field_state_projection import recompute_field_state

        async with tenant_connection(user) as conn:
            field_state = (await recompute_field_state(conn, field_id))["state"]
    except Exception:  # noqa: BLE001 — تعذّر جلب الحالة لا يكسر التقدير (تابع بلا الحالة)
        logging.exception("yield-estimate: field_state unavailable for %s", field_id)
        field_state = None

    if field_state is not None:
        _agronomic = field_state.get("agronomic") or {}
        _truths = _agronomic.get("operational_truths") or {}
        # نوع ثابت: operational_truths كائن دائماً (وإن فارغاً) لا null (مراجعة Copilot).
        result["field_state"] = {
            "validity": field_state.get("validity"),
            "execution_mode": field_state.get("execution_mode"),
            "confidence_level": field_state.get("confidence_level"),
            "agronomic": {"operational_truths": _truths},
        }
        result["requires_review"] = field_state.get("execution_mode") != "auto"

    return result


# ─── ٣. Confidence (NDVI) ────────────────────────────────────────
from api.confidence_engine import compute_ndvi_confidence  # noqa: E402


class NdviConfidenceRequest(BaseModel):
    ndvi_value: float
    observation_date: str  # ISO
    field_area_ha: float
    cloud_pct: float = 0
    cloud_shadow_pct: float = 0
    cirrus_pct: float = 0
    has_ground_truth: bool = False


def _parse_iso_utc(value: str) -> datetime:
    """يحلّل تاريخ ISO ويضمن أنّه واعٍ بالمنطقة (UTC افتراضاً).

    H8 FIX: `fromisoformat` لتاريخ بلا إزاحة يُنتج datetime ساذجاً، فطرحه من
    `datetime.now(timezone.utc)` يرمي TypeError (= 500). هنا نطبّع للمنطقة
    ونُرجع 422 للمدخل غير القابل للتحليل بدل 500.
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as err:
        raise HTTPException(status_code=422, detail=f"تاريخ ISO غير صالح: {value!r}") from err
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


@app.post("/api/v1/confidence/ndvi")
def ndvi_confidence(
    req: NdviConfidenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ثقة قراءة NDVI: cloud + temporal + coverage + source."""
    obs = _parse_iso_utc(req.observation_date)
    conf = compute_ndvi_confidence(
        ndvi_value=req.ndvi_value,
        observation_date=obs,
        field_area_ha=req.field_area_ha,
        cloud_pct=req.cloud_pct,
        cloud_shadow_pct=req.cloud_shadow_pct,
        cirrus_pct=req.cirrus_pct,
        has_ground_truth=req.has_ground_truth,
    )
    return conf.to_dict()


# ─── ٤. Confidence aggregation (recommendation-level) ────────────
from api.confidence_aggregation import (  # noqa: E402
    irrigation_confidence,
)


class IrrigationConfRequest(BaseModel):
    ndvi_confidence: float | None = None
    et0_confidence: float | None = None
    soil_moisture_confidence: float | None = None
    weather_forecast_confidence: float | None = None


@app.post("/api/v1/confidence/irrigation")
def irrigation_rec_confidence(
    req: IrrigationConfRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ثقة توصية ري مُجمَّعة — ET0 حرج (غيابه → unsafe)."""
    agg = irrigation_confidence(
        req.ndvi_confidence,
        req.et0_confidence,
        req.soil_moisture_confidence,
        req.weather_forecast_confidence,
    )
    return agg.to_dict()


# ─── ٥. Failure detection ────────────────────────────────────────
from api.failure_modes import (  # noqa: E402
    detect_sentinel_issues,
    detect_soil_issues,
    detect_weather_issues,
)


class FailureCheckRequest(BaseModel):
    cloud_pct: float | None = None
    days_since_observation: int | None = None
    weather_hours_since_update: int | None = None
    soil: dict | None = None


@app.post("/api/v1/failures/check")
def check_failures(
    req: FailureCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يفحص حالات الفشل المعروفة (سحب، طقس قديم، تربة)."""
    failures = []
    if req.cloud_pct is not None and req.days_since_observation is not None:
        f = detect_sentinel_issues(req.cloud_pct, req.days_since_observation)
        if f:
            failures.append(f.to_dict())
    if req.weather_hours_since_update is not None:
        f = detect_weather_issues(req.weather_hours_since_update)
        if f:
            failures.append(f.to_dict())
    if req.soil:
        for f in detect_soil_issues(req.soil):
            failures.append(f.to_dict())
    return {"failures": failures, "count": len(failures)}


# ─── ٦. Temporal arbitration ─────────────────────────────────────
from api.temporal_arbitration import (  # noqa: E402
    DataSource,
    Measurement,
    TemporalArbiter,
)


class MeasurementInput(BaseModel):
    source: str  # DataSource value
    timestamp: str  # ISO
    value: float | None = None


class TemporalCheckRequest(BaseModel):
    measurements: list[MeasurementInput]
    crop: str | None = None
    stage: str | None = None


@app.post("/api/v1/temporal/check")
def temporal_check(
    req: TemporalCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق أنّ القراءات متّسقة زمنياً (لا NDVI قديم مع ET0 حديث)."""
    arbiter = TemporalArbiter()
    measurements = [
        Measurement(
            source=DataSource(m.source),
            timestamp=_parse_iso_utc(m.timestamp),
            value=m.value,
        )
        for m in req.measurements
    ]
    result = arbiter.check_combination(measurements, crop=req.crop, stage=req.stage)
    return {
        "valid": result.valid,
        "age_span_days": result.age_span_days,
        "issues": [
            {"severity": i.severity, "code": i.code, "message_ar": i.message_ar}
            for i in result.issues
        ],
    }


# ─── ٧. Reports (operation CSV) ──────────────────────────────────
from fastapi.responses import PlainTextResponse  # noqa: E402

from api.reports import FieldReport, OperationReport, operation_to_csv  # noqa: E402


class ReportFieldInput(BaseModel):
    field_id: str
    field_name_ar: str
    farm_id: str = ""
    tenant_id: str = ""
    area_ha: float = 0
    crop: str = ""
    season_label: str = ""
    planting_date: str | None = None
    harvest_date: str | None = None
    lifecycle_stage: str = "CREATED"
    irrigation_events: int = 0
    total_water_m3: float = 0
    fertilizer_events: int = 0
    total_nitrogen_kg: float = 0
    avg_ndvi: float | None = None
    estimated_yield_kg_ha: float | None = None


class OperationReportRequest(BaseModel):
    tenant_id: str
    operation_name_ar: str
    period_start: str
    period_end: str
    fields: list[ReportFieldInput]
    lang: str = "ar"


@app.post("/api/v1/reports/operation", response_class=PlainTextResponse)
def operation_report_csv(
    req: OperationReportRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقرير المزرعة كاملة كـCSV (ثنائي اللغة + BOM للإكسل)."""
    fields = [
        FieldReport(
            field_id=f.field_id,
            field_name_ar=f.field_name_ar,
            farm_id=f.farm_id,
            tenant_id=f.tenant_id,
            area_ha=f.area_ha,
            crop=f.crop,
            season_label=f.season_label,
            planting_date=f.planting_date,
            harvest_date=f.harvest_date,
            lifecycle_stage=f.lifecycle_stage,
            irrigation_events=f.irrigation_events,
            total_water_m3=f.total_water_m3,
            fertilizer_events=f.fertilizer_events,
            total_nitrogen_kg=f.total_nitrogen_kg,
            avg_ndvi=f.avg_ndvi,
            estimated_yield_kg_ha=f.estimated_yield_kg_ha,
        )
        for f in req.fields
    ]
    report = OperationReport(
        tenant_id=req.tenant_id,
        operation_name_ar=req.operation_name_ar,
        fields=fields,
        period_start=req.period_start,
        period_end=req.period_end,
        generated_at=datetime.utcnow().isoformat(),
    )
    return operation_to_csv(report, lang=req.lang)


# ─── ٨. Field lifecycle transition validation (pure) ─────────────
from api.field_lifecycle import LifecycleStage, is_valid_transition  # noqa: E402


class TransitionCheckRequest(BaseModel):
    from_stage: str
    to_stage: str


@app.post("/api/v1/lifecycle/validate-transition")
def validate_transition(
    req: TransitionCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق هل انتقال مرحلة الحقل صالح (CREATED→PREPARED→...→HARVESTED)."""
    try:
        from_s = LifecycleStage(req.from_stage)
        to_s = LifecycleStage(req.to_stage)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مرحلة غير معروفة: {e}") from e
    valid = is_valid_transition(from_s, to_s)
    return {
        "from_stage": from_s.value,
        "to_stage": to_s.value,
        "valid": valid,
        "reason_ar": "انتقال صالح"
        if valid
        else f"لا يُسمح بالانتقال من {from_s.value} إلى {to_s.value}",
    }


# ─── ٩. Event replay — state reconstruction (pure) ───────────────
from api.event_replay import FieldStateReconstructor  # noqa: E402


class ReplayRequest(BaseModel):
    entity_type: str
    entity_id: str
    events: list[dict]  # [{event_type, occurred_at, payload}, ...]


@app.post("/api/v1/replay/reconstruct")
def replay_reconstruct(
    req: ReplayRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُعيد بناء حالة الـentity من سجلّ الأحداث (pure reconstruction).

    ملاحظة: يأخذ الأحداث في الـrequest. النسخة المُوصَّلة بالـDB (تجلب
    الأحداث من events table) تحتاج PostgreSQL — غير مُفعَّلة بعد.
    """
    state = FieldStateReconstructor.reconstruct(
        req.entity_type,
        req.entity_id,
        req.events,
    )
    return {
        "entity_id": state.entity_id,
        "entity_type": state.entity_type,
        "field_name": state.field_name,
        "lifecycle_stage": state.lifecycle_stage,
        "area_ha": state.area_ha,
        "crop": state.crop,
        "planting_date": state.planting_date,
        "harvest_date": state.harvest_date,
        "irrigation_count": state.irrigation_count,
        "fertilizer_count": state.fertilizer_count,
        "last_ndvi": state.last_ndvi,
        "total_events": state.total_events,
        "last_event_at": state.last_event_at,
    }


# ─── ١٠. Field Timeline (المرحلة ١، البند ٧) ─────────────────────
# خطّ زمني موحّد لكلّ ما حدث على الحقل. pure assembler (يأخذ الأحداث).
# النسخة المُوصَّلة بالـDB (تجلب من events table) تحتاج PostgreSQL.
from api.field_timeline import assemble_timeline  # noqa: E402


class TimelineRequest(BaseModel):
    field_id: str
    events: list[dict]
    newest_first: bool = True
    category_filter: list[str] | None = None


@app.post("/api/v1/fields/{field_id}/timeline")
def field_timeline(
    field_id: str,
    req: TimelineRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يبني الخطّ الزمني للحقل (مُصنّف + مرتّب + بإحصاءات الفئات).

    ملاحظة: يأخذ الأحداث في الـrequest. النسخة التي تجلب من events table
    تحتاج PostgreSQL — غير مُفعَّلة بعد.
    """
    tl = assemble_timeline(
        field_id,
        req.events,
        newest_first=req.newest_first,
        category_filter=req.category_filter,
    )
    return tl.to_dict()


# ─── السياق التاريخي للحقل (farm memory) — يغذّي Runtime Cohesion ──
# يجلب أحداث الحقل من events table (RLS مُطبَّق) ويستنتج القضايا المتكرّرة.
# يستهلكه memory_adapter في حلقة القرار (run_field_intelligence).
def _issue_tags_from_event(event_type: str, payload: dict) -> list[str]:
    """يستنتج وسوم القضايا من نوع الحدث/الحمولة (للكشف عن التكرار).

    صدق: استنتاج صريح من البيانات الموجودة، لا تخمين. القضايا الزراعيّة
    المتكرّرة (ملوحة/إجهاد مائي/آفة/تدهور) تُغني القرار بالسياق التاريخي.
    """
    tags: list[str] = []
    et = (event_type or "").lower()
    p = payload or {}
    # من نوع الحدث
    if "salin" in et or p.get("salinity_class") in ("critical", "moderate"):
        tags.append("ملوحة")
    if "water_stress" in et or "drought" in et or p.get("water_stress"):
        tags.append("إجهاد مائي")
    if "pest" in et or "disease" in et or p.get("pest_detected"):
        tags.append("آفة")
    if "degrad" in et or (p.get("degraded_pct") or 0) >= 10:
        tags.append("تدهور")
    if "heat" in et or p.get("heat_risk", 0) and p.get("heat_risk", 0) >= 0.7:
        tags.append("إجهاد حراري")
    return tags


@app.get("/api/v1/fields/{field_id}/history")
async def field_history(
    field_id: str,
    limit: int = 200,
    user: UserSchema = Depends(get_current_user),
):
    """السياق التاريخي للحقل: أحداثه + القضايا المتكرّرة (farm memory).

    يجلب من events table عبر tenant_connection (RLS — كلّ مستأجر أحداثه فقط).
    يُغذّي memory_adapter في حلقة القرار (Runtime Cohesion). صدق: عند تعطّل
    القاعدة يُرجِع events فارغة (لا تاريخ مخترَع) ويُعلن السبب.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }
    out_events: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, occurred_at
                FROM events
                WHERE entity_type = 'field' AND entity_id = $1
                ORDER BY occurred_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(limit, 1000)),  # قصّ [1..1000]: limit≤0 يرمي/يُفرغ بلا داعٍ
            )
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else {}
            out_events.append(
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                    "issue_tags": _issue_tags_from_event(r["event_type"], payload),
                }
            )
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع تاريخاً
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "error": f"تعذّر جلب التاريخ: {e}",
        }
    return {"field_id": field_id, "events": out_events, "total_events": len(out_events)}


# ─── محاكاة what-if — تغذّي Runtime Cohesion (simulate_adapter) ────
# يشغّل WOFOST مرّتين (baseline مقابل سيناريو) ويقارن المحصول/الماء.
# يستهلكه simulate_adapter في حلقة القرار. محاكاة علميّة حقيقيّة (لا أرقام
# مخترَعة): تعتمد طقساً حيّاً من Open-Meteo داخل simulate_wofost.
class WhatIfRequest(BaseModel):
    field_id: str
    crop: str = "قمح صلب"
    lat: float | None = None
    lon: float | None = None
    soil_type: str = "loam"
    planting_date: str | None = None  # ISO؛ افتراض بداية الموسم
    scenario: str = "reduce_irrigation"  # reduce_irrigation | no_irrigation


@app.post("/api/v1/simulate/what-if")
async def simulate_what_if(
    req: WhatIfRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحاكي أثر سيناريو (مثلاً تقليل/إيقاف الريّ) على المحصول والماء.

    Runtime Cohesion: يغذّي حلقة القرار بأثر متوقّع للإجراء المقترَح. يشغّل
    WOFOST مرّتين (baseline مرويّ مقابل السيناريو) ويقارن. صدق: عند تعذّر
    النموذج/الطقس يُعلَن (لا أرقام مخترَعة). lat/lon إلزاميّان للطقس الحيّ.
    """
    if req.lat is None or req.lon is None:
        return {
            "field_id": req.field_id,
            "available": False,
            "note_ar": "lat/lon مطلوبان للطقس الحيّ — لا محاكاة بلا موقع",
        }
    # استيراد آمن لمحرّك WOFOST (وحدة جذريّة — قد لا تكون على المسار)
    try:
        import importlib.util as _ilu
        import os as _os

        _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
        _eng_path = _os.path.join(_root, "wofost_real", "wofost_engine.py")
        if not _os.path.exists(_eng_path):
            return {
                "field_id": req.field_id,
                "available": False,
                "note_ar": "محرّك WOFOST غير متاح على هذا المسار",
            }
        _spec = _ilu.spec_from_file_location("wofost_engine", _eng_path)
        _eng = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_eng)
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن التعذّر
        return {
            "field_id": req.field_id,
            "available": False,
            "error": f"تعذّر تحميل محرّك المحاكاة: {e}",
        }

    from datetime import date as _date

    try:
        pd = _date.fromisoformat(req.planting_date) if req.planting_date else _date.today()
    except ValueError:
        pd = _date.today()

    async def _run(irrigation: bool):
        return await _eng.simulate_wofost(
            req.field_id,
            req.crop,
            req.soil_type,
            req.lat,
            req.lon,
            pd,
            irrigation=irrigation,
        )

    try:
        baseline = await _run(irrigation=True)  # مرويّ كاملاً (الأساس)
        scenario = await _run(irrigation=False)  # السيناريو (بلا/تقليل ريّ)
    except Exception as e:  # noqa: BLE001 — صدق: الطقس/النموذج تعذّر
        return {
            "field_id": req.field_id,
            "available": False,
            "error": f"تعذّرت المحاكاة (طقس/نموذج): {e}",
        }

    # b_yield = محصول الإجراء المقترَح (الريّ الموصى به)؛ s_yield = بلا إجراء (بلا ريّ)
    b_yield = baseline.get("simulation", {}).get("yield_t_ha")
    s_yield = scenario.get("simulation", {}).get("yield_t_ha")
    b_irr = baseline.get("water_balance", {}).get("irrigation_needed_mm")
    s_irr = scenario.get("water_balance", {}).get("irrigation_needed_mm")
    water_saved = round(b_irr - s_irr, 1) if (b_irr is not None and s_irr is not None) else None
    # هل "الإجراء المقترَح" (الريّ) يُجدي؟ مُجدٍ إن رفع المحصول >2% فوق خطّ الأساس
    # (لا إجراء). خطّ الأساس = s_yield، الإجراء = b_yield ⇒ المقارنة ذات معنى.
    helps = None
    if b_yield is not None and s_yield is not None:
        helps = b_yield > s_yield * 1.02  # الريّ الموصى به يرفع المحصول >2%

    return {
        "field_id": req.field_id,
        "available": True,
        "scenario": req.scenario,
        # خطّ الأساس = لا إجراء (بلا ريّ)؛ الإجراء = الريّ الموصى به (قيمتان متمايزتان
        # حتّى تكون recommended_action_helps مقارنةً فعليّةً لا قيمةً بنفسها).
        "baseline_yield_t_ha": s_yield,  # لا إجراء (السيناريو بلا ريّ) — خطّ الأساس
        "action_yield_t_ha": b_yield,  # الإجراء المقترَح (الريّ الموصى به)
        "no_action_yield_t_ha": s_yield,  # مرادف صريح لخطّ الأساس (توافق خلفي)
        "water_saved_mm": water_saved,
        "recommended_action_helps": helps,
    }


# ─── ١١. Scouting Pins (المرحلة ١، البند ٨) ──────────────────────
# مشاهدات ميدانيّة: GPS + صورة + taxonomy يمنيّة + شدّة + حالة + موسمي/دائم.
# التحقّق والـtaxonomy هنا (pure)؛ الحفظ في الموبايل SQLite + mediaStore + syncEngine.
from api.scouting_pins import (  # noqa: E402
    NUTRIENT_DEFICIENCY_GUIDE,
    YEMEN_CROP_ISSUES,
    get_crop_issues,
    make_pin,
)


class PinCreateRequest(BaseModel):
    pin_id: str
    field_id: str
    lat: float
    lng: float
    issue_category: str
    severity: str = "medium"
    status: str = "new"
    persistence: str = "seasonal"
    crop: str | None = None
    issue_code: str | None = None
    note_ar: str | None = None
    photo_uri: str | None = None
    color: str | None = None
    created_by: str | None = None


@app.post("/api/v1/fields/{field_id}/pins")
def create_pin(
    field_id: str,
    req: PinCreateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من مشاهدة ميدانيّة ويُرجعها مُطبَّعة (الحفظ على الموبايل)."""
    try:
        pin = make_pin(
            req.pin_id,
            field_id,
            req.lat,
            req.lng,
            req.issue_category,
            req.severity,
            req.status,
            req.persistence,
            crop=req.crop,
            issue_code=req.issue_code,
            note_ar=req.note_ar,
            photo_uri=req.photo_uri,
            color=req.color,
            created_by=req.created_by or user.user_id,
        )
        return pin.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/api/v1/scouting/taxonomy")
def scouting_taxonomy(
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """قوائم المشاكل (للقوائم المنسدلة). لو crop معطى، يُرجع مشاكله فقط."""
    if crop:
        return {"crop": crop, "issues": get_crop_issues(crop)}
    return {
        "crops": list(YEMEN_CROP_ISSUES.keys()),
        "all_issues": YEMEN_CROP_ISSUES,
        "nutrient_guide": NUTRIENT_DEFICIENCY_GUIDE,
    }


# ─── ١٢. Manual Application Mode (المرحلة ١، البند ٩) ────────────
# يحوّل وصفة kg/ha إلى خطة مشي قابلة للتنفيذ (كغ/مصطبة، أغطية/خزّان،
# سقايات/شجرة) + PDF عربي للطباعة. يبني على prescriptions.py.
from fastapi.responses import Response  # noqa: E402

from api.manual_converter import ApplicationMethod, EquipmentSpec  # noqa: E402
from api.walk_plan import ZoneRateInput, generate_walk_plan  # noqa: E402
from api.walk_plan_pdf import walk_plan_to_pdf_bytes  # noqa: E402


class EquipmentInput(BaseModel):
    terrace_area_m2: float | None = None
    cap_weight_kg: float | None = None
    tank_capacity_l: float | None = None
    tree_spacing_m2: float | None = None
    can_capacity_l: float | None = None
    concentration_kg_l: float | None = None


class ZoneRateInputModel(BaseModel):
    zone_id: str
    rate_kg_ha: float
    area_ha: float
    zone_class: str = "medium"


class WalkPlanRequest(BaseModel):
    field_id: str
    crop: str
    method: str  # broadcast_terrace | backpack_spray | per_tree
    zones: list[ZoneRateInputModel]
    equipment: EquipmentInput
    product_name_ar: str = "السماد"
    minutes_per_ha: float = 60.0


def _build_walk_plan(req: WalkPlanRequest):
    try:
        method = ApplicationMethod(req.method)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"طريقة غير معروفة: {req.method}") from None
    equip = EquipmentSpec(
        terrace_area_m2=req.equipment.terrace_area_m2,
        cap_weight_kg=req.equipment.cap_weight_kg,
        tank_capacity_l=req.equipment.tank_capacity_l,
        tree_spacing_m2=req.equipment.tree_spacing_m2,
        can_capacity_l=req.equipment.can_capacity_l,
        concentration_kg_l=req.equipment.concentration_kg_l,
    )
    zones = [ZoneRateInput(z.zone_id, z.rate_kg_ha, z.area_ha, z.zone_class) for z in req.zones]
    try:
        return generate_walk_plan(
            req.field_id,
            req.crop,
            zones,
            method,
            equip,
            product_name_ar=req.product_name_ar,
            minutes_per_ha=req.minutes_per_ha,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/api/v1/fields/{field_id}/walk-plan")
def field_walk_plan(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحوّل وصفة الحقل إلى خطة مشي يدويّة قابلة للتنفيذ."""
    return _build_walk_plan(req).to_dict()


@app.post("/api/v1/fields/{field_id}/walk-plan/pdf")
def field_walk_plan_pdf(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """نفس خطة المشي لكن كـPDF عربي للطباعة وأخذها للحقل."""
    plan = _build_walk_plan(req)
    try:
        pdf_bytes = walk_plan_to_pdf_bytes(plan.to_dict())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="walk_plan_{field_id}.pdf"'},
    )


# ─── ١٣. Sharing key generation (سدّ فجوة جزئي) ──────────────────
# توليد مفتاح مشاركة (نموذج "المهندس الزراعي الموثوق" من FieldView).
# التوليد والـhashing pure؛ الحفظ/التحقّق في DB يحتاج PostgreSQL pool
# (يبقى غير موصَّل بصدق — SharingKeyService.create_key/validate_key).
import uuid as _uuid  # noqa: E402

from api.sharing import (  # noqa: E402
    SharingScope,
    ThirdPartyType,
    generate_key_plaintext,
    hash_key,
)


class ShareKeyRequest(BaseModel):
    scope: str = "read"  # read | read_write
    third_party_name: str | None = None
    third_party_type: str | None = None  # advisor | dealer | ministry | researcher | other
    allowed_field_ids: list[str] = []
    expires_in_days: int = 30


@app.post("/api/v1/sharing/generate-key")
def generate_share_key(
    req: ShareKeyRequest,
    user: UserSchema = Depends(require_permission(Permission.USER_INVITE)),
):
    """يولّد مفتاح مشاركة (يُعرَض الـplaintext مرّة واحدة فقط).

    ملاحظة: الحفظ في DB يحتاج PostgreSQL (غير موصَّل). هذا يولّد المفتاح
    والـhash والبيانات الوصفيّة — جاهزة للحفظ لاحقاً.
    """
    try:
        scope = SharingScope(req.scope)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"نطاق غير صالح: {req.scope}") from None
    tp_type = None
    if req.third_party_type:
        try:
            tp_type = ThirdPartyType(req.third_party_type)
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"نوع طرف غير صالح: {req.third_party_type}"
            ) from None

    plaintext = generate_key_plaintext()
    now = datetime.now(UTC)
    return {
        "key_id": str(_uuid.uuid4()),
        "key_plaintext": plaintext,  # يُعرَض مرّة واحدة
        "key_hash": hash_key(plaintext),  # للحفظ في DB
        "key_prefix": plaintext[:12],
        "scope": scope.value,
        "third_party_name": req.third_party_name,
        "third_party_type": tp_type.value if tp_type else None,
        "allowed_field_ids": req.allowed_field_ids,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=req.expires_in_days)).isoformat(),
        "note_ar": "احفظ هذا المفتاح الآن — لن يُعرَض مرّة أخرى. الحفظ في قاعدة البيانات يحتاج تفعيل الخادم.",
    }


# ─── ١٤. الوحدات المعتمدة على PostgreSQL (سدّ الفجوة ١) ──────────
# توصيل command_store / event_bus / data_lineage / sharing (الحفظ).
# ⚠ هذه الـendpoints تحتاج DATABASE_URL مضبوطاً (pool حقيقي). كُتِبت ووُصِّلت
# لكنّها غير مُختبَرة ضدّ DB حيّ في هذه البيئة (لا PostgreSQL). تُختبَر عبر
# tests_v9/test_db_integration.py بعد bootstrap_postgres.sh.
from api.command_store import CommandStore  # noqa: E402
from api.data_lineage import LineageAssembler  # noqa: E402
from api.event_bus import EventBus  # noqa: E402
from api.sharing import SharingKeyService  # noqa: E402
from api.sharing import SharingScope as _SScope  # noqa: E402
from api.sharing import ThirdPartyType as _TPType  # noqa: E402


@app.get("/api/v1/lineage/{entity_type}/{entity_id}")
async def entity_lineage(
    entity_type: str,
    entity_id: str,
    limit: int = 500,
    user: UserSchema = Depends(get_current_user),
):
    """يجمع lineage كامل للـentity (command+event+lifecycle+journal+trueup).

    عبر tenant_connection — RLS مُطبَّق (لا تسريب عبر المستأجرين)."""
    async with tenant_connection(user) as conn:
        assembler = LineageAssembler(get_pool(), conn=conn)
        result = await assembler.get_entity_lineage(entity_type, entity_id, limit=limit)
    return {
        "entity_type": result.entity_type,
        "entity_id": result.entity_id,
        "total_entries": result.total_entries,
        "earliest_at": result.earliest_at,
        "latest_at": result.latest_at,
        "commands_count": result.commands_count,
        "events_count": result.events_count,
        "entries": [
            {
                "timestamp": e.timestamp,
                "source_type": e.source_type.value,
                "source_id": e.source_id,
                "action": e.action,
                "summary_ar": e.summary_ar,
            }
            for e in result.entries
        ],
    }


@app.get("/api/v1/events/{entity_type}/{entity_id}")
async def entity_events(
    entity_type: str,
    entity_id: str,
    limit: int = 100,
    user: UserSchema = Depends(get_current_user),
):
    """تاريخ أحداث entity من event_bus (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        bus = EventBus(get_pool(), conn=conn)
        return {"events": await bus.query_entity_history(entity_type, entity_id, limit=limit)}


@app.get("/api/v1/commands/{command_id}")
async def get_command(
    command_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """يجلب أمراً من command_store (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        store = CommandStore(get_pool(), conn=conn)
        cmd = await store.get(command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="الأمر غير موجود")
    return {"command_id": command_id, "found": True}


class SharingKeyCreateRequest(BaseModel):
    scope: str = "read"
    valid_days: int = 30
    third_party_name: str | None = None
    third_party_type: str | None = None
    allowed_field_ids: list[str] = []


@app.post("/api/v1/sharing/keys")
async def create_sharing_key(
    req: SharingKeyCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.USER_INVITE)),
):
    """ينشئ ويحفظ مفتاح مشاركة (عبر tenant_connection — RLS مُطبَّق)."""
    try:
        scope = _SScope(req.scope)
        tp = _TPType(req.third_party_type) if req.third_party_type else None
        async with tenant_connection(user) as conn:
            svc = SharingKeyService(get_pool(), conn=conn)
            key = await svc.create_key(
                tenant_id=getattr(user, "tenant_id", "default"),
                created_by=user.user_id,
                scope=scope,
                valid_days=req.valid_days,
                third_party_name=req.third_party_name,
                third_party_type=tp,
                allowed_field_ids=req.allowed_field_ids,
            )
        return {
            "key_id": key.key_id,
            "key_plaintext": key.key_plaintext,  # مرّة واحدة
            "key_prefix": key.key_prefix,
            "scope": key.scope.value,
            "expires_at": key.expires_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/api/v1/sharing/keys")
async def list_sharing_keys(
    include_revoked: bool = False,
    user: UserSchema = Depends(get_current_user),
):
    """يسرد مفاتيح المشاركة للمستأجر (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        svc = SharingKeyService(get_pool(), conn=conn)
        keys = await svc.list_keys(
            getattr(user, "tenant_id", "default"), include_revoked=include_revoked
        )
    return {"keys": keys}


# ─── ١٥. محرّك التجارب t-test/LSD (المرحلة ٢، البند ١١) ──────────
# الميزة الرئيسيّة لـ"الصدق الإحصائي": يُجيب هل الفرق مؤكّد أم تباين طبيعي.
from api.trial_engine import BlockResult, analyze_paired_trial  # noqa: E402


class TrialBlockInput(BaseModel):
    block_number: int
    treatment_yield: float
    control_yield: float


class TrialAnalysisRequest(BaseModel):
    blocks: list[TrialBlockInput]
    confidence_level: float = 0.95
    treatment_label_ar: str = "المعالجة الجديدة"


@app.post("/api/v1/trials/analyze")
def analyze_trial(
    req: TrialAnalysisRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُحلّل تجربة مقترنة (t-test مزدوج + LSD) ويُعطي حُكماً صادقاً."""
    blocks = [BlockResult(b.block_number, b.treatment_yield, b.control_yield) for b in req.blocks]
    try:
        verdict = analyze_paired_trial(
            blocks,
            confidence_level=req.confidence_level,
            treatment_label_ar=req.treatment_label_ar,
        )
        return verdict.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ─── ١٦. ميزان الماء ET0 (المرحلة ٢، البند ١٢) ──────────────────
# توصية ريّ FAO-56 (Penman-Monteith / Hargreaves) — أزمة مياه اليمن.
from api.water_balance import WeatherInput, water_balance  # noqa: E402


class WaterBalanceRequest(BaseModel):
    crop: str
    stage: str = "mid"  # initial|development|mid|late
    t_min_c: float
    t_max_c: float
    rain_mm: float = 0.0
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100


@app.post("/api/v1/water-balance")
def compute_water_balance(
    req: WaterBalanceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحسب توصية الريّ (ET0 → ETc → احتياج صافٍ بعد المطر)."""
    w = WeatherInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        solar_rad_mj_m2=req.solar_rad_mj_m2,
        rh_mean_pct=req.rh_mean_pct,
        wind_2m_ms=req.wind_2m_ms,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    return water_balance(w, req.crop, req.stage, rain_mm=req.rain_mm).to_dict()


# ─── ١٧. قواعد 4R للتربة الكلسيّة (المرحلة ٢، البند ١٣) ──────────
# توصية تسميد محجوبة حتى توفّر تحليل مختبر (الاستشعار يوجّه/المختبر يحكم).
from api.nutrient_4r import SoilContext, full_4r_plan  # noqa: E402


class Soil4RRequest(BaseModel):
    caco3_pct: float | None = None
    ph: float | None = None
    p_ppm: float | None = None
    fe_ppm: float | None = None
    zn_ppm: float | None = None
    om_pct: float | None = None
    nutrients: list[str] | None = None


@app.post("/api/v1/nutrients/4r-plan")
def nutrient_4r_plan(
    req: Soil4RRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """خطة تسميد 4R للتربة الكلسيّة (تحجب ما يحتاج تحليلاً)."""
    soil = SoilContext(
        caco3_pct=req.caco3_pct,
        ph=req.ph,
        p_ppm=req.p_ppm,
        fe_ppm=req.fe_ppm,
        zn_ppm=req.zn_ppm,
        om_pct=req.om_pct,
    )
    return {"plan": full_4r_plan(soil, req.nutrients)}


# ─── ١٨. مناطق NDVI k-means (المرحلة ٣، البند ١٤) ───────────────
# اقتراح مناطق إدارة من NDVI (بديل منخفض التكلفة) — للفحص لا للقرار الآلي.
from api.zones_kmeans import ZoneCell, delineate_zones  # noqa: E402


class ZoneCellInput(BaseModel):
    cell_id: str
    value: float
    confidence: float = 1.0


class ZoningRequest(BaseModel):
    cells: list[ZoneCellInput]
    n_zones: int = 3


@app.post("/api/v1/fields/{field_id}/zones")
def field_zones(
    field_id: str,
    req: ZoningRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقترح مناطق إدارة من قيم NDVI عبر k-means."""
    cells = [ZoneCell(c.cell_id, c.value, c.confidence) for c in req.cells]
    try:
        return delineate_zones(cells, n_zones=req.n_zones).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ─── ١٩. تتبّع GDD (المرحلة ٣، البند ١٥) ────────────────────────
# النموّ بالحرارة المتراكمة لا بالأيّام — توقيت أدقّ للريّ/التسميد/الحصاد.
from api.gdd_tracker import DailyTemp, track_gdd  # noqa: E402


class DailyTempInput(BaseModel):
    t_min_c: float
    t_max_c: float


class GDDRequest(BaseModel):
    crop: str
    temps: list[DailyTempInput]


@app.post("/api/v1/gdd/track")
def gdd_track(
    req: GDDRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتراكم GDD ويحدّد مرحلة المحصول الحاليّة + المتبقّي للتالية."""
    temps = [DailyTemp(t.t_min_c, t.t_max_c) for t in req.temps]
    try:
        return track_gdd(req.crop, temps).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ─── ٢٠. تشخيص بقواعد الأعراض (المرحلة ٣، البند ١٦) ─────────────
# شجرة قواعد شفّافة (لا ML) — تربط الأعراض بمرشّحين + توصية تأكيد بشري.
from api.disease_diagnosis import diagnose, list_symptoms  # noqa: E402


class DiagnoseRequest(BaseModel):
    crop: str
    symptoms: list[str]
    # تغذية آمنة اختياريّة: عند تمرير field_id نُرفِق سياق الحالة القانونيّة
    # الموحّدة بالاستجابة. غيابه (None) ⇒ السلوك الحاليّ تماماً (لا إرفاق).
    field_id: str | None = None


@app.post("/api/v1/diagnose")
async def diagnose_symptoms(
    req: DiagnoseRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تشخيص أوّلي بقواعد الأعراض (لا قاطع — يوصي بتأكيد بشري/مختبر).

    تغذية آمنة (Stage F): عند تمرير field_id نُرفِق كتلة field_state من الحالة
    القانونيّة الموحّدة (validity/execution_mode/operational_truths) وملاحظة
    مرجعيّة عند ملوحة تربة حرجة — دون تغيير قواعد التشخيص أو أرقامه. fail-safe:
    تعذّر الحالة أو غياب field_id ⇒ يُعاد التشخيص الأصليّ بلا إرفاق.
    """
    result = diagnose(req.crop, req.symptoms).to_dict()

    if req.field_id:
        try:
            from api.field_state_projection import recompute_field_state

            async with tenant_connection(user) as conn:
                # تأكّد أنّ الحقل ضمن المستأجِر قبل الإرفاق — وإلّا 404 يلتقطه except
                # أدناه فلا نُرفِق حالة «حقل شبح» (مراجعة Copilot).
                await _assert_field_in_tenant(conn, req.field_id)
                field_state = (await recompute_field_state(conn, req.field_id))["state"]
            # نُرفِق مقتطفاً من الحالة الموحّدة (لا نغيّر التشخيص).
            _agro = field_state.get("agronomic") or {}
            _truths = _agro.get("operational_truths") or {}
            result["field_state"] = {
                "validity": field_state.get("validity"),
                "execution_mode": field_state.get("execution_mode"),
                "agronomic": {"operational_truths": _truths},
            }
            # ملاحظة مرجعيّة فقط عند ملوحة حرجة — إجهاد الملوحة قد يحاكي/يفاقم
            # أعراض الأمراض. لا تغيير لقواعد/نتيجة التشخيص.
            if _truths.get("salinity_class") == "critical":
                result.setdefault("advisory_notes_ar", []).append(
                    "إجهاد الملوحة قد يحاكي/يفاقم أعراض الأمراض — راجِع حالة التربة."
                )
        except Exception:  # noqa: BLE001 — تغذية best-effort، لا تكسر التشخيص
            logger.warning(
                "diagnose: تعذّر إرفاق الحالة الموحّدة للحقل %s — يُعاد التشخيص بلا حالة",
                req.field_id,
                exc_info=True,
            )

    return result


@app.get("/api/v1/diagnose/symptoms")
def diagnosis_symptom_catalog():
    """قائمة الأعراض المتاحة للاختيار في الموبايل."""
    return {"symptoms": list_symptoms()}


# ─── ٢١. بوابة الثقة الموحّدة (مُستلهَمة من DSS، مُكيّفة بصدق) ────
# تجمع إشارات المحرّكات وتقرّر: واثقة/مراجعة/محجوبة. لا ML غامض.
from api.confidence_gate import EngineSignal  # noqa: E402
from api.confidence_gate import evaluate as _gate_eval  # noqa: E402


class EngineSignalInput(BaseModel):
    engine: str
    has_recommendation: bool
    confidence: float
    blocking_reason_ar: str | None = None
    data_gaps_ar: list[str] = []


class ConfidenceGateRequest(BaseModel):
    signals: list[EngineSignalInput]


@app.post("/api/v1/confidence-gate")
def confidence_gate(
    req: ConfidenceGateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم إشارات المحرّكات ويقرّر مستوى الثقة (واثقة/مراجعة/محجوبة)."""
    signals = [
        EngineSignal(
            engine=s.engine,
            has_recommendation=s.has_recommendation,
            confidence=s.confidence,
            blocking_reason_ar=s.blocking_reason_ar,
            data_gaps_ar=s.data_gaps_ar,
        )
        for s in req.signals
    ]
    return _gate_eval(signals).to_dict()


class EscalationAssessRequest(BaseModel):
    """تقييم تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG)."""

    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = Field(min_length=1, max_length=60)
    has_answer: bool = True
    uncertain_points: list[str] = Field(default_factory=list)


@app.post("/api/v1/escalation/assess")
def escalation_assess(
    req: EscalationAssessRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقرّر تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG) — actionable (مستلِم/أولويّة/مجهول).

    يعمّم مبدأ confidence_gate لأيّ مصدر ثقة (لا المحرّكات فقط): بلا سند/ثقة كافية →
    تصعيد لمرشد زراعي لا إجابة مولّدة (human-in-the-loop). confidence=None أو
    has_answer=false ⇒ BLOCKED (لا تأليف). للمحرّكات استعمل /confidence-gate ثمّ
    escalation_from_gate.
    """
    from core.engines.human_escalation import assess_escalation

    return assess_escalation(
        req.confidence,
        source=req.source,
        has_answer=req.has_answer,
        uncertain_points=req.uncertain_points,
    )


class ExternalPriorBlendRequest(BaseModel):
    """مزج سابقة خارجيّة منشورة (مشروع/ورقة) ببيانات اليمن المتراكمة — وزن تدرّجي."""

    external_prior: float | None = None
    local_estimate: float | None = None
    n_local: int = Field(default=0, ge=0)
    crop_grown_in_yemen: bool
    external_credibility: float = Field(default=0.5, ge=0, le=1)


@app.post("/api/v1/learning/external-prior-blend")
def external_prior_blend(
    req: ExternalPriorBlendRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يمزج سابقة خارجيّة منشورة ببيانات اليمن بوزن تدرّجي n/(n+K) — تظافر قرائن صادق.

    للاستفادة من مشاريع/أوراق خارجيّة (مثل CropSight-US) لمحاصيل تُزرَع في اليمن:
    السابقة الخارجيّة قرينة ضعيفة متلاشية (ثقة ≤50%، غير متحقّقة محلّيّاً)، تتلاشى
    كلّما تراكم محلّي. محصول غير مزروع في اليمن ⇒ غير منطبق (لا استيراد قيمة أجنبيّة).
    دون الحجم المطلوب: تلميح يُصعَّد لمرشد عبر human_escalation.
    """
    from core.engines.external_prior_blend import blend_external_prior

    return blend_external_prior(
        req.external_prior,
        req.local_estimate,
        req.n_local,
        crop_grown_in_yemen=req.crop_grown_in_yemen,
        external_credibility=req.external_credibility,
    )


# ─── ٢٢. اكتمال البيانات + ملاءمة المحاصيل (مُستلهَم من المستندَين) ─
from api.crop_suitability import FieldConditions, rank_crops  # noqa: E402
from api.data_readiness import assess_readiness  # noqa: E402


class ReadinessRequest(BaseModel):
    provided_fields: list[str]


@app.post("/api/v1/data-readiness")
def data_readiness(
    req: ReadinessRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم اكتمال البيانات: ما المتاح الآن، ما المحجوب، وما التالي الأعلى أثراً."""
    return assess_readiness(req.provided_fields).to_dict()


class CropSuitabilityRequest(BaseModel):
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True
    crops: list[str] | None = None


@app.post("/api/v1/crop-suitability")
def crop_suitability(
    req: CropSuitabilityRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يرتّب المحاصيل بمعايير مرجّحة شفّافة (يحجب دون بيانات تربة حاكمة)."""
    cond = FieldConditions(
        ph=req.ph,
        ec_dsm=req.ec_dsm,
        season_rain_mm=req.season_rain_mm,
        temp_mean_c=req.temp_mean_c,
        irrigated=req.irrigated,
    )
    try:
        return rank_crops(cond, req.crops)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ─── ٢٣. سيناريوهات "ماذا لو" الفيزيائيّة (مُستلهَم من ورقة DT) ──
# حساب فيزيائي offline فوق ميزان الماء/GDD — لا توأم رقمي، لا M2M، لا ML.
from api.gdd_tracker import DailyTemp as _DTemp  # noqa: E402
from api.scenario_whatif import (  # noqa: E402
    whatif_planting_date,
    whatif_rainfall_change,
    whatif_temperature_shift,
)
from api.water_balance import WeatherInput as _WInput  # noqa: E402


class WhatIfTempRequest(BaseModel):
    crop: str
    stage: str = "mid"
    t_min_c: float
    t_max_c: float
    temp_shift_c: float
    rain_mm: float = 0.0
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100


@app.post("/api/v1/scenario/temperature")
def scenario_temperature(
    req: WhatIfTempRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو تغيّرت الحرارة؟ أثر فيزيائي على ET0 والاحتياج المائي."""
    w = _WInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    return whatif_temperature_shift(w, req.crop, req.stage, req.temp_shift_c, rain_mm=req.rain_mm)


class WhatIfPlantingRequest(BaseModel):
    crop: str
    temps_baseline: list[dict]  # [{t_min_c, t_max_c}, ...]
    temps_scenario: list[dict]


@app.post("/api/v1/scenario/planting-date")
def scenario_planting_date(
    req: WhatIfPlantingRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو غيّرتُ تاريخ الزراعة؟ أثر على تراكم GDD وبلوغ المراحل."""
    base = [_DTemp(t["t_min_c"], t["t_max_c"]) for t in req.temps_baseline]
    scen = [_DTemp(t["t_min_c"], t["t_max_c"]) for t in req.temps_scenario]
    try:
        return whatif_planting_date(req.crop, base, scen)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class WhatIfRainRequest(BaseModel):
    crop: str
    stage: str = "mid"
    t_min_c: float
    t_max_c: float
    rain_baseline_mm: float
    rain_scenario_mm: float
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100


@app.post("/api/v1/scenario/rainfall")
def scenario_rainfall(
    req: WhatIfRainRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو تغيّر المطر الموسمي؟ أثر على صافي الريّ المطلوب."""
    w = _WInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    return whatif_rainfall_change(
        w, req.crop, req.stage, req.rain_baseline_mm, req.rain_scenario_mm
    )


# ─── ٢٤. تظافر القرائن ودرجات التوصية (اتّفاق: القرائن المتظافرة ترقى) ─
from api.evidence_corroboration import Evidence, EvidenceType, corroborate  # noqa: E402


class EvidenceInput(BaseModel):
    etype: str  # lab_field|regional_prior|remote_sensing|field_obs|historical
    agrees: bool
    note_ar: str = ""


class CorroborationRequest(BaseModel):
    evidences: list[EvidenceInput]
    recommendation_key: str = "general"
    test_type_ar: str = "تربة"


@app.post("/api/v1/evidence/corroborate")
def evidence_corroborate(
    req: CorroborationRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحدّد درجة التوصية (إرشاديّة/مؤيَّدة/مؤكَّدة) بتظافر القرائن + حضّ على الفحص."""
    try:
        evs = [Evidence(EvidenceType(e.etype), e.agrees, e.note_ar) for e in req.evidences]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"نوع قرينة غير معروف: {e}") from e
    return corroborate(
        evs, recommendation_key=req.recommendation_key, test_type_ar=req.test_type_ar
    ).to_dict()


# ─── ٢٥. التقويم الثقافي (عرض فقط — خارج محرّك القرار صراحةً) ────
from api.cultural_calendar import get_cultural_calendar  # noqa: E402


@app.get("/api/v1/cultural-calendar")
def cultural_calendar(governorate: str | None = None):
    """تقويم ثقافي تراثي للعرض فقط — لا يدخل أيّ توصية (وسم صريح)."""
    return get_cultural_calendar(governorate)


# ─── ٢٦. التوقيت الفلكي الرصدي (مرساة موسميّة + تحقّق مع GDD) ────
# الشروق الاحتراقي كأداة توقيت رصديّة (لا تنجيم) — يعمل offline، يُعرَض مع GDD.
from api.astronomical_timing import cross_check_with_gdd, get_calendar_stars  # noqa: E402


@app.get("/api/v1/astronomical-timing/stars")
def astronomical_stars():
    """نجوم التقويم الزراعي العربي كمرساة موسميّة رصديّة (سهيل، الثريّا)."""
    return get_calendar_stars()


@app.get("/api/v1/regional-calendar")
def regional_calendar(governorate: str | None = None):
    """التقويم الزراعي الإقليمي للمحافظة (حِميري للهضبة، حضرمي للوادي)."""
    from api.astronomical_timing import get_regional_calendar

    return get_regional_calendar(governorate)


@app.post("/api/v1/recommendations/economic-adaptation")
def economic_adaptation_endpoint(
    crop_options: list[dict],
    area_ha: float | None = None,
    annual_revenue_usd: float | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يكيّف خيارات المحاصيل حسب القدرة الاقتصاديّة (اقتراح متدرّج لا فرض).

    متّسق مع استقلاليّة المزارع: كلّ الخيارات تبقى مرئيّة، الترتيب اقتراح.
    """
    from core.economic_adaptation import adapt_recommendation

    return adapt_recommendation(
        crop_options, area_ha=area_ha, annual_revenue_usd=annual_revenue_usd
    )


@app.get("/api/v1/recommendations/capacity-profiles")
def capacity_profiles_endpoint():
    """ملفّات طبقات القدرة الاقتصاديّة (مرجع شفّاف)."""
    from core.economic_adaptation import get_capacity_profiles

    return get_capacity_profiles()


@app.post("/api/v1/recommendations/candidates")
def generate_crop_candidates(
    candidates: list[dict],
    goal: str = "max_profit",
    top_n: int = 3,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يولّد بدائل زراعيّة مُقيَّمة حسب هدف المزارع — كلّ الخيارات مرئيّة (الوكالة).

    candidates: قائمة خيارات، كلّ منها dict بصفات موثّقة (crop_id, name_ar, is_suited,
    water_need_level, upfront_cost_level, profit_potential_level, is_staple, drought_score)
    — تُملأ من محرّكات سهول (الملاءمة/الماء/الاقتصاد/تحمّل الجفاف). تقييم حتميّ شفّاف.
    goal ∈ {max_profit, food_security, min_water, drought_resilience}.
    """
    from core.engines.candidate_generator import (
        CropCandidate,
        FarmerGoal,
        generate_candidates,
    )

    try:
        g = FarmerGoal(goal)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"هدف غير معروف: {goal}") from e
    if not isinstance(top_n, int) or top_n < 1:
        raise HTTPException(status_code=422, detail="top_n يجب أن يكون عدداً صحيحاً موجباً")

    def _req_bool(c: dict, key: str) -> bool:
        # JSON يجب أن يكون true/false صريحاً (لا "false" نصّاً تصبح True بصمت)
        v = c.get(key, False)
        if not isinstance(v, bool):
            raise HTTPException(status_code=422, detail=f"{key} يجب أن يكون true/false")
        return v

    def _req_score(c: dict):
        v = c.get("drought_score")
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise HTTPException(status_code=422, detail="drought_score يجب أن يكون رقماً [0,1]")
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise HTTPException(status_code=422, detail="drought_score خارج المدى [0,1]")
        return v

    objs: list = []
    for c in candidates:
        if not isinstance(c, dict) or "crop_id" not in c:
            raise HTTPException(status_code=422, detail="كلّ خيار يجب أن يكون كائناً فيه crop_id")
        objs.append(
            CropCandidate(
                crop_id=str(c["crop_id"]),
                name_ar=str(c.get("name_ar", c["crop_id"])),
                is_suited=_req_bool(c, "is_suited"),
                water_need_level=str(c.get("water_need_level", "mid")),
                upfront_cost_level=str(c.get("upfront_cost_level", "mid")),
                profit_potential_level=str(c.get("profit_potential_level", "unknown")),
                is_staple=_req_bool(c, "is_staple"),
                drought_score=_req_score(c),
            )
        )

    return generate_candidates(objs, g, top_n=top_n)


@app.get("/api/v1/learning/activation-status")
async def learning_activation_status(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """حالة بوّابة تفعيل التعلّم للمستأجر — مدفوعة بتدفّق البيانات (v49).

    تُحسب الأعداد حيّاً من recommendation_outcomes عبر RLS: إجماليّ التوصيات،
    المكتملة (نتيجة مسجّلة)، المقبولة، وضمن نافذة النضج. قبل العتبة: خاملة بصدق
    (لا تتظاهر بتعلّم لم يبدأ). جدول غير مفعَّل ⇒ لقطة صفريّة صريحة.
    """
    import asyncpg as _asyncpg
    from core.learning_activation import DataFlowSnapshot, evaluate_activation

    tenant = str(getattr(user, "tenant_id", ""))
    total = completed = accepted = within_lag = 0
    schema_ready = True
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب الجدول
                    row = await conn.fetchrow(
                        """SELECT COUNT(*) AS total,
                                  COUNT(*) FILTER (WHERE actual_yield_t_ha IS NOT NULL) AS completed,
                                  COUNT(*) FILTER (WHERE accepted) AS accepted,
                                  COUNT(*) FILTER (
                                      WHERE matured_within_lag AND actual_yield_t_ha IS NOT NULL
                                  ) AS within_lag
                           FROM recommendation_outcomes"""
                    )
                total = int(row["total"] or 0)
                completed = int(row["completed"] or 0)
                accepted = int(row["accepted"] or 0)
                within_lag = int(row["within_lag"] or 0)
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                schema_ready = False
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حالة تفعيل التعلّم", e) from e

    snapshot = DataFlowSnapshot(
        tenant_id=tenant,
        completed_outcomes=completed,
        total_recommendations=total,
        accepted_recommendations=accepted,
        outcomes_within_lag=within_lag,
    )
    result = evaluate_activation(snapshot)
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["data_source_note_ar"] = (
        "الأعداد تُحسب حيّاً من recommendation_outcomes عبر RLS (v49 مُفعَّل). "
        "البوّابة مدفوعة بالبيانات: خاملة بصدق حتى تتراكم نتائج كافية وناضجة."
        if schema_ready
        else "جدول recommendation_outcomes غير مفعَّل — لقطة صفريّة صريحة (خاملة)."
    )
    return result


@app.get("/api/v1/devices/fleet-health")
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


@app.get("/api/v1/rbac/who-can")
def rbac_who_can(
    permission: str,
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """الاستعلام العكسي: أيّ الأدوار تملك صلاحيّة معيّنة؟ (تدقيق أمني)."""
    from core.authorization import Permission as _P
    from core.rbac_governance import who_can

    try:
        perm = _P(permission)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"صلاحيّة غير معروفة: {permission}") from e
    return who_can(perm)


@app.get("/api/v1/rbac/permission-matrix")
def rbac_permission_matrix(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """مصفوفة الصلاحيّات الكاملة (كلّ دور × كلّ صلاحيّة) — شفافيّة الحوكمة."""
    from core.rbac_governance import permission_matrix

    return permission_matrix()


@app.get("/api/v1/admin/events/dead-letter")
async def admin_events_dead_letter(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """حوكمة الأحداث الفاشلة (DLQ): يعرض أحداث event_outbox الميّتة + تفاصيلها.

    فوق v_event_dead_letter (v48). مُرشَّح بالمستأجِر (RLS على events) — كلّ مستأجِر
    أحداثه الفاشلة. (عرض ops عابر المستأجرين = شأن superuser منفصل، مؤجَّل.)
    """
    rows: list = []
    try:
        async with tenant_connection(user) as conn:
            recs = await conn.fetch(
                """SELECT outbox_id, event_id::text, nats_subject, retry_count,
                          last_error, last_attempt_at, created_at,
                          event_type, entity_type, entity_id, occurred_at
                   FROM v_event_dead_letter ORDER BY created_at DESC LIMIT 500"""
            )
            rows = [
                {
                    "outbox_id": r["outbox_id"],
                    "event_id": r["event_id"],
                    "nats_subject": r["nats_subject"],
                    "retry_count": r["retry_count"],
                    "last_error": r["last_error"],
                    "last_attempt_at": r["last_attempt_at"].isoformat()
                    if r["last_attempt_at"]
                    else None,
                    "event_type": r["event_type"],
                    "entity_type": r["entity_type"],
                    "entity_id": r["entity_id"],
                }
                for r in recs
            ]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الأحداث الميّتة (DLQ)", e) from e
    return {
        "dead_letter": rows,
        "total": len(rows),
        "note_ar": (
            "أحداث فشل نشرها إلى NATS بعد استنفاد المحاولات. بعد إصلاح السبب "
            "(مثلاً NATS متوقّف) أعِد جدولتها عبر requeue. مراقبة: نبّه لو total>0."
        ),
    }


@app.post("/api/v1/admin/events/dead-letter/{outbox_id}/requeue")
async def admin_requeue_dead_letter(
    outbox_id: int,
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """يعيد جدولة حدث ميّت واحد → pending (بعد إصلاح السبب). فوق requeue_dead_letter (v48)."""
    try:
        async with tenant_connection(user) as conn:
            requeued = await conn.fetchval("SELECT requeue_dead_letter($1)", outbox_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إعادة جدولة حدث ميّت", e) from e
    if not requeued:
        raise HTTPException(status_code=404, detail="لا حدث ميّت بهذا المعرّف (أو غير فاشل)")
    return {"outbox_id": outbox_id, "requeued": True}


@app.post("/api/v1/admin/events/dead-letter/requeue-all")
async def admin_requeue_all_dead_letter(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """يعيد جدولة كلّ الأحداث الميّتة (تشغيل ops بعد إصلاح NATS). فوق requeue_all_dead_letter."""
    try:
        async with tenant_connection(user) as conn:
            count = await conn.fetchval("SELECT requeue_all_dead_letter()")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إعادة جدولة كلّ الأحداث الميّتة", e) from e
    return {"requeued_count": int(count or 0)}


@app.get("/api/v1/rbac/preview-role-change")
def rbac_preview_role_change(
    current_role: str,
    new_role: str,
    user: UserSchema = Depends(require_permission(Permission.USER_CHANGE_ROLE)),
):
    """معاينة أثر تغيير دور قبل تطبيقه (ما يُكتسَب/يُفقَد + تنبيه التصعيد)."""
    from core.rbac_governance import preview_role_change

    return preview_role_change(current_role, new_role)


@app.get("/api/v1/market/crop-gap")
async def market_crop_gap(
    zone_key: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """خريطة تركّز المحاصيل وفجوة السوق لمنطقة (إسقاط مبدأ LULC على حقول المنصّة).

    يكشف التشبّع (فائض محتمل) والفرص (محاصيل مناسبة قليلة الزراعة). صدق: حقول
    المنصّة المشتركة فقط (عيّنة لا مسح)، اتجاه نسبي لا رقم مطلق، لا تنبّؤ سعر.

    عمود zone_key مُفعَّل (v49)؛ تُملأ قيمته لكلّ حقل عبر PATCH /fields/{id}
    (zone_key من agro_climate_zones). الحقول بلا zone_key لا تدخل التجميع — صدق
    بلا تخمين.
    """
    import asyncpg as _asyncpg
    from core.engines.crop_market_gap import CropConcentration, regional_crop_map

    from api.agro_climate_zones import suited_for_zone

    concentrations: list = []
    suitability: dict = {}
    schema_ready = True  # يصبح False فقط عند غياب العمود/الجدول (لا عند 0 صفوف)
    try:
        async with tenant_connection(user) as conn:
            try:
                # SAVEPOINT يعزل غياب العمود/الجدول عن معاملة RLS (لا يُجهضها).
                async with conn.transaction():
                    rows = await conn.fetch(
                        """SELECT f.crop AS crop_id, COUNT(*) AS cnt
                           FROM fields f
                           WHERE f.zone_key = $1 AND f.crop IS NOT NULL
                           GROUP BY f.crop""",
                        zone_key,
                    )
                total = sum(r["cnt"] for r in rows) or 0
                suited = suited_for_zone(zone_key)
                # suited_for_zone يُرجِع suited_crops_ar (أسماء عربيّة)؛ مطابقة
                # crop_id بالاسم تقريبيّة — تُحسَّن عند توحيد قاموس المحاصيل.
                suited_names = set(suited.get("suited_crops_ar", []))
                for r in rows:
                    concentrations.append(
                        CropConcentration(
                            crop_id=r["crop_id"],
                            zone_key=zone_key,
                            field_count=r["cnt"],
                            total_fields_in_zone=total,
                        )
                    )
                    suitability[r["crop_id"]] = r["crop_id"] in suited_names
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                # المخطّط غير جاهز (zone_key/الجدول غير مفعَّل) — يميَّز عن «لا بيانات».
                schema_ready = False
                concentrations = []
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تحليل فجوة سوق المنطقة", e) from e

    # مفاتيح ميتا ثابتة دائماً (استقرار API): نفس التعريف في كلّ المسارات.
    meta = {"zone_key": zone_key, "schema_ready": schema_ready, "live_data_wired": schema_ready}
    if not concentrations:
        meta["total_crops_analysed"] = 0
        meta["note_ar"] = (
            "عمود/جدول مطلوب غير مفعَّل في المخطّط — لا تخمين."
            if not schema_ready
            else "المخطّط جاهز لكن لا حقول كافية بالمنصّة في هذه المنطقة — لا تخمين."
        )
        return meta
    return {**meta, **regional_crop_map(concentrations, suitability)}


@app.get("/api/v1/market/crop-classification-readiness")
async def crop_classification_readiness_endpoint(
    zone_key: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """جاهزيّة تصنيف المحاصيل بالأقمار لمنطقة (البوّابة الصادقة نحو فجوة سوق أشمل).

    يقيس عيّنات التدريب المتاحة (حقول المنصّة: محصول معروف + حدود GPS) ويقرّر
    متى يصبح التصنيف ممكناً. قبل الكفاية: التصنيف «غير متاح» بصدق (لا اختراع).
    """
    import asyncpg as _asyncpg
    from core.engines.crop_classification_readiness import (
        CropSampleInventory,
        assess_classification_readiness,
    )

    fields_by_crop: dict[str, int] = {}
    schema_ready = True  # False فقط عند غياب العمود/الجدول
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب العمود/الجدول
                    rows = await conn.fetch(
                        """SELECT f.crop AS crop_id, COUNT(*) AS cnt
                           FROM fields f
                           JOIN field_boundaries fb ON fb.field_id = f.field_id
                           WHERE f.zone_key = $1 AND f.crop IS NOT NULL
                                 AND fb.geom IS NOT NULL
                           GROUP BY f.crop""",
                        zone_key,
                    )
                fields_by_crop = {r["crop_id"]: r["cnt"] for r in rows}
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                schema_ready = False
                fields_by_crop = {}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("جاهزيّة تصنيف المحاصيل", e) from e

    inv = CropSampleInventory(
        zone_key=zone_key,
        fields_with_crop_and_gps=fields_by_crop,
        avg_temporal_scenes=0.0,  # يُحسب من /imagery/timeseries لاحقاً (مؤجَّل)
        gps_quality_ok=bool(fields_by_crop),
    )
    result = assess_classification_readiness(inv)
    # live_data_wired = جاهزيّة الربط/المخطّط (لا وجود الصفوف)؛ has_sample_data منفصل.
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["has_sample_data"] = bool(fields_by_crop)
    result["data_source_note_ar"] = (
        "⚠ العيّنات من حقول المنصّة (محصول معروف + حدود GPS). المشاهد الزمنيّة "
        "(avg_temporal_scenes) تُحسب من /imagery/timeseries لاحقاً — مؤجَّل بعد "
        "التشغيل؛ حتى ذلك تُقدَّر صفراً (التصنيف يُعلَن غير جاهز بصدق)."
    )
    return result


@app.get("/api/v1/learning/prediction-calibration")
async def prediction_calibration_status(
    crop_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """حالة معايرة التنبّؤ من التاريخ المتراكم (الانحياز المنهجي + التصحيح التدريجي).

    يحلّل أزواج (توقّع,نتيجة) التاريخيّة: هل نُفرط/نُقلّل منهجيّاً؟ ويطبّق تصحيحاً
    متدرّجاً (shrinkage). قبل عيّنة كافية: لا تصحيح (النموذج الأساسي كما هو).

    جدول recommendation_outcomes مُفعَّل (v49)؛ يُحلّل أزواجه الفعليّة عبر RLS.
    بلا أزواج كافية (≥3، ≥2 مزرعة) يُرجِع «عيّنة غير كافية» بصدق (correction_factor=1.0).
    """
    import asyncpg as _asyncpg
    from core.learning.prediction_calibration import (
        PredictionPair,
        analyze_systematic_bias,
    )

    pairs: list = []
    schema_ready = True  # False فقط عند غياب الجدول/العمود
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب الجدول
                    # وحدة التكرار = المزرعة (farm_id) لا المستأجِر: تحت RLS يكون
                    # tenant_id ثابتاً، فعدّه لا يقيس الاستقلال (تفادي pseudoreplication).
                    q = (
                        "SELECT predicted_yield_t_ha AS pred, actual_yield_t_ha AS act, "
                        "crop AS crop_id, farm_id::text AS fid "
                        "FROM recommendation_outcomes "
                        "WHERE predicted_yield_t_ha IS NOT NULL "
                        "AND actual_yield_t_ha IS NOT NULL"
                    )
                    params: list = []
                    if crop_id:
                        q += " AND crop = $1"
                        params.append(crop_id)
                    rows = await conn.fetch(q, *params)
                pairs = [
                    PredictionPair(float(r["pred"]), float(r["act"]), r["crop_id"], r["fid"])
                    for r in rows
                ]
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                schema_ready = False
                pairs = []
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("معايرة التنبّؤ", e) from e

    result = analyze_systematic_bias(pairs)
    # live_data_wired = جاهزيّة الربط/المخطّط (لا وجود الأزواج)؛ has_pairs منفصل.
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["has_pairs"] = bool(pairs)
    result["data_source_note_ar"] = (
        "الأزواج من recommendation_outcomes (توقّع تاريخي + نتيجة فعليّة) عبر RLS "
        "(v49 مُفعَّل)، ووحدة التكرار = المزرعة (farm_id) لا المستأجِر (تفادي "
        "pseudoreplication). بلا أزواج كافية: «عيّنة غير كافية» بصدق (لا تصحيح)."
    )
    return result


class OutcomeRecordRequest(BaseModel):
    """تسجيل نتيجة توصية — يغذّي معايرة التنبّؤ وبوّابة تفعيل التعلّم (مسار الكتابة).

    crop + field_id إلزاميّان (سياق التوصية) — يمنعان صفوفاً فارغة تشوّه العدّادات.
    """

    crop: str = Field(min_length=1, max_length=50)
    field_id: str = Field(min_length=1, max_length=50)
    farm_id: str | None = Field(default=None, max_length=50)
    season_id: str | None = Field(default=None, max_length=50)
    recommendation_id: str | None = Field(default=None, max_length=64)
    predicted_yield_t_ha: float | None = Field(default=None, ge=0)
    actual_yield_t_ha: float | None = Field(default=None, ge=0)
    accepted: bool = False
    matured_within_lag: bool = False


@app.post("/api/v1/recommendations/outcomes", status_code=201)
async def record_recommendation_outcome(
    req: OutcomeRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
):
    """يسجّل نتيجة توصية (توقّع/فعليّ + قبول/نضج) — مسار الكتابة لحلقة التعلّم (v49).

    تقرأ هذه الصفوفَ نقطتا learning/activation-status و prediction-calibration حيّاً.
    tenant عبر RLS (WITH CHECK يفرض المستأجِر). صدق: يسجّل المُرسَل فقط (لا اختراع).
    """
    # اتّساق: matured_within_lag يعني نضج نتيجة فعليّة — يستلزم actual_yield_t_ha.
    if req.matured_within_lag and req.actual_yield_t_ha is None:
        raise HTTPException(
            status_code=422,
            detail="matured_within_lag=true يستلزم actual_yield_t_ha (نتيجة فعليّة)",
        )
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO recommendation_outcomes
                       (tenant_id, field_id, farm_id, season_id, crop, recommendation_id,
                        predicted_yield_t_ha, actual_yield_t_ha, accepted, matured_within_lag,
                        outcome_recorded_at)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                           CASE WHEN $8 IS NOT NULL THEN now() ELSE NULL END)
                   RETURNING outcome_id""",
                str(getattr(user, "tenant_id", "")),
                req.field_id,
                req.farm_id,
                req.season_id,
                req.crop,
                req.recommendation_id,
                req.predicted_yield_t_ha,
                req.actual_yield_t_ha,
                req.accepted,
                req.matured_within_lag,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تسجيل نتيجة التوصية", e) from e
    return {"outcome_id": row["outcome_id"], "recorded": True}


@app.get("/api/v1/fields/{field_id}/water-stress-spectral")
async def field_water_stress_spectral(
    field_id: str,
    ndmi: float | None = None,
    msi: float | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الإجهاد المائي من مؤشّرات الرطوبة الطيفيّة (ndmi/msi) — جسر للقرار.

    يربط المؤشّرات المحسوبة (كانت بلا ربط) بكشف الإجهاد المائي. إشارة استرشاديّة
    تُدمَج مع ميزان الماء — القياس الأرضي يبقى المرجّح. صدق: لا مؤشّر → unknown.

    field-scoped: يتحقّق أنّ الحقل يخصّ المستأجِر (404 وإلّا) عبر RLS. المؤشّرات
    تُمرَّر كمعاملات حاليّاً (جلبها من الراستر لكلّ حقل بند لاحق).
    """
    from core.engines.spectral_stress_bridge import fuse_water_stress

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("التحقّق من الحقل", e) from e

    return {
        "field_id": field_id,
        "indices_source": "query_params",  # صدق: لم تُجلَب من الراستر بعد
        **fuse_water_stress(ndmi=ndmi, msi=msi),
    }


@app.get("/api/v1/indices/coverage-report")
def indices_coverage_report(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تقرير شفّاف: أيّ مؤشّرات طيفيّة مربوطة بالقرار وأيّها عرض/سياق (حوكمة)."""
    from core.engines.spectral_stress_bridge import index_coverage_report

    return index_coverage_report()


@app.get("/api/v1/crops/drought-resilience")
def crop_drought_resilience(
    crop_id: str,
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """درجة تحمّل الجفاف/الحرارة لمحصول من صفات موثّقة (مبدأ TRY، لا أرقام مخترعة).

    يجمع صفات سهول (عمق الجذور، حدّ حرارة الإزهار، عتبة الملوحة) في درجة مركّبة.
    يحذّر إن تجاوزت حرارة الهواء المتوقّعة حدّ الإزهار (قد تكون أخطر). على الحقل
    المرويّ يُضاف تنويه أنّ الريّ يبرّد الغطاء فالهواء يبالغ (Zhu et al. 2022).
    صدق: بلا صفات → لا درجة.
    """
    from core.engines.drought_resilience import compute_drought_resilience

    return compute_drought_resilience(
        crop_id, forecast_max_temp_c=forecast_max_temp_c, is_irrigated=is_irrigated
    )


@app.get("/api/v1/crops/compare-drought-resilience")
def compare_drought_resilience(
    crop_ids: str,
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """يقارن تحمّل محاصيل للجفاف (قائمة مفصولة بفواصل) — لاختيار الأصمد."""
    from core.engines.drought_resilience import compare_crops_resilience

    crops = [c.strip() for c in crop_ids.split(",") if c.strip()]
    return compare_crops_resilience(
        crops, forecast_max_temp_c=forecast_max_temp_c, is_irrigated=is_irrigated
    )


@app.get("/api/v1/calendars/today")
def calendars_today(
    date: str | None = None,
    governorate: str | None = None,
    crop: str | None = None,
):
    """سياق التقويم الزراعيّ لتاريخ (افتراضيّاً اليوم) في نداء واحد — يُسهّل بطاقة
    «التقويم الزراعيّ» في الواجهة:
      • المنزلة القمريّة النشطة + النوء (marker) + الشهر الحميريّ + ملف المنطقة.
      • إن مُرِّر محصول: نافذة زراعته وملاءمة الشهر الحاليّ (تبكير/تأخير).
    عرض/إرشاد تراثيّ-رصديّ صريحاً (display_only=true، خارج محرّك القرار) — التوقيت
    الفعليّ يبقى على GDD/الفيزياء. تاريخ غير صالح ⇒ يُعاد error_ar من الجسر.
    """
    from datetime import date as _date

    from api.yemeni_calendars import calendar_context_for_date

    target_iso = date or _date.today().isoformat()
    ctx = calendar_context_for_date(target_iso, governorate)
    # تاريخ غير صالح ⇒ الجسر يُعيد {error_ar}: لا نُضيف planting (تجنّب خلط خطأ
    # ببيانات مشتقّة من تاريخ آخر) — تدهور رشيق متّسق مع الـdocstring.
    if crop and "error_ar" not in ctx:
        from api.planting_calendar import check_planting_date, planting_window

        month = _date.fromisoformat(target_iso).month  # صحيح هنا (مرّ الجسر)
        ctx["planting"] = {
            "window": planting_window(crop),
            "current_month_fit": check_planting_date(crop, month),
        }
    return ctx


@app.get("/api/v1/calendars/lunar-mansions")
def calendars_lunar_mansions():
    """المنازل القمريّة الـ٢٨ (نجوم الزراعة) — مرجع معرفي تراثي (عرض فقط)."""
    from api.yemeni_calendars import get_lunar_mansions

    return get_lunar_mansions()


@app.get("/api/v1/calendars/himyarite-months")
def calendars_himyarite_months():
    """الشهور الحميريّة الـ١٢ + تنبيه التباين بين المصادر (عرض فقط)."""
    from api.yemeni_calendars import get_himyarite_months

    return get_himyarite_months()


@app.get("/api/v1/calendars/regional-profiles")
def calendars_regional_profiles(governorate: str | None = None):
    """ملفّات التقاويم الإقليميّة (حضرموت/تهامة/المرتفعات/الجوف) — الربط المكانيّ."""
    from api.yemeni_calendars import get_regional_profiles

    return get_regional_profiles(governorate=governorate)


@app.get("/api/v1/calendars/context")
def calendars_context(date_iso: str, governorate: str | None = None):
    """الجسر الزمني: تاريخ → المنزلة النشطة + الشهر الحميري + ملف المنطقة.

    عرض ومعرفة فقط؛ لا يدخل القرار. التواريخ تقريبيّة، المقابلات تختلف.
    """
    from api.yemeni_calendars import calendar_context_for_date

    return calendar_context_for_date(date_iso, governorate=governorate)


@app.get("/api/v1/agricultural-proverbs/for-date")
def agricultural_proverbs_for_date(date_iso: str, governorate: str | None = None):
    """أمثال التاريخ: تاريخ → المنزلة النشطة → أمثالها (الحلقة المكتملة)."""
    from api.agricultural_proverbs import proverbs_for_date

    return proverbs_for_date(date_iso, governorate=governorate)


@app.get("/api/v1/agricultural-proverbs")
def agricultural_proverbs(marker: str | None = None, governorate: str | None = None):
    """أمثال زراعيّة موثّقة تجسر ثقة المزارع — عرض فقط، مفهرسة بالمعلم/المنطقة."""
    from api.agricultural_proverbs import get_proverbs

    return get_proverbs(marker=marker, governorate=governorate)


# ─── ٢٧. التماسك الزمني الموحّد (Convergence) ──────────────────────
# يضمن أنّ المحرّكات الزمنيّة (GDD/water_balance/astronomical) على مرجع واحد.
class TemporalCoherenceRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    planting_date: str | None = None
    gdd_days_counted: int | None = None


@app.post("/api/v1/temporal/coherence")
def temporal_coherence(
    req: TemporalCoherenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """مرجع زمني موحّد + كشف الانحراف الدلالي بين المحرّكات."""
    from api.temporal_coherence import check_temporal_coherence, make_temporal_context

    try:
        ctx = make_temporal_context(req.current_date, req.planting_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    check = check_temporal_coherence(ctx, gdd_days_counted=req.gdd_days_counted)
    return {"context": ctx.to_dict(), "coherence": check.to_dict()}


class AstronomicalCrossCheckRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    gdd_stage: str | None = None
    anchor: str = "suhail_rising"


@app.post("/api/v1/astronomical-timing/cross-check")
def astronomical_cross_check(
    req: AstronomicalCrossCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تحقّق متقاطع: المرساة الفلكيّة مقابل مرحلة GDD (اتّفاق=ثقة، اختلاف=تنبيه)."""
    return cross_check_with_gdd(req.current_date, gdd_stage=req.gdd_stage, anchor=req.anchor)


# ─── ٢٨. حاجز سلامة المدخلات الكيميائيّة (مُكيَّف من v9، سدّ فجوة سلامة) ─
from api.chemical_safety import check_chemical, list_banned  # noqa: E402


class ChemicalCheckRequest(BaseModel):
    chemical: str
    dose_kg_ha: float | None = None


@app.post("/api/v1/chemical-safety/check")
def chemical_safety_check(
    req: ChemicalCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يفحص مادّة كيميائيّة ضدّ الحظر الدولي والجرعة القصوى (فحص/تحذير، لا أتمتة)."""
    return check_chemical(req.chemical, dose_kg_ha=req.dose_kg_ha).to_dict()


@app.get("/api/v1/chemical-safety/banned")
def chemical_safety_banned():
    """قائمة المواد المحظورة/المقيّدة دوليّاً (شفافيّة)."""
    return list_banned()


# ─── ٢٩. مراقبة الحقول بالكاميرا (عين ميدانيّة، لا كشف آلي بالـML) ──
from api.field_cameras import (  # noqa: E402
    CameraSnapshot,
    link_snapshot_as_evidence,
    register_camera,
)


class RegisterCameraRequest(BaseModel):
    camera_id: str
    field_id: str
    name_ar: str
    camera_type: str = "fixed"  # fixed|mobile|timelapse
    lat: float | None = None
    lon: float | None = None
    capture_interval_min: int | None = None
    note_ar: str = ""


@app.post("/api/v1/cameras/register")
def cameras_register(
    req: RegisterCameraRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يسجّل كاميرا مراقبة لحقل (عين ميدانيّة — لا كشف آلي بالذكاء الاصطناعي)."""
    try:
        return register_camera(
            req.camera_id,
            req.field_id,
            req.name_ar,
            req.camera_type,
            lat=req.lat,
            lon=req.lon,
            capture_interval_min=req.capture_interval_min,
            note_ar=req.note_ar,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class SnapshotEvidenceRequest(BaseModel):
    snapshot_id: str
    camera_id: str
    field_id: str
    media_uri: str
    captured_at: str
    linked_pin_id: str | None = None
    note_ar: str = ""


@app.post("/api/v1/cameras/snapshot-evidence")
def cameras_snapshot_evidence(
    req: SnapshotEvidenceRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يحوّل لقطة كاميرا إلى قرينة ميدانيّة (field_obs) للتظافر — لا تشخيص آلي."""
    snap = CameraSnapshot(
        snapshot_id=req.snapshot_id,
        camera_id=req.camera_id,
        field_id=req.field_id,
        media_uri=req.media_uri,
        captured_at=req.captured_at,
        linked_pin_id=req.linked_pin_id,
        note_ar=req.note_ar,
    )
    return link_snapshot_as_evidence(snap)


# ─── ٣٠. حساسيّة المراحل للإجهاد المائي (محاصيل اليمن، يكمّل ميزان الماء) ─
from api.crop_water_sensitivity import (  # noqa: E402
    assess_stress_risk,
    integrated_irrigation_advice,
    supported_crops,
    water_calendar,
    wheat_water_calendar,
)


@app.get("/api/v1/water-sensitivity/crops")
def water_sensitivity_crops():
    """قائمة المحاصيل اليمنيّة المدعومة بحساسيّة المراحل المائيّة."""
    return {"crops": supported_crops()}


@app.get("/api/v1/water-sensitivity/calendar")
def water_sensitivity_calendar(crop: str = "wheat"):
    """التقويم المائي لمحصول: المراحل + حرجيّتها + السياق اليمني.

    المدعوم: wheat, maize, sorghum, millet, barley (أو أسماؤها العربيّة).
    """
    return water_calendar(crop)


@app.get("/api/v1/water-sensitivity/wheat-calendar")
def water_sensitivity_wheat_calendar():
    """(توافق خلفي) التقويم المائي للقمح."""
    return wheat_water_calendar()


class StressRiskRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float


@app.post("/api/v1/water-sensitivity/stress-risk")
def water_sensitivity_stress(
    req: StressRiskRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم خطر الإجهاد المائي بناءً على المحصول والمرحلة ونضوب التربة."""
    return assess_stress_risk(req.crop, req.stage_key, req.depletion_pct)


class IntegratedAdviceRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float
    net_irrigation_mm: float | None = None


@app.post("/api/v1/water-sensitivity/integrated-advice")
def water_sensitivity_integrated(
    req: IntegratedAdviceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """توصية ريّ متكاملة: تجمع الحساسيّة (متى حرج) + الاحتياج (كم مم) في قرار واحد."""
    return integrated_irrigation_advice(
        req.crop,
        req.stage_key,
        req.depletion_pct,
        req.net_irrigation_mm,
    )


# ─── ٣١. الدورة الزراعيّة (تعاقب المحاصيل — خصوبة وقائيّة) ──────────
from api.crop_rotation import (  # noqa: E402
    evaluate_rotation,
    rotation_principles,
    suggest_next_crop,
)


@app.get("/api/v1/rotation/principles")
def rotation_principles_endpoint():
    """مبادئ الدورة الزراعيّة + المحاصيل المصنّفة (تثقيفي)."""
    return rotation_principles()


@app.get("/api/v1/rotation/evaluate")
def rotation_evaluate(previous: str, candidate: str):
    """يقيّم تعاقب محصولَين: هل candidate خيار جيّد بعد previous؟"""
    return evaluate_rotation(previous, candidate)


@app.get("/api/v1/rotation/suggest")
def rotation_suggest(previous: str):
    """يقترح أفضل المحاصيل التالية بعد محصول (مرتّبة)، بسياق يمني."""
    return suggest_next_crop(previous)


# ─── ٣٢. تقويم مواعيد الزراعة المثلى (نوافذ + تحذيرات التبكير/التأخير) ─
from api.planting_calendar import (  # noqa: E402
    check_planting_date,
    planting_window,
)
from api.planting_calendar import (  # noqa: E402
    supported_crops as planting_crops,
)


@app.get("/api/v1/planting/crops")
def planting_crops_endpoint():
    """المحاصيل المدعومة بتقويم مواعيد الزراعة."""
    return {"crops": planting_crops()}


@app.get("/api/v1/planting/window")
def planting_window_endpoint(crop: str = "wheat"):
    """نافذة الزراعة المثلى لمحصول + مخاطر التبكير/التأخير + الحصاد."""
    return planting_window(crop)


@app.get("/api/v1/planting/check")
def planting_check_endpoint(crop: str, month: int):
    """يقيّم: هل الشهر مناسب لزراعة هذا المحصول؟ (1-12)"""
    return check_planting_date(crop, month)


# ─── ٣٣. الإدارة المتكاملة للآفات (IPM — نهج متدرّج، الكيميائي ملاذ أخير) ─
from api.ipm_advisor import ipm_plan, pests_for_crop  # noqa: E402
from api.ipm_advisor import supported_pests as ipm_pests  # noqa: E402


@app.get("/api/v1/ipm/pests")
def ipm_pests_endpoint():
    """الآفات المدعومة بخطّة إدارة متكاملة."""
    return {"pests": ipm_pests()}


@app.get("/api/v1/ipm/plan")
def ipm_plan_endpoint(pest: str):
    """خطّة الإدارة المتكاملة لآفة: وقاية → مراقبة → حيوي → كيميائي (ملاذ أخير)."""
    return ipm_plan(pest)


@app.get("/api/v1/ipm/crop-pests")
def ipm_crop_pests_endpoint(crop: str):
    """الآفات المحتملة لمحصول (للوقاية الاستباقيّة)."""
    return pests_for_crop(crop)


# ─── ٣٤. إدارة الملوحة (تصنيف + غسيل + صوديوم — معايير FAO) ────────
from api.salinity_management import salinity_assessment  # noqa: E402


class SalinityRequest(BaseModel):
    ece_dsm: float | None = None  # ملوحة التربة
    ecw_dsm: float | None = None  # ملوحة ماء الريّ
    sar: float | None = None  # نسبة امتصاص الصوديوم
    crop_threshold_ece: float | None = None  # عتبة تحمّل المحصول


@app.post("/api/v1/salinity/assess")
def salinity_assess_endpoint(
    req: SalinityRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقييم شامل للملوحة: تصنيف التربة/الماء + احتياج الغسيل + خطر الصوديوم."""
    return salinity_assessment(
        ece_dsm=req.ece_dsm,
        ecw_dsm=req.ecw_dsm,
        sar=req.sar,
        crop_threshold_ece=req.crop_threshold_ece,
    )


# ─── ٣٥. دليل البنّ اليمني (محصول نقدي للمرتفعات — شجري دائم) ──────
from api.coffee_advisor import (  # noqa: E402
    coffee_pests,
)
from api.coffee_advisor import (  # noqa: E402
    cultivation_guide as coffee_guide,
)
from api.coffee_advisor import (  # noqa: E402
    site_suitability as coffee_site,
)
from api.coffee_advisor import (  # noqa: E402
    varieties as coffee_varieties,
)


@app.get("/api/v1/coffee/site-suitability")
def coffee_site_endpoint(altitude_m: float):
    """ملاءمة موقع لزراعة البنّ بناءً على الارتفاع (المثالي 1500-2400م)."""
    return coffee_site(altitude_m)


@app.get("/api/v1/coffee/guide")
def coffee_guide_endpoint():
    """دليل زراعة البنّ اليمني: المدرّجات، التظليل، الريّ، التجفيف الطبيعي."""
    return coffee_guide()


@app.get("/api/v1/coffee/varieties")
def coffee_varieties_endpoint(region: str | None = None):
    """أصناف البنّ اليمنيّة (كلّها أو حسب منطقة)."""
    return coffee_varieties(region)


@app.get("/api/v1/coffee/pests")
def coffee_pests_endpoint():
    """آفات البنّ الرئيسيّة (صدأ الأوراق، ثاقبة الثمار) مرتبطة بـIPM."""
    return coffee_pests()


# ─── ٣٦. ما بعد الحصاد (التخزين وتقليل الفقد) ─────────────────────
from api.postharvest_advisor import (  # noqa: E402
    check_storage_moisture,
    storage_best_practices,
    storage_pests,
)


@app.get("/api/v1/postharvest/moisture-check")
def postharvest_moisture_endpoint(crop: str, moisture_pct: float):
    """يقيّم: هل رطوبة الحبوب آمنة للتخزين؟ (القمح ≤12%، الذرة ≤13%)"""
    return check_storage_moisture(crop, moisture_pct)


@app.get("/api/v1/postharvest/pests")
def postharvest_pests_endpoint():
    """الآفات المخزنيّة الرئيسيّة للحبوب (سوسة الأرز، الخابرا...)."""
    return storage_pests()


@app.get("/api/v1/postharvest/best-practices")
def postharvest_practices_endpoint(crop: str | None = None):
    """أفضل ممارسات التخزين لتقليل الفقد بعد الحصاد."""
    return storage_best_practices(crop)


# ─── ٣٧. البذور المحسّنة + الأساليب الزراعيّة المحسّنة ─────────────
from api.seed_and_practices import (  # noqa: E402
    evaluate_seed_source,
    practice_guide,
    seed_selection_criteria,
    supported_practices,
)


@app.get("/api/v1/seed/criteria")
def seed_criteria_endpoint():
    """معايير اختيار البذور/الأصناف المحسّنة (إطار قرار + توجيه لهيئة البحوث)."""
    return seed_selection_criteria()


class SeedSourceRequest(BaseModel):
    certified: bool
    purity_pct: float | None = None
    germination_pct: float | None = None


@app.post("/api/v1/seed/evaluate-source")
def seed_evaluate_endpoint(req: SeedSourceRequest):
    """يقيّم جودة مصدر بذار (اعتماد + نقاوة + إنبات)."""
    return evaluate_seed_source(req.certified, req.purity_pct, req.germination_pct)


@app.get("/api/v1/seed/germination-rate")
def seed_germination_endpoint(sprouted: int, total: int):
    """يحسب معدّل الإنبات من اختبار عيّنة بسيط (المنبت ÷ الإجمالي)."""
    from api.seed_and_practices import germination_rate

    return germination_rate(sprouted, total)


@app.get("/api/v1/seed/storage-check")
def seed_storage_endpoint(temp_f: float, humidity_pct: float):
    """قاعدة تخزين البذور: حرارة(°ف) + رطوبة% < 100."""
    from api.seed_and_practices import storage_check

    return storage_check(temp_f, humidity_pct)


@app.get("/api/v1/seed/sowing-depth")
def seed_sowing_depth_endpoint(seed_size_mm: float, precision: bool = False):
    """عمق البذر المناسب (~5× حجم البذرة، 2× للدقيقة)."""
    from api.seed_and_practices import sowing_depth

    return sowing_depth(seed_size_mm, precision)


@app.get("/api/v1/practices/list")
def practices_list_endpoint():
    """الأساليب الزراعيّة المحسّنة المدعومة."""
    return {"practices": supported_practices()}


@app.get("/api/v1/practices/guide")
def practices_guide_endpoint(practice: str):
    """دليل أسلوب زراعي محسّن (تحميل/زراعة حافظة/مدرّجات/ريّ تكميلي)."""
    return practice_guide(practice)


# ─── ٣٨. إدخال محاصيل/أشجار جديدة (استلهام من جازان/نجران) ─────────
from api.crop_introduction import crop_card, list_candidates  # noqa: E402


@app.get("/api/v1/introduction/candidates")
def introduction_candidates_endpoint(zone: str | None = None):
    """محاصيل/أشجار مرشّحة للإدخال (zone: tihama/jawf) مستلهمة من المناطق المحاذية."""
    return list_candidates(zone)


@app.get("/api/v1/introduction/card")
def introduction_card_endpoint(crop: str):
    """البطاقة التعريفيّة لمحصول/شجرة مرشّحة (المتطلّبات + مصدر الاستلهام)."""
    return crop_card(crop)


class FieldFitRequest(BaseModel):
    crop: str
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True


@app.post("/api/v1/introduction/field-fit")
def introduction_field_fit_endpoint(req: FieldFitRequest):
    """فحص آلي: هل تربة/ظروف حقلك تناسب محصول الإدخال؟ (ربط بمحرّك الملاءمة)."""
    from api.crop_introduction import check_field_fit

    return check_field_fit(
        req.crop,
        req.ph,
        req.ec_dsm,
        req.season_rain_mm,
        req.temp_mean_c,
        req.irrigated,
    )


# ─── ٣٩. بروتوكول أخذ عيّنة التربة (دقّة التحليل تبدأ من العيّنة) ──
from api.soil_sampling_protocol import (  # noqa: E402
    sampling_depth,
    sampling_protocol,
    subsamples_for_area,
)


@app.get("/api/v1/soil-sampling/subsamples")
def soil_subsamples_endpoint(area_ha: float):
    """عدد العيّنات الفرعيّة الموصى بها حسب مساحة الحقل."""
    return subsamples_for_area(area_ha)


@app.get("/api/v1/soil-sampling/depth")
def soil_depth_endpoint(purpose: str = "general"):
    """العمق المناسب لأخذ العيّنة حسب الغرض (general/nitrate/no_till/orchard)."""
    return sampling_depth(purpose)


@app.get("/api/v1/soil-sampling/protocol")
def soil_protocol_endpoint(area_ha: float | None = None, purpose: str = "general"):
    """البروتوكول الكامل لأخذ عيّنة تربة صحيحة (خطوات + تحذيرات + توقيت)."""
    return sampling_protocol(area_ha, purpose)


# ─── ٤٠. حصاد مياه الأمطار (مصدر ماء بديل للمناطق الشحيحة) ────────
from api.water_harvesting import (  # noqa: E402
    harvest_potential,
    harvesting_methods,
    method_guide,
)


@app.get("/api/v1/water-harvesting/potential")
def water_potential_endpoint(
    catchment_area_m2: float, annual_rain_mm: float, surface: str = "roof"
):
    """يقدّر كميّة مياه الأمطار القابلة للحصاد سنويّاً (لتر/م³)."""
    return harvest_potential(catchment_area_m2, annual_rain_mm, surface)


@app.get("/api/v1/water-harvesting/methods")
def water_methods_endpoint():
    """طرق حصاد المياه المناسبة (مدرّجات/سدود/صهاريج/مصاطب كنتوريّة)."""
    return harvesting_methods()


@app.get("/api/v1/water-harvesting/method-guide")
def water_method_guide_endpoint(method: str):
    """دليل طريقة حصاد مياه محدّدة (الفوائد + الأنسب + التحذير)."""
    return method_guide(method)


# ─── ٤١. دراسة الجدوى الاقتصاديّة (هل سأربح؟) ─────────────────────
from api.farm_economics import break_even_price, cost_categories, feasibility  # noqa: E402


@app.get("/api/v1/economics/cost-categories")
def economics_categories_endpoint():
    """بنود التكلفة القياسيّة لبناء تقدير الجدوى."""
    return cost_categories()


class FeasibilityRequest(BaseModel):
    area_ha: float
    yield_t_per_ha: float
    price_per_t: float
    costs: dict[str, float] | None = None
    total_cost: float | None = None


@app.post("/api/v1/economics/feasibility")
def economics_feasibility_endpoint(req: FeasibilityRequest):
    """جدوى المحصول: الإيراد المتوقّع + صافي الربح + الهامل + فحص السوق."""
    return feasibility(
        req.area_ha,
        req.yield_t_per_ha,
        req.price_per_t,
        req.costs,
        req.total_cost,
    )


@app.get("/api/v1/economics/break-even")
def economics_break_even_endpoint(area_ha: float, yield_t_per_ha: float, total_cost: float):
    """سعر التعادل: أدنى سعر/طن يغطّي التكاليف."""
    return break_even_price(area_ha, yield_t_per_ha, total_cost)


# ─── ٤٢. الإكثار الخضري (اللاجنسي) + اختيار الأصل المقاوم ─────────
from api.propagation_advisor import (  # noqa: E402
    crop_propagation,
    propagation_methods,
    rootstock_selection,
)
from api.propagation_advisor import (  # noqa: E402
    method_guide as propagation_method_guide,
)


@app.get("/api/v1/propagation/methods")
def propagation_methods_endpoint():
    """طرق الإكثار الخضري الخمس (عقل/تطعيم/برعمة/تقسيم/ترقيد)."""
    return propagation_methods()


@app.get("/api/v1/propagation/method-guide")
def propagation_method_guide_endpoint(method: str):
    """دليل طريقة إكثار محدّدة (الأنواع + النصيحة + الأنسب)."""
    return propagation_method_guide(method)


@app.get("/api/v1/propagation/crop")
def propagation_crop_endpoint(crop: str):
    """طريقة الإكثار المناسبة لمحصول/شجرة من بطاقات الإدخال."""
    return crop_propagation(crop)


@app.get("/api/v1/propagation/rootstock")
def propagation_rootstock_endpoint(stress: str = "salinity"):
    """إرشاد اختيار الأصل المقاوم حسب الإجهاد (salinity/drought/disease/dwarfing)."""
    return rootstock_selection(stress)


# ─── ٤٣. تصنيف الأقاليم المناخيّة-الزراعيّة لليمن (أين أنت → ماذا يناسبك) ──
from api.agro_climate_zones import (  # noqa: E402
    identify_zone,
    list_zones,
    suited_for_zone,
    zone_profile,
)


@app.get("/api/v1/agro-zones/list")
def agro_zones_list_endpoint():
    """الأقاليم المناخيّة-الزراعيّة الستّة لليمن مع ملخّصها."""
    return list_zones()


@app.get("/api/v1/agro-zones/profile")
def agro_zone_profile_endpoint(zone: str):
    """الملفّ المناخي-الزراعي الكامل لإقليم (حرارة/مطر/محاصيل/تجنّب)."""
    return zone_profile(zone)


@app.get("/api/v1/agro-zones/identify")
def agro_zone_identify_endpoint(location: str):
    """يحدّد الإقليم المناخي من اسم محافظة/منطقة يمنيّة."""
    return identify_zone(location)


@app.get("/api/v1/agro-zones/suited-crops")
def agro_zone_suited_endpoint(zone: str, irrigated: bool = True):
    """المحاصيل الملائمة لإقليم + ما يُتجنّب + التنبيه المائي."""
    return suited_for_zone(zone, irrigated)


@app.get("/api/v1/agro-zones/by-elevation")
def agro_zone_elevation_endpoint(altitude_m: float, is_western: bool = True):
    """يحدّد الإقليم بالارتفاع — الأصدق مناخيّاً (المناخ دالّة الارتفاع)."""
    from api.agro_climate_zones import zone_by_elevation

    return zone_by_elevation(altitude_m, is_western=is_western)


@app.get("/api/v1/agro-zones/identify-smart")
def agro_zone_identify_smart_endpoint(
    location: str, altitude_m: float | None = None, is_western: bool = True
):
    """تحديد ذكي: للمحافظات متعدّدة الأقاليم (كتعز) يطلب المديريّة/الارتفاع."""
    from api.agro_climate_zones import identify_zone_v2

    return identify_zone_v2(location, altitude_m, is_western)


# ─── ٤٤. تحديد الإقليم من إحداثيّات الحقل (GPS → محافظة + إقليم + مناخ) ──
from api.geo_zone_locator import locate_and_recommend, locate_field  # noqa: E402


@app.get("/api/v1/geo-locate/field")
def geo_locate_field_endpoint(lat: float, lon: float, elevation_m: float | None = None):
    """يحدّد المحافظة + الإقليم المناخي + المناخ من إحداثيّات الحقل (GPS)."""
    return locate_field(lat, lon, elevation_m)


@app.get("/api/v1/geo-locate/recommend")
def geo_locate_recommend_endpoint(lat: float, lon: float, elevation_m: float | None = None):
    """تحديد الموقع + توصية مباشرة بالمحاصيل الملائمة (تدفّق كامل)."""
    return locate_and_recommend(lat, lon, elevation_m)


# ─── ٤٥. نوافذ المخاطر المناخيّة الموسميّة + ساعات البرودة ──
from api.seasonal_risk import (  # noqa: E402
    chill_hours_estimate,
    stage_risk_check,
    zone_risk_calendar,
)


@app.get("/api/v1/seasonal-risk/calendar")
def seasonal_risk_calendar_endpoint(zone: str):
    """نوافذ المخاطر المناخيّة الموسميّة لإقليم (موجات حرّ/صقيع/مطر حصاد)."""
    return zone_risk_calendar(zone)


@app.get("/api/v1/seasonal-risk/stage-check")
def seasonal_risk_stage_endpoint(zone: str, stage_ar: str):
    """يفحص مخاطر مرحلة نموّ محدّدة في إقليم (مثلاً الإزهار في الجوف)."""
    return stage_risk_check(zone, stage_ar)


@app.get("/api/v1/seasonal-risk/chill-hours")
def seasonal_risk_chill_endpoint(zone: str):
    """يقدّر ساعات البرودة ويقارنها باحتياج الأشجار المتساقطة."""
    return chill_hours_estimate(zone)


# ─── ٤٦. المناطق العالميّة المشابهة مناخيّاً + محاصيلها المثبتة ──
from api.climate_analogs import (  # noqa: E402
    analog_detail,
    desert_proven_crops,
    list_analog_regions,
)


@app.get("/api/v1/climate-analogs/list")
def climate_analogs_list_endpoint():
    """المناطق العالميّة المشابهة مناخيّاً للصحراء اليمنيّة (الحزم/الجوف)."""
    return list_analog_regions()


@app.get("/api/v1/climate-analogs/detail")
def climate_analogs_detail_endpoint(region: str):
    """تفصيل منطقة مشابهة + دروسها (الجوف السعوديّة/النقب/أريزونا...)."""
    return analog_detail(region)


@app.get("/api/v1/climate-analogs/desert-crops")
def climate_analogs_crops_endpoint(category: str | None = None):
    """المحاصيل المثبتة عالميّاً في المناخ الصحراوي (أشجار/موسميّة/حديثة)."""
    return desert_proven_crops(category)


@app.get("/api/v1/climate-analogs/strategic-tiers")
def climate_analogs_strategic_endpoint(tier: str | None = None):
    """التصنيف الاستراتيجي للمحاصيل الصحراويّة (قيمة × استدامة مائيّة × تصدير)."""
    from api.climate_analogs import strategic_tiers

    return strategic_tiers(tier)


# ─── ٤٧. تحليل سجلّ الطقس اليومي → ذكاء زراعي (إجهاد حراري + ET0 + عجز مائي) ──
from api.weather_analytics import analyze_weather_log, seasonal_planting_guide  # noqa: E402


@app.post("/api/v1/weather-analytics/analyze")
def weather_analyze_endpoint(records: list[dict]):
    """يحلّل سجلّ طقس يومي → إجهاد حراري + ET0 محسوب + عجز مائي + توصية."""
    return analyze_weather_log(records)


@app.post("/api/v1/weather-analytics/planting-guide")
def weather_planting_guide_endpoint(records: list[dict]):
    """دليل المواسم من السجلّ: متى الزراعة الأمثل ومتى الإجهاد."""
    return seasonal_planting_guide(records)


# ─── ٤٨. مورد السيول الواردة (الحزم تستقبل من أحواض أعلى) ──
@app.get("/api/v1/water-harvesting/upstream-flood")
def water_upstream_flood_endpoint(local_rain_mm: float, catchment_note: str = ""):
    """مورد السيول الواردة من أحواض أعلى (يتجاوز المطر المحلّي)."""
    from api.water_harvesting import upstream_flood_water

    return upstream_flood_water(local_rain_mm, catchment_note)


# ─── ٤٩. محرّك القرار الزراعي الموحّد (عقل الحقل) ──
from api.decision_engine import decide_for_location  # noqa: E402


@app.get("/api/v1/decision/for-location")
def decision_for_location_endpoint(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    soil_ph: float | None = None,
    soil_ec_dsm: float | None = None,
    area_ha: float | None = None,
):
    """قرار زراعي متكامل: موقع → إقليم → محاصيل → مخاطر → دليل → خطوات."""
    return decide_for_location(location, lat, lon, elevation_m, soil_ph, soil_ec_dsm, area_ha)


# ─── طبقة تفسير القرار بالذكاء الاصطناعي (Claude يشرح، القواعد تقرّر) ──
from api.decision_explainer import explain_decision  # noqa: E402


@app.get("/api/v1/decision/explain")
def decision_explain_endpoint(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    soil_ph: float | None = None,
    soil_ec_dsm: float | None = None,
    area_ha: float | None = None,
):
    """يفسّر القرار بلغة طبيعيّة. يُرجع prompt جاهزاً لـClaude + بديل offline.

    القرار نفسه من القواعد (شفّاف)؛ الذكاء الاصطناعي يصوغ الشرح فقط.
    الخادم يأخذ prompt_for_server ويستدعي Claude عبر proxy آمن، ثمّ يعيد
    النصّ إلى explain_decision. بلا إنترنت → الشرح من القواعد (offline).
    """
    decision = decide_for_location(location, lat, lon, elevation_m, soil_ph, soil_ec_dsm, area_ha)
    return explain_decision(decision)


# ─── ٥٠. مخطّط البستان المختلط الاستثماري (لوز/زيتون/فستق) ──
from api.orchard_planner import mixed_orchard_plan, orchard_economics_note  # noqa: E402


@app.get("/api/v1/orchard/plan")
def orchard_plan_endpoint(area_ha: float = 1.0):
    """يخطّط بستاناً مختلطاً صحراويّاً: توزيع + كثافة + جدول عائد زمني."""
    return mixed_orchard_plan(area_ha)


@app.get("/api/v1/orchard/economics")
def orchard_economics_endpoint(area_ha: float = 1.0):
    """ملاحظات اقتصاديّة تقديريّة للبستان المختلط (سيناريو لا وعد)."""
    return orchard_economics_note(area_ha)


# ─── ٥١. محاصيل عالية القيمة قليلة الانتشار (فرص دخول مبكر) ──
from api.high_value_crops import high_value_crop_detail, list_high_value_crops  # noqa: E402


@app.get("/api/v1/high-value-crops/list")
def high_value_crops_list_endpoint(tier: str | None = None):
    """محاصيل عالية القيمة مصنّفة بصدق حسب ملاءمة الجوف (مثبتة/بحذر/غير مناسبة)."""
    return list_high_value_crops(tier)


@app.get("/api/v1/high-value-crops/detail")
def high_value_crops_detail_endpoint(crop_ar: str):
    """تفصيل محصول عالي القيمة (جوجوبا/مورينجا/ألوفيرا/كينوا...)."""
    return high_value_crop_detail(crop_ar)


# ─── ٥٢. منتجات تصديريّة متخصّصة (موجة ثانية: أصماغ/توابل/أصباغ) ──
from api.niche_export_crops import list_niche_crops, niche_crop_detail  # noqa: E402


@app.get("/api/v1/niche-crops/list")
def niche_crops_list_endpoint(category: str | None = None):
    """منتجات تصديريّة متخصّصة عالية القيمة (صمغ عربي/جوار/حبّة سوداء/قرطم...)."""
    return list_niche_crops(category)


@app.get("/api/v1/niche-crops/detail")
def niche_crops_detail_endpoint(crop_ar: str):
    """تفصيل منتج متخصّص محدّد + ميزته اليمنيّة."""
    return niche_crop_detail(crop_ar)


# ─── ٥٣. زيوت عطريّة + أعلاف موفّرة للماء (موجة رابعة) ──
from api.aromatic_fodder_crops import list_aromatic_crops, list_fodder_alternatives  # noqa: E402


@app.get("/api/v1/aromatic-crops/list")
def aromatic_crops_list_endpoint():
    """نباتات عطريّة/زيوت أساسيّة متحمّلة للجفاف (قيمة عالية لكلّ قطرة ماء)."""
    return list_aromatic_crops()


@app.get("/api/v1/fodder-alternatives/list")
def fodder_alternatives_list_endpoint():
    """أعلاف موفّرة للماء بديلة للبرسيم المستنزف (Blue panic/سورغم...)."""
    return list_fodder_alternatives()


# ─── ٥٤. الريّ الذكي: قراءة مستشعر الرطوبة + قرار RWC ──
from api.soil_moisture_advisor import (  # noqa: E402
    irrigation_guidance,
    list_soil_types,
)


@app.get("/api/v1/irrigation/soil-types")
def irrigation_soil_types_endpoint():
    """أنواع التربة وقيمها المرجعيّة (سعة حقليّة/نقطة ذبول)."""
    return list_soil_types()


@app.get("/api/v1/irrigation/moisture-decision")
def irrigation_moisture_decision_endpoint(
    vwc: float,
    soil_type: str = "loam",
    crop: str | None = None,
    growth_stage: str | None = None,
    theta_fc: float | None = None,
    theta_wp: float | None = None,
    root_depth_m: float | None = None,
):
    """قرار ريّ ذكي من قراءة مستشعر الرطوبة (VWC → RWC → قرار + كمّيّة).

    vwc: الرطوبة الحجميّة من المستشعر (0-1). soil_type: sand/loam/clay.
    theta_fc/theta_wp: قيم مُعايَرة ميدانيّاً (اختياري، الأدقّ).
    root_depth_m: عمق منطقة الجذور لحساب كمّيّة الريّ (اختياري).
    """
    return irrigation_guidance(vwc, soil_type, crop, growth_stage, theta_fc, theta_wp, root_depth_m)


# ─── ٥٥. WOFOST عبر المحاصيل: دليل تعديل البارامترات ──
from api.wofost_crop_params import (  # noqa: E402
    list_supported_crop_types,
    wofost_adaptation_guidance,
)


@app.get("/api/v1/wofost/crop-types")
def wofost_crop_types_endpoint():
    """أنواع نماذج المحاصيل (حولي/شجرة/خضار/درنيّ) وإطار تعديل كلّ منها."""
    return list_supported_crop_types()


@app.get("/api/v1/wofost/adaptation-guidance")
def wofost_adaptation_endpoint(crop: str):
    """دليل تعديل بارامترات WOFOST لمحصول عن النموذج الأساسي (القمح).

    يُرجع نوع النموذج، نسبة التغيير، البارامترات الرئيسيّة (مع المدى والمصدر)،
    وتحذيرات الحدود — إرشاديّ للمعايرة لا قيم نهائيّة مُعايَرة لليمن.
    """
    return wofost_adaptation_guidance(crop)


# ─── ٥٦. فحص التناقض الزراعي + نضارة القرار ──
from api.agronomic_consistency import (  # noqa: E402
    check_decision_freshness,
    check_irrigation_consistency,
)


@app.get("/api/v1/consistency/irrigation")
def consistency_irrigation_endpoint(
    irrigation_delta_pct: float | None = None,
    rain_forecast_mm: float | None = None,
    soil_moisture_ratio: float | None = None,
    et0_mm: float | None = None,
    recommendation_confidence: float | None = None,
):
    """يفحص توصية ريّ ضدّ الظروف الحاليّة لكشف التناقضات المنطقيّة.

    مثال: زيادة ريّ + توقّع مطر غزير = تناقض يستوجب مراجعة. يُعلِم لا يحجب.
    """
    return check_irrigation_consistency(
        irrigation_delta_pct,
        rain_forecast_mm,
        soil_moisture_ratio,
        et0_mm,
        recommendation_confidence,
    ).to_dict()


@app.get("/api/v1/consistency/freshness")
def consistency_freshness_endpoint(
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
):
    """يفحص أعمار البيانات الداخلة في القرار (عتبات: NDVI≤5ي، تربة≤2ي، طقس≤6س)."""
    return check_decision_freshness(ndvi_age_days, soil_age_days, weather_age_hours).to_dict()


# ─── ٥٧. الحالة التشغيليّة الموحّدة للحقل ──
from api.field_operational_state import resolve_field_state  # noqa: E402


@app.get("/api/v1/field/operational-state")
def field_operational_state_endpoint(
    field_id: str,
    confidence_level: str | None = None,
    irrigation_delta_pct: float | None = None,
    rain_forecast_mm: float | None = None,
    soil_moisture_ratio: float | None = None,
    et0_mm: float | None = None,
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
):
    """يركّب النضارة + الثقة + التناقض في حالة تشغيليّة واحدة رسميّة.

    يُرجع: validity (valid/degraded/conflicted/insufficient) + نمط التنفيذ
    (auto/human_review/blocked) + الأسباب. تركيب شفّاف للمكوّنات الموجودة.
    """
    return resolve_field_state(
        field_id,
        confidence_level,
        irrigation_delta_pct,
        rain_forecast_mm,
        soil_moisture_ratio,
        et0_mm,
        ndvi_age_days,
        soil_age_days,
        weather_age_hours,
    ).to_dict()


# ─── ٥٧-ب. الحالة القانونيّة الموحّدة للحقل (Canonical Field State — Phase 1) ──
# مصدر الحقيقة الواحد للحالة الزراعيّة: على عكس /operational-state أعلاه (آلة
# حاسبة بلا مصادقة، يمرّر المتّصِل كلّ المدخلات)، هذه النقطة tenant-scoped وتجمع
# مدخلات القرار من مصادرها القانونيّة في قاعدة المنصّة بنفسها (نضارة NDVI/تربة/طقس)
# ثمّ تركّبها عبر نفس resolve_field_state. تُرجِع المدخلات أيضاً (شفافيّة التدقيق:
# أيّ مصدر دخل في القرار). الإسقاط المُخزَّن + توجيه بقيّة المستهلكين = مراحل لاحقة.
@app.get("/api/v1/fields/{field_id}/state")
async def field_canonical_state(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الحالة القانونيّة الموحّدة للحقل — مصدر حقيقة واحد للقرار/التنبيه/التوصية.

    يجمع نضارة NDVI (imagery_automation_fields) + التربة (soil_lab_tests) + الطقس
    (weather_automation_cache) من قاعدة المنصّة، يشتقّ الثقة من نضارة NDVI، يركّبها
    في validity (valid/degraded/conflicted/insufficient) + نمط التنفيذ، **ويحفظ
    النتيجة في إسقاط field_state (read model)** كي يقرأها بقيّة المستهلكين.
    صدق: غياب مصدر ⇒ عمره None ⇒ حالة «بيانات ناقصة» لا نضارة مُلفَّقة. 503 عند
    تعذّر القاعدة. يُرجِع inputs المستخدَمة للتدقيق.
    """
    from api.field_state_projection import recompute_field_state

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            result = await recompute_field_state(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة الحالة القانونيّة للحقل", e) from e

    return result["state"]


# ─── ٥٧-ب-٢. تنبيهات مُشتقّة من الحالة القانونيّة الموحّدة (Stage F — derived) ──
# على عكس POST /api/v1/alerts (محتواه من المتّصِل: title_ar/message_ar يدويّ)، هذه
# النقطة تشتقّ تنبيهات صادقة **من الحالة** (مثل مسار المايسترو الذي يقيّم الحالة
# الموحّدة): تُعيد حساب field_state ثمّ تشتقّ تنبيهات بسيطة من agronomic.operational_
# truths + نمط التنفيذ عبر دالّة نقيّة _derive_alerts_from_state (مُختبَرة بلا قاعدة).
# اشتقاق للعرض فقط: لا تكتب في جدول alerts ولا تُصدِر أحداثاً. صدق: لا حقائق ⇒ [].
@app.get("/api/v1/fields/{field_id}/alerts/derived")
async def field_alerts_derived(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تنبيهات الحقل المُشتقّة من الحالة القانونيّة الموحّدة (للعرض فقط).

    tenant-scoped (FIELD_VIEW): يستدعي recompute_field_state ثمّ يشتقّ تنبيهات صادقة
    من الحقائق الزراعيّة (ملوحة تربة حرجة) ونمط التنفيذ (blocked/human_review ⇒
    «القرار يحتاج مراجعة بشريّة»). لا يكتب في جدول alerts (اشتقاق للعرض). صدق: غياب
    الحقائق ⇒ {"alerts": []} لا تنبيه مُلفَّق. 404 إن غاب الحقل، 503 إن تعذّرت القاعدة.
    """
    from api.field_state_projection import _derive_alerts_from_state, recompute_field_state

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            state = (await recompute_field_state(conn, field_id))["state"]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("اشتقاق تنبيهات الحقل من الحالة القانونيّة", e) from e

    return {"field_id": field_id, "alerts": _derive_alerts_from_state(state)}


# ─── ٥٧-ج. قناة خدمة-لخدمة للحالة القانونيّة (للمنسّق/guardrails) ──
# يستدعيها supervisor بـX-Agent-Token + مستأجِر صريح ليُمرِّر الحالة لـguardrails،
# فتمرّ قرارات الحَوكمة عبر مصدر الحقيقة الواحد. **ليست تحت /api/** (لا يوجّهها
# nginx العامّ ⇒ غير قابلة للوصول من الإنترنت؛ داخليّة على الشبكة فقط).
def _require_service_token(x_agent_token: str | None = Header(None, alias="X-Agent-Token")) -> None:
    """يحمي النقاط الداخليّة بالتوكن الخدميّ (fail-closed): يُرفض إن غاب السرّ أو اختلف.

    المقارنة بزمن ثابت (hmac.compare_digest) لمنع تسريب السرّ عبر تحليل التوقيت.
    """
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected or not hmac.compare_digest(x_agent_token or "", expected):
        raise HTTPException(status_code=403, detail="نقطة داخليّة محميّة بـSAHOOL_AGENT_TOKEN")


@_asynccontextmanager
async def tenant_connection_for(tenant_id: str):
    """مثل tenant_connection لكن بمستأجِر صريح (لا user) — لقنوات الخدمة-لخدمة.

    ليس تجاوزاً لـRLS: يضبط app.current_tenant على المستأجِر المُمرَّر صراحةً فيظلّ
    العزل مفروضاً على ذلك المستأجِر فقط (الخدمة تتصرّف نيابةً عنه بعد تحقّق التوكن).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "       set_config('app.current_user_id', $2, true), "
                "       set_config('app.current_role', $3, true)",
                str(tenant_id),
                "service",
                "service",
            )
            yield conn


@app.get("/internal/fields/{field_id}/state")
async def internal_field_state(
    field_id: str,
    tenant_id: str = Query(..., description="معرّف المستأجِر الصريح (خدمة-لخدمة)"),
    _: None = Depends(_require_service_token),
):
    """الحالة القانونيّة للحقل لقنوات الخدمة (supervisor→guardrails).

    محميّة بـX-Agent-Token + مستأجِر صريح (عزل RLS عبر tenant_connection_for).
    404 إن لم يكن الحقل ضمن المستأجِر؛ 503 عند تعذّر القاعدة. تُعيد نفس عقد
    /api/v1/fields/{id}/state (validity/execution_mode/remote_sensing/inputs).
    """
    from api.field_state_projection import recompute_field_state

    try:
        async with tenant_connection_for(tenant_id) as conn:
            await _assert_field_in_tenant(conn, field_id)
            result = await recompute_field_state(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة الحالة القانونيّة (خدمة)", e) from e
    return result["state"]


# ─── ٥٨. حالة جدولة الأتمتة (مراقبة) ──
@app.get("/api/v1/automation/scheduler-status")
def scheduler_status_endpoint():
    """حالة المهامّ الدوريّة المُؤتمتة: آخر تشغيل/نجاح/فشل لكلّ مهمّة.

    للمراقبة التشغيليّة — يكشف إن توقّفت أتمتة (سحب طقس/صور) أو تكرّر فشلها.
    """
    from api.scheduler import scheduler

    return scheduler.status()


# ─── ٥٩. أتمتة الطقس (Open-Meteo دوريّاً) ──
from api.weather_automation import weather_automation  # noqa: E402


@app.post("/api/v1/automation/weather/register")
async def weather_register_endpoint(
    lat: float,
    lon: float,
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """يسجّل إحداثيّة لسحب طقسها تلقائيّاً (الجدولة تحدّثه دوريّاً).

    يُحفظ في القاعدة لو توفّرت (يبقى بعد إعادة التشغيل).
    H1 FIX: يتطلّب مصادقة — يمنع تسجيل/استنزاف مجهول لمهامّ السحب الدوريّة.
    """
    await weather_automation.register_location_persistent(lat, lon, field_id)
    return {
        "registered": True,
        "lat": lat,
        "lon": lon,
        "field_id": field_id,
        "total_registered": weather_automation.registered_count(),
        "note_ar": "ستُسحب بيانات الطقس تلقائيّاً ضمن الدورة القادمة.",
    }


@app.get("/api/v1/automation/weather/cached")
def weather_cached_endpoint(
    lat: float,
    lon: float,
    user: UserSchema = Depends(get_current_user),
):
    """يقرأ آخر طقس مسحوب تلقائيّاً لإحداثيّة (سريع، من الذاكرة)."""
    c = weather_automation.get_cached(lat, lon)
    if c is None:
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "note_ar": "لا طقس مُخزّن لهذه الإحداثيّة — سجّلها أوّلاً عبر /register.",
            },
        )
    return {"found": True, **c.to_dict()}


@app.get("/api/v1/automation/weather/status")
def weather_automation_status_endpoint(
    user: UserSchema = Depends(get_current_user),
):
    """حالة أتمتة الطقس: كم إحداثيّة مسجّلة وكم في الـcache."""
    return weather_automation.status()


# ─── ٦٠. أتمتة الصور الجوّية + المؤشّرات (Sentinel عبر raster-service) ──
from api.imagery_automation import imagery_automation  # noqa: E402


class ImageryFieldRegister(BaseModel):
    field_id: str
    bbox: list[float]  # [west, south, east, north]


@app.post("/api/v1/automation/imagery/register-field")
async def imagery_register_field_endpoint(
    req: ImageryFieldRegister,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """يسجّل حقلاً (bbox) لمتابعة صور Sentinel الجديدة تلقائيّاً.

    عند كلّ دورة جدولة: يُبحَث عن صور جديدة، وتُحسب المؤشّرات (NDVI) لها.
    يُحفظ في القاعدة لو توفّرت (يبقى بعد إعادة التشغيل، لا إعادة معالجة).
    الهويّة (tenant) من التوكن — تُمرَّر لـraster /process عند الحساب التلقائي.
    """
    try:
        await imagery_automation.register_field_persistent(
            req.field_id, req.bbox, tenant_id=str(user.tenant_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "registered": True,
        "field_id": req.field_id,
        "bbox": req.bbox,
        "total_tracked": imagery_automation.tracked_count(),
        "note_ar": "ستُفحَص صور Sentinel الجديدة وتُحسب مؤشّراتها تلقائيّاً.",
    }


@app.get("/api/v1/automation/imagery/status")
def imagery_automation_status_endpoint():
    """حالة أتمتة الصور: الحقول المتابَعة + آخر صورة/مؤشّر لكلّ حقل."""
    return imagery_automation.status()


# ─── ٦١. أتمتة تقييم التنبيهات (تشغيل دوريّ/عند الطلب لكلّ حقول المستأجِر) ──
# الكادينس (ثوان) الذي يُتوقَّع أن يُطلَق فيه التقييم الدوريّ لكلّ الحقول.
# يُعرَض في scheduler-status. الافتراض ٦ ساعات (توقّع الطقس يومي عمليّاً؛
# ٦ ساعات تلتقط تحوّلات الحرارة/المطر دون إغراق Open-Meteo). قابل للضبط عبر ENV.
ALERTS_EVAL_INTERVAL_SECONDS = int(os.getenv("SAHOOL_ALERTS_EVAL_INTERVAL_SECONDS", "21600"))


@app.post("/api/v1/automation/alerts/run")
async def automation_run_alerts_endpoint(
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُشغّل تقييم التنبيهات لكلّ حقول المستأجِر دفعةً واحدة (تشغيل عند الطلب).

    هذا هو المسار الذي يضربه جدولٌ خارجيّ (cron) أو الجدولة الداخليّة دوريّاً
    لتوليد تنبيهات الحقول تلقائيّاً بدل الانتظار لطلب يدويّ لكلّ حقل.

    معزول لكلّ حقل: فشل القاعدة/الطقس لحقل (مثلاً بلا إحداثيّات → 422، أو تعذّر
    Open-Meteo → 503) يُسجَّل في error ويُتخطّى — لا يُسقط بقيّة الحقول ولا يرفع
    500. tenant-isolated (RLS عبر tenant_connection + ترشيح tenant_id). يُرجع
    ملخّصاً لكلّ حقل {field_id, created, skipped} + إجماليّات.
    """
    from api.alert_rules import field_run_summary, summarize_run

    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT field_id FROM fields WHERE tenant_id = $1::uuid ORDER BY name",
                str(user.tenant_id),
            )
    except HTTPException:
        raise  # get_pool() ⇒ 503 (القاعدة معطّلة) — لا حقول لنقرأها أصلاً
    except Exception as e:  # noqa: BLE001 — تعذّر قراءة قائمة الحقول ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حقول المستأجِر", e) from e

    summaries: list[dict] = []
    for r in rows:
        fid = r["field_id"]
        try:
            created, skipped = await _evaluate_field_alerts_persist(user, fid)
            summaries.append(field_run_summary(fid, created=len(created), skipped=skipped))
        except HTTPException as he:  # 404/422/503 لحقل ⇒ تخطٍّ رشيق (لا 500)
            summaries.append(field_run_summary(fid, error=f"{he.status_code}: {he.detail}"))
        except Exception as e:  # noqa: BLE001 — أيّ خطأ آخر لحقل ⇒ تخطٍّ معزول
            logging.warning("automation alerts run: skipped field %s: %s", fid, type(e).__name__)
            summaries.append(field_run_summary(fid, error=type(e).__name__))

    return summarize_run(summaries)


@app.get("/api/v1/climate-analogs/strategy")
def climate_analogs_strategy_endpoint():
    """الاستراتيجيّة المركّبة للجوف (مزيج من المناطق) + اتّجاه Premium Desert Ag."""
    from api.climate_analogs import composite_strategy

    return composite_strategy()


# ─── استبيان دخول المزارع (ONBOARDING) ──────────────────────────
from api.onboarding import get_questionnaire  # noqa: E402
from api.onboarding import validate_response as _ob_validate  # noqa: E402


class OnboardingSubmitRequest(BaseModel):
    field_id: str | None = None
    answers: dict = {}


@app.get("/api/v1/onboarding/questionnaire")
async def onboarding_questionnaire(
    phase: int | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يُرجع تعريف الاستبيان (phase=1 للإلزامي فقط، بلا معامل للكلّ).

    مصمّم للسياق اليمني: offline-first، RTL، أسئلة إلزاميّة قليلة."""
    return get_questionnaire(phase=phase)


@app.post("/api/v1/onboarding/responses")
async def submit_onboarding(
    req: OnboardingSubmitRequest,
    # خدمة ذاتيّة لإعداد المستأجِر — مفتوحة عمداً لأيّ مستخدم مُصادَق (معزولة بالمستأجِر/RLS، لا حارس صلاحيّة).
    user: UserSchema = Depends(get_current_user),
):
    """يحفظ ردّ الاستبيان (عبر tenant_connection — RLS مُطبَّق).

    يتحقّق من اكتمال الحقول الإلزاميّة ويُرجع الناقص إن وُجد."""
    check = _ob_validate(req.answers)
    import json as _json

    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO onboarding_responses
                 (tenant_id, farmer_id, field_id, answers, is_complete, answered_count)
               VALUES ($1::uuid, $2, $3, $4::jsonb, $5, $6)
               RETURNING id""",
            str(user.tenant_id),
            str(user.user_id),
            req.field_id,
            _json.dumps(req.answers, ensure_ascii=False),
            check["valid"],
            check["answered"],
        )
    return {
        "id": row["id"] if row else None,
        "valid": check["valid"],
        "missing_required": check["missing"],
        "answered_count": check["answered"],
    }


@app.get("/api/v1/onboarding/responses")
async def list_onboarding(
    field_id: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يسرد ردود الاستبيان للمستأجر (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        if field_id:
            rows = await conn.fetch(
                "SELECT id, field_id, is_complete, answered_count, created_at "
                "FROM onboarding_responses WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, field_id, is_complete, answered_count, created_at "
                "FROM onboarding_responses ORDER BY created_at DESC LIMIT 100"
            )
    return {"responses": [dict(r) for r in rows]}


# ─── استقبال مزامنة edge مع dedup (Hardening مراجعة 7) ───────────
class EdgeSyncRequest(BaseModel):
    type: str
    data: dict
    idempotency_key: str | None = None
    occurred_at: str | None = None  # وقت حدوث القياس على الجهاز (مرجع سببي)
    device_id: str | None = None
    field_id: str | None = None


@app.post("/api/v1/edge/sync")
@app.post("/v1/edge/sync")
async def edge_sync_receive(
    req: EdgeSyncRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يستقبل نتيجة من جهاز edge ويكتبها مع منع التكرار.

    Hardening: ON CONFLICT على idempotency_key → إعادة الإرسال بعد انقطاع
    الشبكة لا تُكرّر الصفّ. الهويّة من التوكن لا الجسم (أمان)."""
    import json as _json

    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO edge_results
                 (field_id, tenant_id, result_type, device, offline_mode,
                  synced, result_data, idempotency_key, occurred_at)
               VALUES ($1, $2::uuid, $3, $4, true, true, $5::jsonb, $6,
                       COALESCE($7::timestamptz, NOW()))
               ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            req.field_id,
            str(user.tenant_id),
            req.type,
            req.device_id,
            _json.dumps(req.data, ensure_ascii=False),
            req.idempotency_key,
            req.occurred_at,
        )
    # row=None يعني التكرار رُفض (نجح سابقاً) — نُرجع نجاحاً (idempotent)
    return {
        "status": "stored" if row else "duplicate_ignored",
        "id": row["id"] if row else None,
        "idempotency_key": req.idempotency_key,
    }


# ─── Entry point للتطوير ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # P1-2: reload فقط في التطوير (SAHOOL_ENV=development)، مطفأ افتراضيّاً
    _reload = os.getenv("SAHOOL_ENV", "production").lower() == "development"
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=_reload,
        log_level="info",
    )


# ─── مرشد أخذ عيّنات التربة (البند ٣ تكملة) ──────────────────────
from api.zone_sampling import recommend_sampling_strategy, sampling_depth_advice  # noqa: E402


@app.get("/api/v1/sampling/strategy")
async def sampling_strategy(
    area_ha: float,
    has_history: bool = False,
    variability: str = "unknown",
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يوصي باستراتيجيّة أخذ عيّنات التربة (zone vs grid) + العدد + العمق.

    إرشادي — يوفّر تكلفة التحاليل (zone: 3-6 vs grid: ~عيّنة/هكتار)."""
    strat = recommend_sampling_strategy(area_ha, has_history, variability)
    strat["depth_advice"] = sampling_depth_advice(crop)
    return strat


# ═══════════════════════════════════════════════════════════════════
# Field Intelligence — endpoint التشغيل الحيّ للمايسترو
# يربط: auth → tenant → محوّلات حيّة → المايسترو → الحالة → حدث الحفظ
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/v1/field-intelligence/analyze")
def field_intelligence_analyze(
    field_id: str,
    lat: float | None = None,
    lon: float | None = None,
    crop: str | None = None,
    notify: bool = False,
    authorization: str = Header(None),
    user: UserSchema = Depends(get_current_user),
):
    """يُشغّل المسار الكامل للمايسترو لحقل ويُرجِع الحالة الموحّدة + القرار.

    سيادة البيانات: tenant_id من التوكن (موثوق) لا من الجسم (لا spoofing).
    المصادر: محوّلات HTTP حيّة (weather/soil/raster). المتعذّر يُعلَن بصدق.
    الحالة الناتجة جاهزة للحفظ في events (state_to_event_row) كذاكرة موسميّة.
    """
    from core.agronomic_state_engine import state_to_event_row
    from core.alert_engine import evaluate_alerts, summarize_alerts
    from core.correlation import set_correlation
    from core.field_intelligence_adapters import build_live_adapters
    from core.field_intelligence_coordinator import FieldRequest, run_field_intelligence

    # ربط موحّد: correlation_id يمرّ بكلّ ما ينتج عن هذا الطلب (workflow/
    # events/alerts) — لتتبّع "ماذا أنتج ماذا" عبر الخدمات (نمط OpenTelemetry).
    correlation_id = set_correlation()

    # tenant_id من التوكن الموثوق (لا من جسم الطلب — حماية multi-tenant)
    req = FieldRequest(field_id=field_id, lat=lat, lon=lon, crop=crop, tenant_id=user.tenant_id)
    # تمرير رأس التفويض للمحوّلات المحميّة (memory/simulate تنادي نقاط JWT داخليّة)
    adapters = build_live_adapters(authorization=authorization)
    result = run_field_intelligence(req, **adapters)

    state = result.canonical_state
    # التنبيهات الاستباقيّة: من الحالة الموحّدة (change_detection/FVC يُمرَّران عند
    # توفّرهما من العامل — هنا الحالة فقط، فالمحرّك سلبيّ→استباقيّ على ما هو متاح).
    alerts = evaluate_alerts(state)
    # التوصيل اختياريّ (notify=true): warning فأعلى عبر القنوات المُهيّأة. صدق:
    # الإرسال الخارجي يحدث فقط عند تهيئة القناة (لا ادّعاء إرسال).
    alerts_delivery = None
    if notify and alerts:
        from core.alert_delivery import deliver_alerts

        alerts_delivery = deliver_alerts(
            alerts,
            context={
                "field_id": state.field_id,
                "tenant_id": state.tenant_id,
                "now": state.generated_at,
            },
        )
    # حدث الحفظ جاهز (الكتابة الفعليّة في events عبر event_bus على بيئة التشغيل)
    try:
        event_row = state_to_event_row(state, actor_id=user.user_id)
    except ValueError:
        event_row = None  # بلا tenant — لا يُحفَظ (لن يحدث: tenant من التوكن)

    return {
        "field_id": state.field_id,
        "tenant_id": state.tenant_id,
        "generated_at": state.generated_at,
        "operational_truths": state.operational_truths,
        "confidence": state.confidence,
        "confidence_reason": state.confidence_reason,
        "provenance": state.provenance,
        "contradictions": state.contradictions,
        "missing_signals": state.missing_signals,
        "policy_decision": result.policy_decision,
        "governance": result.governance,
        "farm_memory_context": result.farm_memory_context,  # السياق التاريخي
        "correlation_id": correlation_id,  # خيط التتبّع الموحّد (OpenTelemetry-style)
        "simulation": result.simulation,  # أثر what-if المتوقّع
        "alerts": alerts,  # تنبيهات استباقيّة مُصنّفة (محرّك التنبيهات)
        "alerts_summary": summarize_alerts(alerts),
        "alerts_delivery": alerts_delivery,  # نتيجة التوصيل (إن notify=true)
        "_persistable_event": event_row,  # جاهز للإدراج في events table
    }


# ═══════════════════════════════════════════════════════════════════
# تحليل ماء الريّ — endpoint حيّ يستدعي irrigation_water_analysis (كان معزولاً)
# نقيّ-حسابيّ (SAR/RSC + تصنيف FAO-29/USDA-197/USSL)، بلا قاعدة. tenant من التوكن.
# ═══════════════════════════════════════════════════════════════════
class WaterAnalysisRequest(BaseModel):
    sample_id: str
    source: str = "well"  # well | canal | mixed
    na: float | None = None
    ca: float | None = None
    mg: float | None = None
    hco3: float | None = None
    co3: float | None = None
    cl: float | None = None
    ec_dsm: float | None = None
    ph: float | None = None
    sampled_at: str | None = None


@app.post("/api/v1/irrigation/water-analysis")
def irrigation_water_analysis(
    req: WaterAnalysisRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحلّل عيّنة ماء ريّ: SAR/RSC + تصنيف الملوحة/الصوديوم/القلويّة.

    صدق: يُعلِن المؤشّر غير المحسوب (نقص أيونات) صراحةً — لا تقدير مفبرَك.
    حسابيّ بحت (لا قاعدة)؛ التفويض مطلوب (سيادة الوصول)."""
    from core.irrigation_water_analysis import WaterSample, analyze_water_sample

    sample = WaterSample(**req.model_dump())
    return analyze_water_sample(sample)


# ═══════════════════════════════════════════════════════════════════
# تصعيد الآفة — endpoint حيّ يشغّل/يستأنف workflow تصعيد الآفة (كان معزولاً)
# يحقن المخزن المعمّر (PostgresWorkflowStore) إن DATABASE_URL مضبوط ⇒ الاستئناف
# يصمد عبر إعادة التشغيل؛ وإلّا InMemory (مفرد على مستوى العمليّة للتطوير).
# ═══════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
# مفرد InMemory لكلّ مستأجر (تطوير فقط). كان مفرداً واحداً مشتركاً يفهرس بـ
# workflow_id فقط ⇒ مستأجران بنفس workflow_id يتصادمان/يقرأ أحدهما حالة الآخر.
# عزلٌ بمخزن منفصل لكلّ tenant (الإنتاج يستعمل Postgres+RLS فلا يمسّه هذا).
_INMEM_WORKFLOW_STORES: dict = {}


def _get_workflow_store(tenant_id: str | None = None):
    """يُرجِع المخزن المعمّر (Postgres) إن توفّرت القاعدة، وإلّا مفرد InMemory
    معزول لكلّ مستأجر.

    tenant_id: سياق المستأجر لـRLS. workflow_state عليه RLS+FORCE، فالقراءة (load)
    تحتاج ضبط app.current_tenant وإلّا تُحجب الصفوف ⇒ الاستئناف لا يعمل. يُمرَّر
    للمخزن المعمّر ليضبطه عند load (الحفظ يأخذه من حالة الـworkflow). وفي مسار
    InMemory يفصل مخزن كلّ مستأجر (عزل تطويريّ — لا خلط workflow_id عبر المستأجرين).

    صدق: InMemory يُفقَد عند إعادة التشغيل (تطوير فقط)؛ الإنتاج (DATABASE_URL)
    يستعمل workflow_state (v16+v17) فيصمد التقدّم. PostgresWorkflowStore متزامن
    فوق asyncio.run ⇒ يُستدعى عبر thread من endpoint async (لا داخل الحلقة)."""
    from core.workflow_engine import InMemoryWorkflowStore, PostgresWorkflowStore

    dsn = os.getenv("DATABASE_URL", "")
    if dsn:
        return PostgresWorkflowStore(dsn, tenant_id=tenant_id)
    key = str(tenant_id or "")
    store = _INMEM_WORKFLOW_STORES.get(key)
    if store is None:
        store = InMemoryWorkflowStore()
        _INMEM_WORKFLOW_STORES[key] = store
    return store


class PestEscalationRequest(BaseModel):
    workflow_id: str
    field_id: str | None = None
    pest_type: str | None = None
    severity: float = 0.0
    # للاستئناف بعد التعليق: موافقة الخبير (approved) أو رفضه (rejected)
    approval_status: str | None = None


@app.post("/api/v1/pest-escalation/run")
async def pest_escalation_run(
    req: PestEscalationRequest,
    user: UserSchema = Depends(require_permission(Permission.PESTICIDE_APPROVE)),
):
    """يشغّل/يستأنف تدفّق تصعيد الآفة (durable + HIL).

    أوّل نداء (بـpest_type/severity): يصل لخطوة الموافقة ثمّ يُعلَّق (suspended).
    نداء ثانٍ بنفس workflow_id + approval_status=approved: يُستأنف فينفّذ ثمّ يُتابع.
    سيادة: tenant_id من التوكن (لا من الجسم). HIL: لا تنفيذ قبل موافقة الخبير."""
    import asyncio as _aio

    from core.correlation import set_correlation
    from core.pest_escalation_flow import run_pest_escalation
    from core.workflow_engine import workflow_trace

    set_correlation()  # خيط تتبّع موحّد لكلّ ما ينتج عن هذا الطلب
    initial: dict = {}
    if req.pest_type is not None:
        initial["pest_type"] = req.pest_type
    if req.severity:
        initial["severity"] = req.severity
    if req.field_id:
        initial["field_id"] = req.field_id
    if req.approval_status:
        initial["approval_status"] = req.approval_status

    store = _get_workflow_store(str(user.tenant_id))  # سياق RLS للقراءة/الاستئناف
    # المخزن المعمّر متزامن (asyncio.run داخليّاً) ⇒ نُشغّله في thread لا في الحلقة
    state = await _aio.to_thread(
        run_pest_escalation,
        req.workflow_id,
        store=store,
        tenant_id=str(user.tenant_id),
        initial_context=initial or None,
    )
    return {
        "workflow": workflow_trace(state),
        "context": state.context,
        "step_results": state.step_results,
    }


# ── OpenAPI FIX: إعادة بناء نماذج pydantic ذات التعليقات المؤجّلة ──────────
# مع `from __future__ import annotations` تصبح كل التعليقات نصوصاً مؤجّلة، فبعض
# النماذج (forward refs) تحتاج model_rebuild() وإلّا يفشل توليد مخطّط OpenAPI
# بـ500 (مثل OnboardingSubmitRequest) ويتعطّل /openapi.json وexport_openapi.py.
# نُعيد بناء كل نماذج هذه الوحدة بأمان بعد تعريفها جميعاً.
def _rebuild_pydantic_models() -> None:
    import sys as _sys

    _mod = _sys.modules[__name__]
    for _name in dir(_mod):
        _obj = getattr(_mod, _name, None)
        try:
            if isinstance(_obj, type) and issubclass(_obj, BaseModel) and _obj is not BaseModel:
                _obj.model_rebuild()
        except Exception:  # noqa: BLE001 — إعادة البناء أفضل-جهد، لا تُفشل الإقلاع
            pass


_rebuild_pydantic_models()
