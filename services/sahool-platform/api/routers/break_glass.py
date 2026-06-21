"""api/routers/break_glass.py — وصول مدير المنصّة العابر للمستأجرين مُدقَّق
======================================================================
آليّة **break-glass**: مدير المنصّة (platform_admin / صلاحية PLATFORM_MANAGE) لا
يملك وصولاً لبيانات أيّ مستأجِر افتراضيّاً (RLS تعزل بـapp.current_tenant، ودوره
ليس 'admin' فلا يحصل على هروب الخدمة). الوصول العابر مشروعٌ **فقط** عبر منحة
صريحة: محدودة بالزمن، مُتحقَّق منها بـMFA، مُعلَّلة بسبب، ومُدقَّقة على كلّ استخدام.

التصميم (محافِظ — إضافيّ، لا يمسّ tenant_connection العاديّ):
  • POST   /api/v1/admin/break-glass            ← طلب منحة (MFA + سبب + مدّة)
  • GET    /api/v1/admin/break-glass/{token}/fields  ← استخدام مُدقَّق (قراءة حقول الهدف)
  • DELETE /api/v1/admin/break-glass/{id}        ← إبطال منحة

كلّ مسار مُبوَّب بـPLATFORM_MANAGE. كلّ منحة + كلّ استخدام يُدقَّق (audit_log الدائم
+ AUDIT في-الذاكرة). الوصول العابر يمرّ حصراً عبر break_glass_connection (تبعيّة
منفصلة صريحة) — لا نعدّل tenant_connection العاديّ كي لا نُسرّب سهواً.

⚠️ ثوابت الأمان:
  ١) لا وصول عابر بلا منحة صالحة (موجودة، غير منتهية، غير مُبطَلة، تخصّ هذا المدير،
     mfa_verified=TRUE).
  ٢) المنح تنتهي (expires_at مفروض في الاستعلام).
  ٣) كلّ منحة وكلّ استخدام مُدقَّق بالسبب.
  ٤) فقط PLATFORM_MANAGE يطلب/يبطل/يستخدم.
  ٥) لا مسار يتيح لغير-المدير أو لمدير-بلا-منحة قراءة مستأجِر آخر.
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    get_pool,
    require_permission,
)

logger = logging.getLogger("sahool.break_glass")

router = APIRouter()

# سقف مدّة المنحة (دقائق) — منحة عابرة قصيرة العمر؛ لا منح طويلة الأمد.
_MAX_DURATION_MINUTES = 60


# ─── نماذج الطلب ────────────────────────────────────────────────────
class BreakGlassRequest(BaseModel):
    """طلب منحة break-glass — كلّ الحقول إلزاميّة (سبب + MFA + هدف + مدّة)."""

    target_tenant_id: str = Field(..., description="المستأجِر الهدف للوصول العابر (UUID)")
    reason: str = Field(..., min_length=8, max_length=1000, description="سبب الوصول (مُدقَّق)")
    duration_minutes: int = Field(
        ..., ge=1, le=_MAX_DURATION_MINUTES, description=f"مدّة المنحة (≤{_MAX_DURATION_MINUTES})"
    )
    mfa_code: str = Field(..., min_length=6, max_length=10, description="رمز TOTP الحاليّ")


# ─── تحقّق MFA (حقيقيّ — مرآة لخدمة auth، قاعدة users مشتركة) ──────────
async def _verify_admin_mfa(conn, admin_user_id: str, mfa_code: str) -> tuple[bool, str | None]:
    """يتحقّق من رمز MFA للمدير مقابل users.mfa_secret (نفس آليّة auth: pyotp TOTP).

    يُرجِع (verified, admin_email). fail-closed:
      • المدير غير موجود / غير نشط ⇒ (False, …).
      • MFA غير مفعّل للحساب ⇒ (False, …) — break-glass يتطلّب MFA مفعّلاً صراحةً
        (لا يُمنح وصول عابر بلا عامل ثانٍ).
      • mfa_secret فارغ (حالة غير متّسقة) ⇒ (False, …) — لا نمرّر None لـpyotp.
      • رمز خاطئ ⇒ (False, …).
    التحقّق بنافذة ±30s (valid_window=1) — مطابق لخدمة auth.

    ملاحظة عزل: يُقرأ صفّ المدير بمعرّفه (users.id) في سياق إدارة المنصّة (بلا
    app.current_tenant) — لا يكشف بيانات مستأجِر.
    """
    import pyotp

    try:
        uid = int(admin_user_id)
    except (TypeError, ValueError):
        return False, None

    row = await conn.fetchrow(
        "SELECT email, mfa_secret, mfa_enabled, active FROM users WHERE id = $1",
        uid,
    )
    if not row or not row["active"]:
        return False, None
    email = row["email"]
    if not row["mfa_enabled"]:
        # break-glass يتطلّب MFA مفعّلاً — لا تجاوز صامت.
        return False, email
    secret = row["mfa_secret"]
    if not secret:
        # مفعّل بلا سرّ — حالة غير متّسقة؛ fail-closed.
        return False, email
    verified = pyotp.TOTP(secret).verify(mfa_code.strip(), valid_window=1)
    return bool(verified), email


# ─── تدقيق دائم (audit_log) + في-الذاكرة (AUDIT) ─────────────────────
async def _audit_db(conn, action: str, *, admin_user_id: str, target_tenant_id: str, details: str):
    """يكتب حدث تدقيق في جدول audit_log الدائم (ضمن نفس المعاملة).

    audit_log: (action, user_id, details, tenant_id). نضع tenant_id = المستأجِر
    الهدف (موضوع الوصول العابر) كي يربط التحقيق الجنائيّ الحدثَ بالمستأجِر المُتأثّر.
    لا يرفع: فشل التدقيق لا يُفشِل العمليّة الأمنيّة الجارية (best-effort داخل savepoint).
    """
    try:
        async with conn.transaction():  # savepoint
            await conn.execute(
                "INSERT INTO audit_log (action, user_id, details, tenant_id) "
                "VALUES ($1, $2, $3, $4::uuid)",
                action,
                int(admin_user_id) if str(admin_user_id).isdigit() else None,
                details,
                str(target_tenant_id),
            )
    except Exception as e:  # noqa: BLE001 — التدقيق لا يكسر المسار (لكن نُسجّله بوضوح)
        logger.warning("audit_log كتابة %s تخطّي: %s", action, type(e).__name__)


def _audit_mem(kind_action: str, *, user_id: str, tenant_id: str, reason_ar: str):
    """يسجّل في AUDIT في-الذاكرة (يُرى عبر /admin/security/denials وما شابه)."""
    from core.tenant_audit import AUDIT

    AUDIT.record(
        "tenant_scope",
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        action=kind_action,
        reason_ar=reason_ar,
    )


# ─── ١) طلب منحة ────────────────────────────────────────────────────
@router.post("/api/v1/admin/break-glass")
async def request_break_glass(
    req: BreakGlassRequest,
    user: UserSchema = Depends(require_permission(Permission.PLATFORM_MANAGE)),
):
    """يطلب منحة break-glass: يتحقّق من MFA، يُنشئ صفّ منحة، يُدقّق، يُعيد التوكن + الانتهاء.

    fail-closed: MFA غير صحيح ⇒ 403 (لا تُنشأ منحة). المدّة مسقوفة بـ_MAX_DURATION_MINUTES.
    """
    import uuid as _uuid

    # تحقّق شكل UUID للهدف مبكّراً (لا نُنشئ منحة لهدف مُشوَّه).
    try:
        _uuid.UUID(str(req.target_tenant_id))
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="target_tenant_id يجب أن يكون UUID") from e

    grant_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # سياق إدارة المنصّة: لا app.current_tenant (سياسة break_glass_grants
                # تسمح بسياق بلا-مستأجِر). لا نضبط دور 'admin' (لا هروب خدمة عريض).
                verified, admin_email = await _verify_admin_mfa(conn, user.user_id, req.mfa_code)
                if not verified:
                    # تدقيق محاولة فاشلة (لا تُنشأ منحة).
                    await _audit_db(
                        conn,
                        "break_glass_denied",
                        admin_user_id=user.user_id,
                        target_tenant_id=req.target_tenant_id,
                        details=f"MFA غير صحيح/غير مفعّل؛ السبب المطلوب: {req.reason[:200]}",
                    )
                    _audit_mem(
                        "break_glass_denied",
                        user_id=user.user_id,
                        tenant_id=req.target_tenant_id,
                        reason_ar="رفض منحة break-glass: MFA غير صحيح/غير مفعّل",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="تعذّر التحقّق من MFA — break-glass يتطلّب رمز MFA صحيحاً ومفعّلاً.",
                    )

                expires_at = now + timedelta(minutes=req.duration_minutes)
                grant_id = await conn.fetchval(
                    """INSERT INTO break_glass_grants
                           (admin_user_id, admin_email, target_tenant_id, reason,
                            mfa_verified, granted_at, expires_at, grant_token)
                       VALUES ($1, $2, $3::uuid, $4, TRUE, $5, $6, $7)
                       RETURNING id""",
                    int(user.user_id) if str(user.user_id).isdigit() else None,
                    admin_email,
                    str(req.target_tenant_id),
                    req.reason,
                    now,
                    expires_at,
                    grant_token,
                )
                await _audit_db(
                    conn,
                    "break_glass_granted",
                    admin_user_id=user.user_id,
                    target_tenant_id=req.target_tenant_id,
                    details=(
                        f"grant_id={grant_id} duration_min={req.duration_minutes} "
                        f"expires={expires_at.isoformat()} reason={req.reason[:300]}"
                    ),
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء منحة break-glass", e) from e

    _audit_mem(
        "break_glass_granted",
        user_id=user.user_id,
        tenant_id=req.target_tenant_id,
        reason_ar=f"منحة break-glass مُنشأة (سبب: {req.reason[:120]})",
    )
    return {
        "grant_id": grant_id,
        "grant_token": grant_token,
        "target_tenant_id": str(req.target_tenant_id),
        "expires_at": expires_at.isoformat(),
        "mfa_verified": True,
        "note_ar": (
            "منحة وصول عابر مُدقَّقة. قدّم grant_token لاستخدامها قبل الانتهاء. "
            "كلّ استخدام يُدقَّق. أبطِلها فور انتهاء الغرض عبر DELETE."
        ),
    }


# ─── تبعيّة الإنفاذ: break_glass_connection (الجزء الحسّاس) ────────────
@asynccontextmanager
async def break_glass_connection(grant_token: str, user: UserSchema):
    """يفتح اتّصالاً يضبط app.current_tenant على **المستأجِر الهدف** للمنحة فقط — بعد
    التحقّق الكامل من المنحة — ويُدقّق كلّ استخدام. منفصل تماماً عن tenant_connection
    العاديّ (لا يُعدَّل سلوك المستخدمين العاديّين).

    التحقّق (fail-closed، كلّه في استعلام واحد ذرّيّ تحت قفل الصفّ FOR UPDATE):
      • المنحة موجودة بهذا التوكن.
      • تخصّ هذا المدير (admin_user_id = user.user_id).
      • غير مُبطَلة (revoked = FALSE).
      • غير منتهية (expires_at > NOW()).
      • mfa_verified = TRUE.
    أيّ إخفاق ⇒ 403 (لا يُضبط أيّ سياق مستأجِر). عند النجاح: يزيد access_count +
    last_used_at، يُدقّق break_glass_access، ثمّ يضبط app.current_tenant = الهدف.

    ملاحظة أمنيّة: السياق يُضبط على المستأجِر الهدف فقط (RLS تظلّ مفروضة على ذلك
    المستأجِر) — ليس هروباً عريضاً. لا نضبط app.current_role='admin'.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # سياق إدارة المنصّة (بلا مستأجِر) للقراءة/التحديث على break_glass_grants.
            row = await conn.fetchrow(
                """SELECT id, target_tenant_id, reason, admin_email
                   FROM break_glass_grants
                   WHERE grant_token = $1
                     AND admin_user_id = $2
                     AND revoked = FALSE
                     AND mfa_verified = TRUE
                     AND expires_at > NOW()
                   FOR UPDATE""",
                grant_token,
                int(user.user_id) if str(user.user_id).isdigit() else -1,
            )
            if not row:
                # تدقيق محاولة استخدام فاشلة (منحة مفقودة/منتهية/مُبطَلة/لغير المالك).
                _audit_mem(
                    "break_glass_access_denied",
                    user_id=user.user_id,
                    tenant_id="unknown",
                    reason_ar="رفض استخدام break-glass: منحة غير صالحة/منتهية/مُبطَلة",
                )
                raise HTTPException(
                    status_code=403,
                    detail="منحة break-glass غير صالحة (غير موجودة/منتهية/مُبطَلة/لغير صاحبها).",
                )
            target_tenant_id = str(row["target_tenant_id"])
            # عدّاد الاستخدام + آخر استخدام (داخل نفس المعاملة).
            await conn.execute(
                "UPDATE break_glass_grants SET access_count = access_count + 1, "
                "last_used_at = NOW() WHERE id = $1",
                row["id"],
            )
            # تدقيق دائم على كلّ استخدام (قبل ضبط سياق المستأجِر — السياق الإداريّ ما زال فعّالاً).
            await _audit_db(
                conn,
                "break_glass_access",
                admin_user_id=user.user_id,
                target_tenant_id=target_tenant_id,
                details=f"grant_id={row['id']} reason={str(row['reason'])[:300]}",
            )
            # الآن اضبط سياق المستأجِر الهدف فقط (RLS تظلّ مفروضة عليه).
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "       set_config('app.current_user_id', $2, true), "
                "       set_config('app.current_role', $3, true)",
                target_tenant_id,
                str(user.user_id),
                # دور المدير الفعليّ (platform_admin) — **ليس** 'admin' (لا هروب خدمة عريض).
                user.role.value if hasattr(user.role, "value") else str(user.role),
            )
            _audit_mem(
                "break_glass_access",
                user_id=user.user_id,
                tenant_id=target_tenant_id,
                reason_ar=f"استخدام break-glass (سبب: {str(row['reason'])[:120]})",
            )
            yield conn, target_tenant_id


