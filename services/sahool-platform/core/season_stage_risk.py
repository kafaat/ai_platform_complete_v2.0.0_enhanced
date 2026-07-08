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
