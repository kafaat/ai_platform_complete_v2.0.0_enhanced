"""core/wind_geometry.py — ذكاء اتّجاه الرياح المكانيّ (وردة رياح + مصدّات) — منطق صرف.

يجيب سؤال المزارع العمليّ: من أين تأتي الرياح **السائدة**؟ وكيف/أين أُقيم مصدّاً شجريّاً
(shelterbelt) لحماية الحقل؟ لا يعرض الرياح فقط بل يحوّلها **قرار توجيه مكانيّ**.

**صدق حاسم:**
  • يعمل على سلسلة أرصاد مُمرَّرة (اتّجاهات/سُرَع) — لا يخترع تاريخاً.
  • توصية المصدّ تحتاج **الرياح السائدة** (وردة رياح من تاريخ) لا قراءة لحظيّة واحدة —
    عيّنة صغيرة ⇒ ``prevailing=None`` + سبب صريح (لا سائد موهوم من رصدة واحدة).
  • اصطلاح اتّجاه الرياح **أرصاديّ**: الدرجة = الجهة التي تأتي **منها** الريح
    (315° = شماليّة غربيّة، تهبّ نحو الجنوب الشرقيّ).

مراجع زراعيّة (موسومة، قابلة للمعايرة اليمنيّة — الجوف/مأرب/حضرموت/تهامة):
  • المصدّ يُوجَّه **عموديّاً** على الرياح السائدة (أقصى تخفيف للسرعة).
  • تُزرَع الأشجار على الحافة **المواجِهة للريح** (upwind) من الحقل.
  • الحماية الفعّالة downwind تمتدّ ~10× ارتفاع المصدّ (H)، وupwind ~2–5H — FAO/USDA-NRCS.

منطق صرف — بلا I/O ولا قاعدة؛ يُختبَر بأرقام عاديّة ويُغذّي لاحقاً نقطة/بطاقة الرياح.
"""

from __future__ import annotations

import math
from typing import Any

