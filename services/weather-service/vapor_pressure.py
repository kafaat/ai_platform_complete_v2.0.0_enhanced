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


def actual_vapor_pressure_from_rh_kpa(es_kpa: float, rh_pct: float) -> float:
    """ضغط البخار الفعليّ ea من الرطوبة النسبيّة (FAO-56 Eq. 19، مبسّطة):

        ea = es · RH/100

    RH يُقصّ إلى [0, 100] (قيَم المستشعر قد تتجاوز قليلاً) — المُستدعِي يعلن ذلك قيداً.
    """
    rh = max(0.0, min(100.0, rh_pct))
    return es_kpa * rh / 100.0


def actual_vapor_pressure_from_dewpoint_kpa(dew_point_c: float) -> float:
    """ضغط البخار الفعليّ ea من نقطة النَّدى (FAO-56 Eq. 14): ea = e°(Tdew)."""
    return saturation_vapor_pressure_kpa(dew_point_c)
