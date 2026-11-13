"""routers/users.py — إدارة مستخدمي **المستأجِر** (owner/admin، محصوران في مستأجِرهما).

مسارات: GET /v1/auth/users · PATCH /v1/auth/users/{user_id}/role ·
        PATCH /v1/auth/users/{user_id}/deactivate

C-01 (تدقيق المالك، قرار 2026-11-13): ``admin`` مالكُ مستأجِرٍ محصورٌ فيه، و``platform_admin``
وحده عابرٌ للمستأجرين — وهو غير معروف في هذه الخدمة، فلا مسار هنا عابرٌ للمستأجرين.
كانت المسارات الثلاثة تقرأ وتكتب أيّ ``user_id`` بلا ``tenant_id`` في ``WHERE``، وRLS لا
تحرسها لأنّ ``main._acquire`` يضبط ``app.current_role='admin'`` فتفتح ``user_self`` كلّ
الصفوف. فالحدّ هنا في طبقة التطبيق:
  • مستأجِر المُنادي من التوكن المُتحقَّق منه وحده (لا من الجسم ولا الاستعلام)، وفي كلّ ``WHERE``.
  • مستخدمٌ في مستأجِرٍ آخر ⇒ 404 بالجسم نفسه لـ«غير موجود» (لا تسريب وجود).
  • قاعدة الدعوة نفسها (``main.is_inviteable_role``): لا يُمنَح إلّا دورٌ أدنى من مالك
    المستأجِر، ولا يُعدَّل/يُعطَّل مالكٌ/مشرفٌ نظير (لا استيلاء أفقيّ داخل المستأجِر).

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة (require_role،
_verify_caller_mfa، مسبح DB) تبقى في ``main`` ويُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import main
from client_address import client_ip
from fastapi import APIRouter, Depends, Header, HTTPException, Request

router = APIRouter()

_NOT_FOUND = "المستخدم غير موجود"

# C-37 (تدقيق المالك): من يُنشئ الفريق يُديره. التسجيل الذاتيّ يُنشئ ``owner`` والدعوة
# يوجّهها owner/admin (``main.INVITER_ROLES``)، فكان قصرُ المسارات الثلاثة على ``admin``
# يترك المالكَ عاجزاً عن إدارة من دعاهم. الحدود نفسها لكليهما: المستأجِر من التوكن وحده،
# ولا يُمنَح إلّا expert/farmer/viewer، ولا يُعدَّل/يُعطَّل مالكٌ/مشرفٌ نظير.
# ``platform_admin`` ليس هنا عمداً: لا وصول عابرَ للمستأجرين في خدمة auth.
_TEAM_MANAGERS: tuple[str, ...] = ("owner", "admin")


def _caller_tenant(admin: dict) -> uuid.UUID | None:
    """مستأجِر المُنادي من التوكن المُتحقَّق منه؛ قيمة غير UUID (مثل ``tenant_{id}`` لحسابٍ
    بلا مستأجِر) ⇒ None ⇒ لا صفوف (fail-closed) بدل مقارنةٍ نصّيّة قد تطابق شيئاً."""
    try:
        return uuid.UUID(str(admin.get("tenant_id") or ""))
    except ValueError:
        return None


async def _lock_tenant_target(conn, user_id: int, tenant: uuid.UUID | None):
    """يقفل صفّ الهدف **داخل مستأجِر المُنادي**؛ غيابه هنا وفي مستأجِرٍ آخر سواء ⇒ 404.
    هدفٌ ليس دوره أدنى من مالك المستأجِر (مالك/مشرف نظير، أو دور مجهول) ⇒ 403."""
    row = None
    if tenant is not None:
        row = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id=$1 AND tenant_id=$2 FOR UPDATE", user_id, tenant
        )
    if not row:
        raise HTTPException(404, _NOT_FOUND)
    if not main.is_inviteable_role(row["role"]):
        raise HTTPException(403, "لا يُعدَّل حساب مالك/مشرف المستأجِر من هذا المسار")
    return row


@router.get("/v1/auth/users")
async def list_users(admin: Annotated[dict, Depends(main.require_role(*_TEAM_MANAGERS))]):
    tenant = _caller_tenant(admin)
    if tenant is None:
        return []
    async with main._acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, email, full_name, role, active, created_at, tenant_id FROM users"
            " WHERE tenant_id=$1 ORDER BY id",
            tenant,
        )
    return [dict(r) for r in rows]


@router.patch("/v1/auth/users/{user_id}/role")
async def change_role(
    user_id: int,
    role: main.ValidRole,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role(*_TEAM_MANAGERS))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # V29.6.1: احسب IP المتّصِل مرّة واحدة ومرّره إلى step-up وإلى التدقيق — كي تحمل
    # أحداث mfa_stepup_* (success/failed/locked) بصمة IP (مُجزّأة HMAC) لا NULL.
    ip = client_ip(request)
    # Step-up MFA (مُفعَّل بالبيئة): جلسة admin وحدها لا تكفي لتغيير دور — يلزم
    # رمز TOTP حديث من المُنفِّذ نفسه. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر.
    if main._admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await main._verify_caller_mfa(caller_id, x_mfa_code, ip=ip):
            await main.audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"change_role target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    # قاعدة الدعوة نفسها: لا دورَ مالكٍ/مشرف عبر هذا المسار (platform_admin يرفضه ValidRole
    # بـ422). يُفحَص قبل البحث عن الهدف فلا يكشف الردّ شيئاً عن مستأجِرٍ آخر.
    if not main.is_inviteable_role(role):
        raise HTTPException(403, "لا يُمنَح إلّا دورٌ أدنى من مالك المستأجِر: expert/farmer/viewer")
    tenant = _caller_tenant(admin)
    async with main._acquire() as conn, conn.transaction():
        await _lock_tenant_target(conn, user_id, tenant)
        row = await conn.fetchrow(
            "UPDATE users SET role=$1 WHERE id=$2 AND tenant_id=$3 RETURNING id, email, role",
            role,
            user_id,
            tenant,
        )
    if not row:  # الصفّ مقفول أعلاه في المعاملة نفسها؛ حزامٌ لا مسارٌ متوقَّع
        raise HTTPException(404, _NOT_FOUND)
    # إبطال جلسات المستخدم ⇒ يُعاد تحميل الدور الجديد فوريّاً (لا يبقى التوكن القديم بدوره القديم)
    await main.revoke_all_user_sessions(user_id)
    await main.audit_log(
        "change_role",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} new_role={role} stepup={main._admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return dict(row)


@router.patch("/v1/auth/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role(*_TEAM_MANAGERS))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # V29.6.1: احسب IP مرّة ومرّره إلى step-up (بصمة IP في أحداث mfa_stepup_*).
    ip = client_ip(request)
    # Step-up MFA (مُفعَّل بالبيئة): تعطيل حساب إجراء حسّاس — يلزم رمز TOTP حديث
    # من المُنفِّذ. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر (لا mfa_code).
    if main._admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await main._verify_caller_mfa(caller_id, x_mfa_code, ip=ip):
            await main.audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"deactivate target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    tenant = _caller_tenant(admin)
    async with main._acquire() as conn, conn.transaction():
        await _lock_tenant_target(conn, user_id, tenant)
        await conn.execute(
            "UPDATE users SET active=FALSE WHERE id=$1 AND tenant_id=$2", user_id, tenant
        )
    await main.revoke_all_user_sessions(user_id)  # التعطيل فوريّ: إبطال كلّ جلسات الحساب
    await main.audit_log(
        "deactivate_user",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} stepup={main._admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return {"message": "تم إلغاء تفعيل الحساب"}
