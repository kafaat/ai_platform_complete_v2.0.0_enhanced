"""api/field_readiness.py — مؤشّر جاهزيّة بيانات الحقل (Field Data Readiness Index).

الغرض:
   درجة **واحدة مُفسَّرة** لكلّ حقل تجيب: «كم نثق بذكاء هذا الحقل الآن؟» — تُجمَّع من
   إشارات **موجودة أصلاً** في الحالة القانونيّة (لا حساب جديد، لا اختلاق): النضارة
   (أعمار NDVI/تربة/طقس) · الثقة الزمنيّة (`confidence_level`) · حالة المعايرة
   (`remote_sensing.calibration_status`، C5) · تغطية الإشارات (أيّ الكتل الكنسيّة حاضرة).

لماذا (مُلاءمة اليمن + صدق):
   مزارع الجوف بهاتف وإنترنت ضعيف يحتاج أن يعرف **صراحةً** ما يحدّ ثقة توصيته وما يرفعها
   («صورة أحدث»/«تحليل تربة»). فهذا المؤشّر يجعل صدق المنصّة (النقص المُعلَن) **مرئيّاً
   وقابلاً للفعل** بدل أن يبقى مبثوثاً. offline-first + explainable-first حرفيّاً.

صدق صريح — ما هذا وما ليس هو:
   - **تجميع لا قرار:** معلوماتيّ بحت، **لا يغيّر** `validity`/`execution_mode`.
   - **الأوزان مُعلَنة لا معايَرة:** اختِيرت بالحكم الهندسيّ — موسوم `calibrated=False`.
   - **بُعد غير قابل للتقييم (إشارته غائبة) ⇒ يُستبعَد وتُعاد تسوية الأوزان** (لا نُعاقِب
     على ما لا نقيس). كلّ الأبعاد غائبة ⇒ `level="insufficient"`.
   - دالّة **نقيّة** تقرأ `state` فقط (لا I/O)، fail-safe: مدخل غير صالح ⇒ None.
"""

from __future__ import annotations

# أوزان الأبعاد (مُعلَنة، غير معايَرة ميدانيّاً) — تُعاد تسويتها على الأبعاد المتاحة فقط.
_WEIGHTS = {"freshness": 0.35, "confidence": 0.30, "coverage": 0.20, "calibration": 0.15}

# عتبات النضارة (يوم/ساعة) — مُعلَنة (دورة Sentinel-2 ~5 أيّام؛ تربة موسميّة؛ طقس يوميّ).
_NDVI_FRESH_D, _NDVI_STALE_D = 5.0, 21.0
_SOIL_FRESH_D, _SOIL_STALE_D = 90.0, 365.0
_WX_FRESH_H, _WX_STALE_H = 24.0, 120.0

_CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.7, "low": 0.45, "very_low": 0.2}
# المعايرة: calibrated=كامل؛ insufficient=نقص مُعلَن (ليس فشلاً) ⇒ 0.5 (صدق C5).
_CALIBRATION_SCORE = {"calibrated": 1.0, "insufficient_field_calibration": 0.5}

_LEVELS = (
    (80.0, "excellent"),
    (60.0, "good"),
    (40.0, "fair"),
    (20.0, "poor"),
)


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ramp(age, fresh, stale):
    """1.0 إن ≤ fresh، 0.0 إن ≥ stale، خطّيّ بينهما. None ⇒ None (غير مُقيَّم)."""
    a = _num(age)
    if a is None:
        return None
    if a <= fresh:
        return 1.0
    if a >= stale:
        return 0.0
    return round(1.0 - (a - fresh) / (stale - fresh), 3)


