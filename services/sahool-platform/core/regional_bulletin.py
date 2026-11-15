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
_MIN_FIELDS_PRIVACY = 5  # أرضيّة k-anonymity — حدّ أدنى يفرضه الخادم، لا افتراضيّ يُخفَّض
MIN_FIELDS_PRIVACY = _MIN_FIELDS_PRIVACY


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


def effective_privacy_floor(requested: Any) -> int:
    """The k actually applied: a caller may raise the floor, never lower it below the server's.

    The route used to accept ``min_fields_privacy=1`` and pass it straight through, so the
    k-anonymity floor was whatever the caller asked for (RFC R3 DS-R01)."""
    if isinstance(requested, bool):
        return _MIN_FIELDS_PRIVACY
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return _MIN_FIELDS_PRIVACY
    return max(_MIN_FIELDS_PRIVACY, value)


def _suppressed() -> dict[str, Any]:
    # No number of any kind: neither the group's field count nor the floor in the reason text,
    # both of which used to be returned (RFC R3 DS-R02).
    return {"status": "suppressed_for_privacy", "reason": "below_privacy_floor"}


def _aggregate_group(
    fields: list[dict[str, Any]], min_fields: int, thresholds: dict[str, float]
) -> dict[str, Any]:
    """يجمّع مجموعة حقول (مديريّة أو محافظة) إلى إحصاء حالة — أو يكتمها للخصوصيّة."""
    n_fields = len(fields)
    if n_fields < min_fields:
        return _suppressed()
    anomalies = [a for a in (_field_anomaly(f) for f in fields) if a is not None]
    mean_anomaly = round(sum(anomalies) / len(anomalies), 4) if anomalies else None
    scenes = [s for s in (_num(f.get("scene_count")) for f in fields) if s is not None]
    mean_scenes = sum(scenes) / len(scenes) if scenes else 0.0
    dist = _condition_distribution(fields, thresholds)
    return {
        "status": "published",
        "field_count": n_fields,
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
    k = effective_privacy_floor(min_fields_privacy)
    valid = [f for f in fields if isinstance(f, dict) and f.get("governorate")]

    by_gov: dict[str, list[dict[str, Any]]] = {}
    for f in valid:
        by_gov.setdefault(str(f.get("governorate")), []).append(f)

    governorates: list[dict[str, Any]] = []
    gov_sizes: list[int] = []
    for gov in sorted(by_gov):
        gov_fields = by_gov[gov]
        gov_agg = _aggregate_group(gov_fields, k, th)
        governorates.append(
            {"governorate": gov, **gov_agg, **_district_breakdown(gov_fields, k, th)}
        )
        gov_sizes.append(len(gov_fields))
    # A published total minus the published governorates would give the suppressed ones'
    # combined size, so the governorates get the same complementary suppression as districts.
    _complementary_suppression(governorates, gov_sizes, k)
    published_count = sum(1 for g in governorates if g["status"] == "published")

    return {
        "schema": "sahool.regional_bulletin/1",
        "period": period,
        # Honest about time: every NDVI scene stored for the field is used, whatever the period
        # label says. A real temporal filter is a separate change (RFC R3 DS-R03).
        "period_applied_as_filter": False,
        "privacy_floor_fields": k,
        "total_fields": len(valid) if len(valid) >= k else None,
        "governorate_count": len(governorates),
        "published_governorates": published_count,
        "suppressed_governorates": len(governorates) - published_count,
        "governorates": governorates,
        "note_ar": (
            "نشرة تجميعيّة على نمط GEOGLAM — المجموعات دون أرضيّة الخصوصيّة مكتومة بلا أرقام، "
            "وتُكتَم مجموعة مجاورة عند الحاجة كي لا يُستنتَج المكتوم بالطرح؛ لا معرّفات حقول؛ "
            "التصنيف من شذوذ NDVI مقابل المتوسّط التاريخيّ لكلّ المشاهد المخزَّنة (وسم الفترة لا "
            "يرشّح زمنيّاً بعد)؛ لا تخمين للمجموعة الفارغة."
        ),
    }


def _complementary_suppression(groups: list[dict[str, Any]], sizes: list[int], k: int) -> None:
    """Suppress further groups until the suppressed ones together hold 0 or at least k fields.

    Otherwise a parent's published figures minus its published children reveal the suppressed
    children: their combined count, and their condition classes through the distribution
    (RFC R3 DS-R02). The smallest published groups go first. Mutates ``groups`` in place."""
    suppressed = sum(n for g, n in zip(groups, sizes, strict=True) if g["status"] != "published")
    if suppressed == 0:
        return
    published = sorted(
        (i for i, g in enumerate(groups) if g["status"] == "published"), key=lambda i: sizes[i]
    )
    for i in published:
        if suppressed >= k:
            break
        is_governorate = "districts" in groups[i]
        identity = {
            key: groups[i][key]
            for key in ("governorate", "district", "unmapped")
            if key in groups[i]
        }
        groups[i] = {**identity, **_suppressed()}
        if is_governorate:
            # A governorate suppressed for its neighbours' sake must not keep publishing its
            # districts either, or their sum would restore its figures.
            groups[i]["districts"] = []
            groups[i]["district_breakdown"] = "suppressed_with_parent"
        suppressed += sizes[i]


def _district_breakdown(
    gov_fields: list[dict[str, Any]], k: int, thresholds: dict[str, float]
) -> dict[str, Any]:
    """Districts of one governorate, with complementary suppression.

    Fields without a district are not published as a district called "unknown", which looked
    like a real place (RFC R3 DS-R04). If no field has a district, there is no breakdown."""
    mapped = [f for f in gov_fields if f.get("district")]
    if not mapped:
        return {"districts": [], "district_breakdown": "unavailable_no_district_mapping"}
    by_dist: dict[str, list[dict[str, Any]]] = {}
    for f in mapped:
        by_dist.setdefault(str(f.get("district")), []).append(f)
    names = sorted(by_dist)
    groups = [{"district": d, **_aggregate_group(by_dist[d], k, thresholds)} for d in names]
    sizes = [len(by_dist[d]) for d in names]
    unmapped = len(gov_fields) - len(mapped)
    if unmapped:
        # The unmapped remainder is a group in its own right for the subtraction argument.
        groups.append(
            {
                "district": None,
                "unmapped": True,
                **_aggregate_group([f for f in gov_fields if not f.get("district")], k, thresholds),
            }
        )
        sizes.append(unmapped)
    _complementary_suppression(groups, sizes, k)
    return {"districts": groups, "district_breakdown": "available"}
