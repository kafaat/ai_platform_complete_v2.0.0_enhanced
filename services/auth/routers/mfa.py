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

    V29.5: السرّ يُخزَّن **مشفّراً** (encrypted_mfa_secret) لا نصّاً؛ يتطلّب مفتاح تشفير
    مُهيَّأ (fail-closed بدونه). لا يُفعّل MFA بعد — التفعيل عبر /auth/mfa/activate.
    السرّ يُعرَض هنا مرّة واحدة فقط (لبناء رمز QR).
    """
    user_id = int(user["sub"])
    if not main.mfa_crypto.encryption_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MFA_SECRET_ENCRYPTION_KEY غير مُهيَّأ — تعذّر إعداد MFA بأمان",
        )
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email, mfa_enabled, tenant_id FROM users WHERE id=$1", user_id
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if row["mfa_enabled"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA مفعّل بالفعل — عطّله أولاً لإعادة الاقتران"
        )

    secret = main.pyotp.random_base32()
    encrypted = main.mfa_crypto.encrypt_secret(secret)
    async with main._acquire() as conn:
        # نخزّن السرّ مشفّراً ونمسح أيّ نصّ قديم؛ mfa_enabled يبقى FALSE حتى التأكيد.
        await conn.execute(
            "UPDATE users SET encrypted_mfa_secret=$1, mfa_secret=NULL, mfa_enabled=FALSE, "
            "updated_at=NOW() WHERE id=$2",
            encrypted,
            user_id,
        )
    uri = main.pyotp.TOTP(secret).provisioning_uri(name=row["email"], issuer_name="SAHOOL")
    await main.audit_log("mfa_setup_started", user_id, "authenticated")
    await main._emit_mfa_audit(
        user_id=user_id, event="mfa_setup_started", outcome="pending", tenant_id=row["tenant_id"]
    )
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "message": "أكّد الرمز عبر /auth/mfa/activate",
    }


@router.post("/auth/mfa/activate")
async def mfa_activate(req: main.MfaCodeRequest, user: dict = Depends(main.get_current_user)):
    """يفعّل MFA بعد تأكيد أوّل رمز صحيح، ويُصدِر رموز استرداد (تُعرَض مرّة واحدة)."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mfa_secret, encrypted_mfa_secret, mfa_enabled, tenant_id "
            "FROM users WHERE id=$1",
            user_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    try:
        secret = main.mfa_crypto.resolve_mfa_secret(row["encrypted_mfa_secret"], row["mfa_secret"])
    except (main.mfa_crypto.MfaKeyMissing, main.mfa_crypto.MfaSecretUndecryptable):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "تعذّر التحقّق من MFA (خلل تشفير الخادم)"
        ) from None
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ابدأ الاقتران أولاً عبر /auth/mfa/setup")
    if not await main._consume_totp_step(user_id, secret, req.code):  # V29.7 anti-replay
        await main._emit_mfa_audit(
            user_id=user_id,
            event="mfa_activate_failed",
            outcome="failed",
            tenant_id=row["tenant_id"],
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح — تأكّد من تطبيق المصادقة")

    # رحّل أيّ سرّ نصّيّ قديم إلى مشفّر عند التفعيل (نقطة ترحيل نظيفة).
    migrate_enc = (
        main.mfa_crypto.encrypt_secret(secret)
        if (row["mfa_secret"] and not row["encrypted_mfa_secret"])
        else None
    )
    async with main._acquire() as conn:
        if migrate_enc:
            await conn.execute(
                "UPDATE users SET mfa_enabled=TRUE, mfa_enabled_at=NOW(), mfa_failed_attempts=0, "
                "mfa_locked_until=NULL, encrypted_mfa_secret=$1, mfa_secret=NULL, updated_at=NOW() "
                "WHERE id=$2",
                migrate_enc,
                user_id,
            )
        else:
            await conn.execute(
                "UPDATE users SET mfa_enabled=TRUE, mfa_enabled_at=NOW(), mfa_failed_attempts=0, "
                "mfa_locked_until=NULL, updated_at=NOW() WHERE id=$1",
                user_id,
            )
    recovery_codes = main.mfa_crypto.generate_recovery_codes()
    await main._store_recovery_codes(user_id, row["tenant_id"], recovery_codes)
    await main.audit_log("mfa_activated", user_id, "authenticated")
    await main._emit_mfa_audit(
        user_id=user_id, event="mfa_enabled", outcome="success", tenant_id=row["tenant_id"]
    )
    await main._emit_mfa_audit(
        user_id=user_id,
        event="mfa_recovery_codes_rotated",
        outcome="success",
        tenant_id=row["tenant_id"],
    )
    return {
        "message": "تم تفعيل المصادقة الثنائيّة",
        "mfa_enabled": True,
        "recovery_codes": recovery_codes,  # تُعرَض مرّة واحدة فقط — احفظها الآن.
        "recovery_codes_notice": "احفظ رموز الاسترداد الآن — لن تُعرَض مرّة أخرى.",
    }


@router.post("/auth/mfa/disable")
async def mfa_disable(req: main.MfaCodeRequest, user: dict = Depends(main.get_current_user)):
    """يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله مهاجم بتوكن مسروق بلا الجهاز)."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mfa_secret, encrypted_mfa_secret, mfa_enabled, tenant_id "
            "FROM users WHERE id=$1",
            user_id,
        )
    if not row or not row["mfa_enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA غير مفعّل")
    try:
        secret = main.mfa_crypto.resolve_mfa_secret(row["encrypted_mfa_secret"], row["mfa_secret"])
    except (main.mfa_crypto.MfaKeyMissing, main.mfa_crypto.MfaSecretUndecryptable):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "تعذّر التحقّق من MFA (خلل تشفير الخادم)"
        ) from None
    # حالة غير متّسقة (مفعّل بلا سرّ): لا تُمرّر None لـpyotp (تجنّب 500) — أبلغ صراحةً.
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "حالة MFA غير متّسقة — تواصل مع المسؤول")
    if not await main._consume_totp_step(user_id, secret, req.code):  # V29.7 anti-replay
        # V29.6 — تعطيل MFA فعل حسّاس: رمز خاطئ يُدخِل نفس القفل (يمنع brute-force بجلسة مسروقة).
        await main._register_mfa_failure(
            user_id,
            event="mfa_disable_failed",
            locked_event="mfa_locked",
            tenant_id=row["tenant_id"],
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح")
    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_enabled=FALSE, mfa_secret=NULL, encrypted_mfa_secret=NULL, "
            "mfa_failed_attempts=0, mfa_locked_until=NULL, updated_at=NOW() WHERE id=$1",
            user_id,
        )
        await conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id=$1", user_id)
    await main.audit_log("mfa_disabled", user_id, "authenticated")
    await main._emit_mfa_audit(
        user_id=user_id, event="mfa_disabled", outcome="success", tenant_id=row["tenant_id"]
    )
    return {"message": "تم تعطيل المصادقة الثنائيّة", "mfa_enabled": False}
