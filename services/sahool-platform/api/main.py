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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

# جعل النواة قابلة للاستيراد
sys.path.insert(0, str(Path(__file__).parent.parent))

import jwt  # PyJWT
from core.api_adapter import (
    handle_healthz,
    handle_readyz,
)
from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema
from core.offline_first import OfflineQueue
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
    row_version: int | None = None  # عمّاد التزامن التفاؤليّ (v61) — يتزايد كلّ تحديث


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
    # تزامن تفاؤليّ (v61، اختياريّ/متوافق رجعيّاً): إصدار الحقل الأساس وقت قراءة
    # العميل. إن مُرِّر ولم يطابق row_version الحاليّ ⇒ 409 تعارض (كشف تعديل متباعد
    # offline). ليس عموداً يُكتَب — مستثنى من _build_field_update (ليس في الأعمدة).
    base_version: int | None = Field(default=None, ge=1)


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


def _build_versioned_update(
    set_clause: str, values: list, field_id: str, base_version: int | None
) -> tuple[str, list]:
    """يبني UPDATE الحقل مع رفع row_version دائماً + حارس تزامن تفاؤليّ اختياريّ — نقيّ.

    - يُلحق ``row_version = row_version + 1`` بجملة SET فيتغيّر الإصدار كلّ كتابة.
    - field_id يأخذ placeholder ``${len(values)+1}`` في WHERE.
    - إن مُرِّر ``base_version`` (اختيار العميل): يُضاف ``AND row_version = ${…+2}``
      فلا يطابق الصفّ إلّا إن لم يتغيّر منذ قراءة العميل ⇒ كتابة قديمة تُصيب 0 صفّ
      (يترجمها الـendpoint إلى 409). غيابه ⇒ سلوك سابق (لا فحص، متوافق رجعيّاً).

    يُرجِع (sql, exec_values). لا I/O.
    """
    field_idx = len(values) + 1
    sql = (
        f"UPDATE fields SET {set_clause}, row_version = row_version + 1 "
        f"WHERE field_id = ${field_idx}"
    )
    exec_values = [*values, field_id]
    if base_version is not None:
        sql += f" AND row_version = ${field_idx + 1}"
        exec_values.append(base_version)
    return sql, exec_values


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


# نقاط /api/v1/auth/{login,me,logout,signup} نُقلت إلى api/routers/auth.py (نمط P0).
# نقطة /api/v1/me نُقلت إلى api/routers/me.py (نمط P0). النماذج (LoginRequest/
# TokenResponse) والتبعيات/الأسرار تبقى هنا وتُستورَد من الموجِّهات (نماذج/تبعيات لا تُنقَل).


# نقطتا /api/v1/recommendations و /api/v1/recommendations/for-field نُقلتا إلى
# api/routers/recommendations.py (نمط P0) — النموذج FieldRecommendationRequest
# يبقى هنا (لا تُنقَل النماذج).
class FieldRecommendationRequest(BaseModel):
    field_id: str
    farm_id: str = ""
    crop: str
    current_indicators: dict = Field(default_factory=dict)
    growth_stage: str | None = None
    district_id: str | None = None


# نقطة /api/v1/observations نُقلت إلى api/routers/observations.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


# نقطة /api/v1/sync نُقلت إلى api/routers/sync.py (نمط P0) — والاستيرادات المرافقة
# (OperationKind/SyncStatus/apply_supersession/record_operation_offline من
# core.offline_first) نُقلت معها لإزالة F401. النموذج SyncBatchRequest يبقى هنا.


# نقطة /api/v1/queue/status نُقلت إلى api/routers/queue.py،
# /api/v1/capabilities إلى api/routers/capabilities.py، و/api/v1/reports/build إلى
# api/routers/reports.py (مع بقيّة /reports) — نمط P0.


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
            # Canonical Field State: إنشاء حقل يُنشئ سياق القرار ⇒ أعِد حساب
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
                        "trigger": "field.created",
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
        row_version=_i("row_version"),
    )


# أعمدة SELECT لقراءة الحقل التفصيليّة: أساس الملخّص + الأعمدة المتقدّمة (v37).
_FIELD_DETAIL_SELECT = (
    "field_id, farm_id, name, area_ha, crop, soil_type, manager, "
    "field_code, description, water_source, ownership_type, country, region, "
    "lat, lon, geometry, row_version, " + ", ".join(_FIELD_ADVANCED_COLUMNS)
)


# ─── حدود الحقل: provenance + مراجعة بشريّة (HIL) — #15 ───────────────────
# مجموعة حالات المراجعة المسموحة (تطابق قيد CHECK في v58:
# field_boundaries_review_status_chk). 'unreviewed' هي القيمة الافتراضيّة في
# القاعدة، فلا نقبلها كانتقال صريح من الواجهة — المراجِع يَنتقل إلى قرار نهائيّ.
_BOUNDARY_REVIEW_STATES = {"approved", "rejected", "needs_edit"}


class BoundaryReviewRequest(BaseModel):
    """طلب مراجعة بشريّة (HIL) لحدّ الحقل — قرار المراجِع النهائيّ.

    review_status: واحدة من approved|rejected|needs_edit (يُتحقّق منها مقابل
    _BOUNDARY_REVIEW_STATES فيردّ 422 على ما عداها قبل لمس القاعدة).
    """

    review_status: str = Field(..., max_length=20)


class BoundaryScoreRequest(BaseModel):
    """طلب تهديف ثقة حدّ الحقل من خصائصه البنيويّة.

    props: خصائص قابلة للحساب عن الحدّ (vertex_count, area_ha, is_valid,
    ring_count, self_intersections, temporal_agreement?) — تُمرَّر كما هي إلى
    score_boundary (دالّة نقيّة حتميّة). source_type اختياريّ يُسجَّل provenance.

    props أصبحت اختياريّة (#15): إن لم تُرسَل (None) يَشتقّ الخادم الخصائص
    البنيويّة من field_boundaries.geom المخزَّنة عبر استعلام PostGIS واحد ثمّ
    يهدّفها — مع بقاء التوافق الخلفيّ عند إرسالها صراحةً.
    """

    props: dict | None = Field(default=None)
    source_type: str | None = Field(default=None, max_length=30)


# ─── حدود الحقل: تنظيف طوبولوجيّ (v59) + شبكة الجوار (#15) ────────────────


class BoundaryCleanRequest(BaseModel):
    """طلب تنظيف طوبولوجيّ حتميّ لحدّ الحقل المخزَّن (v59).

    tolerance_m: وحدة تحمّل التبسيط بالمتر (افتراضيّ 5.0) — تُمرَّر إلى
    sahool_clean_boundary_geom التي تحوّلها داخليّاً إلى درجات (تقريب صالح قرب
    خطوط عرض اليمن — انظر تعليق الـmigration).
    """

    tolerance_m: float = Field(default=5.0)


# نقاط حدود الحقل الخمس (review/score/clean/boundary-graph) نُقلت إلى
# api/routers/boundaries.py وتُسجَّل عبر app.include_router في نهاية الوحدة.
# نماذج الطلب أعلاه تبقى هنا (تُستورَد من الموجِّه) حفاظاً على
# _rebuild_pydantic_models واستيرادات الاختبارات.


# نقطة /api/v1/geo/reverse نُقلت إلى api/routers/geo.py (نمط P0) — والمساعِد
# _reverse_geocode يبقى هنا (يستخدمه أيضاً معالِج إنشاء الحقل) ويُستورَد من الموجِّه.


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


