"""api/analytics_shapers.py — مُشكِّلات التقارير ولوحة المؤشّرات — تفكيك B1.

دوالّ تشكيل نقيّة (لا قاعدة، لا I/O) تحوّل صفوف التجميع (COUNT/SUM/GROUP BY)
إلى أجسام استجابة الواجهة: ملخّص المزرعة + المساحة حسب المحصول + كتالوج المؤشّرات
+ لوحة المؤشّرات المُجمَّعة. مُستخرَجة من الوحدة الضخمة ``api/main.py`` (نمط B1)؛
يستهلكها ``routers/reports`` و``routers/indicators`` والاختبارات مباشرةً. قابلة
للاختبار offline (CI-enforced). التبعيّة الوحيدة ``_row_to_alert`` من ``api.alert_models``
(وحدة أوراق نقيّة) — بلا اعتماد على ``api.main``.
"""

from __future__ import annotations

from api.alert_models import _row_to_alert


def _count_by_key(rows, key: str) -> dict[str, int]:
    """صفوف GROUP BY ({key, count}) → قاموس {قيمة: عدد}.

    دالّة نقيّة (لا قاعدة): تتجاهل القيم None (تجمعها تحت 'unknown')، وتحوّل
    العدّ إلى int. تُعاد استخدامها لتجميع العمليّات حسب الحالة/النوع.
    """
    out: dict[str, int] = {}
    for r in rows:
        raw = r[key]
        label = str(raw) if raw is not None else "unknown"
        out[label] = out.get(label, 0) + int(r["count"] or 0)
    return out


def _shape_area_by_crop(rows) -> list[dict]:
    """صفوف ({crop, total_area_ha}) → قائمة مُرتّبة تنازليّاً بالمساحة.

    دالّة نقيّة: المحصول None/فارغ ⇒ 'غير محدّد'، المساحة → float مُدوّرة (٢ منزلة).
    تُغذّي مخطّط «المساحة حسب المحصول» في الواجهة.
    """
    shaped = [
        {
            "crop": (r["crop"] or "غير محدّد"),
            "area_ha": round(float(r["total_area_ha"] or 0), 2),
        }
        for r in rows
    ]
    shaped.sort(key=lambda x: x["area_ha"], reverse=True)
    return shaped


def _shape_farm_summary(
    *,
    farms_count: int,
    fields_count: int,
    total_area_ha,
    active_seasons_count: int,
    activities_by_status: dict[str, int],
    open_alerts_count: int,
    area_by_crop: list[dict],
) -> dict:
    """يبني جسم ملخّص المزرعة من العدّادات المُجمَّعة — نقيّ (لا قاعدة).

    يُطبّع المساحة إلى float (٢ منزلة) ويضمن أعداداً صحيحة موجبة. activities_total
    مُشتقّ من مجموع القاموس كي يطابق التفصيل (مصدر واحد للحقيقة).
    """
    return {
        "farms_count": int(farms_count or 0),
        "fields_count": int(fields_count or 0),
        "total_area_ha": round(float(total_area_ha or 0), 2),
        "active_seasons_count": int(active_seasons_count or 0),
        "activities_total": sum(activities_by_status.values()),
        "activities_by_status": activities_by_status,
        "open_alerts_count": int(open_alerts_count or 0),
        "area_by_crop": area_by_crop,
    }


# كتالوج المؤشّرات التي تحسبها المنصّة فعلاً (مصدر كلٍّ موثّق بصدق). ليس 33
# مؤشّراً مُلفَّقاً — بل ما هو مُنفَّذ ومخدوم عبر خدمات حقيقيّة (vegetation/raster
# للطيفيّة، weather للمناخيّة، soil للتربة). الواجهة تعرضه كدليل + فلترة بالفئة.
# renderable=True ⇒ طبقة بلاطات/شبكة مكانيّة يرسمها raster-service (band_math)
# فتظهر في مبدّل طبقات الخريطة. renderable=False ⇒ قيمة قياسيّة (طقس/تربة) غير
# مكانيّة (لا تُرسَم كطبقة) — مرجعيّة فقط. الواجهة تقود مبدّل الخريطة بـrenderable
# لا بقائمة مُبرمَجة (مصدر حقيقة واحد). كلّ renderable مؤكَّد في raster band_math.
_INDICATOR_CATALOG: list[dict] = [
    {
        "id": "ndvi",
        "category": "vegetation",
        "name_ar": "NDVI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "evi",
        "category": "vegetation",
        "name_ar": "EVI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "ndre",
        "category": "vegetation",
        "name_ar": "NDRE",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "msavi",
        "category": "vegetation",
        "name_ar": "MSAVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "savi",
        "category": "vegetation",
        "name_ar": "SAVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "gndvi",
        "category": "vegetation",
        "name_ar": "GNDVI",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "ndwi",
        "category": "water",
        "name_ar": "NDWI",
        "unit": "",
        "source": "raster-service / vegetation-service",
        "renderable": True,
    },
    {
        "id": "ndmi",
        "category": "water",
        "name_ar": "NDMI (الرطوبة)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "msi",
        "category": "water",
        "name_ar": "MSI (الإجهاد المائي)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "et0",
        "category": "water",
        "name_ar": "ET₀",
        "unit": "mm/d",
        "source": "weather-service (FAO-56)",
        "renderable": False,
    },
    {
        "id": "water_deficit",
        "category": "water",
        "name_ar": "عجز المياه",
        "unit": "mm",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "gdd",
        "category": "weather",
        "name_ar": "GDD المتراكم",
        "unit": "°C·يوم",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "temperature",
        "category": "weather",
        "name_ar": "الحرارة",
        "unit": "°C",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "humidity",
        "category": "weather",
        "name_ar": "الرطوبة النسبيّة",
        "unit": "%",
        "source": "weather-service",
        "renderable": False,
    },
    {
        "id": "salinity",
        "category": "soil",
        "name_ar": "الملوحة (SI)",
        "unit": "",
        "source": "raster-service",
        "renderable": True,
    },
    {
        "id": "soil_ph",
        "category": "soil",
        "name_ar": "pH التربة",
        "unit": "",
        "source": "soil-service",
        "renderable": False,
    },
    {
        "id": "soil_ec",
        "category": "soil",
        "name_ar": "EC التربة",
        "unit": "dS/m",
        "source": "soil-service",
        "renderable": False,
    },
    {
        "id": "nitrogen",
        "category": "soil",
        "name_ar": "النيتروجين المتاح",
        "unit": "mg/kg",
        "source": "soil-service",
        "renderable": False,
    },
]


