"""api/sensor_confidence.py — طبقة ثقة الحسّاس + التوأم الرقميّ للجهاز (Device Twin، IoT)

ليس كلّ حسّاس موثوقاً: جهاز لم يُرسل منذ يومين، أو بطّاريّته منخفضة، أو معايرته قديمة
— قراءته أضعف ثقةً. هذه طبقة **تشكيل نقيّة** تحوّل حالة الجهاز الخام (نضارة آخر إرسال،
الحالة، البطّاريّة، عمر المعايرة، جودة الإشارة) إلى **درجة صحّة شفّافة** ومستوى ثقة
لكلّ جهاز — أساس ``Sensor Confidence`` في ثقة القرار لاحقاً، وأساس **التوأم الرقميّ
للجهاز** (Device Twin).

**نمط الصدق**: الدرجة معادلة موزونة **مُوثَّقة** (لا نموذج معايَر) محسوبة على الإشارات
**المتوفّرة فقط** — الإشارة الغائبة **تُستبعَد وتُعلَن** في ``missing_signals`` (لا تُفترَض
قيمة). جهاز بلا أيّ إشارة (لم يُرَ قطّ) ⇒ ``needs_data``/``unknown`` لا «صحّة افتراضيّة».
لا ساعة هنا: عمر آخر إرسال (``age_sec``) يُمرَّر محسوباً من الموجِّه (نقيّ حتميّ، قابل
للاختبار offline).

يستهلكه ``routers/device_twin`` والاختبارات مباشرةً.
"""

from __future__ import annotations

# أوزان عوامل الصحّة (تُطبَّع على المتوفّر فقط). ⚠ تقديريّة موسومة، غير معايَرة.
_WEIGHTS = {
    "freshness": 0.5,  # نضارة آخر إرسال — أقوى إشارة (جهاز صامت = قراءة قديمة)
    "battery": 0.2,
    "calibration": 0.2,
    "signal": 0.1,
}

# عتبات عمر آخر إرسال (ثوانٍ) → درجة نضارة.
_HOUR = 3600
_FRESHNESS_BANDS = ((1 * _HOUR, 1.0), (6 * _HOUR, 0.8), (24 * _HOUR, 0.5), (72 * _HOUR, 0.25))
_STALE_AFTER_SEC = 24 * _HOUR  # أقدم من يوم ⇒ «بائت» (stale)
_OFFLINE_AFTER_SEC = 72 * _HOUR  # أقدم من 3 أيّام ⇒ يُعدّ منقطعاً

_LEVEL_AR = {
    "healthy": "سليم",
    "degraded": "متدهور",
    "stale": "بائت (قراءة قديمة)",
    "offline": "منقطع",
    "poor": "ضعيف",
    "unknown": "غير معروف (يحتاج بيانات)",
}


def _band(value: float, bands: tuple, below_floor: float) -> float:
    """يعيد درجة من جداول عتبات تصاعديّة (أوّل عتبة ≥ القيمة)، أو الأرضيّة."""
    for threshold, score in bands:
        if value <= threshold:
            return score
    return below_floor


def _freshness_score(age_sec) -> float | None:
    """درجة نضارة من عمر آخر إرسال (ثوانٍ) — None إن لم يُرَ الجهاز قطّ (لا تلفيق)."""
    if age_sec is None:
        return None
    if age_sec < 0:
        age_sec = 0
    return _band(age_sec, _FRESHNESS_BANDS, 0.05)


def _battery_score(battery_pct) -> float | None:
    """درجة بطّاريّة من النسبة المئويّة — None إن غابت."""
    if battery_pct is None:
        return None
    p = max(0.0, min(100.0, float(battery_pct)))
    if p >= 50:
        return 1.0
    if p >= 20:
        return 0.6
    if p >= 10:
        return 0.3
    return 0.1


def _calibration_score(calibration_age_days) -> float | None:
    """درجة معايرة من عمرها (أيّام) — None إن غاب (لا نفترض حداثة)."""
    if calibration_age_days is None:
        return None
    d = max(0.0, float(calibration_age_days))
    if d <= 180:
        return 1.0
    if d <= 365:
        return 0.7
    if d <= 730:
        return 0.4
    return 0.2


def _signal_score(signal_quality) -> float | None:
    """درجة جودة إشارة (يقبل 0..1 أو 0..100) — None إن غابت."""
    if signal_quality is None:
        return None
    q = float(signal_quality)
    if q > 1.0:  # على الأرجح 0..100
        q = q / 100.0
    return max(0.0, min(1.0, q))


