"""نشرة حالة المحاصيل الإقليميّة (V66) — تجميع صادق حقل→مديريّة→محافظة، آمن الخصوصيّة.

**الفجوة (تدقيق المرحلة 12 / التقرير الخارجيّ P7+P12):** لا تجميع من مستوى الحقل إلى
المديريّة/المحافظة، ولا نشرة حالة إقليميّة، ولا شذوذ مقابل التاريخ — فقط طبقة معرفة
مديريّات ساكنة (`core/districts`). هذه الوحدة تبني نشرة على نمط GEOGLAM Crop Monitor
(تصنيف حالة: exceptional/favourable/watch/poor) من إشارات حقول مُمرَّرة.

**صدق حاسم (خصوصيّة + لا اختلاق):**
- **أرضيّة خصوصيّة (k-anonymity):** لا يُنشَر تجميع مجموعة تضمّ أقلّ من ``min_fields_privacy``
  حقلاً — تُدرَج مكتومةً بسبب صريح (``suppressed_for_privacy``) بلا أرقام. يمنع استنتاج
  بيانات حقل/مستأجِر مفرد.
- **بلا معرّفات حقول** في المخرَج (تجميعيّ فقط) — لا تسريب هويّات.
- **بلا اختلاق:** التصنيف من شذوذ NDVI مقابل المتوسّط التاريخيّ المُمرَّر؛ الثقة من عدد
  الحقول/المشاهد؛ المجموعة بلا تاريخ كافٍ ⇒ حالة ``unknown`` لا تخمين.

منطق صرف بلا I/O — قابل للاختبار حتميّاً. يستهلك سجلّات الحقول المُمرَّرة فقط (الجلب/RLS
يبقيان في الراوتر/الخدمة؛ التجميع لا يرى إلّا ما يُمرَّر ضمن نطاق المستأجِر).
"""

from __future__ import annotations

from typing import Any

# عتبات تصنيف الحالة على شذوذ NDVI مقابل المتوسّط التاريخيّ (GEOGLAM-style، قابلة للضبط).
_DEFAULT_THRESHOLDS = {
    "exceptional": 0.08,  # ≥ +0.08 ⇒ استثنائيّة
    "favourable": -0.05,  # [−0.05, +0.08) ⇒ مواتية
    "watch": -0.15,  # [−0.15, −0.05) ⇒ مراقبة
    # < −0.15 ⇒ ضعيفة (poor)
}
_MIN_FIELDS_PRIVACY = 5  # أرضيّة k-anonymity الافتراضيّة


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _field_anomaly(field: dict[str, Any]) -> float | None:
    """شذوذ NDVI للحقل: صريح ``ndvi_anomaly`` أو (الحاليّ − المتوسّط التاريخيّ)."""
    direct = _num(field.get("ndvi_anomaly"))
    if direct is not None:
        return direct
    cur = _num(field.get("ndvi_current"))
    hist = _num(field.get("ndvi_historical_mean"))
    if cur is not None and hist is not None:
        return round(cur - hist, 4)
    return None


def classify_condition(anomaly: float | None, thresholds: dict[str, float]) -> str:
    """تصنيف حالة GEOGLAM من الشذوذ. ``None`` ⇒ ``unknown`` (لا تخمين)."""
    if anomaly is None:
        return "unknown"
    if anomaly >= thresholds["exceptional"]:
        return "exceptional"
    if anomaly >= thresholds["favourable"]:
        return "favourable"
    if anomaly >= thresholds["watch"]:
        return "watch"
    return "poor"


def _confidence(n_fields: int, mean_scenes: float, min_fields: int) -> float:
    """ثقة [0,1] من عدد الحقول وكثافة المشاهد — أكثر تغطيةً ⇒ ثقة أعلى."""
    field_factor = min(1.0, n_fields / (min_fields * 3.0))
    scene_factor = min(1.0, mean_scenes / 6.0) if mean_scenes > 0 else 0.5
    return round(field_factor * 0.7 + scene_factor * 0.3, 3)


