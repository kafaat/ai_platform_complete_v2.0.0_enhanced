"""
api/geo_zone_locator.py — تحديد الإقليم المناخي من إحداثيّات الحقل (GPS)

جانب جوهري: المزارع يحدّد موقع حقله على الخريطة (أو من GPS الهاتف) → النظام
يحدّد آليّاً: المحافظة، الإقليم المناخي-الزراعي، والمناخ السائد، دون إدخال يدوي.

كيف يعمل (منهجيّة هجينة موثّقة):
  ١) صناديق إحداثيّة (bounding boxes) للمحافظات اليمنيّة (من بيانات الحدود
     الإداريّة — Humanitarian Data Exchange / FAO GeoNetwork)
  ٢) الارتفاع (elevation) هو المُرجّح الحاسم — المناخ دالّة الارتفاع لا الموقع
     الأفقي وحده (تعز تثبت ذلك: مديريّاتها 486م-1734م)
  ٣) دمج المحافظة + الارتفاع → الإقليم الدقيق عبر agro_climate_zones

المصادر:
  • FAO GAEZ (الأقاليم الإيكولوجيّة-الزراعيّة) + FAO GeoNetwork (حدود إداريّة)
  • وزارة الزراعة والريّ اليمنيّة + مركز بحوث الموارد الطبيعيّة (ذمار)
  • Humanitarian Data Exchange (حدود اليمن الإداريّة) + إحداثيّات موثّقة

⚠ الصناديق الإحداثيّة تقريبيّة (مستطيلات لا حدوداً دقيقة) — قد تتداخل عند
الأطراف. الارتفاع يحسم. للحدود الدقيقة: تكامل مع طبقة PostGIS الفعليّة
(ST_Contains على مضلّعات الحدود الرسميّة) في النشر. توجّه لا يفرض.
"""

from __future__ import annotations

from api.agro_climate_zones import zone_by_elevation, zone_profile

# ─── صناديق إحداثيّة تقريبيّة للمحافظات (lat_min, lat_max, lon_min, lon_max) ──
# مرتّبة بحيث تُفحص المحافظات الأصغر/الأدقّ أوّلاً. إحداثيّات من بيانات موثّقة.
_GOVERNORATE_BOXES: list[dict] = [
    # ── الساحل الغربي (تهامة) ──
    {
        "gov_ar": "الحديدة",
        "box": (13.5, 16.5, 42.5, 43.9),
        "default_zone": "tihama",
        "elevation_hint_m": 50,
    },
    # ── الساحل الجنوبي ──
    {
        "gov_ar": "عدن",
        "box": (12.7, 13.1, 44.8, 45.2),
        "default_zone": "southern_coast",
        "elevation_hint_m": 10,
    },
    {
        "gov_ar": "أبين",
        "box": (13.0, 14.3, 44.8, 46.6),
        "default_zone": "southern_coast",
        "elevation_hint_m": 100,
    },
    {
        "gov_ar": "لحج",
        "box": (12.9, 13.9, 44.2, 45.4),
        "default_zone": "southern_coast",
        "elevation_hint_m": 200,
        "multi_zone": True,
    },
    {
        "gov_ar": "المهرة",
        "box": (14.0, 17.5, 51.0, 53.1),
        "default_zone": "southern_coast",
        "elevation_hint_m": 100,
    },
    # ── المرتفعات الغربيّة الممطرة ──
    {
        "gov_ar": "تعز",
        "box": (13.2, 14.1, 43.0, 44.3),
        "default_zone": "western_highlands",
        "elevation_hint_m": 1400,
        "multi_zone": True,
    },
    {
        "gov_ar": "إب",
        "box": (13.8, 14.5, 43.7, 44.4),
        "default_zone": "western_highlands",
        "elevation_hint_m": 2000,
    },
    {
        "gov_ar": "ريمة",
        "box": (14.4, 14.9, 43.3, 43.8),
        "default_zone": "western_highlands",
        "elevation_hint_m": 1800,
    },
    {
        "gov_ar": "المحويت",
        "box": (15.0, 15.7, 43.3, 43.9),
        "default_zone": "western_highlands",
        "elevation_hint_m": 2000,
    },
    # ── المرتفعات الوسطى (الهضبة الداخليّة) ──
    {
        "gov_ar": "صنعاء",
        "box": (14.9, 16.2, 43.7, 44.7),
        "default_zone": "central_highlands",
        "elevation_hint_m": 2300,
    },
    {
        "gov_ar": "أمانة العاصمة",
        "box": (15.2, 15.5, 44.1, 44.3),
        "default_zone": "central_highlands",
        "elevation_hint_m": 2250,
    },
    {
        "gov_ar": "ذمار",
        "box": (14.3, 15.0, 43.9, 44.7),
        "default_zone": "central_highlands",
        "elevation_hint_m": 2400,
    },
    {
        "gov_ar": "عمران",
        "box": (15.5, 16.5, 43.6, 44.4),
        "default_zone": "central_highlands",
        "elevation_hint_m": 2200,
    },
    {
        "gov_ar": "صعدة",
        "box": (16.3, 17.5, 43.2, 44.4),
        "default_zone": "central_highlands",
        "elevation_hint_m": 1800,
    },
    {
        "gov_ar": "البيضاء",
        "box": (13.6, 14.8, 44.5, 45.9),
        "default_zone": "central_highlands",
        "elevation_hint_m": 2000,
    },
    {
        "gov_ar": "الضالع",
        "box": (13.4, 14.2, 44.4, 45.0),
        "default_zone": "central_highlands",
        "elevation_hint_m": 1500,
    },
    {
        "gov_ar": "حجة",
        "box": (15.5, 16.8, 42.8, 43.8),
        "default_zone": "western_highlands",
        "elevation_hint_m": 1700,
        "multi_zone": True,
    },
    # ── الهضبة الشرقيّة شبه الصحراويّة ──
    {
        "gov_ar": "حضرموت",
        "box": (14.0, 19.0, 47.0, 51.5),
        "default_zone": "eastern_plateau",
        "elevation_hint_m": 900,
        "multi_zone": True,
    },
    {
        "gov_ar": "شبوة",
        "box": (13.8, 16.2, 45.5, 47.5),
        "default_zone": "eastern_plateau",
        "elevation_hint_m": 900,
        "multi_zone": True,
    },
    # ── الصحراء الداخليّة ──
    {
        "gov_ar": "مأرب",
        "box": (15.0, 15.9, 44.9, 46.3),
        "default_zone": "inland_desert",
        "elevation_hint_m": 1000,
    },
    {
        "gov_ar": "الجوف",
        "box": (15.9, 17.8, 44.3, 46.5),
        "default_zone": "inland_desert",
        "elevation_hint_m": 1100,
    },
]

