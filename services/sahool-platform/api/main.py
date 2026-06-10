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

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# جعل النواة قابلة للاستيراد
sys.path.insert(0, str(Path(__file__).parent.parent))

import jwt  # PyJWT
from core.api_adapter import (
    ApiRequest,
    handle_healthz,
    handle_readyz,
    handle_recommendation_request,
)
from core.canonical_schemas import UserRole, UserSchema
from core.offline_first import (
    OfflineQueue,
    OperationKind,
    SyncStatus,
    apply_supersession,
    record_operation_offline,
)
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field

logger = logging.getLogger("sahool.api")

# ─── إعدادات ──────────────────────────────────────────────────────
JWT_SECRET = os.getenv("SAHOOL_JWT_SECRET", "dev-secret-CHANGE-IN-PRODUCTION")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# سياسة أمنيّة: السرّ الضعيف ثغرة خطيرة في الإنتاج.
# في الإنتاج (SAHOOL_ENV=production) نفشل بأمان؛ في التطوير نكتفي بتحذير.
_IS_PRODUCTION = os.getenv("SAHOOL_ENV", "development").lower() == "production"
_WEAK_SECRET = JWT_SECRET == "dev-secret-CHANGE-IN-PRODUCTION" or len(JWT_SECRET) < 32
if _WEAK_SECRET:
    if _IS_PRODUCTION:
        logger.error(
            "🛑 SAHOOL_JWT_SECRET ضعيف أو افتراضي في الإنتاج — توقّف. "
            "عيّن سرّاً قويّاً (≥32 محرفاً) واستخدم RS256."
        )
        sys.exit(1)
    else:
        logger.warning(
            "⚠️ JWT_SECRET افتراضي/ضعيف — مقبول في التطوير فقط. "
            "عيّن سرّاً قويّاً (≥32 محرفاً) واستخدم RS256 قبل الإنتاج."
        )

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

    register_default_tasks(
        fetch_weather=_weather_sweep,
        scan_new_imagery=_imagery_sweep,
        check_decision_freshness=_freshness_sweep,
    )
    scheduler.start()


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


class ActivityItem(BaseModel):
    """عنصر في جدول الأنشطة."""

    activity_id: str
    field_id: str
    field_name_ar: str
    activity_type: str  # irrigation/fertilization/pest_control/harvest
    title_ar: str
    scheduled_for: str  # ISO date
    status: str  # pending/completed/skipped/overdue
    urgency: str  # low/medium/high/critical


# ─── Auth helpers ────────────────────────────────────────────────


