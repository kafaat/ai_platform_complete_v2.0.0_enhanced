"""api/operations_summary.py — طبقة تشكيل نقيّة لتلخيص مركز العمليّات.

دالّة تشكيل واحدة نقيّة (لا قاعدة، لا I/O) تحوّل قواميس العدّ الخام (نواتج
COUNT/GROUP BY عبر ``tenant_connection``) إلى جسم استجابة جدار مركز العمليّات:
إجماليّات (حقول، معدّات، أجهزة، قرارات مُدامة) + تصنيف التنبيهات النشطة بالخطورة
(info/warning/critical) + حالة الريّ (صمّامات/جداول) + آخر نشاط + وسوم صدق.

**نمط الصدق**: المصدر الغائب (``None`` خام من استعلام فرعيّ فشل/غاب جدوله) يُشكَّل
صراحةً 0/None مع ``note_ar`` يوضّح غياب المصدر — لا تلفيق ولا حشو صامت. لا بيانات
طقس خارجيّة هنا (تجلبها الواجهة من نقطتها). ``calibrated`` غير منطبق على العدّ
التجميعيّ (لا معايرة لعدّ)، فنرفعه ``not_applicable`` صراحةً.

يستهلكها ``routers/operations`` والاختبارات مباشرةً — قابلة للاختبار offline.
"""

from __future__ import annotations

_SEVERITIES = ("info", "warning", "critical")


def _as_count(value) -> int | None:
    """قيمة عدّ خام → int موجب، أو None إن غاب المصدر (لا تلفيق).

    ``None`` (استعلام فرعيّ فشل/غاب جدوله) يبقى ``None`` صراحةً ليُوسَم لاحقاً؛
    أيّ رقم يُحوَّل إلى int غير سالب (حارس ضدّ قيم شاذّة).
    """
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else 0


def _shape_alerts_by_severity(raw) -> tuple[dict[str, int], int, bool]:
    """قاموس عدّ التنبيهات النشطة الخام {severity: count} → تصنيف مُسوّى + إجماليّ.

    يضمن ظهور المفاتيح الثلاثة (info/warning/critical) دائماً (0 إن غابت). يعيد
    أيضاً علم ``available`` (False إن كان المصدر كلّه ``None`` — جدول غائب/فشل).
    """
    by_severity = {s: 0 for s in _SEVERITIES}
    if raw is None:
        return by_severity, 0, False
    for sev in _SEVERITIES:
        c = _as_count(raw.get(sev))
        by_severity[sev] = c if c is not None else 0
    total = sum(by_severity.values())
    return by_severity, total, True


def _section_status(available: bool, error: str | None) -> dict:
    """حالة قسم واحد في الجدار — صدق التشغيل (live/degraded/unavailable).

    available=False ⇒ ``unavailable`` (جدول غائب/استعلام تعذّر) مع سبب. متاح مع خطأ
    ⇒ ``degraded`` (بيانات جزئيّة). متاح بلا خطأ ⇒ ``ok`` حيّ (freshness_sec=0، قراءة
    آنيّة؛ يرفعها الموجِّه لاحقاً إن أُضيف cache قصير). لا تلفيق: القسم غير المتاح يُعلَن.
    """
    if not available:
        return {"status": "unavailable", "error": error or "غير متاح (جدول غائب أو استعلام تعذّر)"}
    if error:
        return {"status": "degraded", "freshness_sec": 0, "error": error}
    return {"status": "ok", "freshness_sec": 0}


def shape_operations_summary(
    counts: dict,
    *,
    generated_at: str | None = None,
    errors: dict | None = None,
) -> dict:
    """يبني جسم التلخيص التشغيليّ من قواميس العدّ الخام — نقيّ (لا قاعدة).

    ``counts`` المتوقَّعة (كلّ مفتاح best-effort؛ غيابه/``None`` ⇒ 0/None + note):
      • ``fields`` (int|None) — عدد الحقول للمستأجِر.
      • ``alerts_active`` (dict|None) — {severity: count} للتنبيهات النشطة فقط.
      • ``equipment`` (int|None) — عدد المعدّات.
      • ``iot_devices`` (int|None) — عدد الأجهزة.
      • ``decision_records`` (int|None) — عدد القرارات المُدامة (decision_record).
      • ``irrigation_valves`` (int|None) — عدد الصمّامات.
      • ``irrigation_schedules`` (int|None) — عدد جداول الريّ.
      • ``last_activity_at`` (str|None) — آخر نشاط (ISO) عبر المصادر، أو None.

    ``generated_at`` (ISO): لحظة تجميع التلخيص (يمرّرها الموجِّه). ``errors`` (dict):
    {section: رسالة} لأقسام تدهورت/تعذّرت — لإثراء حالة القسم بسبب صريح.

    الناتج: ``generated_at`` + ``partial`` (أيّ قسم ليس ok) + ``sections`` (لكلّ قسم
    status: ok|degraded|unavailable + freshness_sec/error) + ``totals`` + ``alerts``
    + ``irrigation`` + ``last_activity_at`` + ``provenance``. صدق: القسم غير المتاح يُعلَن.
    """
    c = counts or {}
    errs = errors or {}

    fields = _as_count(c.get("fields"))
    equipment = _as_count(c.get("equipment"))
    devices = _as_count(c.get("iot_devices"))
    decisions = _as_count(c.get("decision_records"))
    valves = _as_count(c.get("irrigation_valves"))
    schedules = _as_count(c.get("irrigation_schedules"))

    alerts_by_sev, alerts_total, alerts_available = _shape_alerts_by_severity(
        c.get("alerts_active")
    )

    # توفّر كلّ قسم (مصدره الخام ليس None) — أساس حالة القسم + ملاحظة الصدق.
    availability = {
        "fields": fields is not None,
        "alerts": alerts_available,
        "equipment": equipment is not None,
        "iot_devices": devices is not None,
        "decision_records": decisions is not None,
        "irrigation": valves is not None or schedules is not None,
    }

    sections = {sec: _section_status(ok, errs.get(sec)) for sec, ok in availability.items()}
    partial = any(s["status"] != "ok" for s in sections.values())

    # وسوم الصدق: أيّ مصدر غير متاح ⇒ ملاحظة صريحة (لا تلفيق).
    missing = [sec for sec, ok in availability.items() if not ok]

    provenance: dict = {
        "calibrated": "not_applicable",  # عدّ تجميعيّ — لا معايرة تنطبق
    }
    if missing:
        provenance["note_ar"] = (
            "مصادر غير متاحة (جدول غائب أو استعلام فرعيّ تعذّر): "
            + "، ".join(missing)
            + " — عُرِضت 0/None دون تلفيق."
        )

    return {
        "generated_at": generated_at,
        "partial": partial,
        "sections": sections,
        "totals": {
            "fields": fields if fields is not None else 0,
            "equipment": equipment if equipment is not None else 0,
            "iot_devices": devices if devices is not None else 0,
            "decision_records": decisions if decisions is not None else 0,
            "active_alerts": alerts_total,
        },
        "alerts": {
            "active_total": alerts_total,
            "by_severity": alerts_by_sev,
            "available": alerts_available,
        },
        "irrigation": {
            "valves": valves if valves is not None else 0,
            "schedules": schedules if schedules is not None else 0,
            "available": valves is not None or schedules is not None,
        },
        "last_activity_at": c.get("last_activity_at"),
        "provenance": provenance,
    }
