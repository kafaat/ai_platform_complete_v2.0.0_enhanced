"""api/routers/notifications.py — تفضيلات الإشعار + إيصالات التسليم + بثّ حيّ.

النطاق notifications (نمط P0):
  • GET/PUT /api/v1/notifications/preferences — تفضيلات (مُستخرَجة من main حرفيّاً).
  • POST   /api/v1/notifications/delivery     — إدامة/تحديث حالة تسليم تنبيه×قناة
    (إغلاق دورة الإشعار، جدول v83 notification_delivery، fail-soft غير كاسر).
  • WS     /api/v1/notifications/ws           — بثّ حيّ بسيط (اشتراك مستأجِر،
    مصادقة داخل القناة بعد accept: التوكن في أوّل إطار auth — أو قناة
    Sec-WebSocket-Protocol البديلة — لا في الـURL إطلاقاً). انظر ملاحظة الإرسال أدناه.

النماذج/المساعِدات (NotificationPreferences، _row_to_prefs، _PREF_SELECT_COLS،
_NOTIF_EVENT_TYPES، _ALERT_SEVERITIES، …) تبقى في api.main وتُستورَد هنا.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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


# ─── بثّ حيّ (WebSocket) — اشتراك مستأجِر + مصادقة داخل القناة (fail-closed) ───────
#
# الإغلاق المرن الصادق: هذه النقطة تُنفّذ **اشتراكاً آمناً**. المصافحة:
#   1) ``accept`` أوّلاً دائماً — الإغلاق قبل accept يُنتِج رمز إغلاق 1006 (شاذّ) في
#      المتصفّح، والواجهة (FE-10: لا توكن في الـURL) تقرؤه فشلاً وتعيد الاتّصال ⇒
#      حلقة إعادة اتّصال. نقبل، ثمّ نصادق داخل القناة، ثمّ نغلق 1008 (إغلاق سياسة
#      نظيف) فقط عند فشل المصادقة.
#   2) التوكن من أوّل إطار ``{"type":"auth","token":<JWT>}`` (القناة المفضّلة، FE-10 —
#      التوكن لا يلمس الـURL) أو من ``Sec-WebSocket-Protocol`` كقناة بديلة نظيفة. رمز
#      الاستعلام ``?token=`` أُزيل عمداً (توكن في الـURL يتسرّب إلى سجلّات الوصول في
#      الوكيل/البوّابة).
#   3) التحقّق بمصدر واحد: get_current_user (نفس فكّ JWT + إصدار + denylist للمسار
#      HTTP) — لا منطق تحقّق موازٍ.
#   4) إقرار صريح ``{"type":"auth_ok"}`` (FE-09) يفكّ بوّابة الصندوق الصادر في الواجهة.
# البثّ الكامل (fan-out من event_bus/NATS لكلّ المشتركين) **لم يُنفَّذ هنا** — لا
# ندّعيه. المنفَّذ: عقد اشتراك موثَّق + إقرار + بنية إرسال (send_to_subscriber).

# مهلة انتظار إطار المصادقة الأوّل بعد accept (ثوانٍ) — بعدها إغلاق 1008 (fail-closed).
_WS_AUTH_TIMEOUT_SECONDS = 10.0
# القناة البديلة النظيفة لعملاء غير المتصفّح: ``Sec-WebSocket-Protocol: sahool-bearer, <JWT>``.
# الخادم يردّ صدى الرمز الدلاليّ فقط (sahool-bearer) لا التوكن — فلا يتسرّب في رأس الردّ.
_WS_SUBPROTOCOL_SCHEME = "sahool-bearer"


def _subprotocol_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    """يستخرج (توكن، رمز الصدى) من ``Sec-WebSocket-Protocol`` إن استُخدمت القناة البديلة.

    العميل يعرض ``sahool-bearer, <JWT>``؛ نعيد (التوكن، "sahool-bearer") ليُردّ صداه في
    accept (بعض العملاء يُجهضون إن لم يُردَّ بروتوكول فرعيّ مطابق). غير ذلك ⇒ (None, None).
    """
    raw = websocket.headers.get("sec-websocket-protocol")
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0] == _WS_SUBPROTOCOL_SCHEME:
        return parts[1], _WS_SUBPROTOCOL_SCHEME
    return None, None


def _verify_ws_token(token: str | None) -> UserSchema | None:
    """مصدر تحقّق واحد — يُعاد استعمال get_current_user (فاكّ الـJWT الوحيد). لا منطق موازٍ.

    يُرجِع المستخدم عند النجاح، أو None عند أيّ فشل (يُغلق المُستدعي القناة 1008).
    """
    if not token:
        return None
    try:
        return get_current_user(authorization=f"Bearer {token}")
    except HTTPException:
        return None
    except Exception:  # noqa: BLE001 — أيّ تعذّر تحقّق ⇒ رفض (لا قبول مشكوك)
        return None


async def _resolve_ws_token(websocket: WebSocket, sub_token: str | None) -> str | None:
    """يحسم توكن القناة: القناة البديلة (sub_token) إن وُجدت، وإلّا أوّل إطار auth.

    ينتظر إطار العميل الأوّل حتى _WS_AUTH_TIMEOUT_SECONDS؛ إطار غير auth/غير JSON/مهلة/
    انقطاع ⇒ None (fail-closed). التوكن لا يُقرأ من الـURL إطلاقاً.
    """
    if sub_token is not None:
        return sub_token
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_WS_AUTH_TIMEOUT_SECONDS)
        frame = json.loads(raw)
    except (TimeoutError, WebSocketDisconnect):
        return None
    except Exception:  # noqa: BLE001 — إطار أوّل مُشوَّه ⇒ لا توكن
        return None
    if isinstance(frame, dict) and frame.get("type") == "auth":
        tok = frame.get("token")
        return tok if isinstance(tok, str) and tok else None
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
async def notifications_ws(websocket: WebSocket):
    """بثّ إشعارات حيّ — اشتراك مستأجِر مُصادَق داخل القناة (accept ثمّ مصادقة، fail-closed).

    العقد: العميل يفتح ``wss://…/api/v1/notifications/ws`` **بلا توكن في الـURL**، ثمّ
    يُرسل أوّل إطار ``{"type":"auth","token":<JWT>}`` (أو يمرّر التوكن عبر
    ``Sec-WebSocket-Protocol: sahool-bearer, <JWT>``). الخادم يقبل أوّلاً، يصادق، يردّ
    ``{"type":"auth_ok"}`` (FE-09)، ثمّ إطار ترحيب يصف قناة المستأجِر، وتبقى القناة
    مفتوحة (heartbeat: العميل يُرسل، والخادم يردّ pong) حتى يقطع العميل. فشل/مهلة
    المصادقة ⇒ إغلاق 1008 نظيف **بعد** accept (لا إغلاق قبل accept — يمنع حلقة إعادة
    الاتّصال FE-10).

    صدق الحدود: الـfan-out الفعليّ (دفع كلّ حدث جديد للمشترِكين) يتطلّب سجلّ اتّصالات
    مشترك + مستهلِك أحداث — غير موصول هنا. send_to_subscriber أعلاه هي نقطة الوصل
    الموثَّقة. لا ندّعي بثّاً لم يُوصَل.
    """
    # 1) accept أوّلاً دائماً (يمنع 1006/حلقة إعادة الاتّصال) — مع صدى البروتوكول الفرعيّ
    #    إن استُخدمت القناة البديلة.
    sub_token, echo = _subprotocol_token(websocket)
    if echo:
        await websocket.accept(subprotocol=echo)
    else:
        await websocket.accept()

    # 2) حسم التوكن (أوّل إطار auth — أو القناة البديلة)، ثمّ 3) تحقّق بمصدر واحد.
    token = await _resolve_ws_token(websocket, sub_token)
    user = _verify_ws_token(token)
    if user is None:
        # fail-closed: قُبِلت القناة لكن بلا هويّة صالحة ⇒ إغلاق سياسة نظيف (1008) لا
        # إجهاض قبل accept. الواجهة تحدّ إعادة المحاولة (maxReconnects) فلا تُشكِّل حلقة.
        await websocket.close(code=1008)
        return

    # 4) إقرار مصادقة صريح (FE-09): الواجهة تُبقي صندوقها الصادر مقفلاً حتى ترى auth_ok.
    await websocket.send_json({"type": "auth_ok"})

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
