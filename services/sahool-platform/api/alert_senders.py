"""api/alert_senders.py — مُرسِلات قنوات حقيقيّة (I/O) للتنبيهات.

تُوصَّل عبر alert_delivery.deliver(sender=real_channel_sender). تُبقي منطق
اختيار القنوات (alert_delivery) نقيّاً، وتضع كلّ الأثر الجانبيّ هنا.

المبدأ (صدق): كلّ قناة **حقيقيّة عند ضبط اعتمادها** عبر متغيّرات البيئة، و**تدهور
رشيق** ('logged_not_sent') عند غيابها — لا نزعم إرسالاً لم يحدث. بلا تبعيّات
جديدة: smtplib + urllib القياسيّان.

القنوات والاعتمادات:
  • email    → SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_PORT/SMTP_FROM
  • sms      → SMS_PROVIDER_URL/SMS_API_KEY (POST JSON عامّ)
  • whatsapp → WHATSAPP_WEBHOOK_URL (+WHATSAPP_API_KEY اختياريّ) (POST JSON)
  • telegram → TELEGRAM_BOT_TOKEN (Bot API sendMessage؛ recipient=chat_id)
  • push     → FCM_SERVER_KEY (FCM legacy HTTP؛ recipient=device token)
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.mime.text import MIMEText

from api.alert_delivery import (
    CHANNEL_EMAIL,
    CHANNEL_PUSH,
    CHANNEL_SMS,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    ChannelMessage,
    DeliveryResult,
)

logger = logging.getLogger("sahool.alert_senders")

# ── اعتمادات القنوات (كلّها اختياريّة — الغياب ⇒ تدهور رشيق) ──────────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@sahool.ye")

SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL", "")
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_FROM = os.getenv("SMS_FROM", "SAHOOL")

WHATSAPP_WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL", "")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")

_HTTP_TIMEOUT = 10


def _not_configured(channel: str) -> DeliveryResult:
    return (channel, False, "logged_not_sent (مزوّد القناة غير مهيّأ)")


def _post_json(url: str, payload: dict, headers: dict | None = None) -> tuple[bool, str]:
    """POST JSON متزامن (urllib) — يُعيد (نجَح، تفصيل)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            ok = 200 <= resp.status < 300
            return ok, f"http_{resp.status}"
    except urllib.error.URLError as e:
        return False, f"http_error: {e}"


def _send_email(msg: ChannelMessage) -> DeliveryResult:
    if not (SMTP_HOST and SMTP_USER):
        return _not_configured(CHANNEL_EMAIL)
    try:
        mime = MIMEText(msg.body_ar, "plain", "utf-8")
        mime["Subject"] = msg.title_ar
        mime["From"] = SMTP_FROM
        mime["To"] = msg.recipient or ""
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=_HTTP_TIMEOUT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(mime)
        return (CHANNEL_EMAIL, True, "مُرسَل (SMTP)")
    except Exception as e:  # noqa: BLE001 — تسليم لا يكسر الإنشاء
        logger.error("فشل إرسال بريد التنبيه: %s", e)
        return (CHANNEL_EMAIL, False, f"smtp_error: {e}")


def _send_sms(msg: ChannelMessage) -> DeliveryResult:
    if not (SMS_PROVIDER_URL and SMS_API_KEY):
        return _not_configured(CHANNEL_SMS)
    ok, detail = _post_json(
        SMS_PROVIDER_URL,
        {"to": msg.recipient, "from": SMS_FROM, "message": f"{msg.title_ar}\n{msg.body_ar}"},
        {"Authorization": f"Bearer {SMS_API_KEY}"},
    )
    return (CHANNEL_SMS, ok, f"sms {detail}")


def _send_whatsapp(msg: ChannelMessage) -> DeliveryResult:
    if not WHATSAPP_WEBHOOK_URL:
        return _not_configured(CHANNEL_WHATSAPP)
    headers = {"Authorization": f"Bearer {WHATSAPP_API_KEY}"} if WHATSAPP_API_KEY else {}
    ok, detail = _post_json(
        WHATSAPP_WEBHOOK_URL,
        {"to": msg.recipient, "text": f"{msg.title_ar}\n{msg.body_ar}"},
        headers,
    )
    return (CHANNEL_WHATSAPP, ok, f"whatsapp {detail}")


def _send_telegram(msg: ChannelMessage) -> DeliveryResult:
    if not TELEGRAM_BOT_TOKEN:
        return _not_configured(CHANNEL_TELEGRAM)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ok, detail = _post_json(
        url, {"chat_id": msg.recipient, "text": f"{msg.title_ar}\n{msg.body_ar}"}
    )
    return (CHANNEL_TELEGRAM, ok, f"telegram {detail}")


def _send_push(msg: ChannelMessage) -> DeliveryResult:
    if not FCM_SERVER_KEY:
        return _not_configured(CHANNEL_PUSH)
    ok, detail = _post_json(
        "https://fcm.googleapis.com/fcm/send",
        {"to": msg.recipient, "notification": {"title": msg.title_ar, "body": msg.body_ar}},
        {"Authorization": f"key={FCM_SERVER_KEY}"},
    )
    return (CHANNEL_PUSH, ok, f"push {detail}")


_DISPATCH = {
    CHANNEL_EMAIL: _send_email,
    CHANNEL_SMS: _send_sms,
    CHANNEL_WHATSAPP: _send_whatsapp,
    CHANNEL_TELEGRAM: _send_telegram,
    CHANNEL_PUSH: _send_push,
}


def real_channel_sender(msg: ChannelMessage) -> DeliveryResult:
    """مُرسِل حقيقيّ (I/O) لقناة واحدة — يُمرَّر إلى alert_delivery.deliver(sender=...).

    قناة بلا عنوان ⇒ فشل صريح (لا ابتلاع). قناة مهيّأة ⇒ إرسال فعليّ؛ غير مهيّأة
    ⇒ 'logged_not_sent' (تدهور رشيق دون ادّعاء إرسال). متزامن — يُنادى داخل خيط
    من النواة (asyncio.to_thread) كي لا يحجب حلقة الأحداث.
    """
    if not msg.deliverable:
        return (msg.channel, False, "لا عنوان مضبوط لهذه القناة")
    handler = _DISPATCH.get(msg.channel)
    if handler is None:
        return (msg.channel, False, "logged_not_sent (قناة غير مدعومة)")
    return handler(msg)