# ─── ٢) استخدام مُدقَّق (قراءة حقول الهدف) — عرض المسار المُدقَّق ──────
@router.get("/api/v1/admin/break-glass/{token}/fields")
async def break_glass_read_fields(
    token: str,
    user: UserSchema = Depends(require_permission(Permission.PLATFORM_MANAGE)),
):
    """قراءة حقول المستأجِر الهدف عبر منحة break-glass صالحة — كلّ استخدام مُدقَّق.

    عرضٌ للمسار المُدقَّق (لا نُعمّم على كلّ النقاط). RLS تُرشّح بالمستأجِر الهدف
    (المضبوط داخل break_glass_connection) — لا تسرّب لمستأجِر آخر.
    """
    try:
        async with break_glass_connection(token, user) as (conn, target_tenant_id):
            recs = await conn.fetch(
                """SELECT field_id, name, area_ha, crop, soil_type, gov
                   FROM fields ORDER BY field_id LIMIT 500"""
            )
            fields = [
                {
                    "field_id": r["field_id"],
                    "name": r["name"],
                    "area_ha": float(r["area_ha"]) if r["area_ha"] is not None else None,
                    "crop": r["crop"],
                    "soil_type": r["soil_type"],
                    "gov": r["gov"],
                }
                for r in recs
            ]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حقول المستأجِر عبر break-glass", e) from e
    return {
        "target_tenant_id": target_tenant_id,
        "fields": fields,
        "total": len(fields),
        "note_ar": "وصول عابر مُدقَّق عبر break-glass — هذا الاستخدام سُجّل في سجلّ التدقيق.",
    }


