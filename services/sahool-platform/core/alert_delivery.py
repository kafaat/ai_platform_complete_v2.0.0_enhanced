"""
alert_delivery.py — طبقة توصيل التنبيهات (channel layer).

محرّك التنبيهات (alert_engine) يُنتج التنبيه؛ هذه الطبقة تُوصِّله. الفصل مقصود:
المنطق لا يعرف القناة، والقناة لا تعرف المنطق. القنوات قابلة للإضافة.

الصدق: الإرسال الخارجي الفعلي يحدث فقط حين تُهيّأ القناة (رابط/اعتمادات). بلا
تهيئة ⇒ no-op مع note صريحة (لا ندّعي إرسالاً لم يحدث). idempotency عبر مجموعة
مفاتيح «سبق توصيلها» تمنع إغراق المزارع بنفس التنبيه.

القنوات المُضمَّنة:
  • LogChannel    — تسجيل (دائماً).
  • InAppChannel  — صفوف قابلة للحفظ (لوحة/PWA) — لا إرسال خارجي.
  • WebhookChannel— POST JSON لرابط مُهيّأ (بوّابة دفع/Slack/تطبيق) — حقيقيّ.
  • ProviderChannel — SMS/WhatsApp: تتطلّب SDK+اعتمادات؛ بلا تهيئة ⇒ no-op صادق.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_RANK = {"critical": 3, "warning": 2, "info": 1}


def _filter_by_severity(alerts: list[dict], min_severity: str) -> list[dict]:
    floor = _RANK.get(min_severity, 2)
    return [a for a in alerts if _RANK.get(a.get("severity"), 1) >= floor]


def _alert_key(field_id: Any, alert: dict) -> str:
    return f"{field_id}:{alert.get('code')}:{alert.get('severity')}"


class LogChannel:
    name = "log"

    def send(self, alerts: list[dict], context: dict) -> dict:
        for a in alerts:
            logger.warning(
                "[ALERT] %s/%s: %s",
                context.get("field_id"),
                a.get("severity"),
                a.get("message_ar"),
            )
        return {"channel": self.name, "delivered": len(alerts), "error": None, "note": None}


class InAppChannel:
    """يُنتج صفوف تنبيه قابلة للحفظ (للوحة/الـPWA يسحبها المزارع). لا إرسال خارجي."""

    name = "in_app"

    def send(self, alerts: list[dict], context: dict) -> dict:
        rows = [
            {
                "field_id": context.get("field_id"),
                "tenant_id": context.get("tenant_id"),
                "severity": a.get("severity"),
                "code": a.get("code"),
                "message_ar": a.get("message_ar"),
                "created_at": context.get("now"),
            }
            for a in alerts
        ]
        return {
            "channel": self.name,
            "delivered": len(rows),
            "rows": rows,
            "error": None,
            "note": "صفوف للحفظ في القاعدة/اللوحة",
        }


class WebhookChannel:
    """POST JSON لرابط مُهيّأ — بوّابة دفع عامّة (تطبيق/Slack/...). حقيقيّ مع url+httpx."""

    name = "webhook"

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    def send(self, alerts: list[dict], context: dict) -> dict:
        if not self.url:
            return {
                "channel": self.name,
                "delivered": 0,
                "error": None,
                "note": "لا رابط — لم يُرسَل",
            }
        try:
            import httpx
        except ImportError:
            return {
                "channel": self.name,
                "delivered": 0,
                "error": None,
                "note": "httpx غير متوفّر — لم يُرسَل",
            }
        payload = {
            "field_id": context.get("field_id"),
            "tenant_id": context.get("tenant_id"),
            "alerts": alerts,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.url, json=payload)
                resp.raise_for_status()
            return {"channel": self.name, "delivered": len(alerts), "error": None, "note": None}
        except Exception as e:  # noqa: BLE001 — فشل الشبكة لا يُسقط التحليل
            return {"channel": self.name, "delivered": 0, "error": str(e)[:200], "note": None}


class ProviderChannel:
    """قناة مزوّد خارجي (SMS/WhatsApp). بلا اعتمادات ⇒ no-op صادق (لا ادّعاء إرسال)."""

    def __init__(self, name: str, configured: bool):
        self.name = name
        self.configured = configured

    def send(self, alerts: list[dict], context: dict) -> dict:
        if not self.configured:
            return {
                "channel": self.name,
                "delivered": 0,
                "error": None,
                "note": f"{self.name} غير مُهيّأ (اعتمادات/SDK مفقودة) — لم يُرسَل",
            }
        # التكامل الفعلي مع SDK المزوّد يُضاف على جهاز التشغيل.
        return {
            "channel": self.name,
            "delivered": 0,
            "error": None,
            "note": "تكامل المزوّد يُضاف على جهاز التشغيل",
        }


def build_default_channels() -> list:
    """يبني القنوات من البيئة: log + in_app دائماً؛ webhook/مزوّدات عند التهيئة."""
    channels: list = [LogChannel(), InAppChannel()]
    url = os.getenv("ALERT_WEBHOOK_URL", "")
    if url:
        channels.append(WebhookChannel(url))
    channels.append(ProviderChannel("whatsapp", bool(os.getenv("WHATSAPP_TOKEN"))))
    channels.append(ProviderChannel("sms", bool(os.getenv("SMS_API_KEY"))))
    return channels


def deliver_alerts(
    alerts: list[dict],
    *,
    channels: list | None = None,
    context: dict | None = None,
    min_severity: str = "warning",
    seen: set | None = None,
) -> dict:
    """يوصّل تنبيهات (warning فأعلى افتراضيّاً) عبر القنوات.

    seen: مجموعة مفاتيح سبق توصيلها (idempotency) — تُحدَّث؛ يمنع تكرار الإزعاج.
    يُرجِع ملخّص: المُحاوَل + المُصفّى (info) + المتخطّى (تكرار) + نتائج القنوات.
    """
    context = context or {}
    channels = channels if channels is not None else build_default_channels()
    eligible = _filter_by_severity(alerts, min_severity)

    skipped = 0
    if seen is not None:
        fresh = []
        for a in eligible:
            key = _alert_key(context.get("field_id"), a)
            if key in seen:
                skipped += 1
            else:
                seen.add(key)
                fresh.append(a)
    else:
        fresh = eligible

    results = [ch.send(fresh, context) for ch in channels] if fresh else []
    return {
        "attempted": len(fresh),
        "filtered_out": len(alerts) - len(eligible),
        "skipped_dedup": skipped,
        "channels": results,
    }