def _shape_indicator_catalog() -> dict:
    """يبني جسم الكتالوج من _INDICATOR_CATALOG — نقيّ (لا قاعدة).

    يحسب categories = {فئة: عدد} ليطابق ما تتوقّعه الواجهة (total + categories).
    """
    categories: dict[str, int] = {}
    for ind in _INDICATOR_CATALOG:
        cat = ind["category"]
        categories[cat] = categories.get(cat, 0) + 1
    renderable_total = sum(1 for ind in _INDICATOR_CATALOG if ind.get("renderable"))
    return {
        "total": len(_INDICATOR_CATALOG),
        "renderable_total": renderable_total,
        "categories": categories,
        "indicators": _INDICATOR_CATALOG,
        "note_ar": "المؤشّرات المُنفَّذة فعلاً ومصادرها — لا قيم مُلفَّقة. "
        "renderable=طبقة بلاطات مكانيّة (تظهر في مبدّل الخريطة)؛ غيرها قيمة قياسيّة مرجعيّة.",
    }


def _shape_indicators_dashboard(
    *,
    fields_rows,
    active_field_ids: set[str],
    alert_rows,
) -> dict:
    """يبني لوحة المؤشّرات المُجمَّعة من صفوف الحقول/المواسم/التنبيهات — نقيّ.

    - fields_summary: صفّ لكلّ حقل (id/name/crop/area + has_active_season).
    - kpis: عدّادات حقيقيّة (إجماليّ الحقول/المساحة/الحقول النشطة/التنبيهات المفتوحة).
      لا NDVI مخترع — قيم المؤشّرات الطيفيّة تأتي من vegetation/raster لكلّ حقل.
    - alerts: قائمة التنبيهات النشطة كما هي (تُمرَّر للّوحة بلا تلفيق).
    """
    import json as _json

    fields_summary = []
    total_area = 0.0
    for r in fields_rows:
        area = float(r["area_ha"]) if r["area_ha"] is not None else 0.0
        total_area += area
        # geometry (GeoJSON) يُمرَّر كما هو ليرسم العميل (موبايل/ويب) حدّ الحقل
        # ويضبط مركز/تكبير الخريطة على حقل المستخدم. JSONB قد يعود نصّاً ⇒ نفكّه.
        # غيابه لا يكسر شيئاً: العميل يحرس على غياب geometry (حقل اختياريّ).
        geom = None
        try:
            geom = r["geometry"]
        except (KeyError, IndexError):
            geom = None
        if isinstance(geom, str):
            try:
                geom = _json.loads(geom)
            except (ValueError, TypeError):
                geom = None
        fields_summary.append(
            {
                "field_id": r["field_id"],
                "field_name": r["name"],
                "crop": r["crop"],
                "area_ha": round(area, 2),
                "has_active_season": r["field_id"] in active_field_ids,
                "geometry": geom,
            }
        )
    active_count = len(active_field_ids)
    kpis = [
        {
            "id": "fields_total",
            "category": "operations",
            "name_ar": "إجماليّ الحقول",
            "value": len(fields_summary),
            "unit": "حقل",
            "status": "good",
        },
        {
            "id": "area_total",
            "category": "operations",
            "name_ar": "إجماليّ المساحة",
            "value": round(total_area, 2),
            "unit": "هـ",
            "status": "good",
        },
        {
            "id": "active_seasons",
            "category": "operations",
            "name_ar": "حقول بموسم نشط",
            "value": active_count,
            "unit": "حقل",
            "status": "good" if active_count else "fair",
        },
        {
            "id": "open_alerts",
            "category": "operations",
            "name_ar": "تنبيهات مفتوحة",
            "value": len(alert_rows),
            "unit": "تنبيه",
            "status": "critical" if alert_rows else "good",
        },
    ]
    return {
        "kpis": kpis,
        "alerts": [_row_to_alert(r).model_dump() for r in alert_rows],
        "fields_summary": fields_summary,
        "note_ar": "عدّادات حيّة من جداولك — المؤشّرات الطيفيّة لكلّ حقل من شاشة الأقمار.",
    }
