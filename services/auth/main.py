"""
SAHOOL v9.1 — services/auth/main.py (المُحسَّن)
═════════════════════════════════════════════════════════════════
التحسينات الجديدة:
  ✅ Refresh Tokens (Redis-backed, 30 يوم)
  ✅ jti claim + JWT Blacklist (إبطال فردي)
  ✅ Password Reset عبر البريد الإلكتروني
  ✅ Account Lockout (5 محاولات → 15 دقيقة)
  ✅ X-Tenant-ID header في كل responses
  ✅ Logout endpoint (يُبطل access + refresh)
  ✅ RBAC roles: owner (تسجيل ذاتيّ) / admin / expert / farmer / viewer
  ✅ audit_log table for sensitive operations
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import uuid4

import asyncpg
import bcrypt
import pyotp  # TOTP (RFC 6238) — المصادقة الثنائيّة MFA
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from prometheus_client import Counter
from pydantic import BaseModel, EmailStr, Field, field_validator

# تسجيل منظّم موحّد (JSON) — يهرّب الاقتباسات/العربي صحيحاً (لا JSON مكسور).
# fallback آمن لو لم تتوفّر الحزمة المشتركة (لا يكسر الخدمة).
try:
    from shared.logging_config import setup_logging

    logger = setup_logging("auth")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"auth","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("auth")

# ── Config ─────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "")
# RS256 (غير متماثل) لإنهاء shared trust domain: auth يوقّع بالمفتاح الخاصّ،
# الخدمات تتحقّق بالمفتاح العامّ (آمن للتوزيع). fallback لـHS256 لو لم تُضبط
# المفاتيح بعد (ترحيل آمن بلا flag-day). المفاتيح عبر env (PEM).
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "")  # PEM (auth فقط)
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "")  # PEM (للتحقّق)
JWT_ALGORITHM = "RS256" if JWT_PRIVATE_KEY else "HS256"
JWT_SIGNING_KEY = JWT_PRIVATE_KEY if JWT_PRIVATE_KEY else JWT_SECRET
JWT_VERIFY_KEY = JWT_PUBLIC_KEY if JWT_PUBLIC_KEY else JWT_SECRET
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))  # 1 hour
REFRESH_EXPIRE_DAYS = int(os.getenv("REFRESH_EXPIRE_DAYS", "30"))  # 30 days
DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://sahool-redis:6379/0")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@sahool.ye")
# مزوّد SMS عامّ عبر HTTP (Twilio/مزوّد محلّيّ) — يُفعَّل عند ضبط العنوان والمفتاح.
SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL", "")
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_FROM = os.getenv("SMS_FROM", "SAHOOL")
BCRYPT_ROUNDS = 12
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ── إشارة الإنتاج (SAHOOL_ENV) — اصطلاح موحّد عبر المنصّة ──────────
# القيم: production / development (الافتراضيّ development). دالّة نقيّة (تقرأ
# os.getenv عند الاستدعاء) كي تكون قابلة للاختبار وحدةً دون رفع الخدمة.
def _is_production() -> bool:
    """True إن كانت SAHOOL_ENV=production (غير حسّاسة لحالة الأحرف)."""
    return os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"


# ── تحصين: RS256 إلزاميّ في الإنتاج (fail-closed) ───────────────────
# HS256 (سرّ متماثل مشترَك) لا يُنهي shared trust domain: أيّ خدمة تحمل السرّ تستطيع
# تزوير توكنات. RS256 (مفتاح خاصّ لـauth فقط) يُنهيه. في الإنتاج نرفض الإقلاع على HS256
# ما لم يُعطَّل صراحةً (مهرب ترحيل: SAHOOL_ALLOW_HS256_IN_PROD=1). قرار نقيّ قابل للاختبار.
def _refuse_hs256_in_production(
    has_rs256: bool, is_production: bool, allow_hs256_env: str | None
) -> bool:
    """يقرّر رفض الإقلاع: إنتاج + بلا RS256 + بلا مهرب صريح ⇒ رفض (نقيّ)."""
    if has_rs256 or not is_production:
        return False
    return (allow_hs256_env or "").strip().lower() not in {"1", "true", "yes", "on"}


# ── فرض MFA للأدوار الحسّاسة (governance #411) ─────────────────────
# الأدوار التي يجب أن تملك MFA مفعّلاً قبل أن تُمنح جلسة. تُحلَّل مرّة واحدة
# عند التحميل (fail-safe). الافتراضيّ 'admin' (المشرف الأعلى للمنصّة).
def _parse_required_mfa_roles(raw: str | None) -> frozenset[str]:
    """يحوّل قائمة أدوار مفصولة بفواصل إلى مجموعة مُطبَّعة (lowercase, trimmed)."""
    if not raw:
        raw = "admin"
    return frozenset(r.strip().lower() for r in raw.split(",") if r.strip())


REQUIRE_MFA_ROLES = _parse_required_mfa_roles(os.getenv("REQUIRE_MFA_ROLES"))
# مفتاح رئيسيّ: الفرض مُفعَّل افتراضيّاً للأدوار الحسّاسة؛ عطّله صراحةً في CI/التطوير عبر ENFORCE_SENSITIVE_MFA=false عند الحاجة.
# يبقى مفروضاً في الإنتاج عبر SAHOOL_ENV=production حتى لو نُسي الضبط.
_ENFORCE_SENSITIVE_MFA = os.getenv("ENFORCE_SENSITIVE_MFA", "true").lower() == "true"
_IS_PRODUCTION = os.getenv("SAHOOL_ENV", "").lower() == "production"
MFA_ENFORCEMENT_ENABLED = _ENFORCE_SENSITIVE_MFA or _IS_PRODUCTION


def _mfa_required_but_missing(
    role: str | None,
    mfa_enabled: bool,
    *,
    enforcement_enabled: bool = MFA_ENFORCEMENT_ENABLED,
    required_roles: frozenset[str] = REQUIRE_MFA_ROLES,
) -> bool:
    """قرار نقيّ: هل يجب رفض الدخول لأنّ دوراً حسّاساً لا يملك MFA؟

    يُرجِع True فقط حين يكون الفرض مُفعَّلاً والدور ضمن القائمة وMFA غير مفعّل.
    افتراضيّاً (لا بيئة) ⇒ enforcement_enabled=False ⇒ يُرجِع False دائماً
    (لا تغيير في السلوك، يبقى CI أخضر).
    """
    if not enforcement_enabled:
        return False
    if mfa_enabled:
        return False
    return (role or "").strip().lower() in required_roles


# ── Step-up MFA لعمليّات admin الحسّاسة (تغيير الدور/التعطيل) ──────────
# مبدأ: جلسة admin مسروقة/معلّقة وحدها يجب ألّا تكفي لتغيير دور أو تعطيل حساب.
# نطلب رمز TOTP حديثاً (step-up) يُتحقَّق منه ضدّ سرّ المُنفِّذ نفسه عند كلّ
# عمليّة مُحوِّرة. مُعطَّل افتراضيّاً (ENV) كي لا يكسر CI/التطوير — أيّ القرار
# مفصول في دالّة نقيّة قابلة للاختبار.
def _admin_stepup_required() -> bool:
    """هل يجب فرض step-up MFA على عمليّات admin المُحوِّرة؟ (قرار نقيّ).

    True فقط حين ENFORCE_ADMIN_STEPUP_MFA=true أو SAHOOL_ENV=production.
    الافتراضيّ (لا بيئة) ⇒ False ⇒ لا تغيير في السلوك (يبقى CI/التطوير أخضر،
    لا يُطلَب mfa_code). يقرأ os.getenv عند الاستدعاء كي يبقى قابلاً للاختبار.
    """
    enforce = os.getenv("ENFORCE_ADMIN_STEPUP_MFA", "false").strip().lower() == "true"
    return enforce or _is_production()


# ── OTP (تأكيد البريد/الهاتف) — الدوالّ/الثوابت النقيّة في otp.py (معزولة عن
# fastapi كي تُختبَر وحدةً في CI دون تثبيت fastapi). نعيد تصديرها هنا. ──
# ملاحظة (بعد تفكيك المسارات): generate_otp / normalize_otp / is_valid_otp_shape /
# otp_codes_match / otp_redis_key لم تَعُد تُستعمَل داخل main.py مباشرةً — بل تُشير
# إليها وحدة routers/email_verify.py عبر main.X وقت التشغيل. لذا نُبقيها مستورَدةً
# في فضاء أسماء main (مع تعليق تجاهُل F401) كي تُحلَّ تلك المراجع — حذفُها يكسر التحقّق.
from otp import (  # noqa: E402
    OTP_LENGTH,
    OTP_MAX_REQUESTS,
    OTP_TTL_SECONDS,
    generate_otp,  # noqa: F401
    is_valid_otp_shape,  # noqa: F401
    normalize_otp,  # noqa: F401
    otp_codes_match,  # noqa: F401
    otp_redis_key,  # noqa: F401
)


# ── Prometheus ─────────────────────────────────────────────────
def _safe_counter(name: str, documentation: str, labelnames=()):
    """Create a Prometheus counter without breaking repeated test imports.

    Several unit tests load this module under different names to inspect pure
    functions. prometheus_client's default registry is process-global, so a
    second import would otherwise raise duplicated-timeseries. In production the
    first registered metric is used; on repeated imports we create an unregistered
    local counter that keeps handlers importable without mutating global metrics.
    """
    try:
        return Counter(name, documentation, labelnames)
    except ValueError as exc:
        if "Duplicated timeseries" not in str(exc):
            raise
        return Counter(name, documentation, labelnames, registry=None)


LOGIN_COUNTER = _safe_counter("sahool_auth_logins_total", "Login attempts", ["status"])
REGISTER_COUNTER = _safe_counter("sahool_auth_register_total", "Registration attempts", ["status"])
RESET_COUNTER = _safe_counter("sahool_auth_resets_total", "Password reset requests")

# ── DB + Redis ─────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None
_redis = None


@asynccontextmanager
async def _acquire():
    """يكتسب اتّصالاً من المسبح ويضبط سياق admin عليه **على كلّ اكتساب**.

    لماذا ليس في init فقط: asyncpg ينفّذ RESET ALL عند تحرير الاتّصال للمسبح فيمحو
    app.current_role='admin' (session-level) الذي ضبطه _init_auth_conn؛ والاكتساب
    التالي يحصل على اتّصال نظيف بلا سياق دور ⇒ سياسة user_self (USING للقراءة، WITH
    CHECK للكتابة) ترفض users ⇒ login=401 وregister=RLS violation. إعادة الضبط هنا
    تصمد أمام RESET ALL. auth خدمة هويّة عابرة للمستأجرين بحكم دورها (init يبقى حزام
    أمان للاستخدام الأوّل). يستعمل _pool.acquire/release مباشرةً (لا تكرار ذاتيّ)."""
    acquired = _pool.acquire()

    async def _set_admin_context(conn):
        execute = getattr(conn, "execute", None)
        if execute is not None:
            await execute("SELECT set_config('app.current_role', 'admin', false)")

    # asyncpg.Pool.acquire() is usable as an async context manager. Some tests use
    # a small fake with the same shape; support both that and awaitable acquire()
    # return values without weakening the production session-context reset.
    if hasattr(acquired, "__aenter__"):
        async with acquired as conn:
            await _set_admin_context(conn)
            yield conn
        return

    conn = await acquired
    try:
        await _set_admin_context(conn)
        yield conn
    finally:
        release = getattr(_pool, "release", None)
        if release is not None:
            await release(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _redis
    # fail-closed: إمّا مفتاحا RS256 (موصى به) أو سرّ HS256 صالح (≥32 حرف)
    if JWT_PRIVATE_KEY:
        if not JWT_PUBLIC_KEY:
            raise RuntimeError("JWT_PRIVATE_KEY مضبوط بلا JWT_PUBLIC_KEY — كلاهما مطلوب لـRS256")
        # RS256 مفعّل — لا حاجة لـJWT_SECRET
    else:
        # وضع HS256 (fallback) — يتطلّب سرّاً قويّاً
        if not JWT_SECRET:
            raise RuntimeError(
                "لا JWT_PRIVATE_KEY (RS256) ولا JWT_SECRET (HS256) — المصادقة معطّلة بأمان"
            )
        if len(JWT_SECRET) < 32:
            # P3-2: فرض الطول — سرّ قصير = أمان ضعيف، نفشل بأمان
            raise RuntimeError("JWT_SECRET too short — يجب ألّا يقلّ عن 32 حرفاً")
        # تحصين الإنتاج: RS256 إلزاميّ (لا HS256) ما لم يُعطَّل صراحةً للترحيل.
        if _refuse_hs256_in_production(
            has_rs256=bool(JWT_PRIVATE_KEY),
            is_production=_is_production(),
            allow_hs256_env=os.getenv("SAHOOL_ALLOW_HS256_IN_PROD"),
        ):
            raise RuntimeError(
                "RS256 مطلوب في الإنتاج: اضبط JWT_PRIVATE_KEY/JWT_PUBLIC_KEY (مفاتيح غير "
                "متماثلة) — HS256 لا يُنهي shared trust domain. للترحيل المؤقّت فقط: "
                "SAHOOL_ALLOW_HS256_IN_PROD=1."
            )

    # FIX: statement_cache_size معامل عميل asyncpg لا إعداد خادم — في
    # server_settings يفشل الاتصال بـ"unrecognized configuration parameter".
    #
    # CRITICAL (شهادة الإنتاج): جدول users عليه FORCE RLS بسياسة user_self التي
    # تسمح بالوصول عبر app.current_user_id أو app.current_tenant أو
    # app.current_role='admin'. خدمة الهويّة **يجب** أن تقرأ users بالبريد قبل معرفة
    # المستأجِر (تسجيل الدخول)، فتحتاج سياق admin. تحت دور sahool_app (NOBYPASSRLS)
    # بلا هذا السياق تُرشَّح كلّ الصفوف ⇒ register=500، login=401 (المنصّة كلّها معطّلة).
    # نضبطه على **كلّ** اتّصال في المسبح عبر init (session-level) فيغطّي كلّ استعلامات
    # users (تسجيل/دخول/MFA/استرجاع…) بلا تكرار. auth وحدها تعمل بسياق admin بحكم دورها.
    async def _init_auth_conn(conn):
        await conn.execute("SELECT set_config('app.current_role', 'admin', false)")

    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        statement_cache_size=0,
        init=_init_auth_conn,
    )
    # FINDING-001: لينشين عزل المستأجرين — ارفض الإقلاع إن تجاوز دور الاتّصال RLS
    # (superuser/BYPASSRLS) ما لم يُعطَّل صراحةً للتطوير. fail-closed افتراضيّاً.
    from shared.db_role_guard import assert_db_role_rls_safe

    await assert_db_role_rls_safe(_pool, service="auth")
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await _redis.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        # حوكمة #408 — Redis إلزاميّ في الإنتاج (fail-closed):
        # بلا Redis يصبح فحص الإبطال (is_jti_revoked) و«قفل الحساب»/الحدّ الأدنى للتوكنات
        # fail-open: توكن مُبطَل/مُسجَّل خروجه يمرّ، والقفل يتعطّل. هذا غير مقبول في الإنتاج.
        # لذا في الإنتاج نرفض الإقلاع بدل التشغيل صامتاً بإبطال معطّل.
        if _is_production():
            raise RuntimeError("Redis مطلوب في الإنتاج — الإبطال/lockout fail-closed") from e
        # التطوير: نُبقي السلوك القديم (تحذير + تنازل) كي يعمل dev/CI بلا Redis.
        logger.warning(f"Redis unavailable: {e} — refresh tokens disabled")
        _redis = None

    await _ensure_admin_user()
    logger.info("✅ auth-service started")
    yield
    if _pool:
        await _pool.close()
    if _redis:
        await _redis.close()


app = FastAPI(title="SAHOOL Auth Service", version="9.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
    expose_headers=["X-Tenant-ID"],
    allow_credentials=True,
)


# ── Middleware: add X-Tenant-ID to responses ──────────────────
@app.middleware("http")
async def tenant_header_middleware(request: Request, call_next):
    response = await call_next(request)
    # Extract tenant from JWT if present
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:], JWT_VERIFY_KEY, algorithms=[JWT_ALGORITHM], audience="sahool"
            )
            # تدقيق B: افرض المُصدِر — توكن من مُصدِر مجهول لا يُشتقّ منه رأس tenant.
            if payload.get("iss") not in _ALLOWED_ISS:
                raise ValueError("Invalid token issuer")
            response.headers["X-Tenant-ID"] = payload.get("tenant_id", "")
        except Exception as e:  # noqa: BLE001
            # توكن غير صالح/منتهٍ — لا نضيف رأس tenant (سلوك مقصود، نسجّل للتتبّع)
            logger.debug("تعذّر استخراج tenant من التوكن: %s", type(e).__name__)
    return response


# ── Models ─────────────────────────────────────────────────────
ValidRole = Literal["owner", "admin", "expert", "farmer", "viewer"]

# ── أدوار الدعوة (governance: انضمام بأدوار أدنى) ───────────────────
# الأدوار التي يجوز **الدعوة** إليها: الأدنى/غير المميَّزة حصراً. owner/admin
# **مستبعَدان عمداً** (منع تصعيد الصلاحيّات: لا يُنشَأ مالك/مشرف عبر دعوة — المالك
# عبر التسجيل الذاتيّ فقط، والمشرف عبر إجراء إداريّ منفصل). دالّة التحقّق نقيّة كي
# تُختبَر وحدةً دون رفع الخدمة (CI).
INVITEABLE_ROLES: frozenset[str] = frozenset({"expert", "farmer", "viewer"})
# الأدوار التي يحقّ لها **توجيه** دعوة (مالك المستأجِر أو مشرف المنصّة فقط).
INVITER_ROLES: frozenset[str] = frozenset({"owner", "admin"})
# الدور المدعوّ إليه — Literal يرفض owner/admin عند التحقّق (422) قبل أيّ منطق.
InviteableRole = Literal["expert", "farmer", "viewer"]


def is_inviteable_role(role: str | None) -> bool:
    """هل يجوز الدعوة لهذا الدور؟ True فقط لـ{expert,farmer,viewer}.

    fail-closed: None/فراغ/أيّ دور مميَّز (owner/admin) ⇒ False (منع تصعيد).
    دالّة نقيّة (لا I/O) لتُختبَر وحدةً في CI دون تبعيّات الخدمة.
    """
    return (role or "").strip().lower() in INVITEABLE_ROLES


def can_invite(role: str | None) -> bool:
    """هل يحقّ لهذا الدور توجيه دعوات؟ True لـowner/admin فقط. fail-closed."""
    return (role or "").strip().lower() in INVITER_ROLES


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    # ملاحظة أمنيّة: لا حقل role هنا عمداً — العميل لا يختار دوره. التسجيل الذاتيّ
    # يُنشئ مستأجِراً معزولاً جديداً ويُسنِد 'owner' (مؤسِّس مستأجِره؛ انظر register).
    # تغيير الأدوار عبر /auth/users/{id}/role المحمي بـadmin فقط (منع تصعيد الصلاحيات).

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رمز خاص")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None  # رمز TOTP المؤقّت — مطلوب إن كان MFA مفعّلاً للحساب


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)  # رمز TOTP (٦ أرقام عادةً)


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ── Invitation models ──────────────────────────────────────────
class InvitationCreateRequest(BaseModel):
    email: EmailStr
    # InviteableRole (Literal) يرفض owner/admin بـ422 قبل المنطق — حزام أوّل ضدّ
    # تصعيد الصلاحيّات؛ يليه فحص is_inviteable_role صريح في المعالِج (دفاع عمق).
    role: InviteableRole


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رمز خاص")
        return v


# ── Tenant provisioning model (تهيئة مستأجِر B2B بيد مدير المنصّة) ────
class TenantProvisionRequest(BaseModel):
    """طلب تهيئة مستأجِر جديد + أوّل مالك له (إعداد B2B، لا تسجيل ذاتيّ).

    لا حقل role/password/tenant_id هنا عمداً: الدور دائماً 'owner' (يُفرَض في
    المعالِج)، والمالك يضبط كلمة مروره لاحقاً عبر رمز إعادة تعيين (لا كلمة مرور
    من المُهيِّئ)، والمستأجِر جديد معزول (gen_random_uuid) لا يختاره المُهيِّئ
    (منع تصادم/تصعيد). tenant_name اختياريّ ويُسجَّل في التدقيق فقط — لا يوجد
    جدول tenants؛ المستأجرون ضمنيّون عبر users.tenant_id (اتّساقاً مع التسجيل الذاتيّ).
    """

    owner_email: EmailStr
    owner_full_name: str = Field(min_length=2, max_length=100)
    tenant_name: str | None = Field(default=None, max_length=200)


# قناة التحقّق: بريد أو هاتف. Literal يرفض أيّ قيمة أخرى عند التحقّق (422).
VerifyChannel = Literal["email", "phone"]


class VerificationRequest(BaseModel):
    channel: VerifyChannel


class VerificationConfirm(BaseModel):
    channel: VerifyChannel
    # رمز رقميّ ٦ خانات. نسمح بحدود واسعة قليلاً للتشذيب ثمّ نتحقّق نقيّاً.
    code: str = Field(min_length=OTP_LENGTH, max_length=OTP_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_id: int
    role: str
    full_name: str
    tenant_id: str


# ── JWT Helpers ────────────────────────────────────────────────
def create_access_token(
    user_id: int, email: str, role: str, full_name: str, tenant_id: str
) -> tuple[str, str]:
    """Returns (token, jti)"""
    now = datetime.now(UTC)
    jti = str(uuid4())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "full_name": full_name,
        "tenant_id": tenant_id,
        "jti": jti,  # ✅ JWT ID for revocation
        "iss": "sahool-auth",  # ✅ issuer
        "aud": "sahool",  # ✅ audience
        "nbf": int(now.timestamp()),  # ✅ not before
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SIGNING_KEY, algorithm=JWT_ALGORITHM), jti


async def create_refresh_token(user_id: int, tenant_id: str) -> str | None:
    """Create refresh token stored in Redis. Returns None if Redis unavailable."""
    if not _redis:
        return None
    token = secrets.token_urlsafe(48)
    key = f"sahool:refresh:{token}"
    await _redis.setex(key, REFRESH_EXPIRE_DAYS * 86400, f"{user_id}:{tenant_id}")
    # سجّل التوكن في مجموعة المستخدم لإبطالها جماعيّاً عند تغيير كلمة المرور/الدور/التعطيل.
    setkey = f"sahool:user:refreshset:{user_id}"
    await _redis.sadd(setkey, token)
    await _redis.expire(setkey, REFRESH_EXPIRE_DAYS * 86400)
    return token


async def revoke_jti(jti: str, exp: int) -> None:
    """Add JTI to blacklist in Redis until it expires."""
    if not _redis:
        return
    ttl = max(0, exp - int(datetime.now(UTC).timestamp()))
    await _redis.setex(f"sahool:jti:revoked:{jti}", ttl, "1")


async def is_jti_revoked(jti: str) -> bool:
    if not _redis:
        return False
    return await _redis.exists(f"sahool:jti:revoked:{jti}") > 0


async def revoke_refresh_token(token: str) -> None:
    if _redis:
        await _redis.delete(f"sahool:refresh:{token}")


# ── إبطال جماعيّ لجلسات المستخدم (تغيير كلمة المرور/إعادتها/التعطيل/تغيير الدور) ──
# الفجوة (مراجعة أمنيّة): النقاط المُغيِّرة للحساب لم تُبطل التوكنات القائمة ⇒ بعد اختراق/
# إعادة تعيين تبقى جلسات المهاجم صالحة حتى ساعة، والتعطيل/خفض الدور غير فوريَّين. الحلّ:
#   • أرضيّة توكن لكلّ مستخدم (token floor): طابع زمنيّ؛ أيّ access token بـiat أقدم منه
#     يُرفَض ⇒ إبطال فوريّ لكلّ التوكنات القائمة دفعةً واحدة (لا حاجة لمعرفة كلّ jti).
#   • حذف كلّ refresh tokens للمستخدم (من مجموعته) ⇒ لا تجديد بعد الإبطال.
async def set_user_token_floor(user_id: int) -> None:
    """يضبط أرضيّة التوكن للمستخدم = الآن — يُبطل كلّ access token أُصدِر قبلها."""
    if not _redis:
        return
    now_ts = int(datetime.now(UTC).timestamp())
    # TTL = عمر التوكن الأقصى (+هامش): بعده تكون كلّ التوكنات القديمة منتهية أصلاً.
    await _redis.setex(
        f"sahool:user:token_floor:{user_id}", JWT_EXPIRE_MINUTES * 60 + 60, str(now_ts)
    )


async def is_token_below_floor(payload: dict) -> bool:
    """هل أُصدِر هذا التوكن قبل أرضيّة المستخدم؟ (⇒ مُبطَل جماعيّاً). fail-open بلا Redis."""
    if not _redis:
        return False
    sub = payload.get("sub")
    iat = payload.get("iat")
    if sub is None or iat is None:
        return False
    floor = await _redis.get(f"sahool:user:token_floor:{sub}")
    if not floor:
        return False
    try:
        return int(iat) < int(floor)
    except (TypeError, ValueError):
        return False


async def revoke_all_user_sessions(user_id: int) -> None:
    """يُبطل كلّ جلسات المستخدم: أرضيّة access + حذف كلّ refresh tokens (idempotent)."""
    if not _redis:
        return
    await set_user_token_floor(user_id)
    setkey = f"sahool:user:refreshset:{user_id}"
    tokens = await _redis.smembers(setkey)
    if tokens:
        keys = [f"sahool:refresh:{t.decode() if isinstance(t, bytes) else t}" for t in tokens]
        await _redis.delete(*keys)
    await _redis.delete(setkey)


# ── Security ───────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No token")
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_VERIFY_KEY,
            algorithms=[JWT_ALGORITHM],
            audience="sahool",
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e

    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token issuer")

    jti = payload.get("jti")
    if jti and await is_jti_revoked(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    # إبطال جماعيّ: توكن أُصدِر قبل أرضيّة المستخدم (تغيير كلمة المرور/الدور/التعطيل) ⇒ مرفوض.
    if await is_token_below_floor(payload):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    return payload


def require_role(*roles: str):
    async def _check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"مطلوب أحد الأدوار: {', '.join(roles)}")
        return user

    return _check


# ── Account Lockout (Redis-backed) ────────────────────────────
async def check_lockout(email: str) -> None:
    """Raise 429 if account is locked."""
    if not _redis:
        return
    key = f"sahool:lockout:{email}"
    if await _redis.exists(key):
        ttl = await _redis.ttl(key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, f"الحساب مقفل {ttl // 60} دقيقة — حاول لاحقاً"
        )


async def record_failed_login(email: str) -> int:
    """Record failed attempt. Returns total attempts."""
    if not _redis:
        return 0
    key = f"sahool:attempts:{email}"
    count = await _redis.incr(key)
    await _redis.expire(key, LOCKOUT_MINUTES * 60)
    if count >= MAX_LOGIN_ATTEMPTS:
        await _redis.setex(f"sahool:lockout:{email}", LOCKOUT_MINUTES * 60, "1")
        await _redis.delete(key)
        logger.warning(f"Account locked: {email} after {count} attempts")
    return count


async def clear_failed_logins(email: str) -> None:
    if _redis:
        await _redis.delete(f"sahool:attempts:{email}")
        await _redis.delete(f"sahool:lockout:{email}")


# ── IP Rate Limiting ───────────────────────────────────────────
async def check_ip_rate(ip: str) -> None:
    if not _redis:
        return
    key = f"sahool:ip_rate:{ip}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 60)
    if count > 20:  # 20 requests/minute per IP
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "طلبات كثيرة")


# ── Audit Log ─────────────────────────────────────────────────
async def audit_log(
    action: str,
    user_id: int | None,
    ip: str,
    details: str | None = None,
    tenant_id: object | None = None,
) -> None:
    if not _pool:
        return
    try:
        async with _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log (action, user_id, ip_address, details, tenant_id, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                -- HIGH-01 FIX: removed  (no UNIQUE constraint on audit_log)
                -- governance #407: tenant_id للتحقيق الجنائيّ المُنطّق بالمستأجِر
            """,
                action,
                user_id,
                ip,
                details,
                tenant_id,
            )
    except Exception as e:  # noqa: BLE001
        # غير قاتل (لا نكسر مسار المصادقة)، لكن فشل كتابة سجلّ التدقيق حسّاس ⇒ error لا warning.
        logger.error("فشل كتابة سجلّ التدقيق (غير قاتل) action=%s: %s", action, type(e).__name__)