# نقطة /api/v1/seasons/{season_id}/simulate نُقلت إلى api/routers/seasons.py (نمط P0).
# النموذج SeasonSimResponse والثابت _SIM_MAX_WINDOW_DAYS يبقيان هنا ويُستورَدان من
# الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


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


# ─── سياسة محرّكات التوصيات لكلّ مستأجِر (Dynamic Recommendation Policy) ─
# المستأجِر يضبط أيّ محرّكات تعمل عبر نقطة الإعدادات الموجودة (لا نقطة كتابة جديدة):
#   PUT /api/v1/settings  مع  scope='platform', key='recommendation_engines',
#   value مثل {"disabled": ["yield"]}  أو  {"enabled": ["irrigation", "disease"]}.
# القراءة تمرّ عبر الاتّصال المنطاقيّ (RLS يحصرها بالمستأجِر الحاليّ تلقائيّاً). صدق
# وتوافق خلفيّ صارم: عند غياب السياسة (أو أيّ خطأ) نُرجع None ⇒ السلوك مطابق لليوم.


async def _resolve_recommendation_policy(raw_value) -> set[str] | None:
    """يحوّل قيمة السياسة الخام (JSONB) إلى مجموعة مُعرّفات مُفعَّلة، أو None.

    دالّة نقيّة (لا قاعدة): تُفصَل عن القراءة كي يُعاد استخدامها في نقطة الاستبطان.
    تدعم شكلين متبادلين حصريّاً:
      • {"disabled": [...]} ⇒ المُفعَّل = كلّ المحرّكات المعروفة ناقص المُعطَّلة.
      • {"enabled":  [...]} ⇒ المُفعَّل = هذه المُعرّفات فقط (مقاطَعة مع المعروفة).
    أيّ شكل آخر (الاثنان معاً/لا شيء/فارغ/مُشوَّه) ⇒ None ⇒ «كلّ الافتراضيّ» (دون تغيير).
    """
    from api.recommendations_hub import list_engines

    if not isinstance(raw_value, dict):
        return None
    known = {e["id"] for e in list_engines()}
    has_disabled = "disabled" in raw_value
    has_enabled = "enabled" in raw_value
    # الشكلان حصريّان: وجود الاثنين أو غيابهما معاً ⇒ سياسة غير محدَّدة ⇒ None.
    if has_disabled == has_enabled:
        return None
    if has_disabled:
        disabled = raw_value.get("disabled")
        if not isinstance(disabled, list) or not disabled:
            return None
        return known - {str(x) for x in disabled}
    enabled = raw_value.get("enabled")
    if not isinstance(enabled, list) or not enabled:
        return None
    return known & {str(x) for x in enabled}


async def _load_recommendation_policy(conn) -> set[str] | None:
    """يقرأ سياسة محرّكات التوصيات للمستأجِر من جدول settings (best-effort).

    يستعلم الاتّصال المنطاقيّ (RLS يحصره بالمستأجِر): scope='platform',
    key='recommendation_engines'. القيمة JSONB قد تعود dict أو نصّاً (نُحلّله).
    أيّ خطأ (لا قاعدة، لا جدول، JSON مُشوَّه) ⇒ None — لا نرفع أبداً في مسار الطلب،
    فيبقى السلوك مطابقاً لليوم عند غياب السياسة.
    """
    import json as _json

    try:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE scope = 'platform' AND key = 'recommendation_engines'"
        )
        if row is None:
            return None
        value = row["value"]
        if isinstance(value, str):
            value = _json.loads(value)
        return await _resolve_recommendation_policy(value)
    except Exception:  # noqa: BLE001 — best-effort: أيّ خطأ ⇒ None (سلوك افتراضيّ)
        logging.exception("recommendation policy load failed; defaulting to all engines")
        return None


# نقطة /api/v1/recommendations/engines نُقلت إلى api/routers/recommendations.py
# (نمط P0) — المساعِد _resolve_recommendation_policy يبقى هنا (تبعية مشتركة).


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


# نقطتا /api/v1/tasks و/api/v1/tasks/{task_id} نُقلتا إلى api/routers/tasks.py (نمط P0).
# النماذج/الثوابت/المساعِدات (TaskListResponse/TaskSummary/TaskUpdateRequest/_TASK_COLS/
# _TASK_STATUSES/_row_to_task) تبقى هنا وتُستورَد من الموجِّه (حفظاً
# لـ_rebuild_pydantic_models/الاختبارات).


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


# نقاط /api/v1/alerts (قائمة/إنشاء/إقرار) نُقلت إلى api/routers/alerts.py (نمط P0).
# النماذج/الثوابت/المساعِدات (AlertSummary/AlertCreateRequest/_ALERT_*/_row_to_alert/
# _log_alert_deliveries) تبقى هنا وتُستورَد من الموجِّه (حفظاً
# لـ_rebuild_pydantic_models/الاختبارات).


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

    from api.alert_rules import (
        FieldAlertContext,
        evaluate_field_alerts,
        thresholds_from_policy,
    )
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    # سياسة عتبات التنبيهات لكلّ مستأجِر (best-effort): تُضبَط عبر النقطة الموجودة
    #   PUT /api/v1/settings  مع scope='platform', key='alert_thresholds',
    #   value = قاموس تجاوزات (مثل {"low_moisture_pct": 20}).
    # نقرؤها داخل الاتّصال المنطاقيّ القائم (RLS يحصره بالمستأجِر). أيّ خطأ ⇒ None،
    # و thresholds_from_policy(None) يُرجع الافتراضات ⇒ سلوك مطابق تماماً للسابق.
    alert_policy = None
    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage = await _field_weather_context(conn, field_id)
            # رطوبة تربة حيّة من telemetry الأجهزة (إن وُجدت) — تُغذّي قاعدة low_moisture.
            soil_reading = await _latest_soil_moisture(conn, field_id)
            try:
                _policy_row = await conn.fetchrow(
                    "SELECT value FROM settings "
                    "WHERE scope = 'platform' AND key = 'alert_thresholds'"
                )
                if _policy_row is not None:
                    alert_policy = _policy_row["value"]
                    # القيمة JSONB قد تعود نصّاً — نُحلّله إلى قاموس.
                    if isinstance(alert_policy, str):
                        import json as _json

                        alert_policy = _json.loads(alert_policy)
            except Exception:  # noqa: BLE001 — best-effort: أيّ خطأ ⇒ None (افتراضات)
                alert_policy = None
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
    # نمرّر عتبات المستأجِر (أو الافتراضات حين لا سياسة). thresholds_from_policy(None)
    # == AlertThresholds() ⇒ مسار «لا سياسة» مطابق تماماً للسلوك السابق.
    generated = evaluate_field_alerts(ctx, thresholds=thresholds_from_policy(alert_policy))

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


# نقاط /api/v1/farms (إنشاء/قائمة/حقول-المزرعة) نُقلت إلى api/routers/farms.py (نمط P0).
# النموذج FarmCreateRequest يبقى هنا ويُستورَد من الموجِّه (حفظاً
# لـ_rebuild_pydantic_models/الاختبارات).


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


# نقاط /api/v1/irrigation/{valves,valves/{id}/state,schedules,schedules/{id}}
# نُقلت إلى api/routers/irrigation.py (نمط P0) — النماذج والمساعِدات (_parse_time
# وValve*/Schedule*Request) تبقى هنا (لا تُنقَل النماذج/التبعيات).


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


# نقاط /api/v1/master-data نُقلت إلى api/routers/master_data.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


