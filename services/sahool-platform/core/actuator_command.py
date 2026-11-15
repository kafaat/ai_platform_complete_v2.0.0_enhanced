"""core/actuator_command.py — ترجمة قرار توزيع مُخلَّص إلى أمر مُشغِّل (نقيّ).

يحوّل `DispatchDecision` بحالة READY إلى شكل الأمر الذي يتوقّعه actuator-service
(`{device_id, command, payload}` — يوقّعه المُشغِّل HMAC ثمّ ينشره على
`sahool/actuator/{device_id}/command`). نقيّ وحتميّ، لا I/O.

أمان (fail-closed): لا يُبنى أمر إلّا لقرار **READY** (محروس + موافَق). أيّ قرار
BLOCKED/PENDING ⇒ ValueError — استحالة بناء أمر لقرار لم يُخلَّص. مفتاح idempotency
مشتقّ حتميّاً (recommendation_id:command:device) ليمنع الإطلاق المزدوج عند الإعادة.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

#: تهجئاتُ الدقائق التي تُحوَّل **هنا** إلى `duration_sec` — المصدرُ المعروف الوحيد للتحويل.
#: actuator-service يقرأ `duration_sec` وحده ويرفض الدقائق صراحةً (لا يُخمِّن ولا يفترض 30 دقيقة).
_MINUTE_DURATION_FIELDS = ("duration_minutes", "duration_min", "durationMinutes")


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def canonical_duration_payload(params: dict | None) -> dict:
    """نقيّ: يُعيد الحمولة بمدّتها في الحقل الكنسيّ `duration_sec`.

    الدقائق تُحوَّل صراحةً (×60) وتُزال تهجئتُها؛ وقيمةٌ غير رقميّة أو غير موجبة ⇒
    ``ValueError("invalid_duration_minutes:<field>")``؛ ودقائقُ تخالف `duration_sec` أو
    تخالف بعضَها ⇒ ``ValueError("conflicting_duration_fields")``. لا مدّة افتراضيّة: حمولةٌ
    بلا مدّة تبقى بلا مدّة، ويرفض المُشغِّلُ فتحَها (`open_command_requires_duration_sec`).
    """
    payload = dict(params or {})
    seconds: list[float] = []
    for key in _MINUTE_DURATION_FIELDS:
        if payload.get(key) is None:
            payload.pop(key, None)
            continue
        minutes = _positive_number(payload.pop(key))
        if minutes is None:
            raise ValueError(f"invalid_duration_minutes:{key}")
        seconds.append(minutes * 60.0)
    if not seconds:
        return payload
    if any(not math.isclose(s, seconds[0], rel_tol=0.0, abs_tol=1e-6) for s in seconds):
        raise ValueError("conflicting_duration_fields")
    if payload.get("duration_sec") is not None:
        declared = _positive_number(payload["duration_sec"])
        if declared is None or not math.isclose(declared, seconds[0], rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("conflicting_duration_fields")
        return payload
    converted = seconds[0]
    payload["duration_sec"] = int(converted) if converted.is_integer() else converted
    return payload


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
    و command إلزاميّان. يُضاف field_id/recommendation_id للـpayload (أثر). والمدّة تُطبَّع
    إلى `duration_sec` عبر ``canonical_duration_payload`` (تحويلٌ صريح أو رفض).
    """
    if not getattr(decision, "executable", False):
        raise ValueError("لا يُبنى أمر تنفيذ لقرار غير مُخلَّص — READY فقط (حاجز/موافقة)")
    if not (device_id or "").strip() or not (command or "").strip():
        raise ValueError("device_id و command مطلوبان لبناء أمر المُشغِّل")

    payload = canonical_duration_payload(params)
    for name in ("field_id", "recommendation_id"):
        authoritative = getattr(decision, name, None)
        if name in payload and payload[name] != authoritative:
            raise ValueError(f"command_{name}_mismatch")
        payload[name] = authoritative
    key = idempotency_key or f"{getattr(decision, 'recommendation_id', '')}:{command}:{device_id}"
    return ActuatorCommand(
        device_id=device_id, command=command, payload=payload, idempotency_key=key
    )
