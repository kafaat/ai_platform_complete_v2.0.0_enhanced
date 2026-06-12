"""core/engines/dem_enrichment.py — إثراء تضاريسيّ من نموذج الارتفاع الرقمي (DEM).

الفكرة (بند مؤجَّل في POST_DEPLOYMENT_ROADMAP — «الإثراء الجغرافي التلقائي»):
بعد رسم الحقل، تُملأ elevation/slope/aspect (أعمدة v37 الموجودة) من DEM، ثمّ
تُترجَم إلى دلالة زراعيّة (تدريج/انجراف/صقيع/تعرّض شمسي/صرف). هذا المكوّن هو
**النواة الحتميّة النقيّة** لذلك: يحسب ويصنّف ويفسّر — قابل للتحقّق بالكامل offline.

⚠ المبدأ (اتّساقاً مع مبادئ المنصّة):
  • حتمي بالكامل: معادلات تضاريس قياسيّة (Horn) + عتبات صريحة موثّقة — لا نموذج
  • طبقة **استرشاديّة/عرض**: تصف الأرض وتقترح، لا تفرض قراراً
  • صادق عند نقص المُدخل: بلا DEM لا اختراع — يُعلَن «غير متاح»
  • سياق اليمن: نصف الكرة الشماليّ (المنحدر الجنوبي أكثر شمساً)، أرض مدرَّجة

⚠ جلب DEM الحيّ (SRTM/Copernicus/Sentinel-Hub) خارج هذا المكوّن (يحتاج شبكة/مزوّد)
— هنا فقط الرياضيّات والتصنيف والتفسير على قيم مُعطاة (مقيسة أو مُدخَلة يدويّاً).
"""

from __future__ import annotations

import math

# ── عتبات المنحدر (٪) — سياق الزراعة المدرَّجة اليمنيّة ──────────────────
SLOPE_FLAT = 2.0  # < 2 ⇒ منبسط (لا تدريج؛ قد يحتاج صرفاً)
SLOPE_GENTLE = 8.0  # 2–8 = لطيف (تدابير خفيفة)
SLOPE_MODERATE = 15.0  # 8–15 = متوسّط (تدريج كنتوري يُنصح)
SLOPE_STEEP = 30.0  # 15–30 = شديد (تدريج ضروري، انجراف عالٍ)
# > 30 = شديد جدّاً (هامشي، تدريج مكثّف/تجنّب الحرث)

# ── نطاقات الارتفاع (م) — أقاليم اليمن الرأسيّة ─────────────────────────
ELEV_COASTAL = 500.0  # تهامة/ساحل — حارّ، بلا صقيع
ELEV_FOOTHILL = 1500.0  # سفوح
ELEV_MIDLAND = 2200.0  # هضبة وسطى
# > 2200 = مرتفعات (صقيع شتويّ محتمل، بنّ/معتدلات)

_COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_COMPASS_AR = {
    "N": "شمالي",
    "NE": "شمالي شرقي",
    "E": "شرقي",
    "SE": "جنوبي شرقي",
    "S": "جنوبي",
    "SW": "جنوبي غربي",
    "W": "غربي",
    "NW": "شمالي غربي",
    "FLAT": "منبسط",
}


def classify_slope(slope_pct: float | None) -> dict:
    """يصنّف المنحدر إلى فئة + دلالة انجراف/تدريج (حتمي)."""
    if slope_pct is None or slope_pct < 0:
        return {"class": "unknown", "class_ar": "غير معروف", "note_ar": "لا قيمة منحدر."}
    if slope_pct < SLOPE_FLAT:
        cls, ar = "flat", "منبسط"
        note = "أرض شبه مستوية — لا حاجة للتدريج؛ انتبه للصرف وتجمّع المياه."
    elif slope_pct < SLOPE_GENTLE:
        cls, ar = "gentle", "لطيف"
        note = "ميل لطيف — زراعة كنتوريّة كافية غالباً؛ انجراف منخفض."
    elif slope_pct < SLOPE_MODERATE:
        cls, ar = "moderate", "متوسّط"
        note = "ميل متوسّط — يُنصح بالتدريج/الخطوط الكنتوريّة لكبح الانجراف."
    elif slope_pct < SLOPE_STEEP:
        cls, ar = "steep", "شديد"
        note = "ميل شديد — التدريج ضروري؛ خطر انجراف عالٍ بلا تدابير."
    else:
        cls, ar = "very_steep", "شديد جدّاً"
        note = "ميل شديد جدّاً — أرض هامشيّة؛ تدريج مكثّف وتجنّب الحرث المكشوف."
    return {
        "class": cls,
        "class_ar": ar,
        "slope_pct": round(slope_pct, 1),
        "terracing_advised": slope_pct >= SLOPE_GENTLE,  # من فئة «متوسّط» (≥8٪) فأعلى
        "erosion_risk": (
            "high"
            if slope_pct >= SLOPE_STEEP
            else "moderate"
            if slope_pct >= SLOPE_GENTLE
            else "low"
        ),
        "note_ar": note,
    }


