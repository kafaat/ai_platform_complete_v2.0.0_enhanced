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

سياق القاعدة (BREAK-GLASS-RUNS-WITHOUT-TENANT-CONTEXT): كلّ وصول يجري داخل
tenant_connection(المُنادي) — لا اتّصال بلا سياق (كان users يُرجِع صفراً تحت sahool_app
فتعطّل MFA، وv237 يُغلق ذراع «بلا سياق» في audit_log/break_glass_grants). سجلّ المنح
عابرٌ بطبيعته فيُلمَس حصراً عبر مسار الخدمة الصريح (app.current_role='admin' — الذراع
الذي تُبقيه v87/v90/v237) داخل savepoint ضيّق (_grant_registry)، ومحصوراً بمنح مستأجِر
المُنادي (مالكها مديرٌ من مستأجِره). سياق الهدف يُشتقّ من صفّ المنحة لا من الجسم.

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
    require_permission,
    tenant_connection,
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

    ملاحظة عزل: يُستدعى داخل tenant_connection(المدير) — سياسة user_self تسمح بصفّه عبر
    app.current_user_id. بلا سياق كانت تُرشّح الصفّ تحت sahool_app ⇒ break-glass معطّل.
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
async def _audit_db(conn, action: str, *, admin_user_id: str, tenant_id: str, details: str):
    """يكتب حدث تدقيق في جدول audit_log الدائم (ضمن نفس المعاملة).

    audit_log: (action, user_id, details, tenant_id). tenant_id = **مستأجِر السياق الفعّال**
    (WITH CHECK في v87 يرفض صفّاً لمستأجِر غير المضبوط): مستأجِر المُنادي لأحداث الطلب/
    الإبطال، والهدفُ المُشتقّ من المنحة لحدث الاستخدام. الهدف يُذكَر في details دائماً.
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
                str(tenant_id),
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


def _role_of(user: UserSchema) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


@asynccontextmanager
async def _grant_registry(conn, user: UserSchema):
    """مسار الخدمة الصريح لسجلّ المنح العابر (break_glass_grants) — لا سواه.

    سياسة v90 تسمح بالجدول لسياق «بلا مستأجِر» أو app.current_role='admin'؛ وv237 تُبقي
    الثاني وحده. فنرفع الدور داخل savepoint ضيّق ثمّ نُعيد دور المُنادي؛ أيّ استثناء يُرجِع
    الـsavepoint فيعود الدور تلقائيّاً. لا تُنفَّذ هنا إلّا عبارات break_glass_grants (يحرسه
    اختبار)، وكلّ استعمال مُدقَّق في audit_log.
    """
    async with conn.transaction():  # savepoint: الرفع لا يعبر هذه الكتلة
        await conn.execute("SELECT set_config('app.current_role', 'admin', true)")
        yield conn
        await conn.execute("SELECT set_config('app.current_role', $1, true)", _role_of(user))


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
    denied = False
    try:
        # سياق المُنادي (مستأجِره + معرّفه) — MFA يقرأ صفّه عبر user_self.
        async with tenant_connection(user) as conn:
            verified, admin_email = await _verify_admin_mfa(conn, user.user_id, req.mfa_code)
            if not verified:
                # تدقيق محاولة فاشلة (لا تُنشأ منحة) — يُرفَع 403 بعد الـcommit لا داخله
                # (الرفع داخل المعاملة كان يُرجِع صفّ التدقيق نفسه).
                denied = True
                await _audit_db(
                    conn,
                    "break_glass_denied",
                    admin_user_id=user.user_id,
                    tenant_id=user.tenant_id,
                    details=(
                        f"MFA غير صحيح/غير مفعّل؛ الهدف المطلوب={req.target_tenant_id} "
                        f"السبب المطلوب: {req.reason[:200]}"
                    ),
                )
            else:
                expires_at = now + timedelta(minutes=req.duration_minutes)
                async with _grant_registry(conn, user):
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
                        _hash_grant_token(grant_token),  # T8: لا يُخزَّن الرمز صريحاً
                    )
                await _audit_db(
                    conn,
                    "break_glass_granted",
                    admin_user_id=user.user_id,
                    tenant_id=user.tenant_id,
                    details=(
                        f"grant_id={grant_id} target={req.target_tenant_id} "
                        f"duration_min={req.duration_minutes} "
                        f"expires={expires_at.isoformat()} reason={req.reason[:300]}"
                    ),
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء منحة break-glass", e) from e

    if denied:
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
    last_used_at، يضبط app.current_tenant = الهدف (من صفّ المنحة)، ثمّ يُدقّق
    break_glass_access في سجلّ ذلك المستأجِر. قراءة المنحة عبر _grant_registry فقط.

    ملاحظة أمنيّة: السياق يُضبط على المستأجِر الهدف فقط (RLS تظلّ مفروضة على ذلك
    المستأجِر) — ليس هروباً عريضاً. لا نضبط app.current_role='admin'.
    """
    uid = int(user.user_id) if str(user.user_id).isdigit() else -1
    async with tenant_connection(user) as conn:  # سياق المُنادي أوّلاً — لا اتّصال بلا سياق
        async with conn.transaction():  # savepoint يحمل سياق الهدف حتى نهاية الاستخدام
            async with _grant_registry(conn, user):
                row = await conn.fetchrow(
                    """SELECT id, target_tenant_id, reason, admin_email, grant_token
                       FROM break_glass_grants
                       WHERE grant_token = $1
                         AND admin_user_id = $2
                         AND revoked = FALSE
                         AND mfa_verified = TRUE
                         AND expires_at > NOW()
                       FOR UPDATE""",
                    _hash_grant_token(grant_token),  # البحث بالـhash (T8)
                    uid,
                )
                if row is not None and not _grant_token_matches(row["grant_token"], grant_token):
                    row = None  # T8: صفّ قديم بنصّ صريح/عدم تطابق ⇒ fail-closed
                if row:
                    # عدّاد الاستخدام + آخر استخدام (داخل نفس المعاملة).
                    await conn.execute(
                        "UPDATE break_glass_grants SET access_count = access_count + 1, "
                        "last_used_at = NOW() WHERE id = $1",
                        row["id"],
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
            # الهدف من صفّ المنحة المُتحقَّق (لا من الجسم) — RLS تظلّ مفروضة عليه.
            target_tenant_id = str(row["target_tenant_id"])
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "       set_config('app.current_user_id', $2, true), "
                "       set_config('app.current_role', $3, true)",
                target_tenant_id,
                str(user.user_id),
                # دور المدير الفعليّ (platform_admin) — **ليس** 'admin' (لا هروب خدمة عريض).
                _role_of(user),
            )
            # تدقيق دائم على كلّ استخدام — في سجلّ المستأجِر المُتأثّر (سياقه الآن).
            await _audit_db(
                conn,
                "break_glass_access",
                admin_user_id=user.user_id,
                tenant_id=target_tenant_id,
                details=f"grant_id={row['id']} reason={str(row['reason'])[:300]}",
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

    أيّ مدير منصّة في **مستأجِر المُنادي** يستطيع إبطال منح ذلك المستأجِر (حوكمة: قطع
    الوصول فوراً). منحةٌ أصدرها مديرٌ من مستأجِر آخر ⇒ 404 (لا كشف وجودها).
    """
    try:
        async with tenant_connection(user) as conn:
            async with _grant_registry(conn, user):
                # مستأجِر المالك من المُنادي المُصادَق (لا من الجسم) — شرطٌ صريح لأنّ دور
                # الخدمة يفتح users أيضاً.
                row = await conn.fetchrow(
                    """UPDATE break_glass_grants
                       SET revoked = TRUE
                       WHERE id = $1 AND revoked = FALSE
                         AND admin_user_id IN (
                             SELECT u.id FROM users u WHERE u.tenant_id::text = $2)
                       RETURNING id, target_tenant_id, admin_user_id""",
                    grant_id,
                    str(user.tenant_id),
                )
            if not row:
                raise HTTPException(status_code=404, detail="لا منحة بهذا المعرّف (أو مُبطَلة مسبقاً).")
            target_tenant_id = str(row["target_tenant_id"])
            await _audit_db(
                conn,
                "break_glass_revoked",
                admin_user_id=user.user_id,
                tenant_id=user.tenant_id,
                details=f"grant_id={grant_id} target={target_tenant_id} revoked_by={user.user_id}",
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


# ─── T8: تخزين رمز المنحة مُجزّأً + حجبه من سجلّ الوصول ─────────────────
# في ذيل الملفّ عمداً: مراسي أسطر المسارات في platform_extraction_map.json (§٣.١٥) لا تنزاح.
# grant_token = token_urlsafe(32) (٢٥٦ بتّاً عشوائيّة) ⇒ SHA-256 بلا سرّ كافٍ، والبحث بالفهرس
# الفريد القائم بلا هجرة. صفّ قديم بنصّ صريح (بلا البادئة) لا يطابق أبداً ⇒ يُرفَض (عمر المنحة
# ≤٦٠ دقيقة؛ يُطلَب غيرها) — فمن قرأ الجدول قبل التغيير لا يملك رمزاً صالحاً بعده.
_GRANT_TOKEN_HASH_PREFIX = "sha256:"


def _hash_grant_token(grant_token: str) -> str:
    """القيمة المخزَّنة في break_glass_grants.grant_token (لا الرمز نفسه)."""
    import hashlib  # محلّيّ: استيراد في الرأس يُزيح المراسي

    digest = hashlib.sha256(str(grant_token).encode("utf-8")).hexdigest()
    return _GRANT_TOKEN_HASH_PREFIX + digest


def _grant_token_matches(stored: str | None, grant_token: str) -> bool:
    """مقارنة بزمن ثابت؛ صفّ قديم بنصّ صريح لا يطابق — fail-closed."""
    if not stored or not str(stored).startswith(_GRANT_TOKEN_HASH_PREFIX):
        return False
    return secrets.compare_digest(str(stored), _hash_grant_token(grant_token))


class _RedactGrantTokenAccessLog(logging.Filter):
    """مسار الاستخدام يحمل الرمز ({token}/fields) ⇒ يُحجَب من سطر uvicorn.access."""

    _PREFIX = "/api/v1/admin/break-glass/"

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path = args[2]
            if path.startswith(self._PREFIX):
                token, sep, tail = path[len(self._PREFIX) :].partition("/")
                if token and sep:  # /{token}/fields فقط؛ DELETE /{grant_id} بلا ذيل يبقى
                    path = f"{self._PREFIX}[redacted]/{tail}"
                    record.args = (*args[:2], path, *args[3:])
        return True


_ACCESS_LOG_FILTER = _RedactGrantTokenAccessLog()
logging.getLogger("uvicorn.access").addFilter(_ACCESS_LOG_FILTER)
