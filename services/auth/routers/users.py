"""routers/users.py — إدارة المستخدمين (admin فقط).

مسارات: GET /auth/users · PATCH /auth/users/{user_id}/role ·
        PATCH /auth/users/{user_id}/deactivate

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة (require_role،
_verify_caller_mfa، مسبح DB) تبقى في ``main`` ويُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

from typing import Annotated

import main
from fastapi import APIRouter, Depends, Header, HTTPException, Request

router = APIRouter()


@router.get("/auth/users", dependencies=[Depends(main.require_role("admin"))])
async def list_users():
    async with main._acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, email, full_name, role, active, created_at, tenant_id FROM users ORDER BY id"
        )
    return [dict(r) for r in rows]


@router.patch("/auth/users/{user_id}/role")
async def change_role(
    user_id: int,
    role: main.ValidRole,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role("admin"))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # Step-up MFA (مُفعَّل بالبيئة): جلسة admin وحدها لا تكفي لتغيير دور — يلزم
    # رمز TOTP حديث من المُنفِّذ نفسه. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر.
    if main._admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await main._verify_caller_mfa(caller_id, x_mfa_code):
            ip = request.client.host if request.client else "unknown"
            await main.audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"change_role target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET role=$1 WHERE id=$2 RETURNING id, email, role", role, user_id
        )
    if not row:
        raise HTTPException(404, "المستخدم غير موجود")
    # إبطال جلسات المستخدم ⇒ يُعاد تحميل الدور الجديد فوريّاً (لا يبقى التوكن القديم بدوره القديم)
    await main.revoke_all_user_sessions(user_id)
    ip = request.client.host if request.client else "unknown"
    await main.audit_log(
        "change_role",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} new_role={role} stepup={main._admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return dict(row)


@router.patch("/auth/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role("admin"))],
    x_mfa_code: Annotated[str | None, Header()] = None,
):
    # Step-up MFA (مُفعَّل بالبيئة): تعطيل حساب إجراء حسّاس — يلزم رمز TOTP حديث
    # من المُنفِّذ. مُعطَّل افتراضيّاً (CI/dev) ⇒ سلوك غير متغيّر (لا mfa_code).
    if main._admin_stepup_required():
        caller_id = int(admin["sub"])
        if not await main._verify_caller_mfa(caller_id, x_mfa_code):
            ip = request.client.host if request.client else "unknown"
            await main.audit_log(
                "admin_op_mfa_denied",
                caller_id,
                ip,
                details=f"deactivate target={user_id}",
                tenant_id=admin.get("tenant_id"),
            )
            raise HTTPException(403, "يتطلّب هذا الإجراء رمز MFA حديثاً (step-up)")
    async with main._acquire() as conn:
        await conn.execute("UPDATE users SET active=FALSE WHERE id=$1", user_id)
    await main.revoke_all_user_sessions(user_id)  # التعطيل فوريّ: إبطال كلّ جلسات الحساب
    ip = request.client.host if request.client else "unknown"
    await main.audit_log(
        "deactivate_user",
        int(admin["sub"]),
        ip,
        details=f"target={user_id} stepup={main._admin_stepup_required()}",
        tenant_id=admin.get("tenant_id"),
    )
    return {"message": "تم إلغاء تفعيل الحساب"}
