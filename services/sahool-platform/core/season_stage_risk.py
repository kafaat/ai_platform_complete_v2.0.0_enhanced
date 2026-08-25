"""core/season_stage_risk.py — مخاطر الطقس **حسب المرحلة** (Stage-aware Risk) — VNext مكوّن #3.

بدل «خطر عامّ للموسم» (risk: high)، يربط إشارات الطقس بالمرحلة الطوريّة الحاليّة — فالخطر
نفسه يختلف أثره جذريّاً بالمرحلة:

  • الإنبات/التأسيس + صقيع/جفاف   ⇒ خطر تأسيس (فشل بادرات).
  • التزهير (mid) + حرارة/رياح     ⇒ عقم لقاح ⇒ خطر إنتاجيّة (الأخطر).
  • امتلاء الحبّ + عجز ماء         ⇒ خسارة وزن الحبّ.
  • الحصاد (late) + مطر/رطوبة      ⇒ تلف/تأخير.

يستخدم ``thermal.flowering_safe_max_c`` من بطاقة المحصول (عتبة حراريّة حقيقيّة لكلّ محصول:
قمح 31°م، ذرة شاميّة 35°م …) لعتبة حرارة التزهير؛ وبقيّة العتبات ثوابت زراعيّة عامّة مُعلَّمة.

صدق:
  • الإشارة الغائبة ⇒ ``evidence_missing`` + خفض الثقة، لا خطر مُختلَق.
  • الثقة سقفها MEDIUM (الطقس **متوقّع لا مضمون**)؛ والمرحلة المجهولة ⇒ لا تقييم مرحليّ.
  • لا يُطلِق إنذاراً على إشارة واحدة غامضة — يذكر السبب والعامل بوضوح.

دالّة نقيّة (لا شبكة/قاعدة) — تُغذّي إسقاط حالة الحقل-الموسم (#5) وبطاقة أدلّة الموسم (#6).
"""

from __future__ import annotations

from datetime import date

from core.crop_cards.loader import load_crop_card

# ثوابت زراعيّة عامّة (مُعلَّمة — تُصقَل محلّيّاً؛ ليست عتبات محصول مخصّصة).
_FROST_TMIN_C = 2.0  # قرب التجمّد — حسّاس عند الإنبات/التزهير
_ESTABLISH_HEAT_TMAX_C = 40.0  # تقشّر/إجهاد بادرات
_WIND_DAMAGE_KMH = 30.0  # رياح تضرّ التزهير/تمنع الرشّ
_HARVEST_RAIN_MM_7D = 15.0  # مطر يهدّد المحصول الناضج
_HARVEST_RH_PCT = 80.0  # رطوبة عالية ⇒ أمراض/تلف عند الحصاد
_WATER_STRESS_FACTOR_WARN = 0.8  # Ks تحت هذا ⇒ إجهاد مائيّ ملموس
_WATER_DEFICIT_MM_WARN = 25.0  # عجز ماء تراكميّ (7-14 يوم) ملموس

_SEV_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_DEFAULT_FLOWERING_MAX_C = 32.0  # احتياطيّ محافظ إن غابت البطاقة (مُعلَّم)


def _has(signals: dict, key: str) -> bool:
    return signals.get(key) is not None


def _water_stressed(signals: dict) -> bool:
    """إجهاد مائيّ من Ks (مفضّل) أو العجز التراكميّ — أيّهما توفّر."""
    ks = signals.get("water_stress_factor")
    if ks is not None:
        return ks < _WATER_STRESS_FACTOR_WARN
    dfc = signals.get("water_deficit_mm")
    return dfc is not None and dfc >= _WATER_DEFICIT_MM_WARN


