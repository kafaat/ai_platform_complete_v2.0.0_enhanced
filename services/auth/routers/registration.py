"""routers/registration.py — التسجيل وتغيير كلمة المرور.

مسارات: POST /auth/register · POST /auth/change-password

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقلت المُعالِجات
حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار
إليها عبر ``main.X``.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

router = APIRouter()


@router.post("/auth/register", response_model=main.TokenResponse, status_code=201)
async def register(req: main.RegisterRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    await main.check_ip_rate(ip)

    hashed = main.bcrypt.hashpw(
        req.password.encode(), main.bcrypt.gensalt(main.BCRYPT_ROUNDS)
    ).decode()
    async with main._acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES ($1, $2, $3, 'owner')
                RETURNING id, email, role, full_name, tenant_id
            """,
                req.email,
                hashed,
                req.full_name,
            )
            # الأمان + الإقلاع: التسجيل الذاتيّ يُنشئ **مستأجِراً جديداً معزولاً**
            # (users.tenant_id افتراضه gen_random_uuid)، فالمُسجِّل هو مؤسِّس مؤسّسته ⇒
            # دوره 'owner' (TENANT_OWNER) كي يستطيع إنشاء/إدارة حقوله وفريقه — وإلّا
            # «Bootstrap Deadlock»: يملك مستأجِراً لا يقدر على تأسيسه. آمن: RLS يعزل
            # المستأجرين فلا تصعيد عابر؛ وهو مالك مستأجِره وحده. الدور المُرسَل من
            # العميل يُتجاهَل (لا حقل role في RegisterRequest). الأعضاء اللاحقون
            # يُضافون لمستأجِر قائم بأدوار أدنى عبر دعوة (manager/agronomist/worker/
            # viewer) — لا عبر التسجيل الذاتيّ.
        except main.asyncpg.UniqueViolationError as e:
            main.REGISTER_COUNTER.labels(status="conflict").inc()
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد الإلكتروني مسجّل مسبقاً") from e

    tid = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"
    token, jti = main.create_access_token(
        row["id"], row["email"], row["role"], row["full_name"], tid
    )
    refresh = await main.create_refresh_token(row["id"], tid)

    await main.audit_log("register", row["id"], ip, tenant_id=row["tenant_id"])
    main.REGISTER_COUNTER.labels(status="success").inc()

    # كوكي مصادقة البلاطات — المستخدِم الجديد مُصادَق فوراً، فتعمل بلاطاته دون JWT في الرابط.
    main.set_tile_auth_cookie(response, token, request)

    return main.TokenResponse(
        access_token=token,
        refresh_token=refresh,
        expires_in=main.JWT_EXPIRE_MINUTES * 60,
        user_id=row["id"],
        role=row["role"],
        full_name=row["full_name"],
        tenant_id=tid,
    )


@router.post("/auth/change-password")
async def change_password(
    req: main.ChangePasswordRequest,
    user: dict = Depends(main.get_current_user),
):
    """✅ NEW: Change password for authenticated user."""
    user_id = int(user["sub"])
    async with main._acquire() as conn:
        row = await conn.fetchrow("SELECT password_hash FROM users WHERE id=$1", user_id)
    if not row or not main.bcrypt.checkpw(
        req.current_password.encode(), row["password_hash"].encode()
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "كلمة المرور الحالية غير صحيحة")

    hashed = main.bcrypt.hashpw(
        req.new_password.encode(), main.bcrypt.gensalt(main.BCRYPT_ROUNDS)
    ).decode()
    async with main._acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE id=$2", hashed, user_id
        )
    await main.revoke_all_user_sessions(user_id)  # إبطال كلّ الجلسات (يشمل الحاليّة) ⇒ إعادة دخول
    await main.audit_log("change_password", user_id, "authenticated")
    return {"message": "تم تغيير كلمة المرور بنجاح"}