def classify_elevation(elevation_m: float | None) -> dict:
    """يصنّف الارتفاع إلى إقليم رأسيّ + دلالة صقيع/منطقة محصوليّة (حتمي)."""
    if elevation_m is None:
        return {"class": "unknown", "class_ar": "غير معروف", "note_ar": "لا قيمة ارتفاع."}
    if elevation_m < ELEV_COASTAL:
        cls, ar = "coastal", "ساحلي/تهامة"
        note = "منخفض حارّ — بلا صقيع؛ محاصيل مداريّة/حارّة، إجهاد حراريّ صيفاً."
        frost = "none"
    elif elevation_m < ELEV_FOOTHILL:
        cls, ar = "foothill", "سفوح"
        note = "سفوح معتدلة — مدى محاصيل واسع؛ صقيع نادر."
        frost = "rare"
    elif elevation_m < ELEV_MIDLAND:
        cls, ar = "midland", "هضبة وسطى"
        note = "هضبة معتدلة — حبوب/خضر؛ صقيع شتويّ ممكن في المنخفضات."
        frost = "possible"
    else:
        cls, ar = "highland", "مرتفعات"
        note = "مرتفعات باردة — بنّ/معتدلات؛ خطر صقيع شتويّ — احذر الزراعة الحسّاسة."
        frost = "likely_winter"
    return {
        "class": cls,
        "class_ar": ar,
        "elevation_m": round(elevation_m, 1),
        "frost_risk": frost,
        "note_ar": note,
    }


def azimuth_to_aspect(azimuth_deg: float | None) -> str:
    """يحوّل سمتاً (0=شمال، 90=شرق، بالساعة) إلى اتّجاه بوصلة ٨ جهات."""
    if azimuth_deg is None or azimuth_deg < 0:
        return "FLAT"
    # كلّ قطاع 45°، مُزاح بنصف قطاع ليتمركز الشمال على 0
    idx = int(((azimuth_deg % 360) + 22.5) // 45) % 8
    return _COMPASS_8[idx]


def aspect_agronomic_note(aspect: str) -> dict:
    """دلالة التعرّض الشمسي زراعيّاً (نصف الكرة الشماليّ — اليمن)."""
    a = (aspect or "").upper()
    if a == "FLAT":
        return {
            "aspect": "FLAT",
            "aspect_ar": "منبسط",
            "exposure": "neutral",
            "note_ar": "أرض منبسطة — تعرّض شمسيّ متوازن، لا أفضليّة اتّجاه.",
        }
    south = a in ("S", "SE", "SW")
    north = a in ("N", "NE", "NW")
    if south:
        exposure, note = (
            "warm",
            (
                "منحدر مواجه للجنوب — أكثر إشعاعاً شمسيّاً (أدفأ، نضج أسرع) لكن "
                "تبخّر-نتح أعلى وحاجة ماء أكبر؛ مناسب للنضج وتجنّب الصقيع."
            ),
        )
    elif north:
        exposure, note = (
            "cool",
            (
                "منحدر مواجه للشمال — أبرد وأكثر رطوبة (إجهاد حراريّ أقلّ، نضج أبطأ)؛ "
                "أفضل لتقليل الإجهاد المائيّ صيفاً، أبطأ في المناطق الباردة."
            ),
        )
    elif a == "E":
        exposure, note = "morning_sun", "مواجه للشرق — شمس الصباح، اعتدال حراريّ بعد الظهر."
    elif a == "W":
        exposure, note = "afternoon_sun", "مواجه للغرب — شمس بعد الظهر الأحرّ، إجهاد حراريّ مسائيّ."
    else:
        # اتّجاه غير معروف (إدخال حرّ غير قياسي) — لا نخترع تفسيراً (لا افتراض غرب).
        return {
            "aspect": a or None,
            "aspect_ar": "غير معروف",
            "exposure": "unknown",
            "note_ar": "اتّجاه غير معروف — لا تفسير تعرّض شمسيّ (أدخِل أحد ٨ جهات قياسيّة).",
        }
    return {"aspect": a, "aspect_ar": _COMPASS_AR.get(a, a), "exposure": exposure, "note_ar": note}


def slope_aspect_from_window(z: list[list[float]], cell_size_m: float) -> dict:
    """يحسب المنحدر (٪) والسمت (°) من نافذة DEM 3×3 بطريقة Horn القياسيّة.

    z: مصفوفة 3×3 للارتفاعات (الصفّ 0 = شمال، العمود 0 = غرب).
    cell_size_m: حجم الخليّة بالأمتار. حتمي — لا تقدير.
    """
    if len(z) != 3 or any(len(r) != 3 for r in z):
        raise ValueError("نافذة DEM يجب أن تكون 3×3")
    if cell_size_m <= 0:
        raise ValueError("حجم الخليّة يجب أن يكون موجباً")
    a, b, c = z[0]
    d, _e, f = z[1]
    g, h, i = z[2]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell_size_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell_size_m)
    rise_run = math.sqrt(dzdx * dzdx + dzdy * dzdy)
    slope_pct = rise_run * 100.0
    if rise_run == 0:  # أرض منبسطة تماماً — لا اتّجاه
        return {"slope_pct": 0.0, "azimuth_deg": None, "aspect": "FLAT"}
    # سمت ESRI: بالساعة من الشمال (0=شمال، 90=شرق)
    aspect = math.degrees(math.atan2(dzdy, -dzdx))
    if aspect < 0:
        aspect = 90.0 - aspect
    elif aspect > 90.0:
        aspect = 360.0 - aspect + 90.0
    else:
        aspect = 90.0 - aspect
    return {
        "slope_pct": round(slope_pct, 2),
        "azimuth_deg": round(aspect, 1),
        "aspect": azimuth_to_aspect(aspect),
    }


