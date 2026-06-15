"""api/routers/notifications.py — تفضيلات الإشعار (نطاق notifications، نمط P0).

نقطتان (GET/PUT /api/v1/notifications/preferences) مُستخرَجتان من main حرفيّاً.
النماذج/المساعِدات (NotificationPreferences، _row_to_prefs، _PREF_SELECT_COLS،
_NOTIF_EVENT_TYPES، _ALERT_SEVERITIES، …) تبقى في api.main وتُستورَد هنا.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _ALERT_SEVERITIES,
    _NOTIF_EVENT_TYPES,
    _PREF_SELECT_COLS,
    NotificationPreferences,
    Permission,
    UserSchema,
    _db_unavailable,
    _row_to_prefs,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get(
    "/api/v1/notifications/preferences",
    response_model=NotificationPreferences,
)
async def get_notification_preferences(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تفضيلات إشعار المستخدم الحاليّ ضمن مستأجِره — قنوات + عناوين + أنواع أحداث.

    تُرشَّح بـ(tenant_id, user_ref) (عزل مستأجِر + لكلّ مستخدم). لا صفّ ⇒ تفضيلات
    افتراضيّة (كلّ القنوات مُعطَّلة) لا 404 (الواجهة تعرض نموذجاً فارغاً صادقاً).
    503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"SELECT {_PREF_SELECT_COLS} FROM notification_preferences "
                "WHERE tenant_id = $1::uuid AND user_ref = $2",
                str(user.tenant_id),
                str(user.user_id),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة تفضيلات الإشعار", e) from e
    if row is None:
        return NotificationPreferences()
    return _row_to_prefs(row)


@router.put(
    "/api/v1/notifications/preferences",
    response_model=NotificationPreferences,
)
async def update_notification_preferences(
    req: NotificationPreferences,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُحدِّث (UPSERT) تفضيلات إشعار المستخدم الحاليّ — صفّ واحد لكلّ (مستأجِر، مستخدم).

    يتحقّق من أنواع الأحداث ودرجة الخطورة (422 على قيمة غير معروفة)، ثمّ يُدرِج/
    يُحدِّث عبر تعارض (tenant_id, user_ref). tenant-isolated. 503 عند تعذّر القاعدة.
    """
    import json as _json

    bad_events = [e for e in req.event_types if e not in _NOTIF_EVENT_TYPES]
    if bad_events:
        raise HTTPException(status_code=422, detail="نوع حدث إشعار غير معروف")
    if req.min_severity is not None and req.min_severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO notification_preferences
                    (tenant_id, user_ref, email_enabled, email_address,
                     sms_enabled, sms_number, push_enabled, push_token,
                     whatsapp_enabled, whatsapp_number, event_types, min_severity)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                           $11::jsonb, $12)
                   ON CONFLICT (tenant_id, user_ref)
                   DO UPDATE SET
                     email_enabled    = EXCLUDED.email_enabled,
                     email_address    = EXCLUDED.email_address,
                     sms_enabled      = EXCLUDED.sms_enabled,
                     sms_number       = EXCLUDED.sms_number,
                     push_enabled     = EXCLUDED.push_enabled,
                     push_token       = EXCLUDED.push_token,
                     whatsapp_enabled = EXCLUDED.whatsapp_enabled,
                     whatsapp_number  = EXCLUDED.whatsapp_number,
                     event_types      = EXCLUDED.event_types,
                     min_severity     = EXCLUDED.min_severity,
                     updated_at       = NOW()
                   RETURNING email_enabled, email_address, sms_enabled,
                     sms_number, push_enabled, push_token, whatsapp_enabled,
                     whatsapp_number, event_types, min_severity""",
                str(user.tenant_id),
                str(user.user_id),
                req.email_enabled,
                req.email_address,
                req.sms_enabled,
                req.sms_number,
                req.push_enabled,
                req.push_token,
                req.whatsapp_enabled,
                req.whatsapp_number,
                _json.dumps(req.event_types),
                req.min_severity,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ تفضيلات الإشعار", e) from e
    return _row_to_prefs(row)
