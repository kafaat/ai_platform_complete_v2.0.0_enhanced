"""gdd.py — نواة درجات النموّ اليوميّة GDD الموحَّدة (Growing Degree Days) — WS-C.1c.

**كلّ حساب GDD اليوميّ من محرّك الطقس، من النواة لا من route.** النواة نقيّة حتميّة
(طقس-داخل، °م·يوم-خارج) و**بلا سياسة محصول**: حرارة الأساس والسقف العلويّ وبداية
الموسم وإعادة الضبط كلّها من Season Service — تُمرَّر إلى النواة، لا تُدفَن فيها. هذا يفصل
النواة (المحرّك) عن السياسة (الموسم) عن العرض (الواجهة).

طريقتان صريحتان موثَّقتان (لا خلط صامت):
  • ``modified`` (الافتراضيّ، Baskerville–Emin المبسّطة): يُقصّ ``tmin`` إلى الأساس
    و``tmax`` إلى [الأساس، السقف] قبل المتوسّط — المعيار الزراعيّ (كان في
    ``season_simulation.gdd_day``).
  • ``simple``: يُقصّ ``tmax`` إلى السقف فقط (بلا قصّ ``tmin``) — (كان في
    ``gdd_phenology.daily_gdd``؛ وبلا سقف = ``fao56.gdd_daily``).

المرجع: McMaster & Wilhelm 1997؛ FAO/NDAWN modified growing degree days.
"""

from __future__ import annotations

import math

FORMULA_VERSION = "gdd/daily/1.0.0"
PRODUCT_ID = "gdd"
UNIT = "degC-day"
METHODS = ("modified", "simple")


def gdd_daily(
    *,
    t_max_c: float,
    t_min_c: float,
    base_c: float,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
) -> float:
    """GDD ليوم واحد بالطريقة المُصرَّح بها. لا سالب. الأساس/السقف من السياسة (Season)."""
    if method == "modified":
        tmax = min(t_max_c, upper_cutoff_c) if upper_cutoff_c is not None else t_max_c
        tmax = max(tmax, base_c)  # يوم كلّه تحت الأساس ⇒ صفر
        tmin = max(t_min_c, base_c)
    elif method == "simple":
        tmax = min(t_max_c, upper_cutoff_c) if upper_cutoff_c is not None else t_max_c
        tmin = t_min_c
    else:
        raise ValueError(f"unknown GDD method {method!r}; expected one of {METHODS}")
    return max(0.0, (tmax + tmin) / 2.0 - base_c)


def _finite(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def accumulate_gdd(
    *,
    daily_t_min: list,
    daily_t_max: list,
    base_c: float,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
) -> tuple[list[float | None], float, int]:
    """يجمع GDD عبر سلسلة أيّام متوازية. يعيد (يوميّ، تراكميّ، عدد الأيّام الصالحة).

    صدق: يوم بحرارة غير محدودة/مفقودة ⇒ ``None`` في اليوميّ ولا يُجمَع (مفقود ≠ صفر).
    """
    daily: list[float | None] = []
    total = 0.0
    counted = 0
    for tmin_raw, tmax_raw in zip(daily_t_min, daily_t_max, strict=False):
        tmin, tmax = _finite(tmin_raw), _finite(tmax_raw)
        if tmin is None or tmax is None:
            daily.append(None)
            continue
        g = gdd_daily(
            t_max_c=tmax,
            t_min_c=tmin,
            base_c=base_c,
            upper_cutoff_c=upper_cutoff_c,
            method=method,
        )
        daily.append(round(g, 3))
        total += g
        counted += 1
    return daily, round(total, 3), counted


def gdd_agro_product(
    *,
    daily_t_min: list,
    daily_t_max: list,
    base_c: float | None,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """منتج GDD الموحَّد لعقد محرّك الطقس — نواة + عتبات مُستخدَمة + فترة صلاحيّة + جودة.

    السياسة (``base_c``/``upper_cutoff_c``/``method``) من Season Service — النواة لا
    تختلقها. غياب ``base_c`` (سياسة) ⇒ ``insufficient`` (لا افتراض). المخرَج يُصرّح
    بالعتبات المُستخدَمة و``calculation_version`` وفترة الصلاحيّة صراحةً.
    """
    base = {
        "product": PRODUCT_ID,
        "calculation_version": FORMULA_VERSION,
        "unit": UNIT,
    }
    limitations: list[str] = []

    if method not in METHODS:
        return {
            **base,
            "daily_gdd": [],
            "accumulated_gdd": None,
            "quality_status": "invalid",
            "thresholds_used": {"method": method},
            "limitations": [f"unknown GDD method {method!r}; expected one of {METHODS}"],
        }

    n_pairs = min(len(daily_t_min), len(daily_t_max))
    bc = _finite(base_c)
    if bc is None:
        return {
            **base,
            "daily_gdd": [],
            "accumulated_gdd": None,
            "quality_status": "insufficient",
            "thresholds_used": {"base_c": None, "upper_cutoff_c": upper_cutoff_c, "method": method},
            "valid_period": {"start_date": start_date, "end_date": end_date, "days": n_pairs},
            "limitations": ["base_c (season policy) missing — cannot compute GDD"],
        }
    if n_pairs == 0:
        return {
            **base,
            "daily_gdd": [],
            "accumulated_gdd": None,
            "quality_status": "insufficient",
            "thresholds_used": {
                "base_c": bc,
                "upper_cutoff_c": _finite(upper_cutoff_c),
                "method": method,
            },
            "valid_period": {"start_date": start_date, "end_date": end_date, "days": 0},
            "limitations": ["no daily temperature pairs supplied"],
        }
    if len(daily_t_min) != len(daily_t_max):
        limitations.append(
            f"t_min/t_max length mismatch ({len(daily_t_min)}/{len(daily_t_max)}) — "
            f"paired to shorter ({n_pairs})"
        )

    daily, accumulated, counted = accumulate_gdd(
        daily_t_min=daily_t_min,
        daily_t_max=daily_t_max,
        base_c=bc,
        upper_cutoff_c=_finite(upper_cutoff_c),
        method=method,
    )
    missing_days = n_pairs - counted
    if missing_days:
        limitations.append(f"{missing_days}/{n_pairs} day(s) had missing/non-finite temperature")
    completeness = round(counted / n_pairs, 3) if n_pairs else 0.0
    quality = "validated" if missing_days == 0 else "degraded"

    return {
        **base,
        "daily_gdd": daily,
        "accumulated_gdd": accumulated,
        "thresholds_used": {
            "base_c": bc,
            "upper_cutoff_c": _finite(upper_cutoff_c),
            "method": method,
        },
        "valid_period": {"start_date": start_date, "end_date": end_date, "days": n_pairs},
        "input_completeness": completeness,
        "quality_status": quality,
        "limitations": limitations,
    }
