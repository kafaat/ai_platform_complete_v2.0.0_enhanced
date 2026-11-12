"""routers/mfa.py — المصادقة الثنائيّة (TOTP / RFC 6238).

مسارات: POST /v1/auth/mfa/setup · POST /v1/auth/mfa/activate · POST /v1/auth/mfa/disable

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import main
import mfa_crypto
import mfa_enrollment
import pyotp
from client_address import client_ip
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter()


# FastAPI dependencies stay here (``main.security`` is bound at import, and this module is
# reloaded with ``main``); the enrollment logic itself lives in the sibling mfa_enrollment.py.
async def _setup_user(credentials: HTTPAuthorizationCredentials | None = Depends(main.security)):
    return await mfa_enrollment.user_for(credentials, "setup")


async def _activation_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(main.security),
):
    return await mfa_enrollment.user_for(credentials, "activate")


async def _load_mfa_row(user_id: int):
    """حالة MFA للمستخدم (activate/disable) — تشمل mfa_locked_until لبوّابة القفل."""
    async with main._acquire() as conn:
        return await conn.fetchrow(
            "SELECT mfa_secret, encrypted_mfa_secret, mfa_enabled, mfa_locked_until, tenant_id "
            "FROM users WHERE id=$1",
            user_id,
        )


async def _refuse_if_mfa_locked(row, user_id: int, *, locked_event: str) -> None:
    """S3/S4 — يرفض أثناء قفل MFA **قبل** فحص الرمز (رمز صحيح أثناء القفل لا يمرّ).

    نفس بوّابة القفل المُطبَّقة في الدخول وstep-up (mfa_runtime): 429 + تدقيق "blocked".
    """
    if mfa_crypto.is_locked(row["mfa_locked_until"]):
        await main._emit_mfa_audit(
            user_id=user_id, event=locked_event, outcome="blocked", tenant_id=row["tenant_id"]
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "تجاوزت محاولات MFA — الحساب مقفل مؤقّتاً، حاول لاحقاً",
            headers={"X-MFA-Locked": "true"},
        )


@router.post("/v1/auth/mfa/setup")
async def mfa_setup(request: Request, user: dict = Depends(_setup_user)):
    """يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri (لتطبيق المصادقة).

    V29.5: السرّ يُخزَّن **مشفّراً** (encrypted_mfa_secret) لا نصّاً؛ يتطلّب مفتاح تشفير
    مُهيَّأ (fail-closed بدونه). لا يُفعّل MFA بعد — التفعيل عبر /v1/auth/mfa/activate.
    السرّ يُعرَض هنا مرّة واحدة فقط (لبناء رمز QR).
    """
    user_id = int(user["sub"])
    if not mfa_crypto.encryption_configured():
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

    secret = pyotp.random_base32()
    try:
        encrypted = mfa_crypto.encrypt_secret(secret)
    except mfa_crypto.MfaKeyMissing as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MFA_SECRET_ENCRYPTION_KEY غير صالح لبيئة الإنتاج",
        ) from exc
    await mfa_enrollment.consume(user)
    async with main._acquire() as conn:
        # نخزّن السرّ مشفّراً ونمسح أيّ نصّ قديم؛ mfa_enabled يبقى FALSE حتى التأكيد.
        # $3=FALSE لجلسة وصول عاديّة؛ TRUE لإثبات تسجيل ⇒ الكتابة مربوطة بلقطة الإثبات.
        enrolled = await conn.fetchrow(
            "UPDATE users SET encrypted_mfa_secret=$1, mfa_secret=NULL, mfa_enabled=FALSE, "
            "updated_at=NOW() WHERE id=$2 AND active=TRUE AND mfa_enabled=FALSE "
            "AND (NOT $3::boolean OR (password_hash IS NOT DISTINCT FROM $4 "
            "AND role IS NOT DISTINCT FROM $5 AND tenant_id IS NOT DISTINCT FROM $6)) "
            "RETURNING id, password_hash, role, tenant_id, active, mfa_enabled, "
            "encrypted_mfa_secret",
            encrypted,
            user_id,
            *mfa_enrollment.guard_values(user),
        )
    if not enrolled:
        raise HTTPException(409, "MFA enrollment state changed; sign in again")
    # Sign the exact post-update snapshot, never a later reread that could bind a
    # password-proven challenge to credentials changed after this mutation.
    activation = (
        await mfa_enrollment.issue(enrolled, stage="activate", encrypted=encrypted)
        if "_enrollment" in user
        else None
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=row["email"], issuer_name="SAHOOL")
    # R-H3: عنوانٌ صالح ومستأجِرٌ مربوط — كان "authenticated" يُسقط الصفّ (inet).
    await main.audit_log(
        "mfa_setup_started", user_id, client_ip(request), tenant_id=row["tenant_id"]
    )
    await main._emit_mfa_audit(
        user_id=user_id, event="mfa_setup_started", outcome="pending", tenant_id=row["tenant_id"]
    )
    return {
        **(
            {"enrollment_token": activation, "expires_in": mfa_enrollment.TTL_SECONDS}
            if activation
            else {}
        ),
        "secret": secret,
        "provisioning_uri": uri,
        "message": "أكّد الرمز عبر /auth/mfa/activate",
    }


@router.post("/v1/auth/mfa/activate")
async def mfa_activate(
    req: main.MfaCodeRequest, request: Request, user: dict = Depends(_activation_user)
):
    """يفعّل MFA بعد تأكيد أوّل رمز صحيح، ويُصدِر رموز استرداد (تُعرَض مرّة واحدة)."""
    user_id = int(user["sub"])
    row = await _load_mfa_row(user_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    # S3 — مفعّل سلفاً ⇒ رفض: لا تُعاد إصدار رموز استرداد بجلسة (مسروقة) بلا تعطيل
    # مُوثَّق برمز صالح أوّلاً (/mfa/disable)، كما يرفض /mfa/setup.
    if row["mfa_enabled"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "MFA مفعّل بالفعل — عطّله أولاً لإعادة الاقتران"
        )
    await _refuse_if_mfa_locked(row, user_id, locked_event="mfa_locked")
    try:
        secret = mfa_crypto.resolve_mfa_secret(row["encrypted_mfa_secret"], row["mfa_secret"])
    except (mfa_crypto.MfaKeyMissing, mfa_crypto.MfaSecretUndecryptable):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "تعذّر التحقّق من MFA (خلل تشفير الخادم)"
        ) from None
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ابدأ الاقتران أولاً عبر /auth/mfa/setup")
    # يُحجَز رقم المحاولة قبل فحص الرمز (INCR ذرّيّ) كي لا تتجاوز الطلبات المتوازية الحدّ.
    attempt = await mfa_enrollment.reserve_attempt(user)
    if not await main._consume_totp_step(user_id, secret, req.code):  # V29.7 anti-replay
        # S3 — نفس عدّاد/قفل MFA (كان تدقيقاً فقط ⇒ تخمين بلا حدّ).
        await main._register_mfa_failure(
            user_id,
            event="mfa_activate_failed",
            locked_event="mfa_locked",
            tenant_id=row["tenant_id"],
        )
        # الإثبات لا يُستهلَك برمز خاطئ (يُعاد المحاولة)، لكن بحدّ لكلّ إثبات ثمّ يُبطَل.
        await mfa_enrollment.register_failed_attempt(user, attempt)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز غير صحيح — تأكّد من تطبيق المصادقة")

    await mfa_enrollment.consume(user)
    # رحّل أيّ سرّ نصّيّ قديم إلى مشفّر عند التفعيل (نقطة ترحيل نظيفة).
    migrate_enc = (
        mfa_crypto.encrypt_secret(secret)
        if (row["mfa_secret"] and not row["encrypted_mfa_secret"])
        else None
    )
    guard = mfa_enrollment.guard_values(user)
    async with main._acquire() as conn:
        if migrate_enc:
            tag = await conn.execute(
                "UPDATE users SET mfa_enabled=TRUE, mfa_enabled_at=NOW(), mfa_failed_attempts=0, "
                "mfa_locked_until=NULL, encrypted_mfa_secret=$1, mfa_secret=NULL, updated_at=NOW() "
                "WHERE id=$2 AND active=TRUE AND mfa_enabled=FALSE "
                "AND mfa_secret IS NOT DISTINCT FROM $3 "
                "AND (NOT $4::boolean OR (password_hash IS NOT DISTINCT FROM $5 "
                "AND role IS NOT DISTINCT FROM $6 AND tenant_id IS NOT DISTINCT FROM $7))",
                migrate_enc,
                user_id,
                row["mfa_secret"],
                *guard,
            )
        else:
            tag = await conn.execute(
                "UPDATE users SET mfa_enabled=TRUE, mfa_enabled_at=NOW(), mfa_failed_attempts=0, "
                "mfa_locked_until=NULL, updated_at=NOW() WHERE id=$1 "
                "AND active=TRUE AND mfa_enabled=FALSE AND encrypted_mfa_secret IS NOT DISTINCT FROM $2 "
                "AND (NOT $3::boolean OR (password_hash IS NOT DISTINCT FROM $4 "
                "AND role IS NOT DISTINCT FROM $5 AND tenant_id IS NOT DISTINCT FROM $6))",
                user_id,
                row["encrypted_mfa_secret"],
                *guard,
            )
    if tag != "UPDATE 1":
        raise HTTPException(409, "MFA enrollment state changed; sign in again")
    recovery_codes = mfa_crypto.generate_recovery_codes()
    await main._store_recovery_codes(user_id, row["tenant_id"], recovery_codes)
    await main.audit_log("mfa_activated", user_id, client_ip(request), tenant_id=row["tenant_id"])
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


@router.post("/v1/auth/mfa/disable")
async def mfa_disable(
    req: main.MfaCodeRequest, request: Request, user: dict = Depends(main.get_current_user)
):
    """يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله مهاجم بتوكن مسروق بلا الجهاز)."""
    user_id = int(user["sub"])
    row = await _load_mfa_row(user_id)
    if not row or not row["mfa_enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA غير مفعّل")
    # S4 — القفل يُفحَص قبل الرمز: كان يُعَدّ ولا يُطبَّق، فرمز صحيح أثناء القفل عطّل MFA.
    await _refuse_if_mfa_locked(row, user_id, locked_event="mfa_locked")
    try:
        secret = mfa_crypto.resolve_mfa_secret(row["encrypted_mfa_secret"], row["mfa_secret"])
    except (mfa_crypto.MfaKeyMissing, mfa_crypto.MfaSecretUndecryptable):
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
    await main.revoke_all_user_sessions(user_id)
    await main.audit_log("mfa_disabled", user_id, client_ip(request), tenant_id=row["tenant_id"])
    await main._emit_mfa_audit(
        user_id=user_id, event="mfa_disabled", outcome="success", tenant_id=row["tenant_id"]
    )
    return {"message": "تم تعطيل المصادقة الثنائيّة", "mfa_enabled": False}
