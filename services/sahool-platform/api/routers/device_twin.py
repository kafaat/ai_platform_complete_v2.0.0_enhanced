"""api/routers/device_twin.py — التوأم الرقميّ للجهاز + ثقة الحسّاس (قراءة فقط، IoT)

نقطة واحدة محروسة بعلم ``FEATURE_DEVICE_TWIN`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/devices/twin`` — لكلّ جهاز IoT للمستأجِر: **توأم رقميّ** (هويّة + حالة
    + صحّة) مع **درجة ثقة شفّافة** من نضارة آخر إرسال/البطّاريّة/عمر المعايرة/جودة
    الإشارة، عبر ``tenant_connection`` (عزل RLS). + ملخّص ثقة الأسطول.

**الصدق**: درجة الصحّة من الطبقة النقيّة ``shape_device_twin`` على الإشارات المتوفّرة
فقط — الغائبة تُعلَن لا تُفترَض؛ جهاز بلا إشارة ⇒ ``unknown`` (needs_data). البطّاريّة
وعمر المعايرة وجودة الإشارة best-effort (من أحدث telemetry/metadata)؛ غيابها لا يُفشِل.
العمر (``age_sec``) يُحسب من ``last_seen_at`` لحظة الطلب. 503 فقط إن تعذّرت القاعدة.
**قراءة فقط**: لا أوامر تشغيل/إيقاف للأجهزة هنا (تلك طبقة Execution لاحقاً بحُرّاسها).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.sensor_confidence import shape_device_twin

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_DEVICES = 500


def _device_twin_enabled() -> bool:
    """هل ميزة التوأم الرقميّ للجهاز مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_DEVICE_TWIN", "").strip().lower() in _TRUTHY


def _age_sec(last_seen, now: datetime) -> float | None:
    """عمر آخر إرسال بالثواني (now − last_seen) — None إن لم يُرَ الجهاز (لا تلفيق)."""
    if last_seen is None:
        return None
    try:
        delta = (now - last_seen).total_seconds()
    except (TypeError, ValueError):
        return None
    return max(0.0, delta)


def _num(meta: dict, *keys):
    """يستخرج أوّل مفتاح رقميّ موجود من metadata — None إن غاب/غير رقميّ (لا افتراض)."""
    for k in keys:
        if k in meta and meta[k] is not None:
            try:
                return float(meta[k])
            except (TypeError, ValueError):
                continue
    return None


async def _latest_battery(conn) -> dict[str, float]:
    """أحدث قراءة بطّاريّة لكلّ جهاز best-effort — {} إن غاب الجدول/لا قراءات."""
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT ON (device_id) device_id, value "
            "FROM device_telemetry WHERE sensor_type IN ('battery', 'battery_pct', 'battery_level') "
            "ORDER BY device_id, recorded_at DESC"
        )
    except Exception:  # noqa: BLE001 — جدول/عمود غائب ⇒ لا بطّاريّة (تُعلَن غائبة لاحقاً)
        return {}
    return {str(r["device_id"]): float(r["value"]) for r in rows if r["value"] is not None}


@router.get("/api/v1/devices/twin")
async def device_twin_endpoint(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """توأم أجهزة المستأجِر + ثقة الحسّاس (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يقرأ ``iot_devices`` + أحدث بطّاريّة best-effort، يحسب عمر آخر إرسال، ثمّ يُشكّل عبر
    الطبقة النقيّة (درجة صحّة + مستوى لكلّ جهاز + ثقة الأسطول). صدق: الإشارة الغائبة تُعلَن.
    """
    if not _device_twin_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة التوأم الرقميّ للجهاز غير مُفعَّلة (اضبط FEATURE_DEVICE_TWIN).",
        )
    now = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT device_id, name, type, field_id, status, last_seen_at, "
                "       firmware_version, metadata "
                f"FROM iot_devices ORDER BY device_id LIMIT {_MAX_DEVICES}"
            )
            battery = await _latest_battery(conn)
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("توأم الأجهزة", e) from e

    devices: list[dict] = []
    for r in rows:
        meta = r["metadata"] if isinstance(r["metadata"], dict) else {}
        did = str(r["device_id"])
        devices.append(
            {
                "device_id": did,
                "name": r["name"],
                "type": r["type"],
                "field_id": r["field_id"],
                "status": r["status"],
                "firmware": r["firmware_version"],
                "age_sec": _age_sec(r["last_seen_at"], now),
                "battery_pct": battery.get(did, _num(meta, "battery_pct", "battery")),
                "calibration_age_days": _num(meta, "calibration_age_days"),
                "signal_quality": _num(meta, "signal_quality", "rssi_pct"),
            }
        )

    out = shape_device_twin(devices, generated_at=now.isoformat())
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذا التوأم (RLS)
    return out
