"""routers/mfa.py — المصادقة الثنائيّة (TOTP / RFC 6238).

مسارات: POST /auth/mfa/setup · POST /auth/mfa/activate · POST /auth/mfa/disable

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()


@router.post("/auth/mfa/setup")
async def mfa_setup(user: dict = Depends(main.get_current_user)):
    """يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri (لتطبيق المصادقة).

    لا يُفعّل MFA بعد — التفعيل يتطلّب تأكيد أوّل رمز عبر /auth/mfa/activate
    (إثبات أنّ المستخدم اقترن فعلاً، لئلّا يُقفل نفسه خارجاً). السرّ يُعرَض هنا
    مرّة واحدة فقط (لا يُعاد بعدها أبداً).
    """
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT email, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if row["mfa_enabled"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA مفعّل بالفعل — عطّله أولاً لإعادة الاقتران"
        )

    secret = main.pyotp.random_base32()
    async with main._acquire() as conn:
        # نخزّن السرّ لكن mfa_enabled يبقى FALSE حتى التأكيد
        await conn.execute(
            "UPDATE users SET mfa_secret=$1, mfa_enabled=FALSE, updated_at=NOW() WHERE id=$2",
            secret,
            user_id,
        )
    uri = main.pyotp.TOTP(secret).provisioning_uri(name=row["email"], issuer_name="SAHOOL")
    await main.audit_log("mfa_setup_started", user_id, "authenticated")
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "message": "أكّد الرمز عبر /auth/mfa/activate",
    }


@router.post("/auth/mfa/activate")
async def mfa_activate(req: main.MfaCodeRequest, user: dict = Depends(main.get_current_user)):
    """يفعّل MFA بعد تأكيد أوّل رمز صحيح (إثبات الاقتران)."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ابدأ الاقتران أولاً عبر /auth/mfa/setup")
    if not main.pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح — تأكّد من تطبيق المصادقة")
    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=TRUE, updated_at=NOW() WHERE id=$1", user_id
        )
    await main.audit_log("mfa_activated", user_id, "authenticated")
    return {"message": "تم تفعيل المصادقة الثنائيّة", "mfa_enabled": True}


@router.post("/auth/mfa/disable")
async def mfa_disable(req: main.MfaCodeRequest, user: dict = Depends(main.get_current_user)):
    """يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله مهاجم بتوكن مسروق بلا الجهاز)."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT mfa_secret, mfa_enabled FROM users WHERE id=$1", user_id)
    if not row or not row["mfa_enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA غير مفعّل")
    # حالة غير متّسقة (مفعّل بلا سرّ): لا تُمرّر None لـpyotp (تجنّب 500) — أبلغ صراحةً.
    if not row["mfa_secret"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "حالة MFA غير متّسقة — تواصل مع المسؤول")
    if not main.pyotp.TOTP(row["mfa_secret"]).verify(req.code.strip(), valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح")
    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=FALSE, mfa_secret=NULL, updated_at=NOW() WHERE id=$1",
            user_id,
        )
    await main.audit_log("mfa_disabled", user_id, "authenticated")
    return {"message": "تم تعطيل المصادقة الثنائيّة", "mfa_enabled": False}
