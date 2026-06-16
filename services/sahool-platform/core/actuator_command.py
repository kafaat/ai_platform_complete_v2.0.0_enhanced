"""core/actuator_command.py — ترجمة قرار توزيع مُخلَّص إلى أمر مُشغِّل (نقيّ).

يحوّل `DispatchDecision` بحالة READY إلى شكل الأمر الذي يتوقّعه actuator-service
(`{device_id, command, payload}` — يوقّعه المُشغِّل HMAC ثمّ ينشره على
`sahool/actuator/{device_id}/command`). نقيّ وحتميّ، لا I/O.

أمان (fail-closed): لا يُبنى أمر إلّا لقرار **READY** (محروس + موافَق). أيّ قرار
BLOCKED/PENDING ⇒ ValueError — استحالة بناء أمر لقرار لم يُخلَّص. مفتاح idempotency
مشتقّ حتميّاً (recommendation_id:command:device) ليمنع الإطلاق المزدوج عند الإعادة.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ActuatorCommand:
    """أمر مُشغِّل جاهز للإدراج/الإرسال — يطابق ما يستهلكه actuator-service."""

    device_id: str
    command: str  # مثل: open_valve | close_valve | start_irrigation
    payload: dict
    idempotency_key: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_actuator_command(
    decision: Any,
    *,
    device_id: str,
    command: str,
    params: dict | None = None,
    idempotency_key: str | None = None,
) -> ActuatorCommand:
    """يبني أمر المُشغِّل من قرار توزيع **READY** فقط (نقيّ).

    fail-closed: قرار غير قابل للتنفيذ (BLOCKED/PENDING) ⇒ ValueError. device_id
    و command إلزاميّان. يُضاف field_id/recommendation_id للـpayload (أثر).
    """
    if not getattr(decision, "executable", False):
        raise ValueError("لا يُبنى أمر تنفيذ لقرار غير مُخلَّص — READY فقط (حاجز/موافقة)")
    if not (device_id or "").strip() or not (command or "").strip():
        raise ValueError("device_id و command مطلوبان لبناء أمر المُشغِّل")

    payload = dict(params or {})
    payload.setdefault("field_id", getattr(decision, "field_id", None))
    payload.setdefault("recommendation_id", getattr(decision, "recommendation_id", None))
    key = idempotency_key or f"{getattr(decision, 'recommendation_id', '')}:{command}:{device_id}"
    return ActuatorCommand(
        device_id=device_id, command=command, payload=payload, idempotency_key=key
    )
