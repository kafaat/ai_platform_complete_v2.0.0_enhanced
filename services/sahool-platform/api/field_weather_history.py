"""ملخّصُ الطقس التاريخيّ لحزمة سياق الحقل (W1-22) — دوالُّ نقيّة بلا شبكة ولا قاعدة.

نُقلت من ``api.routers.field_ai_context`` (حدُّ حجم الراوترات): الراوترُ يجلب ``historical_view``
من weather-service ويستدعي ``summarize_weather_history``؛ ويُعاد تصديرُها من هناك لمستدعيها.
**الغيابُ يبقى ``None`` في كلّ مستوى**، واليومُ المطلوبُ المحذوفُ من الاستجابة غيابٌ كاليوم الفارغ.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any


def _complete_total(values: list[float | None]) -> float | None:
    """مجموعُ سلسلةٍ **مكتملة** أو ``None`` — الغيابُ لا يُجمَع صفراً.

    كانت الحزمةُ تجمع ``float(d.precipitation_mm or 0)``: يومٌ بلا قراءة مطرٍ يُحسَب
    «يوماً جافّاً»، فيصل المستشارَ مجموعٌ أصغرُ من الواقع موسوماً كاملاً، ويُوصي بالريّ
    على جفافٍ لم يُرصَد (weather-4). عددُ الأيّام الناقصة يُعلَن بجانبه بدل إخفائه.
    """
    if not values or any(v is None for v in values):
        return None
    return round(sum(v for v in values if v is not None), 2)


def _missing_count(values: list[float | None]) -> int:
    return sum(1 for v in values if v is None)


def _observed_total(values: list[float | None]) -> float | None:
    """مجموعُ الأيّام **المرصودة** وحدها — ``None`` إن لم يُرصَد يوم.

    ليس بديلاً عن ``_complete_total``: يُعرَض بجانبه مع عدد الأيّام المرصودة، فيبقى للمستشار
    إشارةُ المطر/ET0 حين يتأخّر أرشيف ERA5 أيّاماً في آخر النافذة، دون أن يُقرأ ناقصاً كاملاً.
    """
    present = [v for v in values if v is not None]
    return round(sum(present), 2) if present else None


def _expected_dates(start: date | None, end: date | None) -> list[str]:
    if start is None or end is None or end < start:
        return []
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def summarize_weather_history(
    records: list[Any],
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
    source_missing_days: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """ملخّصُ الطقس التاريخيّ وأشهرُه — دالّةٌ نقيّة، والغيابُ يبقى ``None`` في كلّ مستوى.

    **اليومُ المحذوف من الاستجابة غيابٌ كاليوم الفارغ:** كان العدُّ يرى ``None`` داخل الأيّام
    المُعادة وحدها، فأرشيفٌ أعاد ٧٠٠ يومٍ كاملة من ٧٣٠ مطلوبة يُجمَع «مكتملاً» ويُقرأ أصغرَ من
    الواقع. تُحسَب الأيّامُ المطلوبة الغائبة من النافذة المطلوبة (``requested_start..end``، شاملةً)
    ومن ``coverage.missing_days`` المعلَن من المالك (``source_missing_days``) أيّهما أكبر، فتُضاف
    إلى ``*_days_missing`` ويصير المجموعُ الكامل ``None``.
    """
    temp_vals = [
        (d.temp_max_c + d.temp_min_c) / 2
        for d in records
        if d.temp_max_c is not None and d.temp_min_c is not None
    ]
    expected = _expected_dates(requested_start, requested_end)
    present = {str(d.date)[:10] for d in records if d.date}
    omitted_dates = [day for day in expected if day not in present]
    omitted = max(len(omitted_dates), int(source_missing_days or 0))
    precip: list[float | None] = [d.precipitation_mm for d in records] + [None] * omitted
    et0: list[float | None] = [d.et0_mm for d in records] + [None] * omitted
    summary = {
        "days": len(records),
        "days_omitted_by_source": omitted,
        "avg_temp_c": round(mean(temp_vals), 2) if temp_vals else None,
        "total_precipitation_mm": _complete_total(precip),
        "precipitation_days_missing": _missing_count(precip),
        "observed_precipitation_mm": _observed_total(precip),
        "precipitation_days_observed": len(precip) - _missing_count(precip),
        "total_et0_mm": _complete_total(et0),
        "et0_days_missing": _missing_count(et0),
        "observed_et0_mm": _observed_total(et0),
        "et0_days_observed": len(et0) - _missing_count(et0),
        "first_date": records[0].date if records else None,
        "last_date": records[-1].date if records else None,
    }
    # Keep context compact for the chat runtime: monthly buckets by YYYY-MM.
    monthly: dict[str, dict[str, list[float | None]]] = {}
    for d in records:
        bucket = monthly.setdefault(str(d.date)[:7], {"precipitation_mm": [], "et0_mm": []})
        bucket["precipitation_mm"].append(d.precipitation_mm)
        bucket["et0_mm"].append(d.et0_mm)
    omitted_by_month: dict[str, int] = {}
    for day in omitted_dates:
        # يومٌ مطلوبٌ غائب يُحسَب على شهره: لا مجموعَ شهريّاً «كاملاً» بأيّامٍ محذوفة.
        bucket = monthly.setdefault(day[:7], {"precipitation_mm": [], "et0_mm": []})
        bucket["precipitation_mm"].append(None)
        bucket["et0_mm"].append(None)
        omitted_by_month[day[:7]] = omitted_by_month.get(day[:7], 0) + 1
    monthly_items = [
        {
            "month": month,
            "days": len(v["precipitation_mm"]) - omitted_by_month.get(month, 0),
            "days_omitted_by_source": omitted_by_month.get(month, 0),
            "precipitation_mm": _complete_total(v["precipitation_mm"]),
            "precipitation_days_missing": _missing_count(v["precipitation_mm"]),
            "et0_mm": _complete_total(v["et0_mm"]),
            "et0_days_missing": _missing_count(v["et0_mm"]),
        }
        for month, v in sorted(monthly.items())
    ]
    return summary, monthly_items