def enrich_terrain(elevation_m: float | None, slope_pct: float | None, aspect: str | None) -> dict:
    """يجمع التضاريس في تفسير زراعيّ موحّد (طبقة استرشاد/عرض).

    يدمج الارتفاع (صقيع/إقليم) + المنحدر (انجراف/تدريج) + الاتّجاه (تعرّض شمسي)
    في خلاصة عمليّة — حتميّة، صادقة، لا تفرض قراراً.
    """
    elev = classify_elevation(elevation_m)
    slope = classify_slope(slope_pct)
    asp = (
        aspect_agronomic_note(aspect)
        if aspect
        else {
            "aspect": None,
            "aspect_ar": "غير معروف",
            "exposure": "unknown",
            "note_ar": "لا اتّجاه.",
        }
    )

    advisories: list[str] = []
    if slope.get("terracing_advised"):
        advisories.append("التدريج/الخطوط الكنتوريّة موصى بها لكبح الانجراف.")
    if elev.get("frost_risk") in ("possible", "likely_winter"):
        advisories.append("خطر صقيع شتويّ — تجنّب المحاصيل الحسّاسة أو احمِها.")
    if asp.get("exposure") == "warm":
        advisories.append("تعرّض جنوبيّ أدفأ — راقب حاجة الماء الأعلى صيفاً.")
    if slope.get("class") == "flat":
        advisories.append("أرض منبسطة — تحقّق من الصرف لتفادي التشبّع المائيّ.")

    has_data = any(v is not None for v in (elevation_m, slope_pct)) or bool(aspect)
    return {
        "display_only": True,  # طبقة استرشاد/عرض — لا تفرض قراراً
        "has_terrain_data": has_data,
        "elevation": elev,
        "slope": slope,
        "aspect": asp,
        "advisories_ar": advisories,
        "honesty_note_ar": (
            "تفسير تضاريسيّ حتميّ من قيم DEM (أو إدخال يدويّ). استرشاديّ يصف الأرض "
            "ويقترح تدابير — لا يفرض قراراً. القيم الدقيقة من مسح ميدانيّ أوثق من DEM."
            if has_data
            else "لا بيانات تضاريس بعد (ارتفاع/منحدر/اتّجاه) — لا اختراع؛ "
            "تُملأ من DEM بعد التشغيل أو يدويّاً."
        ),
    }
