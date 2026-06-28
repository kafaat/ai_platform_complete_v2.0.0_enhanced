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
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

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
# ملاحظة: ضبط SMTP_*/SMS_* انتقل إلى mailer.py مع مُرسِلات الإشعارات (مصدر واحد،
# بلا تكرار/انحراف). main.py لم يعد يستعملها مباشرةً بعد استخراج الدوالّ.
BCRYPT_ROUNDS = 12
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ── إشارة الإنتاج (SAHOOL_ENV) — اصطلاح موحّد عبر المنصّة ──────────
# القيم: production / development (الافتراضيّ development). دالّة نقيّة (تقرأ
# os.getenv عند الاستدعاء) كي تكون قابلة للاختبار وحدةً دون رفع الخدمة.
def _is_production() -> bool:
    """True إن كانت SAHOOL_ENV=production (غير حسّاسة لحالة الأحرف)."""
    return os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"


# ── قرارات التفويض النقيّة (سياسة) — استُخرِجت إلى authz.py كي تُفصَل قرارات
# السياسة عن المسارات وحالة الخدمة وتُختبَر وحدةً (CI). نعيد تصديرها هنا كما هي
# (سلوك محفوظ؛ نفس مفاتيح البيئة والتوقيعات والقيم): فرض MFA للأدوار الحسّاسة
# (#411) وأدوار الدعوة (منع تصعيد). _is_production و_admin_stepup_required يبقيان
# هنا (حُرّاس مصدريّة نصّيّة + تكامل lifespan/نقاط admin). ──
from authz import (  # noqa: E402,F401  (إعادة تصدير: تُستعمل في المسارات/الاختبارات)
    INVITEABLE_ROLES,
    INVITER_ROLES,
    MFA_ENFORCEMENT_ENABLED,
    REQUIRE_MFA_ROLES,
    _mfa_required_but_missing,
    _parse_required_mfa_roles,
    can_invite,
    is_inviteable_role,
)


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


# ── مُرسِلات الإشعارات (بريد SMTP / SMS عبر HTTP) — استُخرِجت إلى mailer.py كي
# تُفصَل منطق التسليم (I/O) عن المسارات وحالة الخدمة. نعيد تصديرها هنا كما هي كي
# تبقى متاحة كـmain.<name> (سلوك محفوظ؛ نفس مفاتيح البيئة والتوقيعات). ──
from mailer import (  # noqa: E402,F401  (إعادة تصدير: تُستعمل في المسارات/الاختبارات)
    _is_valid_phone,
    _post_sms_blocking,
    _send_otp_email,
    _send_otp_sms,
    send_otp,
    send_reset_email,
)

