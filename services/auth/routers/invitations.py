"""routers/invitations.py — دعوات أعضاء المستأجِر (انضمام بأدوار أدنى).

مسارات: GET /auth/invitations · POST /auth/invitations ·
        POST /auth/invitations/accept · DELETE /auth/invitations/{invitation_id}

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة (can_invite،
is_inviteable_role، INVITATION_EXPIRY_DAYS، مسبح DB، النماذج) تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import main
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter()


@router.post("/auth/invitations", status_code=201)
async def create_invitation(
    req: main.InvitationCreateRequest,
    request: Request,
    user: Annotated[dict, Depends(main.get_current_user)],
):
    """يُنشئ دعوة عضو لمستأجِر الداعي. owner/admin فقط، وبأدوار أدنى حصراً.

    أمان: tenant_id يُؤخَذ من توكن الداعي (لا من العميل)؛ الدور مُقيَّد بـ
    {expert,farmer,viewer} (Literal + فحص صريح) — owner/admin مرفوضان (تصعيد).
    """
    ip = request.client.host if request.client else "unknown"
    if not main.can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "الدعوة تتطلّب دور مالك المستأجِر")
    # دفاع عمق: حتى لو تجاوز Literal، نرفض أيّ دور غير قابل للدعوة صراحةً.
    if not main.is_inviteable_role(req.role):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "الدور غير قابل للدعوة — المسموح: expert/farmer/viewer (لا owner/admin)",
        )

    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "لا مستأجِر مرتبط بالحساب الداعي")
    inviter_id = int(user["sub"])
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=main.INVITATION_EXPIRY_DAYS)

    async with main._acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO invitations
                (token, email, tenant_id, role, invited_by, status, expires_at)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6)
            RETURNING id, email, role, tenant_id, expires_at, created_at
            """,
            token,
            req.email,
            tenant_id,
            req.role,
            inviter_id,
            expires_at,
        )

    await main.audit_log("invite_created", inviter_id, ip, details=req.email, tenant_id=tenant_id)
    # لا إرسال بريد هنا (SMTP غير مضمون) — نُعيد الرابط لتعرضه الواجهة للنسخ.
    accept_url = f"/accept-invitation?token={token}"
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "tenant_id": str(row["tenant_id"]),
        "token": token,
        "accept_url": accept_url,
        "expires_at": row["expires_at"].isoformat(),
        "status": "pending",
    }


@router.get("/auth/invitations")
async def list_invitations(user: Annotated[dict, Depends(main.get_current_user)]):
    """يسرد الدعوات المعلّقة لمستأجِر الداعي (owner/admin فقط)، tenant-scoped."""
    if not main.can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلّب دور مالك المستأجِر")
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return []
    async with main._acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, email, role, status, expires_at, created_at
            FROM invitations
            WHERE tenant_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
            """,
            tenant_id,
        )
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "role": r["role"],
            "status": r["status"],
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.post("/auth/invitations/accept", response_model=main.TokenResponse, status_code=201)
async def accept_invitation(req: main.InvitationAcceptRequest, request: Request):
    """قبول دعوة (عموميّ، محميّ بالـtoken): يُنشئ مستخدِماً ينضمّ لمستأجِر الداعي.

    أمان: الدور والمستأجِر يُؤخذان من **صفّ الدعوة فقط** — العميل لا يختارهما.
    يرفض إن كان الـtoken غير صالح/منتهٍ/مستهلَكاً أو البريد مسجّلاً مسبقاً.
    """
    ip = request.client.host if request.client else "unknown"
    await main.check_ip_rate(ip)
    now = datetime.now(UTC)

    async with main._acquire() as conn:
        inv = await conn.fetchrow(
            """
            SELECT id, email, tenant_id, role, status, expires_at
            FROM invitations
            WHERE token = $1
            """,
            req.token,
        )
        if not inv or inv["status"] != "pending":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "دعوة غير صالحة أو مستهلَكة")
        if inv["expires_at"] and inv["expires_at"] <= now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "انتهت صلاحيّة الدعوة")
        # حزام أمان نهائيّ: ارفض الدور المميَّز ولو سرّب إلى صفّ الدعوة بأيّ شكل.
        if not main.is_inviteable_role(inv["role"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "دور الدعوة غير مسموح")

        hashed = main.bcrypt.hashpw(
            req.password.encode(), main.bcrypt.gensalt(main.BCRYPT_ROUNDS)
        ).decode()
        # المستخدِم الجديد ينضمّ لمستأجِر الداعي بدوره المدعوّ — كلاهما من صفّ الدعوة.
        try:
            new_user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role, tenant_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, email, role, full_name, tenant_id
                """,
                inv["email"],
                hashed,
                req.full_name,
                inv["role"],
                inv["tenant_id"],
            )
        except main.asyncpg.UniqueViolationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد مسجّل مسبقاً") from e

        # وسم الدعوة مقبولة (idempotent: شرط status='pending' يمنع قبولاً مزدوجاً متسابِقاً).
        await conn.execute(
            "UPDATE invitations SET status='accepted', accepted_at=$1 WHERE id=$2",
            now,
            inv["id"],
        )

    tid = str(new_user["tenant_id"])
    token, _jti = main.create_access_token(
        new_user["id"], new_user["email"], new_user["role"], new_user["full_name"], tid
    )
    refresh = await main.create_refresh_token(new_user["id"], tid)
    await main.audit_log(
        "invite_accepted", new_user["id"], ip, details=new_user["email"], tenant_id=tid
    )

    return main.TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=main.JWT_EXPIRE_MINUTES * 60,
        user_id=new_user["id"],
        role=new_user["role"],
        full_name=new_user["full_name"],
        tenant_id=tid,
    )


@router.delete("/auth/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: int,
    request: Request,
    user: Annotated[dict, Depends(main.get_current_user)],
):
    """يلغي دعوة معلّقة (owner/admin فقط)، tenant-scoped — لا يطال دعوات مستأجِر آخر."""
    ip = request.client.host if request.client else "unknown"
    if not main.can_invite(user.get("role")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلّب دور مالك المستأجِر")
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الدعوة غير موجودة")
    async with main._acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE invitations SET status='revoked'
            WHERE id=$1 AND tenant_id=$2 AND status='pending'
            RETURNING id
            """,
            invitation_id,
            tenant_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الدعوة غير موجودة أو غير معلّقة")
    await main.audit_log("invite_revoked", int(user["sub"]), ip, tenant_id=tenant_id)
    return {"message": "تم إلغاء الدعوة", "id": invitation_id}
