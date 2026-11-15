"""sar_tillage_evidence.py — دليل تغيّر راداريّ (Sentinel-1) حول تاريخ حراثة مُسجَّل.

الغرض: الحراثة/الفلاحة/تجهيز الأرض تُسجَّل في المواسم وسجلّ العمليّات، لكن لا شيء يُظهر
أنّ آلةً مرّت فعلاً. الرادار يعمل تحت السحاب، فنقارن مشهداً قبل التاريخ المُسجَّل بمشهد
بعده فوق مضلّع الحقل.

**دليل داعم احتماليّ، لا إثبات.** المُخرَج يحمل دائماً ``evidence_kind =
"radar_change_evidence"`` و``verified = False`` و``proof = False``، ولا يغيّر حالة الحدث.

الطريقة (مُعلَنة وبسيطة):

* مشاهد GRD قبل التاريخ وبعده داخل نافذة (افتراضيّاً ≤ 24 يوماً لكلّ جانب). مشهد في يوم
  الحدث نفسه يُستبعَد لأنّنا لا نعرف أكان قبل الآلة أم بعدها.
* نفضّل زوجاً من **المدار النسبيّ نفسه واتّجاه المرور نفسه** (زاوية السقوط تغيّر
  الارتداد). إن لم يوجد نأخذ الأقرب ونُعلن عدم التطابق، والنتيجة تصير ``ambiguous``.
* فوق المضلّع: متوسّط القدرة **الخطّيّة** لـVV وVH (σ° أو γ° مُعايَر كما يُصرّح المستدعي؛
  لا يُقبل DN خام)، ثمّ التحويل إلى dB بعد المتوسّط (متوسّط الخطّيّ لا متوسّط الـdB)،
  ونسبة VH/VV بالـdB، والتغيّر Δ = بعد − قبل.
* قيم الـdB هنا ارتداد خام: **لا تُدمج مع NDVI ولا مع أيّ مؤشّر بصريّ**، ولا تُمرَّر
  إلى fuse_health. الرادار ليس NDVI.

لماذا ``ambiguous`` كثيراً: الحراثة تزيد الخشونة فيرتفع VV/VH على التربة العارية، لكنّ
رطوبة التربة (مطر أو ريّ) ترفع الارتداد أيضاً، وحصاد محصول قائم يغيّر التشتّت الحجميّ،
واختلاف المدار يغيّر زاوية السقوط. أيّ واحد منها يجعل الارتفاع غير قابل للنسب للحراثة.

كلّ العتبات أدناه **غير مُعايَرة** — اختيارات أوّليّة من مدى الأدبيّات العامّ، بانتظار
تحقّق حقليّ على حقول يمنيّة بتواريخ حراثة مؤكَّدة. لا تُستعمل لقرار ماليّ أو تنظيميّ.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any

EVIDENCE_KIND = "radar_change_evidence"

# ── عتبات غير مُعايَرة (UNCALIBRATED — pending field validation) ─────────────────
# كلّها اختيارات أوّليّة من مدى منشور عامّ لا من قياس حقليّ في SAHOOL. تغييرها لا يحتاج
# ترحيلاً؛ يحتاج حقولاً بتواريخ حراثة مؤكَّدة ومشاهد S1 مُعايَرة لضبطها.

# أقصى بُعد (أيّام) لمشهد قبل/بعد التاريخ المُسجَّل. دورة S1 للمدار نفسه 12 يوماً
# (6 أيّام حين كان القمران يعملان)، فـ24 يوماً تعطي فرصتين للمدار نفسه. غير مُعايَر.
DEFAULT_WINDOW_DAYS = 24
MAX_WINDOW_DAYS = 36

# ارتفاع VV وVH الأدنى (dB) لاعتبار التغيّر «متّسقاً مع زيادة الخشونة». الأدبيّات تذكر
# عادةً 1–3 dB للحراثة على تربة عارية جافّة. غير مُعايَر.
TILLAGE_RISE_MIN_DB_VV = 1.0
TILLAGE_RISE_MIN_DB_VH = 1.0

# تحت هذا (بالقيمة المطلقة) في الاستقطابين معاً نعدّه «لا تغيّر يُذكر». ضجيج البقع
# (speckle) بعد متوسّط حقل صغير يقارب بضعة أعشار dB. غير مُعايَر.
NO_CHANGE_MAX_ABS_DB = 1.0

# أدنى عدد بكسلات صالحة داخل المضلّع في كلّ مشهد/استقطاب. بكسل S1 GRD IW ≈ 10 م،
# فـ50 بكسلاً ≈ نصف هكتار؛ أقلّ من ذلك يجعل متوسّط البقع غير مستقرّ. غير مُعايَر.
MIN_FIELD_PIXELS = 50

# نسبة VH/VV (dB) قبل الحدث أعلى من هذا توحي بتشتّت حجميّ (غطاء نباتيّ قائم)، فقد
# يكون التغيّر حصاداً لا حراثة. التربة العارية عادةً أقلّ بكثير. غير مُعايَر.
VEGETATION_RATIO_DB_MIN = -6.0

# أيّام قبل مشهد «قبل» تُحسب ضمن نافذة الرطوبة: مطر قبل المشهد الأوّل بأيّام يرفع
# ارتداده هو فيُخفي الارتفاع أو يقلبه. غير مُعايَر.
MOISTURE_LOOKBACK_DAYS = 3

BACKSCATTER_KINDS = ("sigma0_linear", "gamma0_linear")
SURFACE_STATES = ("bare", "vegetated", "unknown")

LIMITS_AR = [
    "دليل داعم احتماليّ فقط؛ لا يثبت مرور آلة ولا ينفيه، ولا يغيّر حالة الحدث.",
    "الرطوبة (مطر/ريّ) والحصاد واختلاف زاوية السقوط ترفع الارتداد أو تخفضه كالحراثة.",
    "العتبات غير مُعايَرة حقليّاً؛ تنتظر حقولاً بتواريخ حراثة مؤكَّدة.",
    "متوسّط حقليّ واحد لكلّ مشهد؛ لا خريطة بكسليّة للتغيّر ولا تسجيل مكانيّ بين المشهدين.",
    "قيم dB ارتداد خام لا تُدمج مع NDVI أو أيّ مؤشّر بصريّ.",
]


def _parse_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("تاريخ مفقود")
    return datetime.fromisoformat(text.replace("Z", "+00:00")[:32]).date()


def _db(linear: float | None) -> float | None:
    if linear is None or not math.isfinite(linear) or linear <= 0:
        return None
    return 10.0 * math.log10(linear)


def _r(value: float | None, nd: int = 3) -> float | None:
    return None if value is None else round(float(value), nd)


def field_backscatter_linear(path: str, geometry_4326: dict) -> dict[str, Any]:
    """متوسّط القدرة الخطّيّة داخل المضلّع لمصدر راستر واحد (حاجب؛ نادِه من خيط).

    يقصّ بنافذة المضلّع (crop) فلا يقرأ المشهد كاملاً. يُسقط nodata وغير المنتهي والقيم
    ≤ 0 (القدرة الخطّيّة موجبة؛ قيم سالبة تعني غالباً أنّ المصدر بالـdB لا خطّيّ).
    """
    import numpy as np
    import rasterio
    from rasterio.mask import mask as rio_mask
    from rasterio.warp import transform_geom

    with rasterio.open(path) as src:
        geom = geometry_4326
        if src.crs is not None and str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
            geom = transform_geom("EPSG:4326", src.crs, geometry_4326)
        try:
            data, _ = rio_mask(src, [geom], crop=True, filled=False, indexes=1)
        except ValueError:  # المضلّع لا يتقاطع مع الراستر
            return {"mean_linear": None, "valid_pixels": 0, "dropped_non_positive": 0}
        arr = np.ma.filled(data.astype("float64"), np.nan)
        res = tuple(float(abs(v)) for v in src.res)
        crs = str(src.crs) if src.crs is not None else None
    inside = arr[np.isfinite(arr)]
    positive = inside[inside > 0]
    return {
        "mean_linear": float(positive.mean()) if positive.size else None,
        "valid_pixels": int(positive.size),
        "dropped_non_positive": int(inside.size - positive.size),
        "pixel_size": res,
        "crs": crs,
    }


def _acq_view(acq: dict, event_day: date) -> dict:
    day = _parse_day(acq.get("datetime"))
    return {
        "item_id": acq.get("item_id"),
        "datetime": acq.get("datetime"),
        "relative_orbit": acq.get("relative_orbit"),
        "orbit_state": (acq.get("orbit_state") or None),
        "days_from_event": (day - event_day).days,
    }


def select_pair(
    acquisitions: Iterable[dict], event_day: date, window_days: int
) -> tuple[dict | None, dict | None, list[str], list[str]]:
    """يختار زوج (قبل، بعد). يُرجِع (before, after, reasons_declared, ambiguity_reasons)."""
    declared: list[str] = []
    before: list[dict] = []
    after: list[dict] = []
    lo = event_day - timedelta(days=window_days)
    hi = event_day + timedelta(days=window_days)
    for acq in acquisitions:
        day = _parse_day(acq.get("datetime"))
        if day == event_day:
            if "same_day_acquisition_excluded" not in declared:
                declared.append("same_day_acquisition_excluded")
            continue
        if lo <= day < event_day:
            before.append(acq)
        elif event_day < day <= hi:
            after.append(acq)
    if not before or not after:
        if not before:
            declared.append("no_acquisition_before_event_in_window")
        if not after:
            declared.append("no_acquisition_after_event_in_window")
        return None, None, declared, []

    def gap(a: dict) -> int:
        return abs((_parse_day(a.get("datetime")) - event_day).days)

    def orbit_key(a: dict) -> tuple | None:
        ro, st = a.get("relative_orbit"), (a.get("orbit_state") or "").lower() or None
        return None if ro is None or st is None else (int(ro), st)

    matched = [
        (b, a)
        for b in before
        for a in after
        if orbit_key(b) is not None and orbit_key(b) == orbit_key(a)
    ]
    if matched:
        b, a = min(matched, key=lambda p: (gap(p[0]) + gap(p[1]), gap(p[1])))
        return b, a, declared, []

    b = min(before, key=gap)
    a = min(after, key=gap)
    ambiguity: list[str] = []
    if b.get("relative_orbit") is None or a.get("relative_orbit") is None:
        ambiguity.append("relative_orbit_unknown")
    elif int(b["relative_orbit"]) != int(a["relative_orbit"]):
        ambiguity.append("relative_orbit_mismatch")
    sb, sa = (b.get("orbit_state") or "").lower(), (a.get("orbit_state") or "").lower()
    if not sb or not sa:
        ambiguity.append("pass_direction_unknown")
    elif sb != sa:
        ambiguity.append("pass_direction_mismatch")
    return b, a, declared, ambiguity


def _classify_change(d_vv: float, d_vh: float) -> tuple[str, str]:
    """(صنف أساسيّ، سبب) من Δ بالـdB قبل تطبيق مُربِكات الغموض."""
    if d_vv >= TILLAGE_RISE_MIN_DB_VV and d_vh >= TILLAGE_RISE_MIN_DB_VH:
        return "consistent", "backscatter_rise_consistent_with_roughness"
    if abs(d_vv) < NO_CHANGE_MAX_ABS_DB and abs(d_vh) < NO_CHANGE_MAX_ABS_DB:
        return "inconsistent", "no_significant_backscatter_change"
    if d_vv <= -NO_CHANGE_MAX_ABS_DB and d_vh <= -NO_CHANGE_MAX_ABS_DB:
        return "inconsistent", "backscatter_decrease"
    return "ambiguous", "mixed_or_partial_polarization_response"


def assess_tillage_change(
    *,
    event_date: str,
    field_geometry: dict,
    acquisitions: list[dict],
    backscatter_kind: str,
    moisture_events: list[dict] | None = None,
    moisture_checked: bool = False,
    surface_state_before: str = "unknown",
    window_days: int = DEFAULT_WINDOW_DAYS,
    resolve_source: Callable[[str], str] = lambda s: s,
    reader: Callable[[str, dict], dict] = field_backscatter_linear,
) -> dict[str, Any]:
    """يقيّم تغيّر الارتداد حول تاريخ حراثة مُسجَّل. حاجب (يقرأ راستر)؛ نادِه من خيط.

    كلّ acquisition: ``item_id``, ``datetime``, ``relative_orbit``, ``orbit_state``,
    ``vv_url``, ``vh_url``. المصادر قدرة خطّيّة مُعايَرة من النوع ``backscatter_kind``.
    """
    if backscatter_kind not in BACKSCATTER_KINDS:
        raise ValueError(f"backscatter_kind يجب أن يكون أحد {BACKSCATTER_KINDS} (لا DN خام)")
    if surface_state_before not in SURFACE_STATES:
        raise ValueError(f"surface_state_before يجب أن يكون أحد {SURFACE_STATES}")
    if not 1 <= int(window_days) <= MAX_WINDOW_DAYS:
        raise ValueError(f"window_days خارج [1, {MAX_WINDOW_DAYS}]")
    event_day = _parse_day(event_date)
    events = list(moisture_events or [])

    out: dict[str, Any] = {
        "evidence_kind": EVIDENCE_KIND,
        "verified": False,
        "proof": False,
        "event_status_effect": "none",
        "event_date": event_day.isoformat(),
        "window_days": int(window_days),
        "confidence_class": None,
        "reasons": [],
        "pair": None,
        "backscatter": None,
        "pixels": None,
        "moisture": {"checked": bool(moisture_checked), "events_in_window": []},
        "thresholds": {
            "calibrated": False,
            "tillage_rise_min_db_vv": TILLAGE_RISE_MIN_DB_VV,
            "tillage_rise_min_db_vh": TILLAGE_RISE_MIN_DB_VH,
            "no_change_max_abs_db": NO_CHANGE_MAX_ABS_DB,
            "min_field_pixels": MIN_FIELD_PIXELS,
            "vegetation_ratio_db_min": VEGETATION_RATIO_DB_MIN,
            "moisture_lookback_days": MOISTURE_LOOKBACK_DAYS,
        },
        "method": (
            "Sentinel-1 GRD: field-mean linear backscatter (VV, VH) before vs after the "
            "recorded date, converted to dB after averaging; same relative orbit and pass "
            "preferred. Raw dB is not mixed with optical indices."
        ),
        "limits_ar": list(LIMITS_AR),
    }

    before, after, declared, orbit_ambiguity = select_pair(
        acquisitions, event_day, int(window_days)
    )
    out["reasons"].extend(declared)
    if before is None or after is None:
        out["confidence_class"] = "no_acquisition"
        return out

    bv, av = _acq_view(before, event_day), _acq_view(after, event_day)
    out["pair"] = {
        "before": bv,
        "after": av,
        "same_relative_orbit": not any("relative_orbit" in r for r in orbit_ambiguity),
        "same_pass_direction": not any("pass_direction" in r for r in orbit_ambiguity),
    }

    stats: dict[str, dict] = {}
    for tag, acq in (("before", before), ("after", after)):
        for pol in ("vv", "vh"):
            src = acq.get(f"{pol}_url")
            if not src:
                raise ValueError(f"{tag}: {pol}_url مفقود ({acq.get('item_id')})")
            stats[f"{tag}_{pol}"] = reader(resolve_source(src), field_geometry)

    min_valid = min(int(s.get("valid_pixels") or 0) for s in stats.values())
    dropped = sum(int(s.get("dropped_non_positive") or 0) for s in stats.values())
    pixel_size = next((s.get("pixel_size") for s in stats.values() if s.get("pixel_size")), None)
    out["pixels"] = {
        "valid_min": min_valid,
        "required": MIN_FIELD_PIXELS,
        "dropped_non_positive": dropped,
        "pixel_size": list(pixel_size) if pixel_size else None,
    }
    if dropped:
        out["reasons"].append("non_positive_values_dropped_source_may_be_db_not_linear")
    if min_valid < MIN_FIELD_PIXELS:
        out["confidence_class"] = "insufficient"
        out["reasons"].append("too_few_field_pixels_for_s1_resolution")
        return out

    def level(tag: str) -> dict:
        vv = _db(stats[f"{tag}_vv"]["mean_linear"])
        vh = _db(stats[f"{tag}_vh"]["mean_linear"])
        return {"vv_db": vv, "vh_db": vh, "vh_vv_ratio_db": vh - vv}

    lb, la = level("before"), level("after")
    delta = {k: la[k] - lb[k] for k in lb}
    out["backscatter"] = {
        "kind": backscatter_kind,
        "before": {k: _r(v) for k, v in lb.items()},
        "after": {k: _r(v) for k, v in la.items()},
        "delta": {k: _r(v) for k, v in delta.items()},
    }

    base, base_reason = _classify_change(delta["vv_db"], delta["vh_db"])
    out["reasons"].append(base_reason)
    ambiguity = list(orbit_ambiguity)

    m_lo = _parse_day(before["datetime"]) - timedelta(days=MOISTURE_LOOKBACK_DAYS)
    m_hi = _parse_day(after["datetime"])
    in_window = []
    for ev in events:
        try:
            day = _parse_day(ev.get("date"))
        except ValueError:
            continue
        if m_lo <= day <= m_hi:
            in_window.append(
                {"date": day.isoformat(), "kind": ev.get("kind"), "amount_mm": ev.get("amount_mm")}
            )
    out["moisture"]["events_in_window"] = in_window
    out["moisture"]["window"] = [m_lo.isoformat(), m_hi.isoformat()]
    if in_window:
        for kind in sorted({str(e["kind"] or "moisture") for e in in_window}):
            ambiguity.append(f"{kind}_recorded_in_window")
    elif not moisture_checked:
        out["reasons"].append("moisture_not_checked")
        if base == "consistent":
            # ارتفاعٌ بلا فحص رطوبة لا يُنسب للحراثة: المطر يرفع الارتداد بالقدر نفسه.
            ambiguity.append("rise_without_moisture_check")

    if surface_state_before == "vegetated":
        ambiguity.append("vegetation_declared_before_possible_harvest_effect")
    elif lb["vh_vv_ratio_db"] > VEGETATION_RATIO_DB_MIN:
        ambiguity.append("volume_scattering_before_possible_vegetation_or_harvest")

    out["reasons"].extend(ambiguity)
    out["confidence_class"] = "ambiguous" if ambiguity else base
    return out