def _mean(vals):
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def compute_field_readiness(state: dict | None) -> dict | None:
    """يحسب كتلة جاهزيّة بيانات الحقل من إشارات الحالة القائمة. None عند مدخل غير صالح.

    يقرأ من ``state``: ``confidence_level`` · ``inputs`` (أعمار) · ``remote_sensing``
    (available/calibration_status) · حضور الكتل (agronomic/water/boundary). لا I/O.
    """
    if not isinstance(state, dict):
        return None

    inputs = state.get("inputs") if isinstance(state.get("inputs"), dict) else {}
    rs = state.get("remote_sensing") if isinstance(state.get("remote_sensing"), dict) else {}

    # ── 1. النضارة (متوسّط الأبعاد المتاحة) ──
    ndvi_age = _num(inputs.get("ndvi_age_days"))
    soil_age = _num(inputs.get("soil_age_days"))
    wx_age = _num(inputs.get("weather_age_hours"))
    fresh_ndvi = _ramp(ndvi_age, _NDVI_FRESH_D, _NDVI_STALE_D)
    fresh_soil = _ramp(soil_age, _SOIL_FRESH_D, _SOIL_STALE_D)
    fresh_wx = _ramp(wx_age, _WX_FRESH_H, _WX_STALE_H)
    freshness = _mean([fresh_ndvi, fresh_soil, fresh_wx])

    # ── 2. الثقة الزمنيّة (من confidence_level القائم) ──
    conf_level = state.get("confidence_level") or inputs.get("confidence_level")
    confidence = _CONFIDENCE_SCORE.get(conf_level) if isinstance(conf_level, str) else None

    # ── 3. المعايرة (C5: calibration_status) ──
    calib_status = rs.get("calibration_status") if isinstance(rs, dict) else None
    calibration = _CALIBRATION_SCORE.get(calib_status) if isinstance(calib_status, str) else None

    # ── 4. تغطية الإشارات الكنسيّة (حاضرة/متوقَّعة) ──
    signals = [
        bool(rs.get("available")),  # NDVI/استشعار
        isinstance(state.get("agronomic"), dict),  # النواة الزراعيّة
        isinstance(state.get("water"), dict),  # المياه الكنسيّة
        isinstance(state.get("boundary"), dict),  # ثقة الحدّ
    ]
    present = sum(1 for s in signals if s)
    coverage = round(present / len(signals), 3)

    dims = {
        "freshness": freshness,
        "confidence": confidence,
        "coverage": coverage,
        "calibration": calibration,
    }

    # ── الدرجة الكلّيّة: متوسّط موزون على الأبعاد المتاحة (إعادة تسوية الأوزان) ──
    avail = {k: v for k, v in dims.items() if v is not None}
    if avail:
        wsum = sum(_WEIGHTS[k] for k in avail)
        overall = round(100.0 * sum(_WEIGHTS[k] * v for k, v in avail.items()) / wsum, 1)
    else:
        overall = 0.0
    level = "insufficient"
    for threshold, name in _LEVELS:
        if overall >= threshold:
            level = name
            break

    return {
        "overall_score": overall,
        "level": level,
        "dimensions": {
            "freshness": {
                "score": freshness,
                "ndvi_age_days": ndvi_age,
                "soil_age_days": soil_age,
                "weather_age_hours": wx_age,
            },
            "confidence": {
                "score": confidence,
                "level": conf_level if isinstance(conf_level, str) else None,
            },
            "calibration": {"score": calibration, "status": calib_status},
            "coverage": {
                "score": coverage,
                "signals_present": present,
                "signals_expected": len(signals),
            },
        },
        "actionable_ar": _actionable(dims, ndvi_age, soil_age, wx_age, present, len(signals)),
        "calibrated": False,  # الأوزان/العتبات غير معايَرة ميدانيّاً (صدق)
        "source": "field_state.canonical",
    }


def _actionable(dims: dict, ndvi_age, soil_age, wx_age, present: int, expected: int) -> list[str]:
    """أهمّ ما يرفع الجاهزيّة (مُرتَّب بأدنى الأبعاد) — إرشاد عمليّ صادق للمزارع."""
    out: list[tuple[float, str]] = []
    f = dims.get("freshness")
    if f is not None and f < 0.6:
        if ndvi_age is None:
            out.append((f, "فعّل صور الأقمار للحقل (لا NDVI متاح)"))
        elif ndvi_age > _NDVI_STALE_D * 0.7:
            out.append((f, f"احصل على صورة قمر أحدث (NDVI عمره {ndvi_age:.0f} يوماً)"))
        if soil_age is None:
            out.append((f - 0.01, "أضِف تحليل تربة (غير متوفّر)"))
        elif soil_age > _SOIL_STALE_D * 0.7:
            out.append((f - 0.01, "حدِّث تحليل التربة (قديم)"))
        if wx_age is not None and wx_age > _WX_STALE_H * 0.7:
            out.append((f - 0.02, "حدِّث بيانات الطقس"))
    c = dims.get("confidence")
    if c is not None and c < 0.6:
        out.append((c, "بيانات رصد أوثق (غيوم/تغطية أعلى)"))
    cov = dims.get("coverage")
    if cov is not None and cov < 0.75:
        out.append((cov, "استكمل بيانات الحقل (محصول/تاريخ زراعة/حدّ)"))
    cal = dims.get("calibration")
    if cal is not None and cal < 0.6:
        out.append((cal + 0.5, "معايرة ميدانيّة لعتبات المحصول ترفع الدقّة"))
    if not out and present < expected:
        out.append((1.0, "استكمل مصادر بيانات الحقل لرفع الجاهزيّة"))
    out.sort(key=lambda t: t[0])
    return [msg for _, msg in out[:3]]