def stage_weather_risks(
    stage: str | None,
    crop_id: str | None,
    signals: dict | None = None,
) -> dict:
    """يقيّم مخاطر الطقس الخاصّة بالمرحلة الطوريّة الحاليّة.

    ``signals`` مفاتيح اختياريّة: ``tmax_c``, ``tmin_c``, ``wind_kmh``, ``rain_mm_next_7d``,
    ``rh_pct``, ``water_stress_factor`` (0..1), ``water_deficit_mm``.

    يُعيد: ``stage``، ``risks`` [{code, severity, reason_ar, factor}]، ``overall_severity``،
    ``requires_action``، ``evidence_used``/``evidence_missing``، ``confidence``.
    """
    signals = signals or {}
    risks: list[dict] = []
    used = [k for k in signals if signals.get(k) is not None]

    if stage is None:
        return {
            "stage": None,
            "risks": [],
            "overall_severity": "none",
            "requires_action": False,
            "evidence_used": used,
            "evidence_missing": ["current_stage"],
            "confidence": "low",
            "note_ar": "لا مرحلة طوريّة معروفة — يتعذّر تقييم المخاطر حسب المرحلة.",
        }

    card = load_crop_card(crop_id) if crop_id else None
    flowering_max = (card or {}).get("thermal", {}).get(
        "flowering_safe_max_c"
    ) or _DEFAULT_FLOWERING_MAX_C

    def add(code: str, severity: str, reason: str, factor: str):
        risks.append({"code": code, "severity": severity, "reason_ar": reason, "factor": factor})

    tmax, tmin = signals.get("tmax_c"), signals.get("tmin_c")
    wind, rain7 = signals.get("wind_kmh"), signals.get("rain_mm_next_7d")
    rh = signals.get("rh_pct")
    stressed = _water_stressed(signals)

    # المفاتيح ذات الصلة لكلّ مرحلة (لحساب evidence_missing بصدق).
    relevant: list[str] = []

    if stage == "initial":
        relevant = ["tmin_c", "tmax_c", "water_stress_factor"]
        if _has(signals, "tmin_c") and tmin <= _FROST_TMIN_C:
            add("establishment_frost", "high", "صقيع قرب الإنبات ⇒ خطر فشل البادرات.", "tmin")
        if _has(signals, "tmax_c") and tmax >= _ESTABLISH_HEAT_TMAX_C:
            add(
                "establishment_heat", "medium", "حرارة عالية ⇒ تقشّر التربة وإجهاد البادرات.", "tmax"
            )
        if stressed:
            add("establishment_water", "high", "نقص ماء عند التأسيس ⇒ خطر إنبات/بادرات.", "water")

    elif stage == "development":
        relevant = ["water_stress_factor", "tmax_c"]
        if stressed:
            add("vegetative_water", "medium", "إجهاد مائيّ في النموّ الخضريّ ⇒ نموّ محدود.", "water")

    elif stage == "mid":  # التزهير/الإثمار — الأكثر حساسيّة
        relevant = ["tmax_c", "water_stress_factor", "wind_kmh"]
        if _has(signals, "tmax_c") and tmax >= flowering_max:
            add(
                "flowering_heat_sterility",
                "high",
                f"حرارة التزهير ({tmax}°م) ≥ عتبة {flowering_max}°م ⇒ عقم لقاح وخسارة غلّة.",
                "tmax",
            )
        if stressed:
            add("flowering_water", "high", "إجهاد مائيّ عند التزهير ⇒ خسارة غلّة كبيرة.", "water")
        if _has(signals, "wind_kmh") and wind >= _WIND_DAMAGE_KMH:
            add(
                "flowering_wind", "medium", "رياح قويّة عند التزهير ⇒ ضرر أزهار/إعاقة تلقيح.", "wind"
            )

    elif stage == "late":  # امتلاء الحبّ/النضج/الحصاد
        relevant = ["water_stress_factor", "rain_mm_next_7d", "rh_pct"]
        if stressed:
            add("grainfill_water", "medium", "عجز ماء عند امتلاء الحبّ ⇒ خسارة وزن الحبّ.", "water")
        if _has(signals, "rain_mm_next_7d") and rain7 >= _HARVEST_RAIN_MM_7D:
            add("harvest_rain", "high", "مطر متوقّع قرب الحصاد ⇒ تلف/تأخير الحصاد.", "rain")
        if _has(signals, "rh_pct") and rh >= _HARVEST_RH_PCT:
            add("harvest_humidity", "medium", "رطوبة عالية عند النضج ⇒ أمراض/تلف الحبّ.", "rh")

    missing = [k for k in relevant if not _has(signals, k)]
    overall = max((r["severity"] for r in risks), key=lambda s: _SEV_ORDER[s], default="none")
    # الثقة سقفها MEDIUM (الطقس متوقّع)؛ تنزل LOW إن نقصت إشارات المرحلة المهمّة.
    confidence = "low" if missing else "medium"

    return {
        "stage": stage,
        "risks": risks,
        "overall_severity": overall,
        "requires_action": _SEV_ORDER[overall] >= _SEV_ORDER["medium"],
        "evidence_used": used,
        "evidence_missing": missing,
        "confidence": confidence,
        "note_ar": (
            "المخاطر مرحليّة (لا خطر عامّ). الطقس متوقّع لا مضمون — راقِب التوقّعات."
            if risks
            else "لا مخاطر طقسيّة مرحليّة بارزة من الإشارات المتاحة."
        ),
    }


