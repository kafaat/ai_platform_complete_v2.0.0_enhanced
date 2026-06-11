"""
event_schema.py — عقد الحدث الموحّد (unified event envelope + validation).

الفجوة (سُمّيت «أساسيّة» في المراجعة): المعرّفات متناثرة — correlation_id،
causation_id، event_id، workflow_id، command_id — بلا عقد واحد يوحّدها. كلّ
خدمة تُصدر أحداثاً بشكلها. هذا الملفّ يعرّف غلافاً واحداً (EventEnvelope) +
تحقّقاً نقيّاً، ويطابق عقد دالّة emit_event SQL الموجودة (لا يعيد اختراعها).

نقيّ (لا I/O، لا DB): التعريف + التحقّق + التحويل لوسائط emit_event. الإصدار
الفعلي يبقى عبر EventBus.emit (outbox pattern) — هذا يضمن أنّ ما يُصدَر **موحّد
الشكل وموصول بخيط التتبّع** (correlation/causation) قبل أن يلمس القاعدة.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

# مصادر الحدث المسموحة (تطابق EventSource في event_bus).
EVENT_SOURCES = frozenset({"mobile", "web", "edge", "scheduler", "system", "ai", "sensor"})

# نوع الحدث: نقطيّ هرميّ (entity.action[.detail]) مثل "field.created".
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@dataclass
class EventEnvelope:
    """غلاف الحدث الموحّد — يربط الحقيقة بخيط التتبّع وسيادة المستأجر.

    correlation_id/causation_id يأتيان من core.correlation (خيط واحد عبر الخدمات)؛
    event_id فريد لكلّ حدث؛ entity_* يحدّد الكيان؛ tenant_id للعزل.
    """

    event_type: str
    entity_type: str
    entity_id: str
    tenant_id: str
    payload: dict = field(default_factory=dict)
    source: str = "system"
    actor_id: str | None = None
    command_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "tenant_id": self.tenant_id,
            "payload": self.payload,
            "source": self.source,
            "actor_id": self.actor_id,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "occurred_at": self.occurred_at,
        }

    def to_emit_args(self) -> dict:
        """وسائط EventBus.emit / دالّة emit_event SQL (لا يعيد اختراع العقد)."""
        return {
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "tenant_id": self.tenant_id,
            "payload": self.payload,
            "source": self.source,
            "actor_id": self.actor_id,
            "command_id": self.command_id,
        }


def validate_envelope(env: EventEnvelope) -> list[str]:
    """يُرجِع قائمة أخطاء (فارغة = صالح). صدق: يُعلن كلّ خلل لا يرمي بصمت."""
    errors: list[str] = []
    if not env.event_type or not _EVENT_TYPE_RE.match(env.event_type):
        errors.append(f"event_type غير صالح: {env.event_type!r} (المتوقّع entity.action)")
    if not env.entity_type:
        errors.append("entity_type مفقود")
    # entity_id نصّيّ لا UUID: معرّفات الكيانات الزراعيّة نصّيّة عمداً
    # (fields.field_id VARCHAR مثل "fld_demo_001") — v18 وحّد الأعمدة على TEXT.
    # فرض UUID هنا كان يرفض كلّ أحداث الحقول الحقيقيّة (regression مكشوف).
    if not isinstance(env.entity_id, str) or not env.entity_id.strip():
        errors.append(f"entity_id مفقود/فارغ: {env.entity_id!r}")
    if not _is_uuid(env.tenant_id):
        errors.append(f"tenant_id ليس UUID: {env.tenant_id!r}")
    if env.source not in EVENT_SOURCES:
        errors.append(f"source غير معروف: {env.source!r}")
    if env.command_id is not None and not _is_uuid(env.command_id):
        errors.append(f"command_id ليس UUID: {env.command_id!r}")
    if not isinstance(env.payload, dict):
        errors.append("payload يجب أن يكون dict")
    return errors


def new_event(
    event_type: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
    *,
    payload: dict | None = None,
    source: str = "system",
    actor_id: str | None = None,
    command_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> EventEnvelope:
    """يبني غلافاً موحّداً، مُلتقطاً خيط التتبّع من core.correlation إن لم يُمرَّر."""
    if correlation_id is None or causation_id is None:
        try:
            from core import correlation as _corr

            correlation_id = correlation_id or _corr.get_correlation_id()
            causation_id = causation_id or _corr.get_causation_id()
        except Exception:  # noqa: BLE001 — غياب السياق لا يُسقط البناء
            pass
    return EventEnvelope(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        payload=payload or {},
        source=source,
        actor_id=actor_id,
        command_id=command_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
