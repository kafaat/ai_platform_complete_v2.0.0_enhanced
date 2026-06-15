"""api/routers/tenant.py — تكوين المستأجِر الفعّال (Tenant Config)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``. القراءة
best-effort (تعذّر القاعدة ⇒ افتراضات محايدة) لم تُمسّ.

الاعتماديّات المشتركة (التبعيات/الأذونات/الاتّصال) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/tenant/config")
async def get_tenant_config(
    user: UserSchema = Depends(require_permission(Permission.SETTINGS_VIEW)),
):
    """التكوين **الفعّال** للمستأجِر — الافتراضات المحايدة مُركَّباً فوقها تخصيصُه.

    يقرأ صفّ الإعداد القائم (scope='platform', key='tenant_config') من جدول
    settings ضمن اتّصال المستأجِر (RLS)، ثمّ يُركّبه فوق القيم الافتراضيّة عبر
    `merge_tenant_config`. القراءة best-effort: تعذّر القاعدة/غياب الصفّ ⇒ None ⇒
    الافتراضات النقيّة (لا فشل — التكوين تحسين تجميليّ لا حرج).

    ⚠ الكتابة لا تمرّ هنا — يضبط المستأجِر تخصيصه عبر النقطة القائمة
    `PUT /api/v1/settings` (scope='platform', key='tenant_config', value=<جزئيّ>)
    بصلاحيّة SETTINGS_MANAGE. لا نضيف نقطة كتابة جديدة (مصدر كتابة واحد).
    """
    import json as _json

    from api.tenant_config import merge_tenant_config

    value: dict | None = None
    try:
        async with tenant_connection(user) as conn:
            value = await conn.fetchval(
                "SELECT value FROM settings WHERE scope = 'platform' AND key = 'tenant_config'"
            )
    except Exception:  # noqa: BLE001 — تعذّر القاعدة ⇒ افتراضات محايدة لا فشل
        value = None

    # قيمة JSONB قد تعود نصّاً (asyncpg دون codec) — فُكّها بأمان قبل الدمج.
    if isinstance(value, str):
        try:
            value = _json.loads(value)
        except (ValueError, TypeError):
            value = None

    # merge_tenant_config نقيّة لا تستثني: تتعامل مع None/المُشوَّه ⇒ تكوين صالح.
    return merge_tenant_config(value)
