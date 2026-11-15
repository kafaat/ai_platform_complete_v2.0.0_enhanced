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

Team administration hardening (admin authz follow-up):
  • the signed claims are checked against active DB membership (``_validate_team_actor``),
    so a stale or deactivated owner/admin token cannot manage the team;
  • sessions are revoked before the account row changes, and a missing or failing
    revocation backend leaves the row untouched (503);
  • the UPDATE itself re-asserts the non-privileged target, so a race returns 409.
Creating another owner or platform administrator stays a separate, reviewed workflow.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

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


async def _validate_team_actor(conn, actor: dict) -> str:
    """Verify signed claims against active DB membership, not JWT role alone."""
    try:
        tenant_id = str(UUID(str(actor.get("tenant_id") or "")))
        actor_id = int(actor["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(403, "هوية المؤسسة أو المستخدم غير صالحة") from exc

    row = await conn.fetchrow(
        "SELECT role, active FROM users WHERE id=$1 AND tenant_id=$2::uuid",
        actor_id,
        tenant_id,
    )
    if (
        not row
        or not row["active"]
        or row["role"] not in ("owner", "admin")
        or row["role"] != actor.get("role")
    ):
        raise HTTPException(403, "إدارة الفريق تتطلّب عضوية إدارية فعّالة في المؤسسة")
    return tenant_id


@router.get("/v1/auth/users")
async def list_users(admin: Annotated[dict, Depends(main.require_role(*_TEAM_MANAGERS))]):
    async with main._acquire() as conn:
        tenant_id = await _validate_team_actor(conn, admin)
        rows = await conn.fetch(
            "SELECT id, email, full_name, role, active, created_at, tenant_id "
            "FROM users WHERE tenant_id=$1::uuid ORDER BY id",
            tenant_id,
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
    # Team management cannot mint an owner or a platform/admin credential.
    if not main.is_inviteable_role(role):
        raise HTTPException(403, "تعيين owner/admin يحتاج إجراءً مستقلاً لنقل الملكية")
    ip = client_ip(request)
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
    async with main._acquire() as conn, conn.transaction():
        tenant_id = await _validate_team_actor(conn, admin)
        target = await conn.fetchrow(
            "SELECT role FROM users WHERE id=$1 AND tenant_id=$2::uuid FOR UPDATE",
            user_id,
            tenant_id,
        )
        if not target:
            raise HTTPException(404, _NOT_FOUND)
        if not main.is_inviteable_role(target["role"]):
            raise HTTPException(403, "لا يجوز تغيير مالك أو مشرف من إدارة الفريق")
        # Invalidate first. If Redis fails, no UPDATE is committed; callers can
        # re-authenticate if a subsequent DB operation fails after invalidation.
        if main._redis is None:
            raise HTTPException(503, "لا يمكن تعديل الحساب دون نظام إبطال الجلسات")
        try:
            await main.revoke_all_user_sessions(user_id)
        except Exception as exc:
            raise HTTPException(503, "تعذّر إبطال الجلسات؛ لم يُعدّل الحساب") from exc
        row = await conn.fetchrow(
            "UPDATE users SET role=$1 WHERE id=$2 AND tenant_id=$3::uuid "
            "AND role NOT IN ('owner','admin') RETURNING id, email, role",
            role,
            user_id,
            tenant_id,
        )
        if not row:
            raise HTTPException(409, "تغيّر دور المستهدف أثناء الطلب")
    await main.audit_log(
        "change_role",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} new_role={role} stepup={main._admin_stepup_required()}",
        tenant_id=tenant_id,
    )
    return dict(row)


@router.patch("/v1/auth/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role(*_TEAM_MANAGERS))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    ip = client_ip(request)
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
    async with main._acquire() as conn, conn.transaction():
        tenant_id = await _validate_team_actor(conn, admin)
        target = await conn.fetchrow(
            "SELECT role, active FROM users WHERE id=$1 AND tenant_id=$2::uuid FOR UPDATE",
            user_id,
            tenant_id,
        )
        if not target:
            raise HTTPException(404, _NOT_FOUND)
        if not main.is_inviteable_role(target["role"]):
            raise HTTPException(403, "لا يمكن تعطيل مالك أو مشرف من إدارة الفريق")
        if not target["active"]:
            return {"message": "الحساب معطّل مسبقاً"}
        # Invalidate first. If Redis fails, no UPDATE is committed; callers can
        # re-authenticate if a subsequent DB operation fails after invalidation.
        if main._redis is None:
            raise HTTPException(503, "لا يمكن تعديل الحساب دون نظام إبطال الجلسات")
        try:
            await main.revoke_all_user_sessions(user_id)
        except Exception as exc:
            raise HTTPException(503, "تعذّر إبطال الجلسات؛ لم يُعدّل الحساب") from exc
        status = await conn.execute(
            "UPDATE users SET active=FALSE WHERE id=$1 AND tenant_id=$2::uuid "
            "AND role NOT IN ('owner','admin') AND active=TRUE",
            user_id,
            tenant_id,
        )
        if status != "UPDATE 1":
            raise HTTPException(409, "تغيّرت حالة المستخدم أثناء الطلب")
    await main.audit_log(
        "deactivate_user",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} stepup={main._admin_stepup_required()}",
        tenant_id=tenant_id,
    )
    return {"message": "تم إلغاء تفعيل الحساب"}
