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
  ✅ RBAC roles: admin / expert / farmer / viewer
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
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel, EmailStr, Field, field_validator
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
BCRYPT_ROUNDS = 12
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
# ── OTP (تأكيد البريد/الهاتف) — الدوالّ/الثوابت النقيّة في otp.py (معزولة عن
# fastapi كي تُختبَر وحدةً في CI دون تثبيت fastapi). نعيد تصديرها هنا. ──
from otp import (  # noqa: E402
    OTP_LENGTH,
    OTP_MAX_REQUESTS,
    OTP_TTL_SECONDS,
    generate_otp,
    is_valid_otp_shape,
    normalize_otp,
    otp_codes_match,
    otp_redis_key,
)

# ── Prometheus ─────────────────────────────────────────────────
LOGIN_COUNTER = Counter("sahool_auth_logins_total", "Login attempts", ["status"])
REGISTER_COUNTER = Counter("sahool_auth_register_total", "Registration attempts", ["status"])
RESET_COUNTER = Counter("sahool_auth_resets_total", "Password reset requests")

# ── DB + Redis ─────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None
_redis = None


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
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        statement_cache_size=0,
    )
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await _redis.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
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
            response.headers["X-Tenant-ID"] = payload.get("tenant_id", "")
        except Exception as e:  # noqa: BLE001
            # توكن غير صالح/منتهٍ — لا نضيف رأس tenant (سلوك مقصود، نسجّل للتتبّع)
            logger.debug("تعذّر استخراج tenant من التوكن: %s", type(e).__name__)
    return response


# ── Models ─────────────────────────────────────────────────────
ValidRole = Literal["admin", "expert", "farmer", "viewer"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    # ملاحظة أمنيّة: لا حقل role هنا عمداً. التسجيل يُنشئ 'farmer' دائماً.
    # الترقية عبر /auth/users/{id}/role المحمي فقط (منع تصعيد الصلاحيات).

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

    jti = payload.get("jti")
    if jti and await is_jti_revoked(jti):
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
async def audit_log(action: str, user_id: int | None, ip: str, details: str | None = None) -> None:
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log (action, user_id, ip_address, details, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                -- HIGH-01 FIX: removed  (no UNIQUE constraint on audit_log)
            """,
                action,
                user_id,
                ip,
                details,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("فشل كتابة سجلّ التدقيق (غير قاتل): %s", type(e).__name__)


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


async def send_otp(channel: str, destination: str, code: str) -> bool:
    """يُرسِل رمز التحقّق عبر القناة.

    STUB: لا توجد بوّابة بريد/SMS حقيقيّة في هذه البيئة — نسجّل فقط (info).
    لربط مزوّد حقيقيّ لاحقاً: استبدل جسم هذه الدالّة باستدعاء SMTP (راجع
    send_reset_email) للبريد، أو بوّابة SMS (Twilio/مزوّد محلّيّ) للهاتف.
    التوقيع ثابت فلا يتغيّر المنادون عند ربط مزوّد حقيقيّ.
    """
    logger.info(
        "📨 OTP STUB — channel=%s destination=%s code=%s (لا مزوّد فعليّ — سجلّ فقط)",
        channel,
        destination,
        code,
    )
    return True


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
    async with _pool.acquire() as conn:
        await conn.execute("SELECT set_config('app.current_tenant', '', true)")
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
    async with _pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES ($1, $2, $3, 'farmer')
                RETURNING id, email, role, full_name, tenant_id
            """,
                req.email,
                hashed,
                req.full_name,
            )
            # الأمان: الدور مثبّت 'farmer' خادم-جانبيّاً. الترقية لأدوار أعلى
            # تتمّ فقط عبر /auth/users/{id}/role المحمي بـrequire_role("admin").
            # الدور المُرسَل من العميل يُتجاهَل تماماً لمنع تصعيد الصلاحيات.
        except asyncpg.UniqueViolationError as e:
            REGISTER_COUNTER.labels(status="conflict").inc()
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد الإلكتروني مسجّل مسبقاً") from e

    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = create_access_token(row["id"], row["email"], row["role"], row["full_name"], tid)
    refresh = await create_refresh_token(row["id"], tid)

    await audit_log("register", row["id"], ip)
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

    async with _pool.acquire() as conn:
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

    await clear_failed_logins(req.email)  # ✅ reset on success
    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = create_access_token(row["id"], row["email"], row["role"], row["full_name"], tid)
    refresh = await create_refresh_token(row["id"], tid)

    logger.info(f"Login OK: user={row['id']} role={row['role']} ip={ip}")
    await audit_log("login", row["id"], ip)
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

    async with _pool.acquire() as conn:
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
    async with _pool.acquire() as conn:
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

    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )

    await _redis.delete(f"sahool:reset:{req.token}")
    await audit_log("password_reset_confirm", user_id, "system")
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@app.post("/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
):
    """✅ NEW: Change password for authenticated user."""
    user_id = int(user["sub"])
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT password_hash FROM users WHERE id=$1", user_id)
    if not row or not bcrypt.checkpw(req.current_password.encode(), row["password_hash"].encode()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "كلمة المرور الحالية غير صحيحة")

    hashed = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )
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
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT email, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if row["mfa_enabled"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA مفعّل بالفعل — عطّله أولاً لإعادة الاقتران"
        )

    secret = pyotp.random_base32()
    async with _pool.acquire() as conn:
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
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ابدأ الاقتران أولاً عبر /auth/mfa/setup")
    if not pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح — تأكّد من تطبيق المصادقة")
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=TRUE, updated_at=NOW() WHERE id=$1", user_id
        )
    await audit_log("mfa_activated", user_id, "authenticated")
    return {"message": "تم تفعيل المصادقة الثنائيّة", "mfa_enabled": True}


