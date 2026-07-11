"""canonical_daily_weather_series.py — WX-10.4: GDD كـView تراكميّ فوق **سلسلة** canonical.

الفرق المعماريّ الحاسم عن ET0/VPD: GDD ليس مؤشّراً لحظيّاً من لقطة واحدة، بل **تراكم فوق
سلسلة سجلّات طقس يوميّة canonical** — كلّ يوم يحمل هويّة لقطته الخاصّة، والنتيجة تُنسَب إلى
**كلّ** يوم/لقطة شارك في التراكم لا إلى آخر لقطة فقط.

المبدأ: النواة (`gdd.gdd_agro_product`) تبقى **سلطة التراكم حرفيّاً** (السياسة/يوم-مفقود/
لا-صفر-صامت/العتبات كما هي) — هذا الملفّ يضيف فقط: (١) تطبيع يوميّ حتميّ قبل الحساب
(ترتيب canonical + إزالة تكرار صريحة لا ضمنيّة/حسب-الوصول)؛ (٢) غلاف نَسَب تراكميّ
(`gdd_lineage_id` مستقلّ عن آخر يوم) + تغطية مفصولة عن جودة البيانات.

نقيّ حتميّ fail-closed: لا I/O، لا اختلاق، لا gap-filling، لا interpolation. غياب يوم من
النطاق يظهر في التغطية (coverage) لا يُملأ بصفر. **لا نطاق-توسّع:** لا تصحيح معادلة، لا
تغيير عتبات، لا تعريف يوم-زراعيّ جديد، لا إعادة تشكيل عقد GDD القديم.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as _date

from gdd import gdd_agro_product

SERIES_VERSION = "wx10/canonical-daily-weather-series/1.0.0"
GDD_VIEW_OWNER = "weather-service"


def _parse_iso_date(value) -> str | None:
    """يتحقّق أنّ القيمة تاريخ ISO (YYYY-MM-DD) صالح ⇒ يعيد التمثيل القانونيّ، وإلّا None."""
    if not isinstance(value, str):
        return None
    try:
        return _date.fromisoformat(value.strip()).isoformat()
    except (ValueError, TypeError):
        return None


def _day_snapshot_id(date_s: str, t_min, t_max, override: str | None) -> str:
    """هويّة لقطة اليوم: override المُصرَّح به إن وُجد، وإلّا بصمة حتميّة (تاريخ+حرارتان)."""
    if isinstance(override, str) and override:
        return override
    payload = json.dumps(
        {"date": date_s, "t_min_c": t_min, "t_max_c": t_max},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "wday/" + hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()[:16]


def _expected_days_inclusive(start: str | None, end: str | None) -> int | None:
    """عدد الأيّام المتوقّع في [start, end] **شامل الطرفين** (دلالة inclusive محفوظة)."""
    if start is None or end is None:
        return None
    try:
        d0 = _date.fromisoformat(start)
        d1 = _date.fromisoformat(end)
    except ValueError:
        return None
    if d1 < d0:
        return None
    return (d1 - d0).days + 1


def build_canonical_daily_series(
    records: list[dict] | None,
    *,
    timezone: str | None = None,
) -> dict:
    """يبني سلسلة طقس يوميّة canonical من سجلّات خام: تطبيع يوميّ حتميّ **قبل** الحساب.

    المراحل (صريحة، لا ضمنيّة): تحقّق التاريخ → (تطبيع منطقة زمنيّة — مُصرَّح؛ المدخل يوميّ
    مسبقاً فلا إعادة تجميع، حفظاً للسلوك) → **إزالة تكرار حتميّة** (لكلّ تاريخ يُنتقى سجلّ
    واحد بترتيب كلّيّ مستقلّ عن ترتيب الوصول: (source_snapshot_id, t_min, t_max)) →
    **ترتيب canonical** تصاعديّ بالتاريخ. يُصرّح `duplicates_resolved` (لا إسقاط صامت) و
    السجلّات غير الصالحة (تاريخ فاسد).

    كلّ سجلّ: ``{date, t_min_c, t_max_c, weather_snapshot_id?}``.
    """
    by_date: dict[str, list[dict]] = {}
    invalid = 0
    for rec in records or []:
        date_s = _parse_iso_date(rec.get("date")) if isinstance(rec, dict) else None
        if date_s is None:
            invalid += 1
            continue
        t_min = rec.get("t_min_c")
        t_max = rec.get("t_max_c")
        override = rec.get("weather_snapshot_id")
        snap = _day_snapshot_id(date_s, t_min, t_max, override)
        by_date.setdefault(date_s, []).append(
            {"date": date_s, "t_min_c": t_min, "t_max_c": t_max, "source_snapshot_id": snap}
        )

    duplicates_resolved = 0
    ordered: list[dict] = []
    for date_s in sorted(by_date):
        group = by_date[date_s]
        if len(group) > 1:
            duplicates_resolved += len(group) - 1
            # اختيار حتميّ مستقلّ عن ترتيب الوصول: أدنى (snapshot_id, t_min, t_max).
            group = sorted(
                group,
                key=lambda r: (
                    str(r["source_snapshot_id"]),
                    str(r["t_min_c"]),
                    str(r["t_max_c"]),
                ),
            )
        ordered.append(group[0])

    return {
        "series_version": SERIES_VERSION,
        "timezone": timezone,
        "ordered_days": ordered,
        "observed_days": len(ordered),
        "duplicates_resolved": duplicates_resolved,
        "invalid_records": invalid,
    }


def gdd_view(
    series: dict,
    *,
    base_c: float | None,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
    period_start: str | None = None,
    period_end: str | None = None,
    reset_policy: str | None = None,
    kernel_daily_t_min: list | None = None,
    kernel_daily_t_max: list | None = None,
    diagnostics: dict | None = None,
) -> dict:
    """WX-10.4 — منتَج GDD كـ**View تراكميّ مُشتقّ من سلسلة canonical يوميّة**.

    النواة `gdd_agro_product` تحسب حرفيّاً (عقد GDD القديم byte-compatible)؛ هذا الغلاف
    يضيف فقط: **نَسَب تراكميّ** (`gdd_lineage_id` من مُعرّفات لقطات الأيّام المُرتَّبة +
    السياسة + الطريقة + نافذة التراكم + المنطقة الزمنيّة + reset_policy — مستقلّ عن آخر يوم)
    + `contributing_state_ids` + **تغطية مفصولة عن جودة البيانات** (period/expected/observed/
    missing/coverage_ratio). لا يُحتسَب يوم مفقود صفراً؛ لا سلسلة ناقصة تُعطى validated.

    **حفظ byte-compat للطول غير المتطابق:** المسار القديم (بلا daily_dates) يمرّر المصفوفتين
    **الأصليّتين** عبر ``kernel_daily_t_min``/``kernel_daily_t_max`` فترى النواة الأطوال
    الأصليّة ويظهر قيد ``t_min/t_max length mismatch`` كما في العقد القديم. المسار المؤرَّخ
    (canonical) تراها النواة من السلسلة بعد التطبيع/إزالة التكرار.
    """
    ordered = series.get("ordered_days", [])
    dates = [d.get("date") for d in ordered]
    contributing_state_ids = [d.get("source_snapshot_id") for d in ordered]

    # مصفوفتا النواة: الأصليّتان إن مُرِّرتا (المسار القديم — حفظ الطول/القيد)، وإلّا من
    # السلسلة المُطبَّعة (المسار المؤرَّخ).
    if kernel_daily_t_min is not None and kernel_daily_t_max is not None:
        k_tmin, k_tmax = kernel_daily_t_min, kernel_daily_t_max
    else:
        k_tmin = [d.get("t_min_c") for d in ordered]
        k_tmax = [d.get("t_max_c") for d in ordered]

    # النواة — سلطة التراكم حرفيّاً (السياسة/العتبات/يوم-مفقود-غير-محدود/عدم-تطابق-الطول كما هي).
    # period_start/period_end **كما هي** (حتّى None) لحفظ ``valid_period`` القديم byte-compatible.
    legacy = gdd_agro_product(
        daily_t_min=k_tmin,
        daily_t_max=k_tmax,
        base_c=base_c,
        upper_cutoff_c=upper_cutoff_c,
        method=method,
        start_date=period_start,
        end_date=period_end,
    )

    # نافذة التغطية (بُعد مستقلّ عن valid_period): المُصرَّح بها، وإلّا حدود السلسلة المرصودة.
    p_start = period_start or (dates[0] if dates else None)
    p_end = period_end or (dates[-1] if dates else None)

    # التغطية — بُعد مستقلّ عن جودة البيانات: أيّام النطاق الغائبة تماماً (فجوات) ≠ أيّام
    # موجودة بحرارة غير محدودة (تلك في limitations النواة). يوم مفقود لا يُملأ صفراً.
    observed_days = len(ordered)
    expected_days = _expected_days_inclusive(p_start, p_end)
    if expected_days is None:
        expected_days = observed_days
    missing_days = max(0, expected_days - observed_days)
    coverage_ratio = round(observed_days / expected_days, 4) if expected_days else 0.0
    coverage = {
        "period_start": p_start,
        "period_end": p_end,
        "expected_days": expected_days,
        "observed_days": observed_days,
        "missing_days": missing_days,
        "coverage_ratio": coverage_ratio,
        "duplicates_resolved": series.get("duplicates_resolved", 0),
        "inclusive_dates": True,
    }

    # تشخيصات صريحة (لا تمسّ عقد GDD القديم): تُفصح عن أعداد المدخل والإسقاطات كي لا يختفي
    # أيّ سجلّ بصمت — invalid_records (تاريخ فاسد) · unmapped_temperature_pairs (أزواج حرارة
    # لم تُربَط بتاريخ) · أطوال مصفوفات المدخل الأصليّة · عدد التواريخ المُمرَّرة.
    diag = {
        "invalid_records": series.get("invalid_records", 0),
        **(diagnostics or {}),
    }

    # جودة السلسلة = جودة البيانات (النواة) **مُخفَّضة** حين التغطية ناقصة — سلسلة ذات فجوات
    # لا تُعطى validated وإن كانت أيّامها الموجودة صحيحة (تغطية ≠ جودة). حقل جديد لا يمسّ
    # quality_status القديم (byte-compatible).
    legacy_q = legacy.get("quality_status")
    if legacy_q in ("insufficient", "invalid"):
        series_quality = legacy_q
    elif coverage_ratio < 1.0:
        series_quality = "degraded_incomplete_coverage"
    else:
        series_quality = legacy_q  # validated/degraded كما هي حين التغطية كاملة

    # هويّة النَّسَب التراكميّة — مستقلّة عن آخر يوم؛ تتغيّر بأيّ يوم/عتبة/طريقة/نافذة، ولا
    # تتغيّر بإعادة ترتيب المدخل بعد الترتيب القانونيّ (contributing_state_ids مُرتَّبة).
    lineage_payload = json.dumps(
        {
            "ordered_daily_state_ids": contributing_state_ids,
            "crop_configuration": {"base_c": base_c, "upper_cutoff_c": upper_cutoff_c},
            "method": method,
            "accumulation_window": {"period_start": p_start, "period_end": p_end},
            "timezone": series.get("timezone"),
            "reset_policy": reset_policy,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    gdd_lineage_id = (
        "gddseq/" + hashlib.sha1(lineage_payload.encode(), usedforsecurity=False).hexdigest()[:16]
    )

    return {
        **legacy,  # عقد GDD القديم حرفيّاً (byte-compatible)
        "derived_from": "canonical_daily_weather_series",
        "series_version": series.get("series_version", SERIES_VERSION),
        "gdd_lineage_id": gdd_lineage_id,
        "contributing_state_ids": contributing_state_ids,
        "coverage": coverage,
        "diagnostics": diag,
        "series_quality_status": series_quality,
        "timezone": series.get("timezone"),
        "reset_policy": reset_policy,
    }