def create_token(user: UserSchema) -> str:
    payload = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "name_ar": user.name_ar,
        "aud": "sahool",  # توحيد: يطابق auth ويُقبل عبر كلّ الخدمات
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(authorization: str = Header(None)) -> UserSchema:
    """يستخرج المستخدم من JWT. fail-closed."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience="sahool")
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e

    try:
        role = UserRole(payload.get("role", "worker"))
    except ValueError:
        role = UserRole.WORKER

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
    """تسجيل دخول dev-mode. في الإنتاج: يُرفض — استخدم خدمة auth الحقيقيّة."""
    # C1 FIX: هذه نقطة تطوير تُصدر JWT بلا كلمة مرور. في الإنتاج تُرفض
    # fail-closed (المصادقة الحقيقيّة عبر خدمة sahool-auth بـbcrypt). يمنع
    # تجاوز المصادقة وانهيار عزل المستأجرين لو أصابت الطلبات هذه النقطة.
    if _IS_PRODUCTION:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة في الإنتاج — استخدم خدمة المصادقة (/auth/login).",
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
def auth_logout(user: UserSchema = Depends(get_current_user)):
    """تسجيل خروج. في dev-mode الـJWT stateless فلا server-side session.

    الإبطال الفعلي يحدث على الجهاز (حذف الـtoken). عند توفّر Redis،
    يُضاف الـtoken لـdenylist هنا.
    """
    return {"status": "logged_out", "message_ar": "تمّ تسجيل الخروج"}


@app.post("/api/v1/auth/signup", response_model=TokenResponse)
def auth_signup(req: LoginRequest):
    """تسجيل مستخدم جديد (dev-mode — نفس منطق login حتّى ربط DB).

    في الإنتاج: يُرفض — استخدم خدمة auth الحقيقيّة (DB + bcrypt).
    """
    # C1 FIX: نفس منطق login بلا كلمة مرور → يُرفض fail-closed في الإنتاج.
    if _IS_PRODUCTION:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة في الإنتاج — استخدم خدمة المصادقة.",
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
    user: UserSchema = Depends(get_current_user),
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


@app.post("/api/v1/observations")
def observations(
    req: ObservationRequest,
    user: UserSchema = Depends(get_current_user),
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


@app.get("/api/v1/fields", response_model=list[FieldSummary])
def list_fields(user: UserSchema = Depends(get_current_user)):
    """قائمة حقول الـtenant — للـHomeScreen.

    MVP الحالي: يُرجع stub data. في الإنتاج: query من DB مع filters
    حسب الـrole (worker يرى حقوله فقط، agronomist يرى الكل).
    """
    # في الإنتاج: SELECT * FROM fields WHERE tenant_id=? AND visible_to(user)
    # هنا: stub demo data للـMVP
    return [
        FieldSummary(
            field_id="fld_demo_001",
            farm_id="farm_demo",
            name_ar="حقل تجريبي ١",
            crop="wheat",
            area_ha=12.5,
            quality_grade="READY",
            last_observation_at=datetime.utcnow().isoformat(),
            pending_activities=2,
            health_summary_ar="صحّي",
        ),
        FieldSummary(
            field_id="fld_demo_002",
            farm_id="farm_demo",
            name_ar="حقل تجريبي ٢",
            crop="barley",
            area_ha=8.3,
            quality_grade="LIMITED",
            last_observation_at=None,
            pending_activities=0,
            health_summary_ar="بانتظار قياسات",
        ),
    ]


@app.get("/api/v1/activities", response_model=list[ActivityItem])
def list_activities(
    user: UserSchema = Depends(get_current_user),
    status: str = "pending",
):
    """قائمة الأنشطة المُجدوَلة — للتذكيرات."""
    now = datetime.utcnow()
    return [
        ActivityItem(
            activity_id="act_001",
            field_id="fld_demo_001",
            field_name_ar="حقل تجريبي ١",
            activity_type="irrigation",
            title_ar="ريّ ١٢ ملم — صباح غد",
            scheduled_for=(now + timedelta(hours=18)).isoformat(),
            status="pending",
            urgency="medium",
        ),
        ActivityItem(
            activity_id="act_002",
            field_id="fld_demo_001",
            field_name_ar="حقل تجريبي ١",
            activity_type="pest_control",
            title_ar="فحص الحشرات الأسبوعي",
            scheduled_for=(now + timedelta(days=2)).isoformat(),
            status="pending",
            urgency="low",
        ),
    ]


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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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
def estimate_field_yield(
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
    return {
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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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


@app.post("/api/v1/diagnose")
def diagnose_symptoms(
    req: DiagnoseRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تشخيص أوّلي بقواعد الأعراض (لا قاطع — يوصي بتأكيد بشري/مختبر)."""
    return diagnose(req.crop, req.symptoms).to_dict()


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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
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
    user: UserSchema = Depends(get_current_user),
):
    """يُشغّل المسار الكامل للمايسترو لحقل ويُرجِع الحالة الموحّدة + القرار.

    سيادة البيانات: tenant_id من التوكن (موثوق) لا من الجسم (لا spoofing).
    المصادر: محوّلات HTTP حيّة (weather/soil/raster). المتعذّر يُعلَن بصدق.
    الحالة الناتجة جاهزة للحفظ في events (state_to_event_row) كذاكرة موسميّة.
    """
    from core.agronomic_state_engine import state_to_event_row
    from core.alert_engine import evaluate_alerts, summarize_alerts
    from core.field_intelligence_adapters import build_live_adapters
    from core.field_intelligence_coordinator import FieldRequest, run_field_intelligence

    # tenant_id من التوكن الموثوق (لا من جسم الطلب — حماية multi-tenant)
    req = FieldRequest(field_id=field_id, lat=lat, lon=lon, crop=crop, tenant_id=user.tenant_id)
    adapters = build_live_adapters()
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
        "alerts": alerts,  # تنبيهات استباقيّة مُصنّفة (محرّك التنبيهات)
        "alerts_summary": summarize_alerts(alerts),
        "alerts_delivery": alerts_delivery,  # نتيجة التوصيل (إن notify=true)
        "_persistable_event": event_row,  # جاهز للإدراج في events table
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