# 16 قطاعاً بوصليّاً — المفتاح الإنجليزيّ + التسمية العربيّة (الجهة التي تأتي منها الريح).
_COMPASS_16: tuple[tuple[str, str], ...] = (
    ("N", "شماليّة"),
    ("NNE", "شماليّة شماليّة شرقيّة"),
    ("NE", "شماليّة شرقيّة"),
    ("ENE", "شرقيّة شماليّة شرقيّة"),
    ("E", "شرقيّة"),
    ("ESE", "شرقيّة جنوبيّة شرقيّة"),
    ("SE", "جنوبيّة شرقيّة"),
    ("SSE", "جنوبيّة جنوبيّة شرقيّة"),
    ("S", "جنوبيّة"),
    ("SSW", "جنوبيّة جنوبيّة غربيّة"),
    ("SW", "جنوبيّة غربيّة"),
    ("WSW", "غربيّة جنوبيّة غربيّة"),
    ("W", "غربيّة"),
    ("WNW", "غربيّة شماليّة غربيّة"),
    ("NW", "شماليّة غربيّة"),
    ("NNW", "شماليّة شماليّة غربيّة"),
)


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def compass_16(deg: Any) -> dict[str, Any] | None:
    """يحوّل درجة اتّجاه إلى قطاع بوصليّ (16 نقطة) + تسمية عربيّة. غير رقميّ ⇒ ``None``.

    الدرجة تُطبَّع [0,360). القطاع بعرض 22.5° متمركز على كلّ نقطة بوصليّة.
    """
    d = _num(deg)
    if d is None:
        return None
    d %= 360.0
    idx = int((d + 11.25) // 22.5) % 16
    key, label = _COMPASS_16[idx]
    return {"deg": round(d, 1), "key": key, "label_ar": label}


def wind_rose(observations: Any, *, min_obs: int = 8) -> dict[str, Any]:
    """وردة رياح: توزيع الاتّجاهات على 16 قطاعاً + الاتّجاه **السائد** (متّجه-متوسّط موزون بالسرعة).

    ``observations``: قائمة عناصرها إمّا رقم (درجة) أو ``(درجة, سرعة)``. السرعة تُوزَن
    (رياح أقوى تحكم السائد)؛ سرعة غائبة ⇒ وزن 1. **صدق:** أقلّ من ``min_obs`` رصدة
    صالحة ⇒ ``prevailing=None`` + ``reason`` (لا سائد موثوق من عيّنة صغيرة).
    """
    if not isinstance(observations, (list, tuple)):
        return {"n": 0, "prevailing": None, "reason": "no_observations", "sectors": {}}

    sin_sum = 0.0
    cos_sum = 0.0
    weight_sum = 0.0
    n = 0
    sectors: dict[str, int] = {}
    for obs in observations:
        if isinstance(obs, (list, tuple)) and len(obs) >= 2:
            deg, spd = _num(obs[0]), _num(obs[1])
        else:
            deg, spd = _num(obs), None
        if deg is None:
            continue
        weight = spd if (spd is not None and spd > 0) else 1.0
        rad = math.radians(deg % 360.0)
        sin_sum += weight * math.sin(rad)
        cos_sum += weight * math.cos(rad)
        weight_sum += weight
        n += 1
        c = compass_16(deg)
        if c is not None:
            sectors[c["key"]] = sectors.get(c["key"], 0) + 1

    if n < min_obs or weight_sum <= 0:
        return {
            "n": n,
            "prevailing": None,
            "reason": "insufficient_observations",
            "min_obs": min_obs,
            "sectors": sectors,
        }
    mean_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0
    return {
        "n": n,
        "prevailing_deg": round(mean_deg, 1),
        "prevailing": compass_16(mean_deg),
        "sectors": sectors,
        "reason": None,
    }


def windbreak_recommendation(prevailing_deg: Any, *, tree_height_m: Any = None) -> dict[str, Any]:
    """توصية مصدّ رياح (توجيه الحاجز + جهة الزرع + عمق الحماية) من الرياح السائدة.

    **صدق:** بلا اتّجاه سائد رقميّ ⇒ ``status="unknown"`` + سبب. المصدّ يُوجَّه **عموديّاً**
    على الريح؛ الأشجار على الحافة المواجِهة للريح (upwind). الحماية ~10× الارتفاع (H)
    downwind و~3H upwind — بلا ارتفاع مُمرَّر لا نُرجِع رقم متر (نُعلن الحاجة، لا نختلق).
    """
    d = _num(prevailing_deg)
    if d is None:
        return {"status": "unknown", "reason": "no_prevailing_wind"}
    d %= 360.0
    upwind = compass_16(d)  # الريح تأتي من هنا
    downwind = compass_16((d + 180.0) % 360.0)  # تتّجه إلى هنا
    # خطّ المصدّ يمتدّ على سَمت عموديّ على الريح (اتّجاه خطّ لا شعاع ⇒ mod 180).
    barrier_azimuth = round((d + 90.0) % 180.0, 1)
    out: dict[str, Any] = {
        "status": "ok",
        "prevailing_from": upwind,
        "wind_towards": downwind,
        "barrier_orientation_deg": barrier_azimuth,
        "plant_side": upwind["key"] if upwind else None,
        "note_ar": (
            f"وجّه المصدّ عموديّاً على الريح السائدة (تأتي من "
            f"{upwind['label_ar'] if upwind else '؟'})؛ ازرع صفوف الأشجار على الحافة "
            "المواجِهة للريح (upwind) لحدّ الحقل."
        ),
    }
    h = _num(tree_height_m)
    if h is not None and h > 0:
        out["protected_downwind_m"] = round(10.0 * h, 1)  # ~10H (القاعدة الزراعيّة)
        out["protected_upwind_m"] = round(3.0 * h, 1)  # ~2–5H (محافظ 3H)
        out["protection_basis"] = "10H_downwind_rule_fao_nrcs"
    else:
        out["protection_basis"] = "needs_tree_height (~10×H downwind)"
    return out
