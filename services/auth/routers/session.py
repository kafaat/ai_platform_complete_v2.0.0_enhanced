"""routers/session.py — الجلسة (تسجيل دخول/خروج/تجديد + من أنا).

مسارات: POST /v1/auth/login · POST /v1/auth/logout · POST /v1/auth/refresh · GET /v1/auth/me

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة (مساعِدات JWT، مسبح DB،
النماذج، الاعتماديّات) تبقى في ``main`` ويُشار إليها عبر ``main.X`` (ربط متين بلا
ربط ساكن قديم).
"""

from __future__ import annotations

from typing import Annotated

import main
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

router = APIRouter()


@router.post("/v1/auth/login", response_model=main.TokenResponse)
async def login(req: main.LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    await main.check_ip_rate(ip)
    await main.check_lockout(req.email)  # ✅ account lockout check

    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash, role, full_name, tenant_id, active, "
            "mfa_enabled, mfa_secret, encrypted_mfa_secret, mfa_failed_attempts, "
            "mfa_locked_until FROM users WHERE email=$1",
            req.email,
        )

    if (
        not row
        or not row["active"]
        or not main.bcrypt.checkpw(
            req.password.encode(),
            row["password_hash"]
            if isinstance(row["password_hash"], bytes)
            else row["password_hash"].encode(),
        )
    ):
        await main.record_failed_login(
            req.email
        )  # ✅ track failed attempts (locks account internally)
        main.LOGIN_COUNTER.labels(status="failed").inc()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "بيانات غير صحيحة")

    # المصادقة الثنائيّة (MFA): إن كانت مفعّلة، كلمة المرور وحدها لا تكفي.
    # fail-closed: مفعّل بلا سرّ ⇒ رفض (لا تجاوز صامت). التحقّق بنافذة ±30s.
    if row["mfa_enabled"]:
        if not req.mfa_code:
            await main.record_failed_login(req.email)
            main.LOGIN_COUNTER.labels(status="mfa_required").inc()
            # 401 برمز خاصّ ليعرف العميل أنّ كلمة المرور صحّت لكن يلزم رمز MFA
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "يتطلّب الحساب رمز المصادقة الثنائيّة (MFA)",
                headers={"X-MFA-Required": "true"},
            )
        # V29.5 — حوكمة MFA: قفل دائم في DB + سرّ مشفّر (توافق رجعيّ للنصّ) + رموز استرداد
        # لمرّة واحدة + تدقيق. fail-closed: locked ⇒ 429، سرّ مشفّر بلا مفتاح ⇒ رفض.
        ok, reason = await main.mfa_login_verify(row, req.mfa_code, ip=ip)
        if not ok:
            if reason == "locked":
                await main.record_failed_login(req.email)
                main.LOGIN_COUNTER.labels(status="mfa_locked").inc()
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "تجاوزت محاولات MFA — الحساب مقفل مؤقّتاً، حاول لاحقاً",
                    headers={"X-MFA-Locked": "true"},
                )
            # V29.6 — سرّ مشفّر بلا مفتاح / تالف ليس خطأ مستخدِم: 503 مميّز، لا نحسبه فشلاً
            # ولا نُدخِله في قفل الحساب (لا نُعاقِب المستخدِم على خلل تشفير الخادم).
            if reason in ("key_missing", "undecryptable"):
                main.LOGIN_COUNTER.labels(status="mfa_crypto_degraded").inc()
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "تعذّر التحقّق من MFA (خلل في تهيئة تشفير الخادم) — تواصل مع المسؤول",
                )
            await main.record_failed_login(req.email)
            main.LOGIN_COUNTER.labels(status="mfa_failed").inc()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "رمز MFA غير صحيح")

    # فرض MFA للأدوار الحسّاسة (governance #411): دور حسّاس بلا MFA مفعّل
    # يُرفض دخوله ويُوجَّه للإعداد. مُعطَّل افتراضيّاً (ENV) كي لا يكسر CI/التطوير.
    if main._mfa_required_but_missing(row["role"], row["mfa_enabled"]):
        main.LOGIN_COUNTER.labels(status="mfa_enrollment_required").inc()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "حسابك بدور حسّاس يتطلّب تفعيل MFA — أكمِل الإعداد عبر /auth/mfa/setup",
            headers={"X-MFA-Enrollment-Required": "true"},
        )

    await main.clear_failed_logins(req.email)  # ✅ reset on success
    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = main.create_access_token(
        row["id"], row["email"], row["role"], row["full_name"], tid
    )
    refresh = await main.create_refresh_token(row["id"], tid)

    main.logger.info(f"Login OK: user={row['id']} role={row['role']} ip={ip}")
    await main.audit_log("login", row["id"], ip, tenant_id=row["tenant_id"])
    main.LOGIN_COUNTER.labels(status="success").inc()

    # كوكي مصادقة البلاطات (HttpOnly) — يُغني عن تمرير JWT في رابط بلاطة <img>.
    main.set_tile_auth_cookie(response, token, request)

    return main.TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=main.JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tid,
    )