def score_device_health(device: dict) -> dict:
    """يحسب صحّة جهاز واحد + مستواه من إشاراته المتوفّرة — نقيّ حتميّ، لا ساعة.

    ``device`` (best-effort): ``device_id``، ``name``، ``type``، ``field_id``،
    ``status`` (online/offline/unknown)، ``age_sec`` (عمر آخر إرسال بالثواني، None إن
    لم يُرَ)، ``battery_pct``، ``calibration_age_days``، ``signal_quality``، ``firmware``.

    الناتج: ``health_score`` (0..1 أو None)، ``level`` (healthy/degraded/stale/offline/
    poor/unknown) + ``level_ar``، ``factors`` (العوامل المحسوبة)، ``missing_signals``
    (المُستبعَدة صراحةً)، و``note_ar``. صدق: الدرجة على المتوفّر فقط؛ بلا إشارة ⇒ unknown.
    """
    raw_factors = {
        "freshness": _freshness_score(device.get("age_sec")),
        "battery": _battery_score(device.get("battery_pct")),
        "calibration": _calibration_score(device.get("calibration_age_days")),
        "signal": _signal_score(device.get("signal_quality")),
    }
    factors = {k: round(v, 3) for k, v in raw_factors.items() if v is not None}
    missing = [k for k, v in raw_factors.items() if v is None]

    # الدرجة = متوسّط موزون على العوامل المتوفّرة فقط (إعادة تطبيع الأوزان).
    if factors:
        wsum = sum(_WEIGHTS[k] for k in factors)
        health = sum(raw_factors[k] * _WEIGHTS[k] for k in factors) / wsum
        health = round(max(0.0, min(1.0, health)), 3)
    else:
        health = None

    status = (device.get("status") or "unknown").lower()
    age_sec = device.get("age_sec")

    # المستوى: الحالة الصريحة والانقطاع أوّلاً، ثمّ الدرجة.
    if status == "offline" or (age_sec is not None and age_sec >= _OFFLINE_AFTER_SEC):
        level = "offline"
    elif health is None:
        level = "unknown"  # لا إشارة أصلاً ⇒ يحتاج بيانات
    elif age_sec is not None and age_sec >= _STALE_AFTER_SEC:
        level = "stale"
    elif health >= 0.8:
        level = "healthy"
    elif health >= 0.5:
        level = "degraded"
    else:
        level = "poor"

    if level == "unknown":
        note = "لا إشارة من الجهاز بعد (لم يُرسِل/لم يُعرَف آخر اتّصال) — الثقة غير محسوبة."
    elif missing:
        note = (
            "درجة محسوبة على الإشارات المتوفّرة فقط؛ غائبة: " + "، ".join(missing) + " (لا افتراض)."
        )
    else:
        note = None

    return {
        "device_id": device.get("device_id"),
        "name": device.get("name"),
        "type": device.get("type"),
        "field_id": device.get("field_id"),
        "status": status,
        "firmware": device.get("firmware"),
        "age_sec": age_sec,
        "health_score": health,
        "level": level,
        "level_ar": _LEVEL_AR[level],
        "factors": factors,
        "missing_signals": missing,
        "note_ar": note,
    }


def shape_device_twin(devices: list[dict], *, generated_at: str | None = None) -> dict:
    """يبني توأم أجهزة المستأجِر + ملخّص ثقة الأسطول — نقيّ حتميّ.

    يصحّح كلّ جهاز عبر ``score_device_health`` ثمّ يلخّص: عدّ بكلّ مستوى، وثقة الأسطول
    (``fleet_confidence`` = متوسّط الدرجات المحسوبة، None إن لا درجة لأيّ جهاز — لا تلفيق).
    صدق: الأجهزة بلا إشارة تُعدّ ``unknown`` صراحةً ولا تُحتسب في متوسّط الثقة.
    """
    twins = [score_device_health(d) for d in devices or []]

    by_level: dict[str, int] = {lvl: 0 for lvl in _LEVEL_AR}
    scored: list[float] = []
    for t in twins:
        by_level[t["level"]] += 1
        if t["health_score"] is not None:
            scored.append(t["health_score"])

    fleet_confidence = round(sum(scored) / len(scored), 3) if scored else None

    return {
        "generated_at": generated_at,
        "devices": twins,
        "device_count": len(twins),
        "scored_count": len(scored),
        "by_level": by_level,
        "fleet_confidence": fleet_confidence,
        "provenance": {
            "calibrated": "not_applicable",
            "note_ar": (
                "ثقة الحسّاس معادلة موزونة شفّافة (نضارة/بطّاريّة/معايرة/إشارة) على "
                "الإشارات المتوفّرة فقط — العتبات تقديريّة غير معايَرة، والجهاز بلا إشارة "
                "unknown لا يُحتسب في ثقة الأسطول (لا تلفيق)."
            ),
        },
    }
