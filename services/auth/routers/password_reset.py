"""routers/password_reset.py — إعادة تعيين كلمة المرور عبر البريد.

مسارات: POST /v1/auth/password-reset/request · POST /v1/auth/password-reset/confirm

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import secrets

import main
from client_address import client_ip
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from session_tokens import consume_reset_token

router = APIRouter()


async def _lookup_user_id(email: str) -> int | None:
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE email=$1", email)
    return row["id"] if row else None


async def _issue_reset_token(user_id: int, email: str, ip: str) -> None:
    token = secrets.token_urlsafe(32)
    await main._redis.setex(f"sahool:reset:{token}", 1800, str(user_id))  # 30 min
    await main.send_reset_email(email, token)
    await main.audit_log("password_reset_request", user_id, ip)


async def _store_password_hash(user_id: int, hashed: str) -> None:
    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )


@router.post("/v1/auth/password-reset/request")
async def request_password_reset(
    req: main.PasswordResetRequest, request: Request, background: BackgroundTasks
):
    """✅ NEW: Request password reset via email."""
    ip = client_ip(request)
    await main.check_ip_rate(ip)
    main.RESET_COUNTER.inc()

    # Always return success (prevent email enumeration).
    # S16(c): إصدار الرمز + SMTP + التدقيق تجري **بعد** الاستجابة (BackgroundTasks)، فزمن
    # الاستجابة لا يكشف وجود البريد: المساران كلاهما = حدّ IP + استعلام واحد + الردّ نفسه.
    user_id = await _lookup_user_id(req.email)
    if user_id is not None and main._redis:
        background.add_task(_issue_reset_token, user_id, req.email, ip)

    return {"message": "إذا كان البريد مسجلاً، ستصلك رسالة إعادة التعيين"}


@router.post("/v1/auth/password-reset/confirm")
async def confirm_password_reset(req: main.PasswordResetConfirm):
    """✅ NEW: Confirm password reset with token."""
    if not main._redis:
        raise HTTPException(503, "Password reset requires Redis")

    # S16(b): استهلاكٌ ذرّيّ (GETDEL) **قبل** أيّ عمل — كان GET ثمّ DELETE بعد التحديث،
    # فطلبان متزامنان بالرمز نفسِه نجحا معاً. الآن الرمز لمرّة واحدة: الخاسر يرى None.
    user_id_str = await consume_reset_token(main._redis, req.token)
    if not user_id_str:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صالح أو منتهي")

    user_id = int(user_id_str)
    # S8: التجزئة عبر password_hashing (حدّ ٧٢ بايت صريح)؛ S16(b): التخزين بعد استهلاكٍ ذرّيّ.
    hashed = main.hash_password(req.new_password, main.BCRYPT_ROUNDS)
    await _store_password_hash(user_id, hashed)
    await main.revoke_all_user_sessions(user_id)  # إبطال كلّ الجلسات القائمة بعد إعادة التعيين
    await main.audit_log("password_reset_confirm", user_id, "system")
    return {"message": "تم تغيير كلمة المرور بنجاح"}