# ─── الإعدادات (Settings) — منصّة/مزرعة/ريّ/إشعارات — (v28) ───────
class SettingRequest(BaseModel):
    scope: str = Field(pattern="^(platform|farm|irrigation|notification)$")
    key: str = Field(min_length=1, max_length=80)
    value: dict | None = None


# نقاط /api/v1/settings نُقلت إلى api/routers/settings.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


# ─── تكوين المستأجِر (Tenant Config) — هويّة/وحدات/لغة/محاصيل — (#13) ─
# نقطة /api/v1/tenant/config نُقلت إلى api/routers/tenant.py (نمط P0).


# ─── تحليلات التكاليف الفعليّة (Cost Analytics) ──────────────────
# يستبدل ملخّص التكاليف الثابت في ReportsPage. يُجمّع تكاليف حقيقيّة من جداول
# قائمة: field_tasks.actual_cost_usd + equipment_maintenance.cost_usd. لا ترحيل.


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


# نقاط /api/v1/reports/{farm-summary,field/{id}/summary,season/{id}/summary}
# نُقلت إلى api/routers/reports.py (نمط P0).


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


# نقاط /api/v1/documents نُقلت إلى api/routers/documents.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


# ═══════════════════════════════════════════════════════════════════
#   Open-Meteo Weather Integration (مجاني، بدون مفتاح)
# ═══════════════════════════════════════════════════════════════════


# ─── TrueUp (yield calibration) — موصَّل end-to-end ──────────────
# جلسة التصحيح الذاتي: بند ١ — توصيل وحدة واحدة فعلاً بدل الجزر المعزولة.
# TrueUpEngine.compute هو pure logic (مُختبَر في test_v12_modules.py: 23/23).
# هنا نوصّله بـendpoint حقيقي. الـpersist (apply) يحتاج DB pool — يُفعّل
# عند توفّر PostgreSQL؛ حتّى ذلك الحين الـendpoint يحسب ويُرجع النتيجة.

from api.trueup import TrueUpEngine  # noqa: E402

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


# ─── Geometry validation — موصَّل end-to-end ─────────────────────
# جلسة التصحيح الذاتي: توصيل وحدة ثانية. geospatial_integrity.py مُختبَر
# (test_geospatial.py: 29/29). هذا الـendpoint يستخدمه للتحقّق من حدود الحقل
# قبل الحفظ — يمنع CRS mismatch + self-intersection + إحداثيّات خارج اليمن.

from api.geospatial_integrity import validate_field_geometry  # noqa: E402


class GeometryValidateRequest(BaseModel):
    geojson: dict
    declared_crs: str | None = None


# ═══════════════════════════════════════════════════════════════
# توصيل الوحدات pure-logic المتبقّية (جلسة "بناء الكل")
# كلّها مُختبَرة كـpure logic؛ هنا نوصّلها بـendpoints حقيقيّة.
# الوحدات التي تحتاج DB (command_store, event_bus, event_replay, sharing,
# data_lineage) تبقى غير موصَّلة حتّى توفّر PostgreSQL — لا نزيّف توصيلها.
# ═══════════════════════════════════════════════════════════════

# ─── ١. Prescriptions (variable-rate N) ──────────────────────────
from api.prescriptions import PrescriptionGenerator  # noqa: E402

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


# ─── ٢. Yield estimate ───────────────────────────────────────────


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


# ─── ٣. Confidence (NDVI) ────────────────────────────────────────


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


# ─── ٤. Confidence aggregation (recommendation-level) ────────────
# (نُقل استيراد irrigation_confidence إلى api/routers/confidence.py بعد نقل
#  المعالِج — لم يبقَ له مستخدِم في main.py.)


class IrrigationConfRequest(BaseModel):
    ndvi_confidence: float | None = None
    et0_confidence: float | None = None
    soil_moisture_confidence: float | None = None
    weather_forecast_confidence: float | None = None


# ─── ٥. Failure detection ────────────────────────────────────────
# نقطة /api/v1/failures/check نُقلت إلى api/routers/failures.py (نمط P0) —
# والاستيرادات المرافقة (detect_sentinel_issues/detect_soil_issues/
# detect_weather_issues) نُقلت معها لإزالة F401. النموذج FailureCheckRequest
# يبقى هنا (يُستورَد من الموجِّه + _rebuild_pydantic_models).


class FailureCheckRequest(BaseModel):
    cloud_pct: float | None = None
    days_since_observation: int | None = None
    weather_hours_since_update: int | None = None
    soil: dict | None = None


# ─── ٦. Temporal arbitration ─────────────────────────────────────
# (نُقل استيراد DataSource/Measurement/TemporalArbiter إلى
#  api/routers/temporal.py بعد نقل المعالِجَين — لم يبقَ لها مستخدِم في main.py.)


class MeasurementInput(BaseModel):
    source: str  # DataSource value
    timestamp: str  # ISO
    value: float | None = None


class TemporalCheckRequest(BaseModel):
    measurements: list[MeasurementInput]
    crop: str | None = None
    stage: str | None = None


# ─── ٧. Reports (operation CSV) ──────────────────────────────────
# نقطة /api/v1/reports/operation نُقلت إلى api/routers/reports.py (نمط P0)؛
# واستيرادا fastapi PlainTextResponse و api.reports نُقلا معها لإزالة F401.
# النموذجان ReportFieldInput/OperationReportRequest يبقيان هنا (لا تُنقَل النماذج).


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


# ─── ٨. Field lifecycle transition validation (pure) ─────────────
# نقطة /api/v1/lifecycle/validate-transition نُقلت إلى api/routers/lifecycle.py (نمط P0).
# النموذج TransitionCheckRequest يبقى هنا ويُستورَد من الموجِّه (حفظاً
# لـ_rebuild_pydantic_models/الاختبارات)؛ LifecycleStage/is_valid_transition صارتا
# يتيمتين هنا فاستُورِدتا في الموجِّه من api.field_lifecycle مباشرةً.


class TransitionCheckRequest(BaseModel):
    from_stage: str
    to_stage: str


# ─── ٩. Event replay — state reconstruction (pure) ───────────────
# نقطة /api/v1/replay/reconstruct نُقلت إلى api/routers/replay.py (نمط P0).
# النموذج ReplayRequest يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/
# الاختبارات)؛ FieldStateReconstructor صار يتيماً هنا فاستُورِد في الموجِّه من
# api.event_replay مباشرةً.


class ReplayRequest(BaseModel):
    entity_type: str
    entity_id: str
    events: list[dict]  # [{event_type, occurred_at, payload}, ...]


# ─── ١٠. Field Timeline (المرحلة ١، البند ٧) ─────────────────────
# خطّ زمني موحّد لكلّ ما حدث على الحقل. pure assembler (يأخذ الأحداث).
# النسخة المُوصَّلة بالـDB (تجلب من events table) تحتاج PostgreSQL.


class TimelineRequest(BaseModel):
    field_id: str
    events: list[dict]
    newest_first: bool = True
    category_filter: list[str] | None = None


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


# نقطة /api/v1/simulate/what-if نُقلت إلى api/routers/simulate.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).


# ─── ١١. Scouting Pins (المرحلة ١، البند ٨) ──────────────────────
# مشاهدات ميدانيّة: GPS + صورة + taxonomy يمنيّة + شدّة + حالة + موسمي/دائم.
# التحقّق والـtaxonomy هنا (pure)؛ الحفظ في الموبايل SQLite + mediaStore + syncEngine.

# كتالوجات scouting (NUTRIENT_DEFICIENCY_GUIDE/YEMEN_CROP_ISSUES/get_crop_issues)
# انتقل استعمالها مع نقطة /api/v1/scouting/taxonomy إلى api/routers/scouting.py.


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