# ── W2: المصادم — نافذةٌ حرجة متوقَّعة × تنبؤٌ يوميّ ⇒ حدثُ تصادمٍ بزمنٍ قياديّ ──
#
# ``stage_weather_risks`` أعلاه يقاطع الطقس × المرحلة **الحاليّة** بقيمٍ مجمَّعة، فيجيب
# «هل الحقل في خطرٍ اليوم؟». وهذا يجيب سؤالاً آخر: «هل سيصادف طورُه الأضعف طقساً
# متطرّفاً، ومتى؟» — والفرق بينهما هو الزمن القياديّ الذي يسمح بإجراءٍ تحضيريّ بدل
# إجراءٍ إسعافيّ.
#
# العتبة **ليست جديدة**: ``thermal.flowering_safe_max_c`` من بطاقة المحصول نفسها التي
# يقرؤها ``stage_weather_risks`` (ذرة ٣٥°م · قمح ٣١°م · بندورة ٣٢°م، بمصادر مكتوبة في
# البطاقة). وهي **غير مُعايَرة محلّيّاً** — يُعلَن ذلك في المُخرَج ولا يُخفى.

_COLLISION_THRESHOLD_SOURCE = "crop_card.thermal.flowering_safe_max_c"
_COLLISION_CALIBRATION = "uncalibrated"


def _window_day_bounds(window: dict, horizon: int) -> tuple[int, int, list[str]]:
    """أوّلُ يومٍ وآخرُه (إزاحةً عن اليوم) داخل الأفق، مع ما نقص مُعلَناً."""
    missing: list[str] = []
    first = window.get("lead_days")
    first = 0 if first is None else int(first)
    end_offset = window.get("_end_offset")
    if end_offset is None:
        missing.append("window_end_beyond_forecast_horizon")
        last = horizon
    else:
        last = int(end_offset)
        if last > horizon:
            missing.append("window_end_beyond_forecast_horizon")
            last = horizon
    return max(0, first), last, missing


def _end_offset_from(window: dict, today: date | None) -> int | None:
    """إزاحةُ نهاية النافذة بالأيّام — مُشتقّةٌ من النافذة نفسها لا مطلوبةٌ من المُستدعي.

    إلزامُ المُستدعي بتمريرها يخلق مصدرَ خطأٍ ثانياً: نافذةٌ تحمل تاريخَ نهايتها
    ورقمٌ منفصل قد يخالفه. المصدر الواحد أصدق.
    """
    end = window.get("end_date")
    if not end or today is None:
        return None
    try:
        return (date.fromisoformat(end) - today).days
    except (TypeError, ValueError):
        return None


