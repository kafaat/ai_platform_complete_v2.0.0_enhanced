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
  • push     → FCM_CREDENTIALS_JSON (FCM HTTP v1 عبر shared.fcm؛ recipient=device token)
"""

from __future__ import annotations

import asyncio
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
from shared.fcm import fcm_push_active, send_push

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
    """FCM HTTP v1 عبر ``shared.fcm``: حسابٌ خدميّ مُتحقَّق منه وإيصالُ رسالةٍ مُسمّى.

    كان هذا المسار يرسل إلى ``fcm.googleapis.com/fcm/send`` القديم بـ``FCM_SERVER_KEY``،
    متجاوزاً تحقّقَ الاعتماد والإيصال الذي يفرضه ``shared/fcm.py`` على بقيّة المنصّة
    (Copilot على #997). المُرسِل متزامن ويُنادى من خيطٍ عامل (``asyncio.to_thread``)، فحلقةٌ
    محلّيّة لنداء الشبكة غير المتزامن آمنة هنا: لا حلقةَ أحداثٍ تعمل في ذلك الخيط. ولو
    نودي من داخل حلقةٍ عاملة فالفشل صريح — لا مسارَ قديم يُعاد إليه.
    """
    if not fcm_push_active():
        return _not_configured(CHANNEL_PUSH)
    try:
        accepted = asyncio.run(send_push(msg.recipient or "", msg.title_ar, msg.body_ar))
    except RuntimeError as e:
        logger.error("تعذّر إرسال Push عبر FCM v1: %s", e)
        return (CHANNEL_PUSH, False, f"push fcm_v1_error: {e}")
    return (CHANNEL_PUSH, accepted, "push fcm_v1 " + ("accepted" if accepted else "not_accepted"))


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