# نقطة /api/v1/scouting/taxonomy نُقلت إلى api/routers/scouting.py (نمط P0).


# ─── ١٢. Manual Application Mode (المرحلة ١، البند ٩) ────────────
# يحوّل وصفة kg/ha إلى خطة مشي قابلة للتنفيذ (كغ/مصطبة، أغطية/خزّان،
# سقايات/شجرة) + PDF عربي للطباعة. يبني على prescriptions.py.
from api.manual_converter import ApplicationMethod, EquipmentSpec  # noqa: E402
from api.walk_plan import ZoneRateInput, generate_walk_plan  # noqa: E402


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


# ─── ١٣. Sharing key generation (سدّ فجوة جزئي) ──────────────────
# توليد مفتاح مشاركة (نموذج "المهندس الزراعي الموثوق" من FieldView).
# التوليد والـhashing pure؛ الحفظ/التحقّق في DB يحتاج PostgreSQL pool
# (يبقى غير موصَّل بصدق — SharingKeyService.create_key/validate_key).
# الـendpoint POST /api/v1/sharing/generate-key مُستخرَج إلى routers/sharing.py.


class ShareKeyRequest(BaseModel):
    scope: str = "read"  # read | read_write
    third_party_name: str | None = None
    third_party_type: str | None = None  # advisor | dealer | ministry | researcher | other
    allowed_field_ids: list[str] = []
    expires_in_days: int = 30


# ─── ١٤. الوحدات المعتمدة على PostgreSQL (سدّ الفجوة ١) ──────────
# توصيل command_store / event_bus / data_lineage / sharing (الحفظ).
# نقاط الاستبطان نُقلت إلى موجِّهات P0:
#   GET /api/v1/lineage/{entity_type}/{entity_id} → api/routers/lineage.py
#   GET /api/v1/events/{entity_type}/{entity_id}  → api/routers/events.py
#   GET /api/v1/commands/{command_id}             → api/routers/commands.py
# LineageAssembler/EventBus صارا يتيمين هنا فاستُورِدا في موجِّهيهما من وحدتيهما
# الحقيقيّتين مباشرةً (data_lineage/event_bus). CommandStore يبقى مُستورَداً هنا لأنّ
# موجِّهات أخرى (fields/irrigation) تستورده من api.main (إعادة تصدير).
from api.command_store import CommandStore  # noqa: E402, F401  (إعادة تصدير لموجِّهات أخرى)


class SharingKeyCreateRequest(BaseModel):
    scope: str = "read"
    valid_days: int = 30
    third_party_name: str | None = None
    third_party_type: str | None = None
    allowed_field_ids: list[str] = []


# المساران POST/GET /api/v1/sharing/keys مُستخرَجان إلى routers/sharing.py.


# ─── ١٥. محرّك التجارب t-test/LSD (المرحلة ٢، البند ١١) ──────────
# الميزة الرئيسيّة لـ"الصدق الإحصائي": يُجيب هل الفرق مؤكّد أم تباين طبيعي.
# نقطة /api/v1/trials/analyze نُقلت إلى api/routers/trials.py (نمط P0).
# النماذج تبقى هنا وتُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class TrialBlockInput(BaseModel):
    block_number: int
    treatment_yield: float
    control_yield: float


class TrialAnalysisRequest(BaseModel):
    blocks: list[TrialBlockInput]
    confidence_level: float = 0.95
    treatment_label_ar: str = "المعالجة الجديدة"


# ─── ١٦. ميزان الماء ET0 (المرحلة ٢، البند ١٢) ──────────────────
# توصية ريّ FAO-56 (Penman-Monteith / Hargreaves) — أزمة مياه اليمن.
# نقطة /api/v1/water-balance نُقلت إلى api/routers/water_balance.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
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


# ─── ١٧. قواعد 4R للتربة الكلسيّة (المرحلة ٢، البند ١٣) ──────────
# توصية تسميد محجوبة حتى توفّر تحليل مختبر (الاستشعار يوجّه/المختبر يحكم).
# نقطة /api/v1/nutrients/4r-plan نُقلت إلى api/routers/nutrients.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class Soil4RRequest(BaseModel):
    caco3_pct: float | None = None
    ph: float | None = None
    p_ppm: float | None = None
    fe_ppm: float | None = None
    zn_ppm: float | None = None
    om_pct: float | None = None
    nutrients: list[str] | None = None


# ─── ١٨. مناطق NDVI k-means (المرحلة ٣، البند ١٤) ───────────────
# اقتراح مناطق إدارة من NDVI (بديل منخفض التكلفة) — للفحص لا للقرار الآلي.


class ZoneCellInput(BaseModel):
    cell_id: str
    value: float
    confidence: float = 1.0


class ZoningRequest(BaseModel):
    cells: list[ZoneCellInput]
    n_zones: int = 3


# ─── ١٩. تتبّع GDD (المرحلة ٣، البند ١٥) ────────────────────────
# النموّ بالحرارة المتراكمة لا بالأيّام — توقيت أدقّ للريّ/التسميد/الحصاد.
# نقطة /api/v1/gdd/track نُقلت إلى api/routers/gdd.py (نمط P0).
# النماذج تبقى هنا وتُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class DailyTempInput(BaseModel):
    t_min_c: float
    t_max_c: float


class GDDRequest(BaseModel):
    crop: str
    temps: list[DailyTempInput]


# ─── ٢٠. تشخيص بقواعد الأعراض (المرحلة ٣، البند ١٦) ─────────────
# شجرة قواعد شفّافة (لا ML) — تربط الأعراض بمرشّحين + توصية تأكيد بشري.


class DiagnoseRequest(BaseModel):
    crop: str
    symptoms: list[str]
    # تغذية آمنة اختياريّة: عند تمرير field_id نُرفِق سياق الحالة القانونيّة
    # الموحّدة بالاستجابة. غيابه (None) ⇒ السلوك الحاليّ تماماً (لا إرفاق).
    field_id: str | None = None


# ─── ٢١. بوابة الثقة الموحّدة (مُستلهَمة من DSS، مُكيّفة بصدق) ────
# تجمع إشارات المحرّكات وتقرّر: واثقة/مراجعة/محجوبة. لا ML غامض.
# نقطة /api/v1/confidence-gate نُقلت إلى api/routers/confidence_gate.py (نمط P0) —
# والاستيرادان المرافقان (EngineSignal/evaluate) نُقلا معها لإزالة F401. النماذج
# (EngineSignalInput/ConfidenceGateRequest) تبقى هنا (تُستورَد من الموجِّه).


class EngineSignalInput(BaseModel):
    engine: str
    has_recommendation: bool
    confidence: float
    blocking_reason_ar: str | None = None
    data_gaps_ar: list[str] = []


class ConfidenceGateRequest(BaseModel):
    signals: list[EngineSignalInput]


class EscalationAssessRequest(BaseModel):
    """تقييم تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG)."""

    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = Field(min_length=1, max_length=60)
    has_answer: bool = True
    uncertain_points: list[str] = Field(default_factory=list)


class ExternalPriorBlendRequest(BaseModel):
    """مزج سابقة خارجيّة منشورة (مشروع/ورقة) ببيانات اليمن المتراكمة — وزن تدرّجي."""

    external_prior: float | None = None
    local_estimate: float | None = None
    n_local: int = Field(default=0, ge=0)
    crop_grown_in_yemen: bool
    external_credibility: float = Field(default=0.5, ge=0, le=1)