# ── OTP (تأكيد البريد/الهاتف) — الدوالّ/الثوابت النقيّة في otp.py (معزولة عن
# fastapi كي تُختبَر وحدةً في CI دون تثبيت fastapi). نعيد تصديرها هنا. ──
from otp import (  # noqa: E402
    OTP_MAX_REQUESTS,
    OTP_TTL_SECONDS,
    generate_otp,
    is_valid_otp_shape,
    normalize_otp,
    otp_codes_match,
    otp_redis_key,
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

# أدوار الدعوة/التحقّق منها (INVITEABLE_ROLES/INVITER_ROLES/is_inviteable_role/
# can_invite) استُخرِجت إلى authz.py وأُعيد تصديرها أعلى الملفّ (قرارات سياسة نقيّة).


# ── نماذج الطلب/الاستجابة (Pydantic) — استُخرِجت حرفيّاً إلى models.py ──
# لتقليص main.py وفصل عقود البيانات عن المنطق؛ نعيد تصديرها هنا كما هي كي تبقى
# قابلة للاستيراد من main (سلوك محفوظ؛ الاختبارات تصل إليها عبر main.<Model>).
# InviteableRole/VerifyChannel من نوع Literal تُعرَّف هناك أيضاً (تُستعمل في النماذج).
from models import (  # noqa: E402,F401  (F401: InviteableRole/VerifyChannel معاد تصديرهما)
    ChangePasswordRequest,
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InviteableRole,
    LoginRequest,
    MfaCodeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TenantProvisionRequest,
    TokenResponse,
    VerificationConfirm,
    VerificationRequest,
    VerifyChannel,
)


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


# ── Password Reset / OTP delivery helpers ──────────────────────
# مُرسِلات البريد/الـSMS (send_reset_email, _send_otp_email, _post_sms_blocking,
# _is_valid_phone, _send_otp_sms, send_otp) استُخرِجت إلى mailer.py وأُعيد تصديرها
# أعلى الملفّ. منطق حدّ المعدّل التالي يبقى هنا لاعتماده على حالة Redis (_redis).


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


@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    await check_ip_rate(ip)

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    async with _acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES ($1, $2, $3, 'owner')
                RETURNING id, email, role, full_name, tenant_id
            """,
                req.email,
                hashed,
                req.full_name,
            )
            # الأمان + الإقلاع: التسجيل الذاتيّ يُنشئ **مستأجِراً جديداً معزولاً**
            # (users.tenant_id افتراضه gen_random_uuid)، فالمُسجِّل هو مؤسِّس مؤسّسته ⇒
            # دوره 'owner' (TENANT_OWNER) كي يستطيع إنشاء/إدارة حقوله وفريقه — وإلّا
            # «Bootstrap Deadlock»: يملك مستأجِراً لا يقدر على تأسيسه. آمن: RLS يعزل
            # المستأجرين فلا تصعيد عابر؛ وهو مالك مستأجِره وحده. الدور المُرسَل من
            # العميل يُتجاهَل (لا حقل role في RegisterRequest). الأعضاء اللاحقون
            # يُضافون لمستأجِر قائم بأدوار أدنى عبر دعوة (manager/agronomist/worker/
            # viewer) — لا عبر التسجيل الذاتيّ.
        except asyncpg.UniqueViolationError as e:
            REGISTER_COUNTER.labels(status="conflict").inc()
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد الإلكتروني مسجّل مسبقاً") from e

    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = create_access_token(row["id"], row["email"], row["role"], row["full_name"], tid)
    refresh = await create_refresh_token(row["id"], tid)

    await audit_log("register", row["id"], ip, tenant_id=row["tenant_id"])
    REGISTER_COUNTER.labels(status="success").inc()

    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tid,
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    await check_ip_rate(ip)
    await check_lockout(req.email)  # ✅ account lockout check

    async with _acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash, role, full_name, tenant_id, active, "
            "mfa_enabled, mfa_secret FROM users WHERE email=$1",
            req.email,
        )

    if (
        not row
        or not row["active"]
        or not bcrypt.checkpw(
            req.password.encode(),
            row["password_hash"]
            if isinstance(row["password_hash"], bytes)
            else row["password_hash"].encode(),
        )
    ):
        await record_failed_login(req.email)  # ✅ track failed attempts (locks account internally)
        LOGIN_COUNTER.labels(status="failed").inc()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "بيانات غير صحيحة")

    # المصادقة الثنائيّة (MFA): إن كانت مفعّلة، كلمة المرور وحدها لا تكفي.
    # fail-closed: مفعّل بلا سرّ ⇒ رفض (لا تجاوز صامت). التحقّق بنافذة ±30s.
    if row["mfa_enabled"]:
        if not req.mfa_code:
            await record_failed_login(req.email)
            LOGIN_COUNTER.labels(status="mfa_required").inc()
            # 401 برمز خاصّ ليعرف العميل أنّ كلمة المرور صحّت لكن يلزم رمز MFA
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "يتطلّب الحساب رمز المصادقة الثنائيّة (MFA)",
                headers={"X-MFA-Required": "true"},
            )
        secret = row["mfa_secret"]
        if not secret or not pyotp.TOTP(secret).verify(req.mfa_code.strip(), valid_window=1):
            await record_failed_login(req.email)
            LOGIN_COUNTER.labels(status="mfa_failed").inc()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "رمز MFA غير صحيح")

    # فرض MFA للأدوار الحسّاسة (governance #411): دور حسّاس بلا MFA مفعّل
    # يُرفض دخوله ويُوجَّه للإعداد. مُعطَّل افتراضيّاً (ENV) كي لا يكسر CI/التطوير.
    if _mfa_required_but_missing(row["role"], row["mfa_enabled"]):
        LOGIN_COUNTER.labels(status="mfa_enrollment_required").inc()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "حسابك بدور حسّاس يتطلّب تفعيل MFA — أكمِل الإعداد عبر /auth/mfa/setup",
            headers={"X-MFA-Enrollment-Required": "true"},
        )

    await clear_failed_logins(req.email)  # ✅ reset on success
    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = create_access_token(row["id"], row["email"], row["role"], row["full_name"], tid)
    refresh = await create_refresh_token(row["id"], tid)

    logger.info(f"Login OK: user={row['id']} role={row['role']} ip={ip}")
    await audit_log("login", row["id"], ip, tenant_id=row["tenant_id"])
    LOGIN_COUNTER.labels(status="success").inc()

    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tid,
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """✅ NEW: Refresh access token using refresh token."""
    if not _redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Refresh tokens require Redis")
    key = f"sahool:refresh:{req.refresh_token}"
    value = await _redis.get(key)
    if not value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token غير صالح أو منتهي")

    user_id_str, tenant_id = value.split(":", 1)
    user_id = int(user_id_str)

    async with _acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, role, full_name, tenant_id, active FROM users WHERE id=$1", user_id
        )
    if not row or not row["active"]:
        await revoke_refresh_token(req.refresh_token)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "المستخدم غير نشط")

    # Rotate refresh token
    await revoke_refresh_token(req.refresh_token)
    new_refresh = await create_refresh_token(user_id, tenant_id)
    token, jti = create_access_token(
        row["id"], row["email"], row["role"], row["full_name"], tenant_id
    )

    return TokenResponse(
        access_token=token,
        refresh_token=new_refresh,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tenant_id,
    )


@app.post("/auth/logout")
async def logout(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
):
    """✅ NEW: Invalidate access token (JTI blacklist) + refresh token."""
    ip = request.client.host if request.client else "unknown"
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                JWT_VERIFY_KEY,
                algorithms=[JWT_ALGORITHM],
                audience="sahool",
            )
            # تدقيق B: افرض المُصدِر — توكن من مُصدِر مجهول يُعامَل كغير صالح (لا إبطال له).
            if payload.get("iss") not in _ALLOWED_ISS:
                raise JWTError("Invalid token issuer")
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                await revoke_jti(jti, exp)
        except JWTError:
            # توكن غير صالح عند الخروج — لا شيء لإبطاله (نسجّل للتدقيق)
            logger.debug("logout: توكن غير صالح، لا jti لإبطاله")

    # Also revoke refresh token if provided in body
    body = {}
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        # لا جسم JSON (خروج بلا refresh token) — سلوك مقبول، نسجّل
        logger.debug("logout: لا جسم JSON في الطلب: %s", type(e).__name__)
    if rt := body.get("refresh_token"):
        await revoke_refresh_token(rt)

    await audit_log("logout", None, ip)
    return {"message": "تم تسجيل الخروج بنجاح"}


@app.post("/auth/password-reset/request")
async def request_password_reset(req: PasswordResetRequest, request: Request):
    """✅ NEW: Request password reset via email."""
    ip = request.client.host if request.client else "unknown"
    await check_ip_rate(ip)
    RESET_COUNTER.inc()

    # Always return success (prevent email enumeration)
    async with _acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE email=$1", req.email)

    if row and _redis:
        token = secrets.token_urlsafe(32)
        await _redis.setex(f"sahool:reset:{token}", 1800, str(row["id"]))  # 30 min
        await send_reset_email(req.email, token)
        await audit_log("password_reset_request", row["id"], ip)

    return {"message": "إذا كان البريد مسجلاً، ستصلك رسالة إعادة التعيين"}


@app.post("/auth/password-reset/confirm")
async def confirm_password_reset(req: PasswordResetConfirm):
    """✅ NEW: Confirm password reset with token."""
    if not _redis:
        raise HTTPException(503, "Password reset requires Redis")

    user_id_str = await _redis.get(f"sahool:reset:{req.token}")
    if not user_id_str:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صالح أو منتهي")

    user_id = int(user_id_str)
    hashed = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()

    async with _acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )

    await _redis.delete(f"sahool:reset:{req.token}")
    await revoke_all_user_sessions(user_id)  # إبطال كلّ الجلسات القائمة بعد إعادة التعيين
    await audit_log("password_reset_confirm", user_id, "system")
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@app.post("/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
):
    """✅ NEW: Change password for authenticated user."""
    user_id = int(user["sub"])
    async with _acquire() as conn:
        row = await conn.fetchrow("SELECT password_hash FROM users WHERE id=$1", user_id)
    if not row or not bcrypt.checkpw(req.current_password.encode(), row["password_hash"].encode()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "كلمة المرور الحالية غير صحيحة")

    hashed = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    async with _acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )
    await revoke_all_user_sessions(user_id)  # إبطال كلّ الجلسات (يشمل الحاليّة) ⇒ إعادة دخول
    await audit_log("change_password", user_id, "authenticated")
    return {"message": "تم تغيير كلمة المرور بنجاح"}


# ── MFA (TOTP / RFC 6238) ─────────────────────────────────────
@app.post("/auth/mfa/setup")
async def mfa_setup(user: dict = Depends(get_current_user)):
    """يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri (لتطبيق المصادقة).

    لا يُفعّل MFA بعد — التفعيل يتطلّب تأكيد أوّل رمز عبر /auth/mfa/activate
    (إثبات أنّ المستخدم اقترن فعلاً، لئلّا يُقفل نفسه خارجاً). السرّ يُعرَض هنا
    مرّة واحدة فقط (لا يُعاد بعدها أبداً).
    """
    user_id = int(user["sub"])
    async with _acquire() as conn:
        row = await conn.fetchrow("SELECT email, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if row["mfa_enabled"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA مفعّل بالفعل — عطّله أولاً لإعادة الاقتران"
        )

    secret = pyotp.random_base32()
    async with _acquire() as conn:
        # نخزّن السرّ لكن mfa_enabled يبقى FALSE حتى التأكيد
        await conn.execute(
            "UPDATE users SET mfa_secret=$1, mfa_enabled=FALSE, updated_at=NOW() WHERE id=$2",
            secret,
            user_id,
        )
    uri = pyotp.TOTP(secret).provisioning_uri(name=row["email"], issuer_name="SAHOOL")
    await audit_log("mfa_setup_started", user_id, "authenticated")
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "message": "أكّد الرمز عبر /auth/mfa/activate",
    }


@app.post("/auth/mfa/activate")
async def mfa_activate(req: MfaCodeRequest, user: dict = Depends(get_current_user)):
    """يفعّل MFA بعد تأكيد أوّل رمز صحيح (إثبات الاقتران)."""
    user_id = int(user["sub"])
    async with _acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ابدأ الاقتران أولاً عبر /auth/mfa/setup")
    if not pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح — تأكّد من تطبيق المصادقة")
    async with _acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=TRUE, updated_at=NOW() WHERE id=$1", user_id
        )
    await audit_log("mfa_activated", user_id, "authenticated")
    return {"message": "تم تفعيل المصادقة الثنائيّة", "mfa_enabled": True}


@app.post("/auth/mfa/disable")
async def mfa_disable(req: MfaCodeRequest, user: dict = Depends(get_current_user)):
    """يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله مهاجم بتوكن مسروق بلا الجهاز)."""
    user_id = int(user["sub"])
    async with _acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA غير مفعّل")
    # حالة غير متّسقة (مفعّل بلا سرّ): لا تُمرّر None لـpyotp (تجنّب 500) — أبلغ صراحةً.
    if not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "حالة MFA غير متّسقة — تواصل مع المسؤول")
    if not pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح")
    async with _acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=FALSE, mfa_secret=NULL, updated_at=NOW() WHERE id=$1",
            user_id,
        )
    await audit_log("mfa_disabled", user_id, "authenticated")
    return {"message": "تم تعطيل المصادقة الثنائيّة", "mfa_enabled": False}


# ── Email/Phone Verification (تأكيد البريد/الهاتف — soft) ──────
# تحقّق ناعم (soft): لا يحجب الدخول، بل يُعلّم الحساب verified_email/_phone.
# الرمز يُخزَّن في Redis قصير الأجل (TTL) كإعادة استخدام لبنية refresh/reset
# القائمة — لا حاجة لجدول جديد. التسليم STUB (سجلّ) — راجع send_otp.


@app.post("/auth/verify/request")
async def verify_request(
    req: VerificationRequest,
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
):
    """يُصدر رمز OTP من ٦ أرقام لقناة المستخدم (بريد/هاتف) ويُخزّنه في Redis.

    محميّ (يتطلّب توكناً)، ومحدود المعدّل (IP + لكلّ مستخدم+قناة). التسليم STUB.
    """
    ip = request.client.host if request.client else "unknown"
    await check_ip_rate(ip)
    if not _redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "خدمة التحقّق تتطلّب Redis")
    user_id = int(user["sub"])
    await check_otp_request_rate(user_id, req.channel)

    # وجهة التسليم: البريد من التوكن؛ الهاتف غير مخزّن بعد (stub) فنستخدم نائباً.
    destination = user.get("email", "") if req.channel == "email" else f"user:{user_id}"

    code = generate_otp()
    await _redis.setex(otp_redis_key(user_id, req.channel), OTP_TTL_SECONDS, code)
    # صدق: الرسالة تعكس واقع التسليم — لا ندّعي إرسالاً إن لم يُهيّأ مزوّد القناة.
    delivered = await send_otp(req.channel, destination, code)
    await audit_log(f"verify_request_{req.channel}", user_id, ip)
    return {
        "message": "تم إرسال رمز التحقّق" if delivered else "تعذّر تسليم الرمز عبر القناة",
        "delivered": delivered,
        "channel": req.channel,
        "expires_in": OTP_TTL_SECONDS,
    }


@app.post("/auth/verify/confirm")
async def verify_confirm(
    req: VerificationConfirm,
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
):
    """يتحقّق من رمز OTP مقابل Redis (مقارنة ثابتة الزمن) ويُعلّم الحساب مُتحقَّقاً."""
    ip = request.client.host if request.client else "unknown"
    # حدّ معدّل بالـIP أيضاً على التأكيد — الرمز ٦ أرقام فقط، فبلا حدٍّ يمكن تخمينه قسريّاً.
    await check_ip_rate(ip)
    if not _redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "خدمة التحقّق تتطلّب Redis")
    user_id = int(user["sub"])

    submitted = normalize_otp(req.code)
    if not is_valid_otp_shape(submitted):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "صيغة الرمز غير صحيحة")

    key = otp_redis_key(user_id, req.channel)
    stored = await _redis.get(key)
    if not stored or not otp_codes_match(submitted, stored):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صالح أو منتهٍ")

    # نجاح: نُثبّت العلَم في القاعدة أوّلاً ثم نستهلك الرمز — لو فشل التحديث يبقى
    # الرمز صالحاً لإعادة المحاولة (لا نخسره). جملتان ثابتتان بلا SQL ديناميكيّ
    # (اسم العمود لا يأتي من المستخدم، لكن نتجنّب البناء النصّيّ مبدئيّاً).
    async with _acquire() as conn:
        if req.channel == "email":
            await conn.execute(
                "UPDATE users SET verified_email=TRUE, updated_at=NOW() WHERE id=$1",
                user_id,
            )
        else:
            await conn.execute(
                "UPDATE users SET verified_phone=TRUE, updated_at=NOW() WHERE id=$1",
                user_id,
            )
    await _redis.delete(key)
    await audit_log(f"verify_confirm_{req.channel}", user_id, ip)
    return {"message": "تم التحقّق بنجاح", "channel": req.channel, "verified": True}


@app.get("/auth/verify")
async def verify(user: Annotated[dict, Depends(get_current_user)]):
    return {
        "valid": True,
        "user_id": user["sub"],
        "role": user["role"],
        "tenant_id": user["tenant_id"],
    }


@app.get("/auth/me")
async def me(user: Annotated[dict, Depends(get_current_user)]):
    return {k: user[k] for k in ("sub", "email", "role", "full_name", "tenant_id")}


@app.get("/auth/verify/status")
async def verify_status(user: Annotated[dict, Depends(get_current_user)]):
    """حالة تحقّق الحساب (بريد/هاتف) من القاعدة — لعرضها في الواجهة."""
    user_id = int(user["sub"])
    async with _acquire() as conn:
        row = await conn.fetchrow(
            "SELECT verified_email, verified_phone FROM users WHERE id=$1", user_id
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    return {
        "verified_email": bool(row["verified_email"]),
        "verified_phone": bool(row["verified_phone"]),
    }


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


@app.get("/auth/users", dependencies=[Depends(require_role("admin"))])
async def list_users():
    async with _acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, email, full_name, role, active, created_at, tenant_id FROM users ORDER BY id"
        )
    return [dict(r) for r in rows]


@app.patch("/auth/users/{user_id}/role")
async def change_role(
    user_id: int,
    role: ValidRole,
    request: Request,
    admin: Annotated[dict, Depends(require_role("admin"))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # Step-up MFA (مُفعَّل بالبيئة): جلسة admin وحدها لا تكفي لتغيير دور — يلزم
    # رمز TOTP حديث من المُنفِّذ نفسه. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر.
    if _admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await _verify_caller_mfa(caller_id, x_mfa_code):
            ip = request.client.host if request.client else "unknown"
            await audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"change_role target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    async with _acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET role=$1 WHERE id=$2 RETURNING id, email, role", role, user_id
        )
    if not row:
        raise HTTPException(404, "المستخدم غير موجود")
    # إبطال جلسات المستخدم ⇒ يُعاد تحميل الدور الجديد فوريّاً (لا يبقى التوكن القديم بدوره القديم)
    await revoke_all_user_sessions(user_id)
    ip = request.client.host if request.client else "unknown"
    await audit_log(
        "change_role",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} new_role={role} stepup={_admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return dict(row)


@app.patch("/auth/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: Annotated[dict, Depends(require_role("admin"))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # Step-up MFA (مُفعَّل بالبيئة): تعطيل حساب إجراء حسّاس — يلزم رمز TOTP حديث
    # من المُنفِّذ. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر (لا mfa_code).
    if _admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await _verify_caller_mfa(caller_id, x_mfa_code):
            ip = request.client.host if request.client else "unknown"
            await audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"deactivate target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    async with _acquire() as conn:
        await conn.execute("UPDATE users SET active=FALSE WHERE id=$1", user_id)
    await revoke_all_user_sessions(user_id)  # التعطيل فوريّ: إبطال كلّ جلسات الحساب
    ip = request.client.host if request.client else "unknown"
    await audit_log(
        "deactivate_user",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} stepup={_admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return {"message": "تم إلغاء تفعيل الحساب"}


# ── Tenant provisioning (تهيئة مستأجِر B2B بيد مدير المنصّة) ────────────
# القرار التصميميّ: التسجيل الذاتيّ (register) يُنشئ مستأجِراً + مالكاً معاً بكلمة
# مرور يختارها المُسجِّل. التهيئة الإداريّة (هنا) تختلف: مدير المنصّة (دور auth
# 'admin' ⇒ PLATFORM_ADMIN) يُنشئ مستأجِراً جديداً معزولاً + أوّل مالك له دون
# أن يعرف المالكُ كلمةَ مرور مسبقة — يضبطها بنفسه عبر **رمز إعادة تعيين** (نعيد
# استخدام آليّة password-reset القائمة: مفتاح Redis sahool:reset:{token} مدّته
# ٣٠ دقيقة + send_reset_email). كلمة المرور الأوّليّة عشوائيّة غير قابلة للاستعمال.
#
# الأمان (لا تصعيد عابر للمستأجرين): المالك المُهيَّأ هو مالك مستأجِر **جديد
# منفصل** (tenant_id فريد جديد، gen_random_uuid) — لا علاقة له بمستأجِر المُهيِّئ.
# المُهيِّئ (admin) لا ينضمّ للمستأجِر الجديد ولا يحصل على توكن له ⇒ لا يصل لبياناته
# (RLS يعزل المستأجرين). إذن منح 'owner' لمستأجِر مولود حديثاً ليس رفعاً للصلاحيّة
# داخل مستأجِر قائم، بل تأسيس مستأجِر فارغ معزول (نفس منطق register).
#
# جدول tenants: لا يوجد في الهجرات — المستأجرون **ضمنيّون** عبر users.tenant_id
# (افتراضه gen_random_uuid)، اتّساقاً مع التسجيل الذاتيّ. لذا لا صفّ tenants يُدرَج؛
# tenant_name (إن أُرسِل) يُدوَّن في سجلّ التدقيق فقط.
@app.post("/auth/tenants", status_code=201)
async def provision_tenant(
    req: TenantProvisionRequest,
    request: Request,
    admin: Annotated[dict, Depends(require_role("admin"))],
):
    """يُهيّئ مستأجِراً جديداً معزولاً + أوّل مالك له (مدير المنصّة فقط).

    يُنشئ مستخدِم المالك بدور 'owner' وكلمة مرور أوّليّة عشوائيّة غير قابلة
    للاستعمال، ثمّ يُصدر رمز إعادة تعيين (Redis) ليضبط المالك كلمة مروره. يرفض
    إن كان البريد مسجّلاً مسبقاً (409). يُدوّن tenant_provisioned في التدقيق.
    """
    ip = request.client.host if request.client else "unknown"
    admin_id = int(admin["sub"])

    # كلمة مرور أوّليّة عشوائيّة غير قابلة للاستعمال: يُهشَّر سرّ عشوائيّ لا يُكشَف
    # لأحد ⇒ لا يمكن تسجيل الدخول بها؛ المالك يضبط كلمته عبر رمز إعادة التعيين.
    unusable = bcrypt.hashpw(secrets.token_urlsafe(48).encode(), bcrypt.gensalt(BCRYPT_ROUNDS))
    hashed = unusable.decode()

    async with _acquire() as conn:
        try:
            # tenant_id يُترَك للافتراضيّ gen_random_uuid ⇒ مستأجِر جديد معزول
            # (نفس نمط register). الدور 'owner' مكتوب نصّاً هنا (لا من العميل).
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES ($1, $2, $3, 'owner')
                RETURNING id, email, role, full_name, tenant_id
                """,
                req.owner_email,
                hashed,
                req.owner_full_name,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد الإلكتروني مسجّل مسبقاً") from e

    new_tenant_id = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"

    # رمز إعداد كلمة المرور: إعادة استخدام آليّة password-reset القائمة (Redis، ٣٠ دقيقة).
    # نتدهور برشاقة بلا Redis (التطوير): نُعيد الحقول دون رمز (المالك يطلب إعادة تعيين لاحقاً).
    setup_token: str | None = None
    if _redis:
        setup_token = secrets.token_urlsafe(32)
        await _redis.setex(f"sahool:reset:{setup_token}", 1800, str(row["id"]))  # 30 دقيقة
        # إرسال بريد الإعداد (نفس قالب إعادة التعيين) — best-effort (SMTP قد لا يكون مهيّأً).
        await send_reset_email(req.owner_email, setup_token)

    # التدقيق: tenant_provisioned بمستأجِر جديد + معرّف المُهيِّئ (admin). نُدوّن tenant_name
    # في details للتتبّع (لا جدول tenants لتخزينه). tenant_id = المستأجِر الجديد المُهيَّأ.
    details = req.tenant_name or req.owner_email
    await audit_log("tenant_provisioned", admin_id, ip, details=details, tenant_id=row["tenant_id"])
    logger.info(
        "tenant provisioned: tenant=%s owner_user=%s by_admin=%s",
        new_tenant_id,
        row["id"],
        admin_id,
    )

    # رابط الإعداد للواجهة (نفس مسار إعادة التعيين) — يُعرَض إن لم يُهيّأ SMTP.
    setup_link = (
        f"{os.getenv('FRONTEND_URL', 'https://app.sahool.ye')}/reset-password?token={setup_token}"
        if setup_token
        else None
    )
    return {
        "tenant_id": new_tenant_id,
        "owner_user_id": row["id"],
        "owner_email": row["email"],
        "owner_role": row["role"],  # دائماً 'owner'
        "setup_token": setup_token,
        "setup_link": setup_link,
        "message": (
            "تمّت تهيئة المستأجِر؛ أُرسِل/أُتيح رابط ضبط كلمة المرور للمالك"
            if setup_token
            else "تمّت تهيئة المستأجِر؛ يطلب المالك إعادة تعيين كلمة المرور (Redis غير متاح)"
        ),
    }