# عتبات ارتفاع لترجيح الإقليم (متّسقة مع zone_by_elevation)
_ELEV_COASTAL_MAX = 300  # ≤300م → ساحلي
_ELEV_LOWLAND_MAX = 1000  # ≤1000م → صحراء/هضبة منخفضة
_ELEV_PLATEAU_MAX = 1500  # ≤1500م → هضبة شرقيّة
# >1500م → مرتفعات


def _point_in_box(lat: float, lon: float, box: tuple) -> bool:
    lat_min, lat_max, lon_min, lon_max = box
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _is_western(lon: float) -> bool:
    """الجهة الغربيّة (المرتفعات الممطرة) مقابل الوسطى/الشرقيّة. ~44.5° فاصل تقريبي."""
    return lon < 44.5


def locate_field(lat: float, lon: float, elevation_m: float | None = None) -> dict:
    """يحدّد المحافظة + الإقليم المناخي + المناخ من إحداثيّات الحقل.

    elevation_m اختياري لكن يُنصح به بشدّة (يحسم التصنيف في المحافظات الجبليّة).
    """
    # تحقّق أنّ الإحداثيّات داخل اليمن تقريباً
    if not (12.0 <= lat <= 19.5 and 42.0 <= lon <= 54.5):
        return {
            "supported": False,
            "message_ar": (
                f"الإحداثيّات ({lat:.3f}, {lon:.3f}) خارج حدود اليمن التقريبيّة. "
                "تأكّد من الموقع (خط العرض 12-19.5، الطول 42-54.5)."
            ),
        }

    # ابحث عن المحافظة المطابقة
    matched = [g for g in _GOVERNORATE_BOXES if _point_in_box(lat, lon, g["box"])]

    gov_ar = None
    is_multi = False
    default_zone = None
    if matched:
        # لو تطابقت أكثر من محافظة (تداخل أطراف)، خذ الأصغر صندوقاً (الأدقّ)
        def box_area(g):
            b = g["box"]
            return (b[1] - b[0]) * (b[3] - b[2])

        best = min(matched, key=box_area)
        gov_ar = best["gov_ar"]
        is_multi = best.get("multi_zone", False)
        default_zone = best["default_zone"]

    # حدّد الإقليم: الارتفاع يحسم إن توفّر، وإلّا الافتراضي حسب المحافظة
    # الجهة الغربيّة الممطرة تُحدَّد بالمحافظة المطابقة لا بخطّ الطول وحده
    # (صنعاء عند 44.2° داخليّة وسطى رغم أنّها غرب 44.5)
    western_govs = {"تعز", "إب", "ريمة", "المحويت", "حجة", "الحديدة"}
    is_western_region = (gov_ar in western_govs) if gov_ar else _is_western(lon)

    if elevation_m is not None:
        # في المدى الملتبس (300-1500م) نُرجّح إقليم المحافظة الافتراضي إن عُرفت
        # (يميّز هضبة حضرموت الشرقيّة عن صحراء الجوف، وكلاهما ~700-1000م).
        # للمحافظات متعدّدة الأقاليم: نقبل الافتراضي فقط إن لم يكن ساحليّاً
        # (الساحل يُحسم بالارتفاع المنخفض ≤300 أصلاً).
        ambiguous = 300 < elevation_m <= 1500
        if ambiguous and default_zone:
            zone_result = zone_profile(default_zone)
            zone_source_ar = f"موقع المحافظة ({gov_ar}) + ارتفاع {elevation_m:.0f}م"
        else:
            zone_result = zone_by_elevation(elevation_m, is_western=is_western_region)
            zone_source_ar = f"الارتفاع {elevation_m:.0f}م (الأدقّ)"
    elif default_zone:
        zone_result = zone_profile(default_zone)
        zone_source_ar = f"موقع المحافظة ({gov_ar})"
    else:
        # داخل اليمن لكن خارج الصناديق المعرّفة — رجّح بالإحداثيّات فقط
        # شرق 47° = صحراء/هضبة شرقيّة، غرب = نرجّح بالعرض
        if lon >= 47:
            zone_result = zone_profile("eastern_plateau")
        elif lat <= 13.5:
            zone_result = zone_profile("southern_coast")
        else:
            zone_result = zone_profile("inland_desert")
        zone_source_ar = "تقدير بالإحداثيّات (خارج المحافظات المعرّفة)"

    out = {
        "supported": True,
        "coordinates": {"lat": lat, "lon": lon},
        "elevation_m": elevation_m,
        "governorate_ar": gov_ar or "غير محدّدة بدقّة",
        "zone_source_ar": zone_source_ar,
        "zone": zone_result.get("zone"),
        "zone_name_ar": zone_result.get("name_ar"),
        "climate_ar": zone_result.get("climate_ar"),
        "temp_range_c": zone_result.get("temp_range_c"),
        "annual_rain_mm": zone_result.get("annual_rain_mm"),
        "humidity_pct": zone_result.get("humidity_pct"),
        "water_source_ar": zone_result.get("water_source_ar"),
        "suited_crops_ar": zone_result.get("suited_crops_ar"),
        "avoid_ar": zone_result.get("avoid_ar"),
        "yemen_note_ar": zone_result.get("yemen_note_ar"),
    }

    # تنبيه صادق للمحافظات متعدّدة الأقاليم بلا ارتفاع
    if is_multi and elevation_m is None:
        out["multi_zone_warning_ar"] = (
            f"⚠ محافظة {gov_ar} تمتدّ عبر أكثر من إقليم مناخي (ساحل/مرتفعات). "
            "التصنيف الحالي تقريبي — أضف ارتفاع الحقل (من GPS) للدقّة الحاسمة."
        )

    out["disclaimer_ar"] = (
        "التحديد من صناديق إحداثيّة تقريبيّة + الارتفاع. الحدود الدقيقة تحتاج "
        "طبقة PostGIS رسميّة (ST_Contains). أكّد بمعرفتك بمنطقتك."
    )
    out["source_ar"] = (
        "FAO GAEZ + GeoNetwork (حدود إداريّة) + وزارة الزراعة والريّ اليمنيّة "
        "(مركز بحوث الموارد بذمار) + Humanitarian Data Exchange."
    )
    return out


