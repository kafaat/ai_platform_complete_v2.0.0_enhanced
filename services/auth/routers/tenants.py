"""routers/tenants.py — تهيئة مستأجِر B2B (مدير المنصّة فقط).

مسارات: POST /auth/tenants

شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ). نُقل المُعالِج حرفيّاً
مع تغيير ``@app`` إلى ``@router``؛ التبعيّات المشتركة تبقى في ``main`` ويُشار إليها عبر
``main.X``.

القرار التصميميّ: التسجيل الذاتيّ (register) يُنشئ مستأجِراً + مالكاً معاً بكلمة
مرور يختارها المُسجِّل. التهيئة الإداريّة (هنا) تختلف: مدير المنصّة (يُبوَّب بدور
auth الإداريّ هنا) يُنشئ مستأجِراً جديداً معزولاً + أوّل مالك له دون
أن يعرف المالكُ كلمةَ مرور مسبقة — يضبطها بنفسه عبر **رمز إعادة تعيين** (نعيد
استخدام آليّة password-reset القائمة: مفتاح Redis sahool:reset:{token} مدّته
٣٠ دقيقة + send_reset_email). كلمة المرور الأوّليّة عشوائيّة غير قابلة للاستعمال.

الأمان (لا تصعيد عابر للمستأجرين): المالك المُهيَّأ هو مالك مستأجِر **جديد
منفصل** (tenant_id فريد جديد، gen_random_uuid) — لا علاقة له بمستأجِر المُهيِّئ.
المُهيِّئ (admin) لا ينضمّ للمستأجِر الجديد ولا يحصل على توكن له ⇒ لا يصل لبياناته
(RLS يعزل المستأجرين). إذن منح 'owner' لمستأجِر مولود حديثاً ليس رفعاً للصلاحيّة
داخل مستأجِر قائم، بل تأسيس مستأجِر فارغ معزول (نفس منطق register).

جدول tenants: لا يوجد في الهجرات — المستأجرون **ضمنيّون** عبر users.tenant_id
(افتراضه gen_random_uuid)، اتّساقاً مع التسجيل الذاتيّ. لذا لا صفّ tenants يُدرَج؛
tenant_name (إن أُرسِل) يُدوَّن في سجلّ التدقيق فقط.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

import main
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter()


@router.post("/auth/tenants", status_code=201)
async def provision_tenant(
    req: main.TenantProvisionRequest,
    request: Request,
    admin: Annotated[dict, Depends(main.require_role("admin"))],
):
    """يُهيّئ مستأجِراً جديداً معزولاً + أوّل مالك له (مدير المنصّة فقط).

    يُنشئ مستخدِم المالك بدور 'owner' وكلمة مرور أوّليّة عشوائيّة غير قابلة
    للاستعمال، ثمّ يُصدر رمز إعادة تعيين (Redis) ليضبط المالك كلمة مروره. يرفض
    إن كان البريد مسجّلاً مسبقاً (409). يُدوّن tenant_provisioned في التدقيق.
    """
    ip = request.client.host if request.client else "unknown"
    admin_id = int(admin["sub"])

    # كلمة مرور أوّليّة عشوائيّة غير قابلة للاستعمال: يُهشَّر سرّ عشوائيّ لا يُكشَف
    # لأحد ⇒ لا يمكن تسجيل الدخول بها؛ المالك يضبط كلمته عبر رمز إعادة التعيين.
    unusable = main.bcrypt.hashpw(
        secrets.token_urlsafe(48).encode(), main.bcrypt.gensalt(main.BCRYPT_ROUNDS)
    )
    hashed = unusable.decode()

    async with main._acquire() as conn:
        try:
            # tenant_id يُترَك للافتراضيّ gen_random_uuid ⇒ مستأجِر جديد معزول
            # (نفس نمط register). الدور 'owner' مكتوب نصّاً هنا (لا من العميل).
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES ($1, $2, $3, 'owner')
                RETURNING id, email, role, full_name, tenant_id
                """,
                req.owner_email,
                hashed,
                req.owner_full_name,
            )
        except main.asyncpg.UniqueViolationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, "البريد الإلكتروني مسجّل مسبقاً") from e

    new_tenant_id = str(row["tenant_id"]) if row["tenant_id"] else f"tenant_{row['id']}"

    # رمز إعداد كلمة المرور: إعادة استخدام آليّة password-reset القائمة (Redis، ٣٠ دقيقة).
    # نتدهور برشاقة بلا Redis (التطوير): نُعيد الحقول دون رمز (المالك يطلب إعادة تعيين لاحقاً).
    setup_token: str | None = None
    if main._redis:
        setup_token = secrets.token_urlsafe(32)
        await main._redis.setex(f"sahool:reset:{setup_token}", 1800, str(row["id"]))  # 30 دقيقة
        # إرسال بريد الإعداد (نفس قالب إعادة التعيين) — best-effort (SMTP قد لا يكون مهيّأً).
        await main.send_reset_email(req.owner_email, setup_token)

    # التدقيق: tenant_provisioned بمستأجِر جديد + معرّف المُهيِّئ (admin). نُدوّن tenant_name
    # في details للتتبّع (لا جدول tenants لتخزينه). tenant_id = المستأجِر الجديد المُهيَّأ.
    details = req.tenant_name or req.owner_email
    await main.audit_log(
        "tenant_provisioned", admin_id, ip, details=details, tenant_id=row["tenant_id"]
    )
    main.logger.info(
        "tenant provisioned: tenant=%s owner_user=%s by_admin=%s",
        new_tenant_id,
        row["id"],
        admin_id,
    )

    # رابط الإعداد للواجهة (نفس مسار إعادة التعيين) — يُعرَض إن لم يُهيّأ SMTP.
    setup_link = (
        f"{os.getenv('FRONTEND_URL', 'https://app.sahool.ye')}/reset-password?token={setup_token}"
        if setup_token
        else None
    )
    return {
        "tenant_id": new_tenant_id,
        "owner_user_id": row["id"],
        "owner_email": row["email"],
        "owner_role": row["role"],  # دائماً 'owner'
        "setup_token": setup_token,
        "setup_link": setup_link,
        "message": (
            "تمّت تهيئة المستأجِر؛ أُرسِل/أُتيح رابط ضبط كلمة المرور للمالك"
            if setup_token
            else "تمّت تهيئة المستأجِر؛ يطلب المالك إعادة تعيين كلمة المرور (Redis غير متاح)"
        ),
    }