# ─── ٢٢. اكتمال البيانات + ملاءمة المحاصيل (مُستلهَم من المستندَين) ─
# ملاحظة: نقطة /api/v1/crop-suitability نُقلت إلى api/routers/crop_suitability.py
# (نمط P0) — والاستيراد المرافق (FieldConditions/rank_crops) نُقل معها لإزالة F401.
# نموذج CropSuitabilityRequest يبقى هنا (يُستورَد من الموجِّه + _rebuild_pydantic_models).


# نقطة /api/v1/data-readiness نُقلت إلى api/routers/data_readiness.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class ReadinessRequest(BaseModel):
    provided_fields: list[str]


class CropSuitabilityRequest(BaseModel):
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True
    crops: list[str] | None = None


# نقطة /api/v1/crop-suitability نُقلت إلى api/routers/crop_suitability.py (نمط P0).


# ─── ٢٣. سيناريوهات "ماذا لو" الفيزيائيّة (مُستلهَم من ورقة DT) ──
# حساب فيزيائي offline فوق ميزان الماء/GDD — لا توأم رقمي، لا M2M، لا ML.
# نقاط /api/v1/scenario/* نُقلت إلى api/routers/scenario.py (نمط P0) — والاستيرادات
# المرافقة (DailyTemp/WeatherInput/whatif_*) نُقلت معها لإزالة F401. النماذج تبقى هنا
# (تُستورَد من الموجِّه + _rebuild_pydantic_models).


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


# نقطة /api/v1/scenario/temperature نُقلت إلى api/routers/scenario.py (نمط P0).


class WhatIfPlantingRequest(BaseModel):
    crop: str
    temps_baseline: list[dict]  # [{t_min_c, t_max_c}, ...]
    temps_scenario: list[dict]


# نقطة /api/v1/scenario/planting-date نُقلت إلى api/routers/scenario.py (نمط P0).


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


# نقطة /api/v1/scenario/rainfall نُقلت إلى api/routers/scenario.py (نمط P0).


# ─── ٢٤. تظافر القرائن ودرجات التوصية (اتّفاق: القرائن المتظافرة ترقى) ─
# نقطة /api/v1/evidence/corroborate نُقلت إلى api/routers/evidence.py (نمط P0) —
# والاستيراد المرافق (Evidence/EvidenceType/corroborate) نُقل معها لإزالة F401.
# النماذج (EvidenceInput/CorroborationRequest) تبقى هنا (تُستورَد من الموجِّه).


class EvidenceInput(BaseModel):
    etype: str  # lab_field|regional_prior|remote_sensing|field_obs|historical
    agrees: bool
    note_ar: str = ""


class CorroborationRequest(BaseModel):
    evidences: list[EvidenceInput]
    recommendation_key: str = "general"
    test_type_ar: str = "تربة"


# ─── ٢٥. التقويم الثقافي (عرض فقط — خارج محرّك القرار صراحةً) ────
# نقطة /api/v1/cultural-calendar نُقلت إلى api/routers/cultural_calendar.py (نمط P0).


# ─── ٢٦. التوقيت الفلكي الرصدي (مرساة موسميّة + تحقّق مع GDD) ────
# الشروق الاحتراقي كأداة توقيت رصديّة (لا تنجيم) — يعمل offline، يُعرَض مع GDD.


# نقطة /api/v1/regional-calendar نُقلت إلى api/routers/regional_calendar.py (نمط P0).


# نقاط /api/v1/recommendations/{economic-adaptation,capacity-profiles,candidates}
# نُقلت إلى api/routers/recommendations.py (نمط P0).


# نقاط /api/v1/rbac/{who-can,permission-matrix,preview-role-change} نُقلت إلى
# api/routers/rbac.py (نمط P0). نقاط /api/v1/admin/events/dead-letter[/...] نُقلت
# إلى api/routers/admin.py (نمط P0). التبعيات/المساعِدات تبقى هنا وتُستورَد من الموجِّهات.


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


# نقطة /api/v1/recommendations/outcomes نُقلت إلى api/routers/recommendations.py
# (نمط P0) — النموذج OutcomeRecordRequest يبقى هنا (نماذج/تبعيات لا تُنقَل).


# نقطة /api/v1/indices/coverage-report نُقلت إلى api/routers/indices.py (نمط P0).


# نقاط /api/v1/crops/* (drought-resilience) نُقلت إلى api/routers/crops.py (نمط P0).


# ─── ٢٧. التماسك الزمني الموحّد (Convergence) ──────────────────────
# يضمن أنّ المحرّكات الزمنيّة (GDD/water_balance/astronomical) على مرجع واحد.
class TemporalCoherenceRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    planting_date: str | None = None
    gdd_days_counted: int | None = None


class AstronomicalCrossCheckRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    gdd_stage: str | None = None
    anchor: str = "suhail_rising"


# ─── ٢٨. حاجز سلامة المدخلات الكيميائيّة (مُكيَّف من v9، سدّ فجوة سلامة) ─
# نقاط /api/v1/chemical-safety/* نُقلت إلى api/routers/chemical_safety.py (نمط P0) —
# والاستيراد المرافق (check_chemical/list_banned) نُقل معها لإزالة F401. النموذج يبقى
# هنا (يُستورَد من الموجِّه + _rebuild_pydantic_models).
class ChemicalCheckRequest(BaseModel):
    chemical: str
    dose_kg_ha: float | None = None


# ─── ٢٩. مراقبة الحقول بالكاميرا (عين ميدانيّة، لا كشف آلي بالـML) ──
# مسارات /api/v1/cameras/* نُقلت إلى api/routers/cameras.py (نمط P0).
# النماذج تبقى هنا وتُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class RegisterCameraRequest(BaseModel):
    camera_id: str
    field_id: str
    name_ar: str
    camera_type: str = "fixed"  # fixed|mobile|timelapse
    lat: float | None = None
    lon: float | None = None
    capture_interval_min: int | None = None
    note_ar: str = ""


class SnapshotEvidenceRequest(BaseModel):
    snapshot_id: str
    camera_id: str
    field_id: str
    media_uri: str
    captured_at: str
    linked_pin_id: str | None = None
    note_ar: str = ""


# ─── ٣٠. نماذج طلب حساسيّة المراحل للإجهاد المائي ─────────────────
# الدوالّ نُقلت إلى api.routers.water_sensitivity؛ النماذج تبقى هنا وتُستورَد منه
# (إبقاء النماذج في main يحفظ _rebuild_pydantic_models واستيرادات الاختبارات).
class StressRiskRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float


class IntegratedAdviceRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float
    net_irrigation_mm: float | None = None


# ─── ٣١. الدورة الزراعيّة (تعاقب المحاصيل — خصوبة وقائيّة) ──────────
# نقاط /api/v1/rotation/* نُقلت إلى api/routers/rotation.py (نمط P0) — والاستيراد
# المرافق (evaluate_rotation/rotation_principles/suggest_next_crop) نُقل معها لإزالة F401.


# ─── ٣٢. تقويم مواعيد الزراعة المثلى (نوافذ + تحذيرات التبكير/التأخير) ─
# نقاط /api/v1/planting/* نُقلت إلى api/routers/planting.py (نمط P0) — والاستيرادات
# المرافقة (check_planting_date/planting_window/supported_crops) نُقلت معها لإزالة F401.


# ─── ٣٣. الإدارة المتكاملة للآفات (IPM — نهج متدرّج، الكيميائي ملاذ أخير) ─
# نقاط /api/v1/ipm/* نُقلت إلى api/routers/ipm.py (نمط P0) — والاستيرادات المرافقة
# (ipm_plan/pests_for_crop/supported_pests) نُقلت معها لإزالة F401.