@app.post("/auth/mfa/disable")
async def mfa_disable(req: MfaCodeRequest, user: dict = Depends(get_current_user)):
    """يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله مهاجم بتوكن مسروق بلا الجهاز)."""
    user_id = int(user["sub"])
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA غير مفعّل")
    # حالة غير متّسقة (مفعّل بلا سرّ): لا تُمرّر None لـpyotp (تجنّب 500) — أبلغ صراحةً.
    if not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "حالة MFA غير متّسقة — تواصل مع المسؤول")
    if not pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح")
    async with _pool.acquire() as conn:
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
    await send_otp(req.channel, destination, code)
    await audit_log(f"verify_request_{req.channel}", user_id, ip)
    return {
        "message": "تم إرسال رمز التحقّق",
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

    # نجاح: نستهلك الرمز (استعمال واحد) ونُثبّت العلَم في القاعدة.
    await _redis.delete(key)
    column = "verified_email" if req.channel == "email" else "verified_phone"
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {column}=TRUE, updated_at=NOW() WHERE id=$1",  # noqa: S608
            user_id,
        )
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
    async with _pool.acquire() as conn:
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
@app.get("/auth/users", dependencies=[Depends(require_role("admin"))])
async def list_users():
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, email, full_name, role, active, created_at, tenant_id FROM users ORDER BY id"
        )
    return [dict(r) for r in rows]


@app.patch("/auth/users/{user_id}/role", dependencies=[Depends(require_role("admin"))])
async def change_role(user_id: int, role: ValidRole):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET role=$1 WHERE id=$2 RETURNING id, email, role", role, user_id
        )
    if not row:
        raise HTTPException(404, "المستخدم غير موجود")
    return dict(row)


@app.patch("/auth/users/{user_id}/deactivate", dependencies=[Depends(require_role("admin"))])
async def deactivate_user(user_id: int):
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE users SET active=FALSE WHERE id=$1", user_id)
    return {"message": "تم إلغاء تفعيل الحساب"}


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
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready", "redis": _redis is not None}
    except Exception as e:
        raise HTTPException(503, f"DB not ready: {e}") from e
