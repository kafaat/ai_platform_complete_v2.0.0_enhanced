"""api/agronomic_replay.py — طبقة تشكيل نقيّة لإعادة تشغيل الموسم (Replay Map، #4/D)

تدمج سلاسل الحقل المُدامة المتفرّقة (NDVI، طقس، ريّ، قرارات، نتائج) في **خطّ زمنيّ
واحد مرتّب** قابل لإعادة التشغيل (scrub) — «أعِد تشغيل الموسم»: ماذا حدث، متى، وبأيّ
أثر. على عكس ``event_replay`` (إعادة بناء حالة من الأحداث للتشخيص)، هذا **عرض زمنيّ
أغرونوميّ** يجمع مساراً لكلّ نوع مصدر فوق محور زمن مشترك.

المسارات (tracks): ``ndvi`` · ``weather`` · ``irrigation`` · ``decision`` · ``outcome``.
لكلّ حدث: تاريخه، مساره، تسمية عربيّة، قيمة/ملخّص، ومرجع المصدر (``ref_id``) إن وُجد.

**الصدق**: كلّ حدث من سجلّ مُدام فعليّ (لا حدث مُختلق)؛ المسار الفارغ يُعلَن صفراً لا
يُحشى؛ التواريخ تُمرَّر كما وردت (ISO)؛ المدى ``span`` من البيانات فقط. ``calibrated``
غير منطبق ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O، لا ساعة عدا generated_at المُمرَّر) — قابل للاختبار offline؛
يستهلكه ``routers/agronomic_replay``.
"""

from __future__ import annotations

_TRACKS = ("ndvi", "weather", "irrigation", "decision", "outcome")

_TRACK_AR = {
    "ndvi": "مؤشّر NDVI",
    "weather": "طقس",
    "irrigation": "ريّ",
    "decision": "قرار",
    "outcome": "نتيجة ميدانيّة",
}


def _iso(value) -> str | None:
    """تطبيع طابع زمنيّ إلى ISO نصّيّ — None إن غاب (لا تلفيق)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _event(date, track: str, label_ar: str, *, value=None, ref_id=None) -> dict | None:
    """يبني حدثاً واحداً للخطّ — يُهمَل (None) إن غاب تاريخه (لا حدث بلا زمن)."""
    iso = _iso(date)
    if iso is None:
        return None
    return {
        "date": iso,
        "track": track,
        "track_ar": _TRACK_AR[track],
        "label_ar": label_ar,
        "value": value,
        "ref_id": ref_id,
    }


def build_agronomic_replay(
    field_id: str,
    *,
    ndvi: list[dict] | None = None,
    weather: list[dict] | None = None,
    irrigation: list[dict] | None = None,
    decisions: list[dict] | None = None,
    outcomes: list[dict] | None = None,
    generated_at: str | None = None,
) -> dict:
    """يدمج سلاسل الحقل في خطّ زمنيّ واحد مرتّب لإعادة التشغيل — نقيّ حتميّ.

    كلّ مُدخَل قائمة قواميس من سجلّ مُدام (best-effort):
      • ``ndvi``: ``{acquisition_date, ndvi_mean}`` (من ndvi_timeseries).
      • ``weather``: ``{date, summary_ar?|t_max?|rain_mm?}`` (إن توفّر مصدر طقس مُدام).
      • ``irrigation``: ``{last_run_at, name?, water_target_mm?}`` (من irrigation_schedules).
      • ``decisions``: ``{created_at, decision_type, decision_id, confidence?}`` (decision_record).
      • ``outcomes``: ``{created_at, success?, outcome_id, decision_id?}`` (outcome_record).

    الناتج: ``events`` (مدموجة مرتّبة تصاعديّاً بالتاريخ) + ``counts_by_track`` + ``span``
    (أوّل/آخر تاريخ) + ``tracks`` + ``provenance``. صدق: حدث بلا تاريخ يُهمَل؛ المسار
    الفارغ يُعلَن 0؛ لا تواريخ مخترَعة.
    """
    events: list[dict] = []

    for r in ndvi or []:
        mean = r.get("ndvi_mean")
        ev = _event(
            r.get("acquisition_date") or r.get("date"),
            "ndvi",
            f"NDVI {round(float(mean), 3)}" if mean is not None else "قياس NDVI",
            value=float(mean) if mean is not None else None,
            ref_id=r.get("field_id"),
        )
        if ev:
            events.append(ev)

    for r in weather or []:
        ev = _event(
            r.get("date") or r.get("observed_at"),
            "weather",
            r.get("summary_ar") or "رصد طقس",
            value={k: r[k] for k in ("t_max", "t_min", "rain_mm") if k in r} or None,
        )
        if ev:
            events.append(ev)

    for r in irrigation or []:
        ev = _event(
            r.get("last_run_at") or r.get("date"),
            "irrigation",
            r.get("name") or "تشغيل ريّ",
            value=r.get("water_target_mm"),
            ref_id=r.get("schedule_id"),
        )
        if ev:
            events.append(ev)

    for r in decisions or []:
        ev = _event(
            r.get("created_at") or r.get("date"),
            "decision",
            r.get("decision_type") or "قرار",
            value=r.get("confidence"),
            ref_id=r.get("decision_id"),
        )
        if ev:
            events.append(ev)

    for r in outcomes or []:
        success = r.get("success")
        label = (
            "نتيجة: نجاح"
            if success is True
            else ("نتيجة: إخفاق" if success is False else "نتيجة مُقاسة")
        )
        ev = _event(
            r.get("created_at") or r.get("date"),
            "outcome",
            label,
            value=success,
            ref_id=r.get("outcome_id"),
        )
        if ev:
            events.append(ev)

    events.sort(key=lambda e: e["date"])  # تصاعديّ زمنيّاً (إعادة تشغيل من البداية)

    counts = {t: 0 for t in _TRACKS}
    for e in events:
        counts[e["track"]] += 1

    span = {"start": events[0]["date"], "end": events[-1]["date"]} if events else None

    return {
        "field_id": field_id,
        "generated_at": generated_at,
        "tracks": [{"track": t, "track_ar": _TRACK_AR[t]} for t in _TRACKS],
        "events": events,
        "counts_by_track": counts,
        "event_count": len(events),
        "span": span,
        "provenance": {
            "calibrated": "not_applicable",
            "note_ar": (
                "خطّ زمنيّ من سجلّات مُدامة فقط (NDVI/طقس/ريّ/قرار/نتيجة)؛ الحدث بلا "
                "تاريخ يُهمَل والمسار الفارغ يُعلَن صفراً — لا أحداث مخترَعة."
            ),
        },
    }