def locate_and_recommend(lat: float, lon: float, elevation_m: float | None = None) -> dict:
    """تحديد الموقع + توصية مباشرة بالمحاصيل الملائمة (تدفّق كامل للمزارع)."""
    loc = locate_field(lat, lon, elevation_m)
    if not loc.get("supported"):
        return loc
    rain_max = (loc.get("annual_rain_mm") or [0, 0])[1]
    rainfed = rain_max >= 400
    # ربط المناطق المشابهة (للصحراء الداخليّة فقط)
    from api.climate_analogs import analogs_for_zone

    analogs = analogs_for_zone(loc.get("zone") or "")
    return {
        **loc,
        "recommendation_ar": {
            "suited_crops_ar": loc.get("suited_crops_ar"),
            "avoid_ar": loc.get("avoid_ar"),
            "rainfed_possible": rainfed,
            "water_note_ar": (
                "زراعة بعليّة ممكنة (أمطار كافية)."
                if rainfed
                else "زراعة مرويّة ضروريّة — راجع وحدتي حصاد المياه وحساسيّة الريّ."
            ),
            "global_analogs_ar": analogs if analogs.get("applicable") else None,
            "next_step_ar": (
                "افحص ملاءمة حقلك المحدّد (تربة/ملوحة) عبر محرّك الملاءمة، ثمّ "
                "قدّر الجدوى الاقتصاديّة قبل القرار."
            ),
        },
    }