# ─── ٣٤. إدارة الملوحة (تصنيف + غسيل + صوديوم — معايير FAO) ────────
# نقطة /api/v1/salinity/assess نُقلت إلى api/routers/salinity.py (نمط P0).
# النموذج يبقى هنا ويُستورَد من الموجِّه (حفظاً لـ_rebuild_pydantic_models/الاختبارات).
class SalinityRequest(BaseModel):
    ece_dsm: float | None = None  # ملوحة التربة
    ecw_dsm: float | None = None  # ملوحة ماء الريّ
    sar: float | None = None  # نسبة امتصاص الصوديوم
    crop_threshold_ece: float | None = None  # عتبة تحمّل المحصول


# ─── ٣٥. دليل البنّ اليمني (محصول نقدي للمرتفعات — شجري دائم) ──────
# مسارات /api/v1/coffee/* مُستخرَجة إلى routers/coffee.py.


# ─── ٣٦. ما بعد الحصاد (التخزين وتقليل الفقد) ─────────────────────
# مسارات /api/v1/postharvest/* نُقلت إلى api/routers/postharvest.py (نمط P0).


# ─── ٣٧. البذور المحسّنة + الأساليب الزراعيّة المحسّنة ─────────────
# نقاط /api/v1/practices/* نُقلت إلى api/routers/practices.py (نمط P0) — والاستيراد
# المرافق (practice_guide/supported_practices) نُقل معها لإزالة F401. نقاط /api/v1/seed/*
# في api/routers/seed.py تستورد رموزها مباشرةً من api.seed_and_practices.


# نموذج طلب تقييم مصدر البذار — يبقى مُعرَّفاً هنا ويُستورَد من api.routers.seed
# (إبقاء النماذج في main يحفظ _rebuild_pydantic_models واستيرادات الاختبارات).
class SeedSourceRequest(BaseModel):
    certified: bool
    purity_pct: float | None = None
    germination_pct: float | None = None


# ─── ٣٨. إدخال محاصيل/أشجار جديدة (استلهام من جازان/نجران) ─────────


class FieldFitRequest(BaseModel):
    crop: str
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True


# ─── ٣٩. بروتوكول أخذ عيّنة التربة (دقّة التحليل تبدأ من العيّنة) ──
# مسارات /api/v1/soil-sampling/* مُستخرَجة إلى routers/soil_sampling.py.


# ─── ٤١. دراسة الجدوى الاقتصاديّة (هل سأربح؟) ─────────────────────


class FeasibilityRequest(BaseModel):
    area_ha: float
    yield_t_per_ha: float
    price_per_t: float
    costs: dict[str, float] | None = None
    total_cost: float | None = None


# ─── ٤٢. الإكثار الخضري (اللاجنسي) + اختيار الأصل المقاوم ─────────
# مسارات /api/v1/propagation/* مُستخرَجة إلى routers/propagation.py.


# ─── ٤٣. تصنيف الأقاليم المناخيّة-الزراعيّة لليمن (أين أنت → ماذا يناسبك) ──
# نُقلت نقاط /api/v1/agro-zones/* إلى api/routers/agro_zones.py (نمط P0)؛
# واستيراد api.agro_climate_zones المرافق نُقل معها لإزالة F401.


# ─── ٤٤. تحديد الإقليم من إحداثيّات الحقل (GPS → محافظة + إقليم + مناخ) ──
# نقطتا /api/v1/geo-locate/{field,recommend} نُقلتا إلى api/routers/geo_locate.py
# (نمط P0) — والاستيراد المرافق (locate_field/locate_and_recommend) نُقل معها لإزالة
# F401. (الكشف العكسي _reverse_geocode يبقى هنا — يستورد locate_field كسولاً داخله.)


# ─── ٤٥. نوافذ المخاطر المناخيّة الموسميّة + ساعات البرودة ──
# نقاط /api/v1/seasonal-risk/* نُقلت إلى api/routers/seasonal_risk.py (نمط P0) —
# والاستيرادات المرافقة (chill_hours_estimate/stage_risk_check/zone_risk_calendar)
# نُقلت معها لإزالة F401.


# ─── ٤٧. تحليل سجلّ الطقس اليومي → ذكاء زراعي (إجهاد حراري + ET0 + عجز مائي) ──


# ─── ٤٩. محرّك القرار الزراعي الموحّد (عقل الحقل) ──


# ─── طبقة تفسير القرار بالذكاء الاصطناعي (Claude يشرح، القواعد تقرّر) ──


# ─── ٥٠. مخطّط البستان المختلط الاستثماري (لوز/زيتون/فستق) ──
# نقاط /api/v1/orchard/* نُقلت إلى api/routers/orchard.py (نمط P0) — والاستيراد
# المرافق (mixed_orchard_plan/orchard_economics_note) نُقل معها لإزالة F401.


# ─── ٥١. محاصيل عالية القيمة قليلة الانتشار (فرص دخول مبكر) ──
# نقاط /api/v1/high-value-crops/* نُقلت إلى api/routers/high_value_crops.py (نمط P0) —
# والاستيراد المرافق (high_value_crop_detail/list_high_value_crops) نُقل معها لإزالة F401.


# ─── ٥٢. منتجات تصديريّة متخصّصة (موجة ثانية: أصماغ/توابل/أصباغ) ──
# نقاط /api/v1/niche-crops/* نُقلت إلى api/routers/niche_crops.py (نمط P0) — والاستيراد
# المرافق (list_niche_crops/niche_crop_detail) نُقل معها لإزالة F401.


# ─── ٥٣. زيوت عطريّة + أعلاف موفّرة للماء (موجة رابعة) ──
# نقطة /api/v1/aromatic-crops/list نُقلت إلى api/routers/aromatic_crops.py ونقطة
# /api/v1/fodder-alternatives/list إلى api/routers/fodder_alternatives.py (نمط P0) —
# والاستيراد المرافق (list_aromatic_crops/list_fodder_alternatives) نُقل معها لإزالة F401.


# ─── ٥٤. الريّ الذكي: قراءة مستشعر الرطوبة + قرار RWC ──
# نُقلت نقاط /api/v1/irrigation/{soil-types,moisture-decision} إلى
# api/routers/irrigation.py (نمط P0) — والاستيراد المرافق نُقل معها لإزالة F401.


# ─── ٥٥. WOFOST عبر المحاصيل: دليل تعديل البارامترات ──
# نقاط /api/v1/wofost/* نُقلت إلى api/routers/wofost.py (نمط P0) — والاستيراد المرافق
# (list_supported_crop_types/wofost_adaptation_guidance) نُقل معها لإزالة F401.


# ─── ٥٦. فحص التناقض الزراعي + نضارة القرار ──
# (نُقل استيراد check_decision_freshness/check_irrigation_consistency إلى
#  api/routers/consistency.py بعد نقل المعالِجَين — لم يبقَ لهما مستخدِم
#  على مستوى الوحدة في main.py؛ الاستيراد الكسول داخل startup يبقى مستقلّاً.)


# ─── ٥٧. الحالة التشغيليّة الموحّدة للحقل ──
# نقطة /api/v1/field/operational-state نُقلت إلى api/routers/field_single.py (نمط P0)
# — والاستيراد المرافق (resolve_field_state) نُقل معها لإزالة F401.