# ─── ٣) إبطال منحة ──────────────────────────────────────────────────
@router.delete("/api/v1/admin/break-glass/{grant_id}")
async def revoke_break_glass(
    grant_id: int,
    user: UserSchema = Depends(require_permission(Permission.PLATFORM_MANAGE)),
):
    """يُبطِل منحة break-glass (revoked=TRUE) + يُدقّق. بعدها أيّ استخدام يُرفَض.

    أيّ مدير منصّة (PLATFORM_MANAGE) يستطيع إبطال أيّ منحة (حوكمة: قطع الوصول فوراً).
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE break_glass_grants
                       SET revoked = TRUE
                       WHERE id = $1 AND revoked = FALSE
                       RETURNING id, target_tenant_id, admin_user_id""",
                    grant_id,
                )
                if not row:
                    raise HTTPException(
                        status_code=404, detail="لا منحة بهذا المعرّف (أو مُبطَلة مسبقاً)."
                    )
                target_tenant_id = str(row["target_tenant_id"])
                await _audit_db(
                    conn,
                    "break_glass_revoked",
                    admin_user_id=user.user_id,
                    target_tenant_id=target_tenant_id,
                    details=f"grant_id={grant_id} revoked_by={user.user_id}",
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إبطال منحة break-glass", e) from e

    _audit_mem(
        "break_glass_revoked",
        user_id=user.user_id,
        tenant_id=target_tenant_id,
        reason_ar="إبطال منحة break-glass",
    )
    return {"grant_id": grant_id, "revoked": True, "target_tenant_id": target_tenant_id}
