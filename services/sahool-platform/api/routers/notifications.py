"""api/routers/notifications.py — تفضيلات الإشعار + إيصالات التسليم + بثّ حيّ.

النطاق notifications (نمط P0):
  • GET/PUT /api/v1/notifications/preferences — تفضيلات (مُستخرَجة من main حرفيّاً).
  • POST   /api/v1/notifications/delivery     — إدامة/تحديث حالة تسليم تنبيه×قناة
    (إغلاق دورة الإشعار، جدول v83 notification_delivery، fail-soft غير كاسر).
  • WS     /api/v1/notifications/ws           — بثّ حيّ بسيط (اشتراك مستأجِر،
    تحقّق توكن fail-closed في الـhandshake). انظر ملاحظة الإرسال أدناه.

النماذج/المساعِدات (NotificationPreferences، _row_to_prefs، _PREF_SELECT_COLS،
_NOTIF_EVENT_TYPES، _ALERT_SEVERITIES، …) تبقى في api.main وتُستورَد هنا.
"""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from api.alert_models import _ALERT_SEVERITIES
from api.main import (
    _NOTIF_EVENT_TYPES,
    _PREF_SELECT_COLS,
    NotificationPreferences,
    Permission,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    _row_to_prefs,
    get_current_user,
    require_permission,
    tenant_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# حالات تسليم مسموحة — مرآة قيد CHECK في migrations/v83 (لا حالة مُلفّقة، 422 على
# قيمة خارجها قبل لمس القاعدة).
_DELIVERY_STATUSES = {"queued", "sent", "failed", "delivered"}


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


# ─── إيصالات التسليم (إغلاق دورة الإشعار، v83) ──────────────────────────────────


class DeliveryReceipt(BaseModel):
    """إيصال تسليم تنبيه عبر قناة — يُدِيم/يُحدِّث حالة في notification_delivery (v83).

    alert_key: مفتاح التنبيه (مرآة _alert_key في core.alert_delivery: field:code:severity).
    channel: قناة التسليم (log/in_app/webhook/sms/whatsapp/email/push/…).
    status: حالة دورة الحياة — queued|sent|failed|delivered (مجموعة مغلقة).
    error: سبب الفشل (provenance) — اختياريّ، NULL عند النجاح.
    """

    alert_key: str = Field(min_length=1, max_length=512)
    channel: str = Field(min_length=1, max_length=64)
    status: str = "queued"
    error: str | None = Field(default=None, max_length=2000)


class DeliveryReceiptOut(BaseModel):
    delivery_id: str
    alert_key: str
    channel: str
    status: str
    error: str | None = None


@router.post(
    "/api/v1/notifications/delivery",
    response_model=DeliveryReceiptOut,
)
async def upsert_notification_delivery(
    req: DeliveryReceipt,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُدِيم/يُحدِّث حالة تسليم تنبيه عبر قناة (إغلاق دورة الإشعار، جدول v83).

    upsert على UNIQUE(tenant_id, alert_key, channel): أوّل تسليم يُنشئ إيصالاً
    (queued)؛ التحديثات اللاحقة تُرقّي الحالة (sent→delivered) أو تُسجّل فشلاً
    (failed + error). tenant-isolated عبر tenant_connection (RLS). 422 على حالة
    غير معروفة (قبل لمس القاعدة). 503 عند تعذّر القاعدة (نمط _db_unavailable).

    الصدق: هذا إيصال **حالة** لا ادّعاء إرسال خارجيّ فعليّ — الحالة تُكتب كما يُمليها
    المُسلِّم (المُهيّأ يكتب sent/delivered؛ غير المُهيّأ يبقى queued أو failed).
    يُصدَر NOTIFICATION_DELIVERED عبر outbox (fail-soft) لإتاحة البثّ الحيّ والتدقيق.
    """
    if req.status not in _DELIVERY_STATUSES:
        raise HTTPException(status_code=422, detail="حالة تسليم غير معروفة")
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO notification_delivery
                    (tenant_id, alert_key, channel, status, error)
                   VALUES ($1::uuid, $2, $3, $4, $5)
                   ON CONFLICT (tenant_id, alert_key, channel)
                   DO UPDATE SET
                     status     = EXCLUDED.status,
                     error      = EXCLUDED.error,
                     updated_at = NOW()
                   RETURNING delivery_id, alert_key, channel, status, error""",
                str(user.tenant_id),
                req.alert_key,
                req.channel,
                req.status,
                req.error,
            )
            # تدقيق + بثّ حيّ: حدث domain ضمن نفس المعاملة (savepoint، fail-soft —
            # غياب جداول الأحداث لا يكسر إدامة الإيصال).
            await _emit_domain_event(
                conn,
                user,
                "NOTIFICATION_DELIVERED",
                "notification_delivery",
                str(row["delivery_id"]),
                {
                    "alert_key": req.alert_key,
                    "channel": req.channel,
                    "status": req.status,
                },
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ إيصال تسليم الإشعار", e) from e
    return DeliveryReceiptOut(
        delivery_id=str(row["delivery_id"]),
        alert_key=row["alert_key"],
        channel=row["channel"],
        status=row["status"],
        error=row["error"],
    )


# ─── بثّ حيّ (WebSocket) — اشتراك مستأجِر + handshake موثَّق (fail-closed) ─────────
#
# الإغلاق المرن الصادق: هذه النقطة تُنفّذ **اشتراكاً آمناً** — تحقّق توكن في الـ
# handshake (fail-closed: توكن غائب/غير صالح ⇒ إغلاق فوريّ 1008 قبل قبول أيّ بثّ)
# ثمّ تبقي القناة مفتوحة على قناة المستأجِر. البثّ الكامل (fan-out من event_bus/NATS
# لكلّ المشتركين) **لم يُنفَّذ هنا** (بنية تتطلّب سجلّ اتّصالات مشترك + مستهلِك
# أحداث) — لا ندّعيه. ما هو منفَّذ: عقد اشتراك موثَّق + إطار ترحيب يصف القناة +
# بنية إرسال موثَّقة (send_to_subscriber) جاهزة للوصل بمستهلِك الأحداث لاحقاً.


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> UserSchema | None:
    """يتحقّق من توكن الـWebSocket في الـhandshake (fail-closed).

    التوكن يُمرَّر كمعامل استعلام ``?token=`` (لا تدعم متصفّحات WebSocket رؤوس
    Authorization مخصّصة في الـhandshake). يُعاد استعمال get_current_user (نفس فكّ
    JWT + إصدار + denylist) بتركيب رأس Bearer — مصدر تحقّق واحد، لا منطق موازٍ.

    يُرجِع UserSchema عند النجاح، أو None بعد إغلاق الاتّصال (1008) عند الفشل —
    fail-closed: لا بثّ قبل تحقّق ناجح.
    """
    if not token:
        await websocket.close(code=1008)  # policy violation — لا توكن
        return None
    try:
        # get_current_user دالّة متزامنة نقيّة الفكّ (بلا I/O قاعدة) — تُستدعى مباشرةً
        # بتركيب رأس Bearer؛ ترفع HTTPException عند أيّ فشل تحقّق (fail-closed).
        return get_current_user(authorization=f"Bearer {token}")
    except HTTPException:
        await websocket.close(code=1008)  # توكن غير صالح/مُبطَل/مصدر مجهول
        return None
    except Exception:  # noqa: BLE001 — أيّ تعذّر تحقّق ⇒ إغلاق (لا قبول مشكوك)
        await websocket.close(code=1008)
        return None


async def send_to_subscriber(websocket: WebSocket, message: dict) -> bool:
    """يُرسِل إطار JSON لمشترِك واحد (بنية الإرسال الموثَّقة، نقطة وصل البثّ).

    يُرجِع True عند الإرسال، False إن انقطع الاتّصال (يلتقطه المُستدعي لإسقاط
    المشترِك من السجلّ). نقطة الوصل: مستهلِك أحداث (NATS sahool.events.>) يستدعي
    هذه الدالّة لكلّ مشترِك في قناة المستأجِر عند وصول حدث جديد — لم يُوصَل بعد.
    """
    try:
        await websocket.send_json(message)
        return True
    except Exception:  # noqa: BLE001 — انقطاع/إغلاق ⇒ إسقاط المشترِك
        return False


@router.websocket("/api/v1/notifications/ws")
async def notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
):
    """بثّ إشعارات حيّ — اشتراك مستأجِر موثَّق (handshake fail-closed).

    العقد: العميل يفتح ``wss://…/api/v1/notifications/ws?token=<JWT>``. يُتحقَّق من
    التوكن قبل ``accept`` (fail-closed)؛ ثمّ يُرسَل إطار ترحيب يصف قناة المستأجِر
    المُشترَك فيها، وتبقى القناة مفتوحة (heartbeat: العميل قد يُرسل، والخادم يردّ
    pong) حتى يقطع العميل.

    صدق الحدود: الـfan-out الفعليّ (دفع كلّ حدث جديد للمشترِكين) يتطلّب سجلّ اتّصالات
    مشترك + مستهلِك أحداث — غير موصول هنا. send_to_subscriber أعلاه هي نقطة الوصل
    الموثَّقة. لا ندّعي بثّاً لم يُوصَل.
    """
    user = await _authenticate_ws(websocket, token)
    if user is None:
        return  # أُغلق الاتّصال داخل _authenticate_ws (fail-closed)

    await websocket.accept()
    channel = f"sahool.notifications.{user.tenant_id}"
    await websocket.send_json(
        {
            "type": "subscribed",
            "channel": channel,
            "tenant_id": str(user.tenant_id),
            "note": "اشتراك موثَّق فُتح — يصل البثّ الحيّ عند وصل مستهلِك الأحداث.",
        }
    )
    try:
        while True:
            # نبضة بقاء: ننتظر رسائل العميل (ping/اشتراك مستقبليّ) ونردّ pong.
            # لا منطق fan-out هنا (موثَّق أعلاه). الانقطاع يكسر الحلقة بنظافة.
            await websocket.receive_text()
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001 — أيّ خطأ قناة ⇒ إغلاق نظيف (لا 500)
        logger.debug("notifications_ws انتهى: %s", e)
        return