# ─── ٥٧-ب. الحالة القانونيّة الموحّدة للحقل (Canonical Field State — Phase 1) ──
# مصدر الحقيقة الواحد للحالة الزراعيّة: على عكس /operational-state أعلاه (آلة
# حاسبة بلا مصادقة، يمرّر المتّصِل كلّ المدخلات)، هذه النقطة tenant-scoped وتجمع
# مدخلات القرار من مصادرها القانونيّة في قاعدة المنصّة بنفسها (نضارة NDVI/تربة/طقس)
# ثمّ تركّبها عبر نفس resolve_field_state. تُرجِع المدخلات أيضاً (شفافيّة التدقيق:
# أيّ مصدر دخل في القرار). الإسقاط المُخزَّن + توجيه بقيّة المستهلكين = مراحل لاحقة.


# ─── ٥٧-ب-٢. تنبيهات مُشتقّة من الحالة القانونيّة الموحّدة (Stage F — derived) ──
# على عكس POST /api/v1/alerts (محتواه من المتّصِل: title_ar/message_ar يدويّ)، هذه
# النقطة تشتقّ تنبيهات صادقة **من الحالة** (مثل مسار المايسترو الذي يقيّم الحالة
# الموحّدة): تُعيد حساب field_state ثمّ تشتقّ تنبيهات بسيطة من agronomic.operational_
# truths + نمط التنفيذ عبر دالّة نقيّة _derive_alerts_from_state (مُختبَرة بلا قاعدة).
# اشتقاق للعرض فقط: لا تكتب في جدول alerts ولا تُصدِر أحداثاً. صدق: لا حقائق ⇒ [].


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


# ─── ٦٠. أتمتة الصور الجوّية + المؤشّرات (Sentinel عبر raster-service) ──
# نموذج طلب تسجيل حقل للصور — يبقى مُعرَّفاً هنا ويُستورَد من api.routers.automation
# (إبقاء النماذج في main يحفظ _rebuild_pydantic_models واستيرادات الاختبارات).
class ImageryFieldRegister(BaseModel):
    field_id: str
    bbox: list[float]  # [west, south, east, north]


# ─── ٦١. أتمتة تقييم التنبيهات (تشغيل دوريّ/عند الطلب لكلّ حقول المستأجِر) ──
# الكادينس (ثوان) الذي يُتوقَّع أن يُطلَق فيه التقييم الدوريّ لكلّ الحقول.
# يُعرَض في scheduler-status. الافتراض ٦ ساعات (توقّع الطقس يومي عمليّاً؛
# ٦ ساعات تلتقط تحوّلات الحرارة/المطر دون إغراق Open-Meteo). قابل للضبط عبر ENV.
ALERTS_EVAL_INTERVAL_SECONDS = int(os.getenv("SAHOOL_ALERTS_EVAL_INTERVAL_SECONDS", "21600"))


# ─── استبيان دخول المزارع (ONBOARDING) ──────────────────────────


class OnboardingSubmitRequest(BaseModel):
    field_id: str | None = None
    answers: dict = {}


# ─── استقبال مزامنة edge مع dedup (Hardening مراجعة 7) ───────────
class EdgeSyncRequest(BaseModel):
    type: str
    data: dict
    idempotency_key: str | None = None
    occurred_at: str | None = None  # وقت حدوث القياس على الجهاز (مرجع سببي)
    device_id: str | None = None
    field_id: str | None = None


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
# نقطة /api/v1/sampling/strategy نُقلت إلى api/routers/sampling.py (نمط P0).


# ═══════════════════════════════════════════════════════════════════
# Field Intelligence — endpoint التشغيل الحيّ للمايسترو
# يربط: auth → tenant → محوّلات حيّة → المايسترو → الحالة → حدث الحفظ
# ═══════════════════════════════════════════════════════════════════
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


# ─── تسجيل موجِّهات APIRouter (تفكيك main تدريجيّاً، نمط P0) ────────────────
# يُستورَد في نهاية الوحدة فقط — بعد تعريف كلّ التبعيات/النماذج المشتركة — كي
# يُحلّ الاستيراد الدائريّ: routers/boundaries.py يستورد من api.main، وحين يصل
# المُفسّر إلى هنا تكون كلّ تلك الرموز مُعرَّفة. التسجيل يحدث وقت الاستيراد فتُسجَّل
# المسارات على ``app`` كما لو كانت مُعرَّفة هنا (مخطّط OpenAPI مطابق).
# دفعة 7 (routers-batch7): ١٥ نطاقاً مُستخرَجاً (تحليلات/مؤشّرات/ثقة/زمن/تشخيص/
# تعلّم/سوق/اتّساق/إدخال/اقتصاد/تهيئة/طقس-تحليلي/قرار/أمثال/توقيت-فلكي).
# دفعة الأمن/الهوية (routers-sec) — نطاقات auth/me/tenant/rbac/admin مُفكَّكة من main
# (نمط P0، سلوك محفوظ بالكامل: مسارات/أذونات/توكن/OpenAPI مطابقة).
from api.routers.admin import router as admin_router  # noqa: E402
from api.routers.agricultural_proverbs import (  # noqa: E402
    router as agricultural_proverbs_router,
)
from api.routers.agro_zones import router as agro_zones_router  # noqa: E402

# الدفعة ٩ (Batch 9) — نطاقات CQRS/استبطان + كتابات (commands/events/lineage/replay/
# lifecycle/seasons/alerts/tasks/farms) مُفكَّكة من main (نمط P0).
from api.routers.alerts import router as alerts_router  # noqa: E402
from api.routers.analytics import router as analytics_router  # noqa: E402
from api.routers.aromatic_crops import router as aromatic_crops_router  # noqa: E402
from api.routers.astronomical_timing import (  # noqa: E402
    router as astronomical_timing_router,
)
from api.routers.auth import router as auth_router  # noqa: E402
from api.routers.automation import router as automation_router  # noqa: E402
from api.routers.boundaries import router as boundaries_router  # noqa: E402
from api.routers.calendars import router as calendars_router  # noqa: E402

# الدفعة ٨ (Batch 8) — نطاقات إضافيّة مُفكَّكة من main (نمط P0)
from api.routers.cameras import router as cameras_router  # noqa: E402