# ── Tenant member invitations ─────────────────────────────────
# القرار: الأعضاء الإضافيّون ينضمّون لمستأجِر **قائم** عبر دعوة بأدوار **أدنى**
# (expert/farmer/viewer) — لا عبر التسجيل الذاتيّ. owner/admin لا يُدعى إليهما
# (منع تصعيد). القبول يأخذ الدور والمستأجِر من صفّ الدعوة فقط (لا يختارهما العميل).
INVITATION_EXPIRY_DAYS = 7


@app.post("/auth/invitations", status_code=201)
async def create_invitation(
    req: InvitationCreateRequest,
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
):
    """يُنشئ دعوة عضو لمستأجِر الداعي. owner/admin فقط، وبأدوار أدنى حصراً.

    أمان: tenant_id يُؤخَذ من توكن الداعي (لا من العميل)؛ الدور مُقيَّد بـ
    {expert,farmer,viewer} (Literal + فحص صريح) — owner/admin مرفوضان (تصعيد).
    """
    ip = request.client.host if request.client else "unknown"
    if not can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "الدعوة تتطلّب دور مالك المستأجِر")
    # دفاع عمق: حتى لو تجاوز Literal، نرفض أيّ دور غير قابل للدعوة صراحةً.
    if not is_inviteable_role(req.role):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "الدور غير قابل للدعوة — المسموح: expert/farmer/viewer (لا owner/admin)",
        )

    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "لا مستأجِر مرتبط بالحساب الداعي")
    inviter_id = int(user["sub"])
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=INVITATION_EXPIRY_DAYS)

    async with _acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO invitations
                (token, email, tenant_id, role, invited_by, status, expires_at)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6)
            RETURNING id, email, role, tenant_id, expires_at, created_at
            """,
            token,
            req.email,
            tenant_id,
            req.role,
            inviter_id,
            expires_at,
        )

    await audit_log("invite_created", inviter_id, ip, details=req.email, tenant_id=tenant_id)
    # لا إرسال بريد هنا (SMTP غير مضمون) — نُعيد الرابط لتعرضه الواجهة للنسخ.
    accept_url = f"/accept-invitation?token={token}"
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "tenant_id": str(row["tenant_id"]),
        "token": token,
        "accept_url": accept_url,
        "expires_at": row["expires_at"].isoformat(),
        "status": "pending",
    }


@app.get("/auth/invitations")
async def list_invitations(user: Annotated[dict, Depends(get_current_user)]):
    """يسرد الدعوات المعلّقة لمستأجِر الداعي (owner/admin فقط)، tenant-scoped."""
    if not can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلّب دور مالك المستأجِر")
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return []
    async with _acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, email, role, status, expires_at, created_at
            FROM invitations
            WHERE tenant_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
            """,
            tenant_id,
        )
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "role": r["role"],
            "status": r["status"],
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@app.post("/auth/invitations/accept", response_model=TokenResponse, status_code=201)
async def accept_invitation(req: InvitationAcceptRequest, request: Request):
    """قبول دعوة (عموميّ، محميّ بالـtoken): يُنشئ مستخدِماً ينضمّ لمستأجِر الداعي.

    أمان: الدور والمستأجِر يُؤخذان من **صفّ الدعوة فقط** — العميل لا يختارهما.
    يرفض إن كان الـtoken غير صالح/منتهٍ/مستهلَكاً أو البريد مسجّلاً مسبقاً.
    """
    ip = request.client.host if request.client else "unknown"
    await check_ip_rate(ip)
    now = datetime.now(UTC)

    async with _acquire() as conn:
        inv = await conn.fetchrow(
            """
            SELECT id, email, tenant_id, role, status, expires_at
            FROM invitations
            WHERE token = $1
            """,
            req.token,
        )
        if not inv or inv["status"] != "pending":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "دعوة غير صالحة أو مستهلَكة")
        if inv["expires_at"] and inv["expires_at"] <= now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "انتهت صلاحيّة الدعوة")
        # حزام أمان نهائيّ: ارفض الدور المميَّز ولو سرّب إلى صفّ الدعوة بأيّ شكل.
        if not is_inviteable_role(inv["role"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "دور الدعوة غير مسموح")

        hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
        # المستخدِم الجديد ينضمّ لمستأجِر الداعي بدوره المدعوّ — كلاهما من صفّ الدعوة.
        try:
            new_user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role, tenant_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, email, role, full_name, tenant_id
                """,
                inv["email"],
                hashed,
                req.full_name,
                inv["role"],
                inv["tenant_id"],
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد مسجّل مسبقاً") from e

        # وسم الدعوة مقبولة (idempotent: شرط status='pending' يمنع قبولاً مزدوجاً متسابِقاً).
        await conn.execute(
            "UPDATE invitations SET status='accepted', accepted_at=$1 WHERE id=$2",
            now,
            inv["id"],
        )

    tid = str(new_user["tenant_id"])
    token, _jti = create_access_token(
        new_user["id"], new_user["email"], new_user["role"], new_user["full_name"], tid
    )
    refresh = await create_refresh_token(new_user["id"], tid)
    await audit_log("invite_accepted", new_user["id"], ip, details=new_user["email"], tenant_id=tid)

    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user_id=new_user["id"],
        role=new_user["role"],
        full_name=new_user["full_name"],
        tenant_id=tid,
    )


@app.delete("/auth/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: int,
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
):
    """يلغي دعوة معلّقة (owner/admin فقط)، tenant-scoped — لا يطال دعوات مستأجِر آخر."""
    ip = request.client.host if request.client else "unknown"
    if not can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلّب دور مالك المستأجِر")
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الدعوة غير موجودة")
    async with _acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE invitations SET status='revoked'
            WHERE id=$1 AND tenant_id=$2 AND status='pending'
            RETURNING id
            """,
            invitation_id,
            tenant_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الدعوة غير موجودة أو غير معلّقة")
    await audit_log("invite_revoked", int(user["sub"]), ip, tenant_id=tenant_id)
    return {"message": "تم إلغاء الدعوة", "id": invitation_id}


# ── Observability ─────────────────────────────────────────────
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "auth", "version": "9.1.0"}


@app.get("/readyz")
async def readyz():
    try:
        async with _acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready", "redis": _redis is not None}
    except Exception as e:
        # لا نُسرّب تفاصيل الاتصال/المضيف/المستخدم من استثناء asyncpg في readyz العام.
        raise HTTPException(503, "DB not ready") from e