# ── Password Reset Helpers ─────────────────────────────────────
async def send_reset_email(email: str, token: str) -> bool:
    """Send password reset email via SMTP."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP not configured — cannot send reset email")
        return False
    try:
        from email.mime.text import MIMEText

        import aiosmtplib

        reset_url = (
            f"{os.getenv('FRONTEND_URL', 'https://app.sahool.ye')}/reset-password?token={token}"
        )
        body = f"""
مرحباً،

طلبت إعادة تعيين كلمة المرور لحساب SAHOOL المرتبط بـ {email}.

رابط إعادة التعيين (صالح 30 دقيقة):
{reset_url}

إذا لم تطلب ذلك، تجاهل هذا البريد.

فريق SAHOOL — منصة الزراعة الذكية اليمنية
"""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "SAHOOL — إعادة تعيين كلمة المرور"
        msg["From"] = SMTP_FROM
        msg["To"] = email

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info(f"Reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ── OTP Verification Helpers (تأكيد البريد/الهاتف) ─────────────
# دوالّ نقيّة (قابلة للاختبار دون Redis/شبكة) لتوليد الرمز وتشكيله والمقارنة.


async def _send_otp_email(destination: str, code: str) -> bool:
    """يُرسِل OTP بريداً عبر SMTP (نفس نمط send_reset_email)."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("OTP بريد: SMTP غير مضبوط — لم يُرسَل (destination=%s)", destination)
        return False
    try:
        from email.mime.text import MIMEText

        import aiosmtplib

        body = (
            f"رمز تحقّق SAHOOL هو: {code}\n\n"
            f"صالح لمدّة {OTP_TTL_SECONDS // 60} دقيقة. لا تشاركه مع أحد.\n\n"
            "فريق SAHOOL — منصّة الزراعة الذكيّة اليمنيّة"
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "SAHOOL — رمز التحقّق"
        msg["From"] = SMTP_FROM
        msg["To"] = destination
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info("OTP بريد أُرسِل إلى %s", destination)
        return True
    except Exception as e:
        logger.error("فشل إرسال OTP بريداً: %s", e)
        return False


def _post_sms_blocking(phone: str, message: str) -> bool:
    """POST متزامن لمزوّد SMS عامّ (urllib — بلا تبعيّة جديدة)."""
    import json
    import urllib.error
    import urllib.request

    # المفتاح في ترويسة Authorization فقط — لا نُكرّره في الجسم (يقلّل سطح التعرّض).
    payload = json.dumps({"to": phone, "from": SMS_FROM, "message": message}).encode()
    req = urllib.request.Request(
        SMS_PROVIDER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SMS_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.URLError as e:
        logger.error("فشل إرسال OTP عبر SMS: %s", e)
        return False


def _is_valid_phone(destination: str) -> bool:
    """رقم هاتف صالح للإرسال؟ (أرقام دوليّة E.164 مبسّطة) — يستبعد النوائب مثل
    'user:{id}' المستعمَلة قبل حفظ أرقام الهواتف فعليّاً."""
    d = destination.strip().lstrip("+")
    return d.isdigit() and 7 <= len(d) <= 15


async def _send_otp_sms(destination: str, code: str) -> bool:
    """يُرسِل OTP عبر مزوّد SMS HTTP — تشغيل الطلب الحاجب في خيط."""
    if not SMS_PROVIDER_URL or not SMS_API_KEY:
        logger.warning("OTP هاتف: مزوّد SMS غير مضبوط — لم يُرسَل (destination=%s)", destination)
        return False
    if not _is_valid_phone(destination):
        # وجهة نائبة (لم يُحفَظ رقم هاتف بعد) — لا نُرسِل لرقم غير حقيقيّ (إهدار/أخطاء).
        logger.warning("OTP هاتف: وجهة غير صالحة (نائبة؟) — لم يُرسَل")
        return False
    message = f"رمز تحقّق SAHOOL: {code} (صالح {OTP_TTL_SECONDS // 60} دقيقة)"
    return await asyncio.to_thread(_post_sms_blocking, destination, message)


async def send_otp(channel: str, destination: str, code: str) -> bool:
    """يُرسِل رمز التحقّق عبر القناة المطلوبة (بريد SMTP أو SMS عبر HTTP).

    حقيقيّ عند ضبط الاعتماد: البريد عبر SMTP_*، والهاتف عبر SMS_PROVIDER_URL/SMS_API_KEY.
    تدهور رشيق: إن لم يُضبط مزوّد القناة نُسجّل تحذيراً (دون الرمز) ونُعيد False —
    يبقى الرمز في Redis (فيعمل التطوير) لكن دون إعلان نجاح زائف في الإنتاج.
    التوقيع ثابت فلا يتغيّر المنادون. أمان: لا نُسجّل الرمز نفسه أبداً.
    """
    if channel == "email":
        return await _send_otp_email(destination, code)
    if channel == "phone":
        return await _send_otp_sms(destination, code)
    logger.warning("OTP: قناة غير مدعومة channel=%s", channel)
    return False


async def check_otp_request_rate(user_id: int, channel: str) -> None:
    """يحدّ من عدد طلبات إصدار OTP لكلّ مستخدم+قناة (منع إغراق/إساءة)."""
    if not _redis:
        return
    key = f"sahool:otp_rate:{channel}:{user_id}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 3600)  # نافذة ساعة
    if count > OTP_MAX_REQUESTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "طلبات تحقّق كثيرة — حاول بعد قليل",
        )


# ── Admin User ─────────────────────────────────────────────────
async def _ensure_admin_user():
    admin_pass = os.getenv("ADMIN_PASSWORD", "")
    if not admin_pass:
        logger.warning("ADMIN_PASSWORD not set — admin login disabled")
        return
    hashed = bcrypt.hashpw(admin_pass.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    async with _acquire() as conn:
        # سياق admin مضبوط على مستوى المسبح (init) ⇒ WITH CHECK لسياسة user_self يمرّ.
        # حزام أمان: نُعيد ضبطه محليّاً للمعاملة أيضاً تحسّباً لأيّ RESET ALL على
        # تحرير الاتّصال يمحو GUC الجلسة — الإقحام التأسيسيّ للمدير يبقى متيناً.
        await conn.execute("SELECT set_config('app.current_role', 'admin', true)")
        await conn.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES ('admin@sahool.ye', $1, 'مدير النظام', 'admin')
            ON CONFLICT (email) DO NOTHING
        """,
            hashed,
        )
    logger.info("✅ Admin user ensured")


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════


# ── Email/Phone Verification (تأكيد البريد/الهاتف — soft) ──────
# تحقّق ناعم (soft): لا يحجب الدخول، بل يُعلّم الحساب verified_email/_phone.
# الرمز يُخزَّن في Redis قصير الأجل (TTL) كإعادة استخدام لبنية refresh/reset
# القائمة — لا حاجة لجدول جديد. التسليم STUB (سجلّ) — راجع send_otp.


# ── Admin endpoints ───────────────────────────────────────────
async def _verify_caller_mfa(admin_user_id: int, mfa_code: str | None) -> bool:
    """يتحقّق من رمز TOTP حديث ضدّ سرّ المُنفِّذ نفسه (step-up).

    fail-closed: يُرجِع True فقط حين يكون المستخدم موجوداً وMFA مفعّلاً ولديه سرّ
    والرمز صحيح (نافذة ±30s، مطابِق تماماً لتحقّق الدخول). أيّ نقص (لا مستخدم،
    MFA غير مفعّل، لا سرّ، رمز غائب/خاطئ) ⇒ False (يُرفض الإجراء).
    """
    if not mfa_code or not _pool:
        return False
    async with _acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mfa_enabled, mfa_secret FROM users WHERE id=$1", admin_user_id
        )
    if not row or not row["mfa_enabled"]:
        return False
    secret = row["mfa_secret"]
    if not secret:
        return False
    # نفس التحقّق المُستخدَم في الدخول حرفيّاً (pyotp.TOTP(...).verify(..., valid_window=1)).
    return bool(pyotp.TOTP(secret).verify(mfa_code.strip(), valid_window=1))


# ── Tenant member invitations ─────────────────────────────────
# القرار: الأعضاء الإضافيّون ينضمّون لمستأجِر **قائم** عبر دعوة بأدوار **أدنى**
# (expert/farmer/viewer) — لا عبر التسجيل الذاتيّ. owner/admin لا يُدعى إليهما
# (منع تصعيد). القبول يأخذ الدور والمستأجِر من صفّ الدعوة فقط (لا يختارهما العميل).
INVITATION_EXPIRY_DAYS = 7


# ══════════════════════════════════════════════════════════════
# تسجيل الراوترات المفكَّكة (نمط تفكيك المنصّة — محفوظ السلوك)
# يُستدعى في **نهاية** الملفّ بعد تعريف app وكلّ التبعيّات المشتركة (مساعِدات JWT،
# مسبح DB، النماذج، الاعتماديّات) كي تُحلّ وحدات routers/ رموزها عبر main.X بلا
# استيراد دائريّ. التسطيح (_include_flat) يُبقي عدّ المسارات والمسح الساكن صحيحَيْن.
# ══════════════════════════════════════════════════════════════
from router_registry import register_routers  # noqa: E402

register_routers(app)