# routers-plat: نطاقات منصّيّة مُستخرَجة (سلوك محفوظ، نمط P0)
from api.routers.capabilities import router as capabilities_router  # noqa: E402
from api.routers.chemical_safety import router as chemical_safety_router  # noqa: E402
from api.routers.climate_analogs import router as climate_analogs_router  # noqa: E402
from api.routers.coffee import router as coffee_router  # noqa: E402
from api.routers.commands import router as commands_router  # noqa: E402
from api.routers.confidence import router as confidence_router  # noqa: E402
from api.routers.confidence_gate import router as confidence_gate_router  # noqa: E402
from api.routers.consistency import router as consistency_router  # noqa: E402
from api.routers.crop_suitability import router as crop_suitability_router  # noqa: E402
from api.routers.crops import router as crops_router  # noqa: E402
from api.routers.cultural_calendar import router as cultural_calendar_router  # noqa: E402
from api.routers.data_readiness import router as data_readiness_router  # noqa: E402
from api.routers.decision import router as decision_router  # noqa: E402
from api.routers.devices import router as devices_router  # noqa: E402
from api.routers.diagnose import router as diagnose_router  # noqa: E402
from api.routers.documents import router as documents_router  # noqa: E402
from api.routers.economics import router as economics_router  # noqa: E402
from api.routers.edge import router as edge_router  # noqa: E402
from api.routers.equipment import router as equipment_router  # noqa: E402
from api.routers.escalation import router as escalation_router  # noqa: E402
from api.routers.events import router as events_router  # noqa: E402
from api.routers.evidence import router as evidence_router  # noqa: E402
from api.routers.failures import router as failures_router  # noqa: E402
from api.routers.farms import router as farms_router  # noqa: E402
from api.routers.field_intelligence import (  # noqa: E402
    router as field_intelligence_router,
)
from api.routers.field_single import router as field_single_router  # noqa: E402
from api.routers.fields import router as fields_router  # noqa: E402
from api.routers.fodder_alternatives import router as fodder_alternatives_router  # noqa: E402
from api.routers.gdd import router as gdd_router  # noqa: E402
from api.routers.geo import router as geo_router  # noqa: E402
from api.routers.geo_locate import router as geo_locate_router  # noqa: E402
from api.routers.high_value_crops import router as high_value_crops_router  # noqa: E402
from api.routers.indicators import router as indicators_router  # noqa: E402
from api.routers.indices import router as indices_router  # noqa: E402
from api.routers.introduction import router as introduction_router  # noqa: E402
from api.routers.inventory import router as inventory_router  # noqa: E402
from api.routers.ipm import router as ipm_router  # noqa: E402
from api.routers.irrigation import router as irrigation_router  # noqa: E402
from api.routers.learning import router as learning_router  # noqa: E402
from api.routers.lifecycle import router as lifecycle_router  # noqa: E402
from api.routers.lineage import router as lineage_router  # noqa: E402
from api.routers.market import router as market_router  # noqa: E402
from api.routers.master_data import router as master_data_router  # noqa: E402
from api.routers.me import router as me_router  # noqa: E402
from api.routers.niche_crops import router as niche_crops_router  # noqa: E402
from api.routers.notifications import router as notifications_router  # noqa: E402
from api.routers.nutrients import router as nutrients_router  # noqa: E402
from api.routers.observations import router as observations_router  # noqa: E402
from api.routers.onboarding import router as onboarding_router  # noqa: E402
from api.routers.orchard import router as orchard_router  # noqa: E402
from api.routers.pest_escalation import router as pest_escalation_router  # noqa: E402
from api.routers.planting import router as planting_router  # noqa: E402
from api.routers.postharvest import router as postharvest_router  # noqa: E402
from api.routers.practices import router as practices_router  # noqa: E402
from api.routers.propagation import router as propagation_router  # noqa: E402
from api.routers.queue import router as queue_router  # noqa: E402
from api.routers.rbac import router as rbac_router  # noqa: E402
from api.routers.recommendations import router as recommendations_router  # noqa: E402
from api.routers.regional_calendar import router as regional_calendar_router  # noqa: E402
from api.routers.registry import router as registry_router  # noqa: E402
from api.routers.replay import router as replay_router  # noqa: E402
from api.routers.reports import router as reports_router  # noqa: E402
from api.routers.rotation import router as rotation_router  # noqa: E402
from api.routers.salinity import router as salinity_router  # noqa: E402
from api.routers.sampling import router as sampling_router  # noqa: E402
from api.routers.scenario import router as scenario_router  # noqa: E402
from api.routers.scouting import router as scouting_router  # noqa: E402
from api.routers.seasonal_risk import router as seasonal_risk_router  # noqa: E402
from api.routers.seasons import router as seasons_router  # noqa: E402
from api.routers.seed import router as seed_router  # noqa: E402
from api.routers.settings import router as settings_router  # noqa: E402
from api.routers.sharing import router as sharing_router  # noqa: E402
from api.routers.simulate import router as simulate_router  # noqa: E402
from api.routers.soil_sampling import router as soil_sampling_router  # noqa: E402
from api.routers.sync import router as sync_router  # noqa: E402
from api.routers.tasks import router as tasks_router  # noqa: E402
from api.routers.temporal import router as temporal_router  # noqa: E402
from api.routers.tenant import router as tenant_router  # noqa: E402
from api.routers.trials import router as trials_router  # noqa: E402
from api.routers.water_balance import router as water_balance_router  # noqa: E402
from api.routers.water_harvesting import router as water_harvesting_router  # noqa: E402
from api.routers.water_sensitivity import router as water_sensitivity_router  # noqa: E402
from api.routers.weather import router as weather_router  # noqa: E402
from api.routers.weather_analytics import (  # noqa: E402
    router as weather_analytics_router,
)
from api.routers.wofost import router as wofost_router  # noqa: E402

app.include_router(boundaries_router)
app.include_router(notifications_router)
app.include_router(registry_router)
app.include_router(automation_router)
app.include_router(devices_router)
app.include_router(irrigation_router)
app.include_router(recommendations_router)
app.include_router(reports_router)
app.include_router(agro_zones_router)
app.include_router(water_sensitivity_router)
app.include_router(seed_router)
app.include_router(climate_analogs_router)
app.include_router(calendars_router)
app.include_router(water_harvesting_router)
app.include_router(propagation_router)
app.include_router(inventory_router)
app.include_router(equipment_router)
app.include_router(coffee_router)
app.include_router(weather_router)
app.include_router(soil_sampling_router)
app.include_router(sharing_router)
app.include_router(crop_suitability_router)
app.include_router(scenario_router)
app.include_router(crops_router)
app.include_router(chemical_safety_router)
app.include_router(rotation_router)
app.include_router(planting_router)
app.include_router(ipm_router)
app.include_router(practices_router)
app.include_router(seasonal_risk_router)
app.include_router(orchard_router)
app.include_router(high_value_crops_router)
app.include_router(niche_crops_router)
app.include_router(aromatic_crops_router)
app.include_router(fodder_alternatives_router)
app.include_router(wofost_router)
app.include_router(analytics_router)
app.include_router(indicators_router)
app.include_router(confidence_router)
app.include_router(temporal_router)
app.include_router(diagnose_router)
app.include_router(learning_router)
app.include_router(market_router)
app.include_router(consistency_router)
app.include_router(introduction_router)
app.include_router(economics_router)
app.include_router(onboarding_router)
app.include_router(weather_analytics_router)
app.include_router(decision_router)
app.include_router(agricultural_proverbs_router)
app.include_router(astronomical_timing_router)
# الدفعة ٨ (Batch 8)
app.include_router(observations_router)
app.include_router(master_data_router)
app.include_router(settings_router)
app.include_router(documents_router)
app.include_router(simulate_router)
app.include_router(scouting_router)
app.include_router(trials_router)
app.include_router(water_balance_router)
app.include_router(nutrients_router)
app.include_router(gdd_router)
app.include_router(data_readiness_router)
app.include_router(cultural_calendar_router)
app.include_router(regional_calendar_router)
app.include_router(cameras_router)
app.include_router(salinity_router)
app.include_router(postharvest_router)
app.include_router(sampling_router)
app.include_router(fields_router)
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(tenant_router)
app.include_router(rbac_router)
app.include_router(admin_router)
# الدفعة ٩ (Batch 9)
app.include_router(commands_router)
app.include_router(events_router)
app.include_router(lineage_router)
app.include_router(replay_router)
app.include_router(lifecycle_router)
app.include_router(seasons_router)
app.include_router(alerts_router)
app.include_router(tasks_router)
app.include_router(farms_router)
# routers-plat: نطاقات منصّيّة مُستخرَجة (سلوك محفوظ، نمط P0)
app.include_router(sync_router)
app.include_router(queue_router)
app.include_router(capabilities_router)
app.include_router(geo_router)
app.include_router(failures_router)
app.include_router(confidence_gate_router)
app.include_router(escalation_router)
app.include_router(evidence_router)
app.include_router(indices_router)
app.include_router(geo_locate_router)
app.include_router(field_single_router)
app.include_router(edge_router)
app.include_router(field_intelligence_router)
app.include_router(pest_escalation_router)