@router.post("/v1/auth/refresh", response_model=main.TokenResponse)
async def refresh_token(req: main.RefreshRequest, request: Request, response: Response):
    """✅ NEW: Refresh access token using refresh token."""
    if not main._redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Refresh tokens require Redis")
    key = f"sahool:refresh:{req.refresh_token}"
    value = await main._redis.get(key)
    if not value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token غير صالح أو منتهي")

    user_id_str, tenant_id = value.split(":", 1)
    user_id = int(user_id_str)

    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, role, full_name, tenant_id, active FROM users WHERE id=$1", user_id
        )
    if not row or not row["active"]:
        await main.revoke_refresh_token(req.refresh_token)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "المستخدم غير نشط")

    # Rotate refresh token
    await main.revoke_refresh_token(req.refresh_token)
    new_refresh = await main.create_refresh_token(user_id, tenant_id)
    token, jti = main.create_access_token(
        row["id"], row["email"], row["role"], row["full_name"], tenant_id
    )

    # جدّد كوكي مصادقة البلاطات كي يبقى صالحاً مع تجديد التوكن (وإلّا انتهت مع انتهاء JWT).
    main.set_tile_auth_cookie(response, token, request)

    return main.TokenResponse(
        access_token=token,
        refresh_token=new_refresh,
        expires_in=main.JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tenant_id,
    )


@router.post("/v1/auth/logout")
async def logout(
    request: Request,
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(main.security)],
):
    """✅ NEW: Invalidate access token (JTI blacklist) + refresh token."""
    ip = request.client.host if request.client else "unknown"
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                main.JWT_VERIFY_KEY,
                algorithms=[main.JWT_ALGORITHM],
                audience="sahool",
            )
            # تدقيق B: افرض المُصدِر — توكن من مُصدِر مجهول يُعامَل كغير صالح (لا إبطال له).
            if payload.get("iss") not in main._ALLOWED_ISS:
                raise JWTError("Invalid token issuer")
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                await main.revoke_jti(jti, exp)
        except JWTError:
            # توكن غير صالح عند الخروج — لا شيء لإبطاله (نسجّل للتدقيق)
            main.logger.debug("logout: توكن غير صالح، لا jti لإبطاله")

    # Also revoke refresh token if provided in body
    body = {}
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        # لا جسم JSON (خروج بلا refresh token) — سلوك مقبول، نسجّل
        main.logger.debug("logout: لا جسم JSON في الطلب: %s", type(e).__name__)
    if rt := body.get("refresh_token"):
        await main.revoke_refresh_token(rt)

    # امسح كوكي مصادقة البلاطات كي لا تبقى صالحة بعد الخروج على متصفّح مشترك.
    main.clear_tile_auth_cookie(response, request)

    await main.audit_log("logout", None, ip)
    return {"message": "تم تسجيل الخروج بنجاح"}


@router.get("/v1/auth/me")
async def me(user: Annotated[dict, Depends(main.get_current_user)]):
    return {k: user[k] for k in ("sub", "email", "role", "full_name", "tenant_id")}
