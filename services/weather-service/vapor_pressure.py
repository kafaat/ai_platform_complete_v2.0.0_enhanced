"""vapor_pressure.py — بدائيّات الضغط البخاري المشتركة (FAO-56) — WS-C.1a.

مصدر واحد لصيغة ضغط البخار المشبع (SVP) يستهلكه **VPD وET0 معاً** — فلا تتكرّر
الصيغة (كانت محبوسة داخل ``core/engines/et0.py`` وتُنسَخ في الاختبارات). نقيّ حتميّ،
بلا I/O، قابل للاختبار offline.

المرجع: FAO-56 Irrigation and Drainage Paper 56, Eq. 11 (Tetens/Murray).
"""

from __future__ import annotations

import math

FORMULA_VERSION = "fao56-eq11/1.0.0"


def saturation_vapor_pressure_kpa(t_c: float) -> float:
    """ضغط البخار المشبع e°(T) بالـkPa عند حرارة T °C — FAO-56 Eq. 11.

        e°(T) = 0.6108 · exp( 17.27·T / (T + 237.3) )

    نقيّ: يقبل عدداً ويعيد عدداً. المُستدعِي مسؤول عن تحقّق المدى (لا يُقصّ هنا).
    """
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def mean_saturation_vapor_pressure_kpa(t_max_c: float, t_min_c: float) -> float:
    """متوسّط SVP من الحدّين (FAO-56 Eq. 12): es = (e°(Tmax) + e°(Tmin)) / 2.

    FAO-56 يوصي بالمتوسّط من الحدّين لا e°(Tmean) (يُبالِغ الأخير في es).
    """
    return (saturation_vapor_pressure_kpa(t_max_c) + saturation_vapor_pressure_kpa(t_min_c)) / 2.0


# ضجيجُ مستشعرٍ مقبولٌ حول الحدّين: مقاييسُ الرطوبة تُبلِّغ 100.4٪ أو -0.3٪ عند
# التشبّع أو الصفر. أمّا 350٪ أو -40٪ فليست ضجيجاً بل قراءةٌ مكسورة — وقصُّها
# يُنتِج `ea` صالحَ الشكل من مُدخَلٍ لا معنى له، فيمضي إلى ET0 ومنه إلى قرار ريّ.
_RH_SENSOR_TOLERANCE_PCT = 5.0


def actual_vapor_pressure_from_rh_kpa(es_kpa: float, rh_pct: float) -> float:
    """ضغط البخار الفعليّ ea من الرطوبة النسبيّة (FAO-56 Eq. 19، مبسّطة):

        ea = es · RH/100

    **القصُّ محدودٌ بنطاق ضجيج المستشعر** ``[-5, 105]``، وما خرج عنه يُرفَض
    بـ``ValueError`` ولا يُقصّ.

    والفرقُ ليس تجميلاً: القصُّ غيرُ المحدود يحوّل **غيابَ قياسٍ** إلى **قياسٍ
    واثق**. قراءةُ 350٪ تصير 100٪، فيخرج ``ea`` سليمَ الشكل ويمضي إلى ET0 ثمّ إلى
    قرار ريّ — بلا أثرٍ واحدٍ يقول إنّ المُدخَل كان مكسوراً. والرفضُ يُبقي العطلَ
    مرئيّاً حيث وقع، وهو ما تفعله بقيّةُ هذه الطبقة (`None` = مفقود، لا افتراض).
    """
    if not -_RH_SENSOR_TOLERANCE_PCT <= rh_pct <= 100.0 + _RH_SENSOR_TOLERANCE_PCT:
        raise ValueError(
            f"rh_pct={rh_pct!r} خارج نطاق ضجيج المستشعر "
            f"[{-_RH_SENSOR_TOLERANCE_PCT}, {100.0 + _RH_SENSOR_TOLERANCE_PCT}] — "
            "قراءةٌ مكسورة لا تُقصّ إلى قيمةٍ صالحة"
        )
    rh = max(0.0, min(100.0, rh_pct))
    return es_kpa * rh / 100.0


def actual_vapor_pressure_from_dewpoint_kpa(dew_point_c: float) -> float:
    """ضغط البخار الفعليّ ea من نقطة النَّدى (FAO-56 Eq. 14): ea = e°(Tdew)."""
    return saturation_vapor_pressure_kpa(dew_point_c)


def svp_slope_kpa_per_c(t_c: float) -> float:
    """ميل منحنى ضغط البخار المشبع Δ (kPa/°C) عند T — FAO-56 Eq. 13.

        Δ = 4098 · e°(T) / (T + 237.3)²

    بدائيّة مشتركة يستهلكها Penman-Monteith في ET0 (C.1b) — نفس مصدر e°.
    """
    return 4098.0 * saturation_vapor_pressure_kpa(t_c) / (t_c + 237.3) ** 2
