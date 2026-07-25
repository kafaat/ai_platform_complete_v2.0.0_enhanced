"""stream_events.py — بناء أحداث البثّ ونشرها (NATS/MQTT) — خالٍ من fastapi.

``build_stream_event`` منطق صرف يبني ``dict`` قانونيّاً واحداً لكلّ نوع حدث؛ قابل
للاختبار الوحدويّ بلا خدمات. النشر (NATS + MQTT) **best-effort / import-guarded**:
لا تبعيّة صلبة — إن غابت المكتبات أو الوسطاء نُسجّل ونستمرّ (نظير موقف MQTT الليّن
القائم في ``main.py``). النداءات قابلة للحقن كي تُختبر الوحدة بلا وسيط حيّ.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("video-processor")

# أنواع الأحداث القانونيّة.
VALID_KINDS: frozenset[str] = frozenset(
    {
        "stream.started",
        "stream.stopped",
        "recording.started",
        "recording.stopped",
        "stream.error",
    }
)

# بادئة موضوع NATS: ``sahool.video.<kind>`` ⇒ مثال ``sahool.video.stream.started``.
NATS_SUBJECT_PREFIX = "sahool.video"


def nats_subject(kind: str) -> str:
    """موضوع NATS القانونيّ للنوع (``sahool.video.stream.started`` …)."""
    return f"{NATS_SUBJECT_PREFIX}.{kind}"


def mqtt_topic(kind: str) -> str:
    """موضوع MQTT القانونيّ (نقاط ← شرطات مائلة): ``sahool/video/stream/started``."""
    return f"sahool/video/{kind.replace('.', '/')}"


def build_stream_event(kind: str, stream: Any, ts: Any = None) -> dict[str, Any]:
    """يبني حدثاً قانونيّاً من قيد بثّ (``StreamEntry`` أو ``dict``).

    نوع غير قانونيّ ⇒ ``ValueError``. الشكل القانونيّ ثابت عبر الأنواع كي يعتمد عليه
    المستهلِكون (NATS/MQTT). ``ts`` طابع زمنيّ يُحقَن (لا ``datetime.now`` هنا).
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"نوع حدث غير قانونيّ: {kind!r} (المسموح: {sorted(VALID_KINDS)})")

    def _f(name: str) -> Any:
        if isinstance(stream, dict):
            return stream.get(name)
        return getattr(stream, name, None)

    return {
        "kind": kind,
        "stream_id": _f("stream_id"),
        "tenant_id": _f("tenant_id"),
        "source_url": _f("source_url"),
        "state": _f("state"),
        "ts": ts,
    }


def event_payload(event: dict[str, Any]) -> bytes:
    """يُسلسِل الحدث JSON (UTF-8، عربيّ غير مهروب) — الحمولة المنشورة."""
    return json.dumps(event, ensure_ascii=False, default=str).encode("utf-8")


async def _maybe_await(value: Any) -> Any:
    """يسمح بحاقن متزامن أو لا-متزامن على حدّ سواء."""
    if inspect.isawaitable(value):
        return await value
    return value


async def emit_stream_event(
    event: dict[str, Any],
    *,
    nats_publish: Callable[[str, bytes], Any] | None = None,
    mqtt_publish: Callable[[str, bytes], Any] | None = None,
) -> dict[str, str]:
    """ينشر الحدث إلى NATS وMQTT — best-effort، لا يرفع أبداً.

    ``nats_publish`` / ``mqtt_publish`` نداءان قابلان للحقن ``(subject_or_topic, payload)``
    (متزامن أو لا-متزامن). عند غيابهما يُحاوَل ناشرٌ افتراضيّ import-guarded؛ أيّ عطل
    (مكتبة غائبة/وسيط ساقط) يُسجَّل ويُتخطّى. يُرجِع خريطة نتائج لكلّ ناقل.
    """
    kind = event.get("kind", "")
    payload = event_payload(event)
    results: dict[str, str] = {}

    subject = nats_subject(kind)
    try:
        publisher = nats_publish if nats_publish is not None else _default_nats_publish
        await _maybe_await(publisher(subject, payload))
        results["nats"] = "ok"
    except Exception as e:  # noqa: BLE001 — best-effort: عطل النشر لا يُسقِط الطلب
        logger.debug("نشر NATS تعذّر [%s]: %s", subject, type(e).__name__)
        results["nats"] = f"skip:{type(e).__name__}"

    topic = mqtt_topic(kind)
    try:
        publisher = mqtt_publish if mqtt_publish is not None else _default_mqtt_publish
        await _maybe_await(publisher(topic, payload))
        results["mqtt"] = "ok"
    except Exception as e:  # noqa: BLE001 — best-effort
        logger.debug("نشر MQTT تعذّر [%s]: %s", topic, type(e).__name__)
        results["mqtt"] = f"skip:{type(e).__name__}"

    return results


async def _default_nats_publish(subject: str, payload: bytes) -> None:
    """ناشر NATS افتراضيّ import-guarded — اتصال قصير الأمد best-effort.

    غياب ``nats-py`` أو ``NATS_URL`` أو سقوط الوسيط ⇒ يرفع (يلتقطه ``emit_stream_event``
    كتخطٍّ). لا نُبقي اتصالاً دائماً هنا — الخدمة تعمل وتُختبَر بلا وسيط.
    """
    import os

    url = os.getenv("NATS_URL", "").strip()
    if not url:
        raise RuntimeError("NATS_URL غير مضبوط")
    import nats  # import-guarded: تبعيّة اختياريّة

    nc = await nats.connect(url, connect_timeout=2)
    try:
        await nc.publish(subject, payload)
        await nc.flush(timeout=2)
    finally:
        await nc.close()


async def _default_mqtt_publish(topic: str, payload: bytes) -> None:
    """ناشر MQTT افتراضيّ import-guarded — نظير موقف ``main.publish_alert`` الليّن."""
    import os

    broker = os.getenv("MQTT_BROKER_URL", "").strip()
    if not broker or broker.startswith("disabled"):
        raise RuntimeError("MQTT معطّل/غير مضبوط")
    from urllib.parse import urlparse

    from aiomqtt import Client as MQTTClient  # import-guarded

    parsed = urlparse(broker)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1883
    # مصادقة MQTT: تُمرَّر إن ضُبط MQTT_USERNAME (وسيط allow_anonymous=false)؛
    # الاتّصال المجهول يبقى متوافقًا للخلف. لا سرّ في المستودع (env حصرًا).
    username = os.getenv("MQTT_USERNAME", "").strip()
    auth = {"username": username, "password": os.getenv("MQTT_PASSWORD", "")} if username else {}
    async with MQTTClient(host, port=port, **auth) as client:
        await client.publish(topic, payload, qos=1)
