"""api/routers/settings.py — إعدادات المستأجِر (Settings)
==========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    SettingRequest,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.put("/api/v1/settings")
async def upsert_setting(
    req: SettingRequest,
    user: UserSchema = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    """يحفظ/يحدّث إعداداً (upsert idempotent لكلّ مستأجر+نطاق+مفتاح)."""
    import json as _json
    import uuid as _uuid

    setting_id = "set_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO settings
                (setting_id, tenant_id, scope, key, value, updated_by)
               VALUES ($1, $2::uuid, $3, $4, $5::jsonb, $6)
               ON CONFLICT (tenant_id, scope, key) DO UPDATE
                 SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by
               RETURNING setting_id, scope, key""",
            setting_id,
            str(user.tenant_id),
            req.scope,
            req.key,
            _json.dumps(req.value or {}),
            str(user.user_id),
        )
    return {
        "setting_id": row["setting_id"],
        "scope": row["scope"],
        "key": row["key"],
        "message_ar": "حُفِظ الإعداد",
    }


@router.get("/api/v1/settings")
async def list_settings(
    scope: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.SETTINGS_VIEW)),
):
    """إعدادات المستأجر (مُرشَّحة اختياريّاً بالنطاق)."""
    async with tenant_connection(user) as conn:
        if scope:
            rows = await conn.fetch(
                "SELECT setting_id, scope, key, value, updated_by "
                "FROM settings WHERE scope = $1 ORDER BY key",
                scope,
            )
        else:
            rows = await conn.fetch(
                "SELECT setting_id, scope, key, value, updated_by FROM settings ORDER BY scope, key"
            )
    return [
        {
            "setting_id": r["setting_id"],
            "scope": r["scope"],
            "key": r["key"],
            "value": r["value"] if isinstance(r["value"], dict) else {},
            "updated_by": r["updated_by"],
        }
        for r in rows
    ]
