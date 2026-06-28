"""routers/password_reset.py — إعادة تعيين كلمة المرور عبر البريد.

مسارات: POST /auth/password-reset/request · POST /auth/password-reset/confirm

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import secrets

import main
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()


@router.post("/auth/password-reset/request")
async def request_password_reset(req: main.PasswordResetRequest, request: Request):
    """✅ NEW: Request password reset via email."""
    ip = request.client.host if request.client else "unknown"
    await main.check_ip_rate(ip)
    main.RESET_COUNTER.inc()

    # Always return success (prevent email enumeration)
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE email=$1", req.email)

    if row and main._redis:
        token = secrets.token_urlsafe(32)
        await main._redis.setex(f"sahool:reset:{token}", 1800, str(row["id"]))  # 30 min
        await main.send_reset_email(req.email, token)
        await main.audit_log("password_reset_request", row["id"], ip)

    return {"message": "إذا كان البريد مسجلاً، ستصلك رسالة إعادة التعيين"}


@router.post("/auth/password-reset/confirm")
async def confirm_password_reset(req: main.PasswordResetConfirm):
    """✅ NEW: Confirm password reset with token."""
    if not main._redis:
        raise HTTPException(503, "Password reset requires Redis")

    user_id_str = await main._redis.get(f"sahool:reset:{req.token}")
    if not user_id_str:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صالح أو منتهي")

    user_id = int(user_id_str)
    hashed = main.bcrypt.hashpw(
        req.new_password.encode(), main.bcrypt.gensalt(main.BCRYPT_ROUNDS)
    ).decode()

    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )

    await main._redis.delete(f"sahool:reset:{req.token}")
    await main.revoke_all_user_sessions(user_id)  # إبطال كلّ الجلسات القائمة بعد إعادة التعيين
    await main.audit_log("password_reset_confirm", user_id, "system")
    return {"message": "تم تغيير كلمة المرور بنجاح"}