def critical_window_collisions(
    crop_id: str | None,
    window: dict | None,
    forecast_daily: list[dict] | None,
    *,
    today: date | None = None,
) -> dict:
    """يقاطع النافذة الحرجة المتوقَّعة مع سلسلة التنبؤ اليوميّة داخلها.

    ``window`` مُخرَجُ ``core.gdd_phenology.project_next_critical_window`` ·
    ``forecast_daily`` قائمةٌ مرتّبة من اليوم +١ فصاعداً، كلُّ عنصرٍ قاموسٌ قد يحمل
    ``tmax_c`` · ``end_offset`` إزاحةُ نهاية النافذة بالأيّام إن عُرِفت.

    صدق (مفروضٌ بالاختبار):
      • **لا خطر مُختلَق خارج النافذة**: نافذةٌ منقضية/مجهولة ⇒ ``not_applicable``،
        لا مسحٌ للأفق كلّه بحثاً عن حرارة (وهو ما يجعل الإنذار عامّاً بلا معنى).
      • العتبة **غير مُعايَرة** وتُعلَن كذلك مع مصدرها — لا رقم بلا نسب.
      • الأفقُ الأقصر من النافذة **يُعلَن** ولا يُمَدّ.
      • الثقة **موروثة** من النافذة وسقفها ``medium``: تصادمٌ مبنيٌّ على نافذةٍ
        تقويميّة لا يصير أوثقَ من نافذته.
      • لا مُدخَل ⇒ ``insufficient_context``، ولا حدثَ مُلفَّق.
    """
    base = {
        "window": window,
        "events": [],
        "max_severity": "none",
        "requires_action": False,
        "threshold_source": _COLLISION_THRESHOLD_SOURCE,
        "calibration": _COLLISION_CALIBRATION,
        "confidence": None,
        "evidence_missing": [],
    }

    if not window or window.get("status") not in ("upcoming", "in_window"):
        return {
            **base,
            "status": "not_applicable",
            "note_ar": (
                "لا نافذة حرجة قادمة أو جارية — لا يُمسَح الأفق بحثاً عن حرارة، "
                "فالخطر خارج النافذة ليس خطراً على هذا الطور."
            ),
        }

    if not forecast_daily:
        return {
            **base,
            "status": "insufficient_context",
            "confidence": window.get("confidence"),
            "evidence_missing": ["forecast_daily_missing"],
            "note_ar": "نافذةٌ معروفة بلا تنبؤٍ يوميّ ⇒ لا تصادم يُقاس (ولا يُنفى).",
        }

    card = load_crop_card(crop_id) if crop_id else None
    flowering_max = (card or {}).get("thermal", {}).get("flowering_safe_max_c")
    missing: list[str] = []
    if flowering_max is None:
        flowering_max = _DEFAULT_FLOWERING_MAX_C
        missing.append("crop_flowering_threshold_missing")

    probe = dict(window)
    probe["_end_offset"] = _end_offset_from(window, today)
    first, last, bound_missing = _window_day_bounds(probe, len(forecast_daily))
    missing += bound_missing

    events: list[dict] = []
    for offset in range(first, min(last, len(forecast_daily)) + 1):
        if offset <= 0 or offset > len(forecast_daily):
            continue
        day = forecast_daily[offset - 1] or {}
        tmax = day.get("tmax_c")
        if tmax is None:
            continue
        if tmax >= flowering_max:
            over = float(tmax) - float(flowering_max)
            severity = "high" if over >= 3.0 else "medium"
            events.append(
                {
                    "code": "heat_during_critical_window",
                    "severity": severity,
                    "lead_days": offset,
                    "date": day.get("date"),
                    "measured_tmax_c": tmax,
                    "threshold_c": flowering_max,
                    "exceedance_c": round(over, 1),
                    "reason_ar": (
                        f"حرارةٌ متوقَّعة {tmax}°م تتجاوز عتبة التزهير {flowering_max}°م "
                        f"بعد {offset} يوماً — عقمُ لقاحٍ محتمَل داخل النافذة الحرجة."
                    ),
                }
            )

    if not any(d and d.get("tmax_c") is not None for d in forecast_daily[max(0, first - 1) : last]):
        missing.append("tmax_missing_inside_window")

    overall = max((e["severity"] for e in events), key=lambda s: _SEV_ORDER[s], default="none")
    # الثقة موروثة: تصادمٌ على نافذةٍ تقويميّة لا يصير أوثقَ من نافذته.
    confidence = window.get("confidence") or "low"
    return {
        **base,
        "status": "collisions" if events else "clear",
        "events": events,
        "max_severity": overall,
        "requires_action": _SEV_ORDER[overall] >= _SEV_ORDER["medium"],
        "confidence": confidence,
        "evidence_missing": missing,
        "note_ar": (
            "تصادمٌ موقوت داخل النافذة الحرجة — العتبة مُعلَنة غير مُعايَرة محلّيّاً، "
            "والطقس متوقَّع لا مضمون."
            if events
            else "لا تجاوزَ للعتبة داخل النافذة ضمن الأفق المتاح — نفيٌ مقيس لا وعدٌ بالسلامة."
        ),
    }
