"""routers/email_verify.py — تأكيد البريد/الهاتف (تحقّق ناعم soft).

مسارات: GET /v1/auth/verify · GET /v1/auth/verify/status · POST /v1/auth/verify/confirm ·
        POST /v1/auth/verify/request

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة (مساعِدات OTP، مسبح DB،
الاعتماديّات) تبقى في ``main`` ويُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

from typing import Annotated

import main
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter()


@router.post("/v1/auth/verify/request")
async def verify_request(
    req: main.VerificationRequest,
    request: Request,
    user: Annotated[dict, Depends(main.get_current_user)],
):
    """يُصدر رمز OTP من ٦ أرقام لقناة المستخدم (بريد/هاتف) ويُخزّنه في Redis.

    محميّ (يتطلّب توكناً)، ومحدود المعدّل (IP + لكلّ مستخدم+قناة). التسليم STUB.
    """
    ip = request.client.host if request.client else "unknown"
    await main.check_ip_rate(ip)
    if not main._redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "خدمة التحقّق تتطلّب Redis")
    user_id = int(user["sub"])
    await main.check_otp_request_rate(user_id, req.channel)

    # وجهة التسليم: البريد من التوكن؛ الهاتف غير مخزّن بعد (stub) فنستخدم نائباً.
    destination = user.get("email", "") if req.channel == "email" else f"user:{user_id}"

    code = main.generate_otp()
    await main._redis.setex(main.otp_redis_key(user_id, req.channel), main.OTP_TTL_SECONDS, code)
    # صدق: الرسالة تعكس واقع التسليم — لا ندّعي إرسالاً إن لم يُهيّأ مزوّد القناة.
    delivered = await main.send_otp(req.channel, destination, code)
    await main.audit_log(f"verify_request_{req.channel}", user_id, ip)
    return {
        "message": "تم إرسال رمز التحقّق" if delivered else "تعذّر تسليم الرمز عبر القناة",
        "delivered": delivered,
        "channel": req.channel,
        "expires_in": main.OTP_TTL_SECONDS,
    }


@router.post("/v1/auth/verify/confirm")
async def verify_confirm(
    req: main.VerificationConfirm,
    request: Request,
    user: Annotated[dict, Depends(main.get_current_user)],
):
    """يتحقّق من رمز OTP مقابل Redis (مقارنة ثابتة الزمن) ويُعلّم الحساب مُتحقَّقاً."""
    ip = request.client.host if request.client else "unknown"
    # حدّ معدّل بالـIP أيضاً على التأكيد — الرمز ٦ أرقام فقط، فبلا حدٍّ يمكن تخمينه قسريّاً.
    await main.check_ip_rate(ip)
    if not main._redis:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "خدمة التحقّق تتطلّب Redis")
    user_id = int(user["sub"])

    submitted = main.normalize_otp(req.code)
    if not main.is_valid_otp_shape(submitted):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "صيغة الرمز غير صحيحة")

    key = main.otp_redis_key(user_id, req.channel)
    stored = await main._redis.get(key)
    if not stored or not main.otp_codes_match(submitted, stored):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صالح أو منتهٍ")

    # نجاح: نُثبّت العلَم في القاعدة أوّلاً ثم نستهلك الرمز — لو فشل التحديث يبقى
    # الرمز صالحاً لإعادة المحاولة (لا نخسره). جملتان ثابتتان بلا SQL ديناميكيّ
    # (اسم العمود لا يأتي من المستخدم، لكن نتجنّب البناء النصّيّ مبدئيّاً).
    async with main._acquire() as conn:
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
    await main._redis.delete(key)
    await main.audit_log(f"verify_confirm_{req.channel}", user_id, ip)
    return {"message": "تم التحقّق بنجاح", "channel": req.channel, "verified": True}


@router.get("/v1/auth/verify")
async def verify(user: Annotated[dict, Depends(main.get_current_user)]):
    return {
        "valid": True,
        "user_id": user["sub"],
        "role": user["role"],
        "tenant_id": user["tenant_id"],
    }


@router.get("/v1/auth/verify/status")
async def verify_status(user: Annotated[dict, Depends(main.get_current_user)]):
    """حالة تحقّق الحساب (بريد/هاتف) من القاعدة — لعرضها في الواجهة."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT verified_email, verified_phone FROM users WHERE id=$1", user_id
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    return {
        "verified_email": bool(row["verified_email"]),
        "verified_phone": bool(row["verified_phone"]),
    }