def _aggregate_group(
    fields: list[dict[str, Any]], min_fields: int, thresholds: dict[str, float]
) -> dict[str, Any]:
    """يجمّع مجموعة حقول (مديريّة أو محافظة) إلى إحصاء حالة — أو يكتمها للخصوصيّة."""
    n_fields = len(fields)
    tenants = {str(f.get("tenant_id")) for f in fields if f.get("tenant_id") is not None}
    if n_fields < min_fields:
        # أرضيّة الخصوصيّة: لا نشر بلا أرقام — كتم صريح (لا تسريب حقل/مستأجِر مفرد).
        return {
            "status": "suppressed_for_privacy",
            "reason": f"fewer_than_{min_fields}_fields",
            "field_count": n_fields,
        }
    anomalies = [a for a in (_field_anomaly(f) for f in fields) if a is not None]
    mean_anomaly = round(sum(anomalies) / len(anomalies), 4) if anomalies else None
    scenes = [s for s in (_num(f.get("scene_count")) for f in fields) if s is not None]
    mean_scenes = sum(scenes) / len(scenes) if scenes else 0.0
    dist = _condition_distribution(fields, thresholds)
    return {
        "status": "published",
        "field_count": n_fields,
        "tenant_count": len(tenants),
        "fields_with_history": len(anomalies),
        "mean_ndvi_anomaly": mean_anomaly,
        "condition": classify_condition(mean_anomaly, thresholds),
        "condition_distribution": dist,
        "confidence": _confidence(n_fields, mean_scenes, min_fields),
    }


def _condition_distribution(
    fields: list[dict[str, Any]], thresholds: dict[str, float]
) -> dict[str, int]:
    counts = {"exceptional": 0, "favourable": 0, "watch": 0, "poor": 0, "unknown": 0}
    for f in fields:
        counts[classify_condition(_field_anomaly(f), thresholds)] += 1
    return counts


def bulletin_rows_to_records(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """يحوّل صفوف DB (``gov``/``field_id``/``ndvi_current``/``ndvi_historical_mean``/
    ``scene_count``) إلى سجلّات النشرة التي يفهمها ``build_regional_bulletin``.

    منطق صرف قابل للاختبار (الاستعلام المُقيَّد بالمستأجِر/RLS يبقى في الراوت). يقبل
    ``gov`` (عمود جدول الحقول) أو ``governorate`` صراحةً. الصفوف بلا محافظة تُهمَل لاحقاً.
    """
    records: list[dict[str, Any]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        records.append(
            {
                "governorate": r.get("gov") or r.get("governorate"),
                "district": r.get("district"),
                "tenant_id": r.get("tenant_id"),
                "field_id": r.get("field_id"),
                "ndvi_current": r.get("ndvi_current"),
                "ndvi_historical_mean": r.get("ndvi_historical_mean"),
                "scene_count": r.get("scene_count"),
            }
        )
    return records


def build_regional_bulletin(
    fields: list[dict[str, Any]],
    *,
    period: str | None = None,
    min_fields_privacy: int = _MIN_FIELDS_PRIVACY,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """يبني نشرة حالة إقليميّة (محافظة → مديريّات) من سجلّات حقول مُمرَّرة.

    كلّ سجلّ: ``{governorate, district, tenant_id, ndvi_anomaly | (ndvi_current +
    ndvi_historical_mean), scene_count?}``. المجموعات دون أرضيّة الخصوصيّة تُكتَم بصدق.
    """
    th = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
    valid = [f for f in fields if isinstance(f, dict) and f.get("governorate")]

    by_gov: dict[str, list[dict[str, Any]]] = {}
    for f in valid:
        by_gov.setdefault(str(f.get("governorate")), []).append(f)

    governorates: list[dict[str, Any]] = []
    published_count = 0
    suppressed_count = 0
    for gov in sorted(by_gov):
        gov_fields = by_gov[gov]
        by_dist: dict[str, list[dict[str, Any]]] = {}
        for f in gov_fields:
            by_dist.setdefault(str(f.get("district") or "unknown"), []).append(f)
        districts = []
        for dist in sorted(by_dist):
            agg = _aggregate_group(by_dist[dist], min_fields_privacy, th)
            districts.append({"district": dist, **agg})
        gov_agg = _aggregate_group(gov_fields, min_fields_privacy, th)
        if gov_agg["status"] == "published":
            published_count += 1
        else:
            suppressed_count += 1
        governorates.append({"governorate": gov, **gov_agg, "districts": districts})

    return {
        "schema": "sahool.regional_bulletin/1",
        "period": period,
        "privacy_floor_fields": min_fields_privacy,
        "total_fields": len(valid),
        "governorate_count": len(governorates),
        "published_governorates": published_count,
        "suppressed_governorates": suppressed_count,
        "governorates": governorates,
        "note_ar": (
            "نشرة تجميعيّة على نمط GEOGLAM — المجموعات دون أرضيّة الخصوصيّة مكتومة بلا أرقام؛ "
            "لا معرّفات حقول؛ التصنيف من شذوذ NDVI مقابل المتوسّط التاريخيّ (لا تخمين للمجموعة الفارغة)."
        ),
    }
