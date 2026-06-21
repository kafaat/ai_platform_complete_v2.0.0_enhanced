"""api/routers/decision_confidence.py — ثقة القرار الموحَّدة لحقل (قراءة فقط)

نقطة واحدة محروسة بعلم ``FEATURE_DECISION_CONFIDENCE`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/fields/{field_id}/decision-confidence`` — يجمع مصادر الثقة الأربعة
    لحقل (حسّاس/دليل/استشعار/طقس) من البنية الحقيقيّة ثمّ يدمجها عبر الطبقة النقيّة
    ``fuse_decision_confidence``، فيُظهر **كم يمكن الوثوق بقرارات هذا الحقل الآن**.

**عرض ثقة قراءة فقط**: لا يُعدّل القرار ولا ينفّذ. كلّ مصدر best-effort:
  • **حسّاس**: ثقة أسطول أجهزة الحقل (``shape_device_twin`` على ``iot_devices``).
  • **دليل**: مستوى الدليل المُدام من عدد ``outcome_record`` للحقل (عتبة evidence_registry).
  • **استشعار**: نضارة أحدث ``ndvi_timeseries`` للحقل (حداثة القياس).
  • **طقس**: غير مُدام per-field هنا ⇒ ``needs_data`` صريح (لا يُفترَض).

المصدر الغائب يُعلَن missing (لا تلفيق). 503 إن تعذّرت القاعدة كليّاً.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.decision_confidence import fuse_decision_confidence
from api.evidence_map import EVIDENCE_VERIFIED_MIN_SAMPLES
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
_DAY = 86400


def _decision_confidence_enabled() -> bool:
    """هل ميزة ثقة القرار الموحَّدة مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_DECISION_CONFIDENCE", "").strip().lower() in _TRUTHY


def _evidence_value(decisions: int, outcomes: int) -> tuple[float | None, str]:
    """يُحوّل عدّ القرارات/القياسات المُدامة لحقل إلى درجة دليل 0..1 + وصف — None إن لا شيء."""
    if outcomes >= EVIDENCE_VERIFIED_MIN_SAMPLES:
        return 1.0, f"مؤكَّد ميدانيّاً ({outcomes} قياس)"
    if outcomes > 0:
        return 0.6, f"مدعوم أوّليّاً ({outcomes}/{EVIDENCE_VERIFIED_MIN_SAMPLES} قياس)"
    if decisions > 0:
        return 0.3, "إرشاديّ (قرارات بلا قياس ميدانيّ)"
    return None, "لا قرار ولا قياس لهذا الحقل (needs_data)"


def _satellite_value(age_days: float | None) -> tuple[float | None, str]:
    """نضارة الاستشعار من عمر أحدث NDVI (أيّام) → درجة 0..1 + وصف — None إن لا قياس."""
    if age_days is None:
        return None, "لا قياس NDVI مُدام لهذا الحقل (needs_data)"
    if age_days <= 7:
        return 1.0, f"NDVI حديث (منذ {int(age_days)} يوم)"
    if age_days <= 14:
        return 0.8, f"NDVI منذ {int(age_days)} يوم"
    if age_days <= 30:
        return 0.5, f"NDVI منذ {int(age_days)} يوم"
    if age_days <= 60:
        return 0.25, f"NDVI قديم (منذ {int(age_days)} يوم)"
    return 0.05, f"NDVI متقادم جدّاً (منذ {int(age_days)} يوم)"


@router.get("/api/v1/fields/{field_id}/decision-confidence")
async def decision_confidence_endpoint(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """ثقة قرارات حقل واحد (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يجمع حسّاس/دليل/استشعار/طقس من المصادر المُدامة (كلّ best-effort) ثمّ يدمجها عبر
    الطبقة النقيّة. صدق: المصدر الغائب يُعلَن missing/needs_data؛ الطقس غير متوفّر per-field.
    """
    if not _decision_confidence_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة ثقة القرار الموحَّدة غير مُفعَّلة (اضبط FEATURE_DECISION_CONFIDENCE).",
        )
    now = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            # حسّاس: أجهزة الحقل ⇒ ثقة الأسطول.
            try:
                drows = await conn.fetch(
                    "SELECT device_id, name, type, field_id, status, last_seen_at, "
                    "firmware_version, metadata FROM iot_devices WHERE field_id = $1",
                    field_id,
                )
            except Exception:  # noqa: BLE001 — جدول غائب ⇒ لا حسّاس
                drows = []
            # دليل: عدّ قرارات/قياسات الحقل.
            decisions = await _scalar(conn, "decision_record", field_id)
            outcomes = await _scalar(conn, "outcome_record", field_id)
            # استشعار: أحدث NDVI.
            try:
                ndvi_date = await conn.fetchval(
                    "SELECT MAX(acquisition_date) FROM ndvi_timeseries WHERE field_id = $1",
                    field_id,
                )
            except Exception:  # noqa: BLE001 — جدول غائب ⇒ لا استشعار
                ndvi_date = None
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("ثقة القرار", e) from e

    # حسّاس: ثقة الأسطول لأجهزة الحقل.
    devices = []
    for r in drows:
        meta = r["metadata"] if isinstance(r["metadata"], dict) else {}
        last = r["last_seen_at"]
        age_sec = (now - last).total_seconds() if last is not None else None
        devices.append(
            {
                "device_id": str(r["device_id"]),
                "status": r["status"],
                "age_sec": max(0.0, age_sec) if age_sec is not None else None,
                "battery_pct": _num(meta, "battery_pct", "battery"),
                "calibration_age_days": _num(meta, "calibration_age_days"),
                "signal_quality": _num(meta, "signal_quality", "rssi_pct"),
            }
        )
    twin = shape_device_twin(devices)
    sensor_value = twin["fleet_confidence"]  # None إن لا جهاز مُصحَّح
    sensor_detail = (
        f"ثقة أسطول {twin['scored_count']}/{twin['device_count']} جهاز"
        if devices
        else "لا أجهزة على هذا الحقل (needs_data)"
    )

    ev_value, ev_detail = _evidence_value(decisions, outcomes)
    age_days = (date.today() - ndvi_date).days if ndvi_date is not None else None
    sat_value, sat_detail = _satellite_value(age_days)

    components = {
        "sensor": {"value": sensor_value, "detail_ar": sensor_detail},
        "evidence": {"value": ev_value, "detail_ar": ev_detail},
        "satellite": {"value": sat_value, "detail_ar": sat_detail},
        "weather": {"value": None, "detail_ar": "ثقة طقس per-field غير مُدامة هنا (needs_data)"},
    }

    out = fuse_decision_confidence(components, generated_at=now.isoformat())
    out["field_id"] = field_id
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه الثقة (RLS)
    return out


async def _scalar(conn, table: str, field_id: str) -> int:
    """عدّ صفوف جدول لحقل best-effort — 0 عند تعذّره (جدول غائب)."""
    try:
        val = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE field_id = $1",  # noqa: S608 — table من ثابت داخليّ لا من مدخل
            field_id,
        )
    except Exception:  # noqa: BLE001 — جدول غائب ⇒ 0
        return 0
    return int(val or 0)


def _num(meta: dict, *keys):
    """يستخرج أوّل مفتاح رقميّ من metadata — None إن غاب/غير رقميّ (لا افتراض)."""
    for k in keys:
        if k in meta and meta[k] is not None:
            try:
                return float(meta[k])
            except (TypeError, ValueError):
                continue
    return None
