"""core/gdd_phenology.py — تقدير المرحلة بالزمن الحراريّ (GDD) — VNext مكوّن #2.

يكمّل ``core.season_phenology`` (المدفوع بالأيّام) بتقدير **حراريّ** أدقّ فسيولوجيّاً:
بدل الاعتماد على «أيّام بعد البذار» وحدها، يستخدم درجات النموّ المتراكمة (GDD) مقابل
``thermal.gdd_to_maturity`` من بطاقة المحصول، ويكشف **تباعد** الأيّام عن الحرارة (طقس أحرّ
⇒ تقدّم طوريّ أسرع من التقويم؛ أبرد ⇒ أبطأ) — وهو ما تؤكّده تحديثات FAO-56 المتّجهة نحو GDD.

اشتقاق عتبات GDD الطوريّة (تقريب صادق، مُوثَّق لا مُدَّعى قياساً):
  عتبة GDD عند حدّ المرحلة = ``gdd_to_maturity × (مجموع أيّام المراحل حتّى الحدّ ÷ إجماليّها)``
  — توزيع نسبيّ لدرجات النموّ على مراحل FAO-56 بحسب أطوالها في البطاقة.

صدق:
  • بطاقة بلا ``gdd_to_maturity`` أو = 0 (المُعمِّرات: بُنّ/نخيل/عنب…) ⇒ GDD غير منطبق
    (``gdd_applicable=False``) — لا تقدير حراريّ مُلفَّق لمحصول لا يناسبه النموذج الحوليّ.
  • بيانات ناقصة ⇒ ``None``/علَم صريح، لا رقم مخترَع.

دالّة نقيّة (لا شبكة/قاعدة) — تُغذّي محرّك مخاطر المرحلة (#3) وبطاقة أدلّة الموسم (#6).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta

from core.crop_cards.loader import load_crop_card

# المرحلة الحرجة = ``mid`` (التزهير/التلقيح) — **ليست مفردةً جديدة**: هي تعريف
# ``core.season_phenology.is_reproductive_stage`` نفسه («الطور الأكثر حساسيّة للإجهاد
# الحراريّ/المائيّ»). يُعاد استعماله ولا يُعاد اختراعه، وإلّا صار للمنصّة تعريفان للحرج.
CRITICAL_STAGE = "mid"

# WS-C.1c Zero-Legacy: نواة حساب GDD اليوميّة (daily_gdd/accumulate_gdd) أُزيلت من هنا —
# مِلكيّتها الوحيدة الآن محرّك الطقس (services/weather-service/gdd.py: gdd_daily/accumulate_gdd،
# ``POST /v1/weather/agro/gdd``). لم تكن هذه النسخة تُغذّي أيّ مسار إنتاجيّ (لا مستورِد إنتاجيّ
# لـdaily_gdd/accumulate_gdd من هذا الملفّ) — كانت نواة مكرّرة فحسب. يبقى هنا **سياسة المحصول**
# فقط (أساس/عتبات المراحل/تعيين المرحلة)، وهي مِلك Season لا نواة حساب.


def gdd_base_c(crop_id: str | None) -> float | None:
    """حرارة أساس GDD من بطاقة المحصول، أو None إن غابت البطاقة/الحقل."""
    card = load_crop_card(crop_id) if crop_id else None
    if card is None:
        return None
    return card.get("thermal", {}).get("gdd_base_c")


def gdd_stage_thresholds(crop_id: str | None) -> list[dict]:
    """عتبات GDD لكلّ مرحلة طوريّة (مشتقّة من stage_days نسبيّاً × gdd_to_maturity).

    يُعيد قائمة {stage, name_ar, gdd_start, gdd_end} أو فارغة إن تعذّر (لا phenology/kc،
    أو gdd_to_maturity ≤ 0 كالمُعمِّرات). صدق: التوزيع نسبيّ تقريبيّ لا قياس ميدانيّ.
    """
    card = load_crop_card(crop_id) if crop_id else None
    if card is None:
        return []
    total_gdd = card.get("thermal", {}).get("gdd_to_maturity", 0) or 0
    stages = list(card.get("phenology", {}).get("stages", []))
    stage_days = card.get("kc", {}).get("stage_days", [])
    if total_gdd <= 0 or not stages or not stage_days:
        return []
    total_days = sum(stage_days)
    if total_days <= 0 or len(stage_days) < len(stages):
        return []
    out: list[dict] = []
    cum_days = 0
    for i, st in enumerate(stages):
        gdd_start = round(total_gdd * (cum_days / total_days), 1)
        cum_days += stage_days[i]
        gdd_end = round(total_gdd * (cum_days / total_days), 1)
        out.append(
            {
                "stage": st["stage"],
                "name_ar": st.get("name_ar", st["stage"]),
                "gdd_start": gdd_start,
                "gdd_end": gdd_end,
            }
        )
    return out


def stage_from_gdd(crop_id: str | None, accumulated_gdd: float | None) -> dict | None:
    """المرحلة الطوريّة الموافقة لدرجات نموّ متراكمة — أو None إن تعذّر/تجاوز النضج."""
    if accumulated_gdd is None:
        return None
    thresholds = gdd_stage_thresholds(crop_id)
    for th in thresholds:
        if th["gdd_start"] <= accumulated_gdd < th["gdd_end"]:
            return th
    return None


def phenology_progress(
    crop_id: str | None,
    days_since_sowing: int | None,
    accumulated_gdd: float | None = None,
) -> dict:
    """يدمج تقدير المرحلة بالأيّام (season_phenology) والحرارة (GDD) ويكشف التباعد.

    يُعيد قاموساً: ``gdd_applicable``، ``gdd_to_maturity``، ``accumulated_gdd``،
    ``gdd_fraction`` (0..1+)، ``maturity_reached_gdd``، ``days_stage``/``gdd_stage``
    (اسم كلٍّ)، و``divergence`` {diverged, direction: ahead/behind/aligned} حين يتوفّر
    التقديران. صدق: المُعمِّرات/الناقص ⇒ gdd_applicable=False دون رقم مُلفَّق.
    """
    from core.season_phenology import current_stage  # تفادي دور الاستيراد

    card = load_crop_card(crop_id) if crop_id else None
    total_gdd = (card or {}).get("thermal", {}).get("gdd_to_maturity", 0) or 0
    gdd_applicable = total_gdd > 0 and bool(gdd_stage_thresholds(crop_id))

    days_st = current_stage(crop_id, days_since_sowing)
    gdd_st = stage_from_gdd(crop_id, accumulated_gdd) if gdd_applicable else None

    result: dict = {
        "gdd_applicable": gdd_applicable,
        "gdd_to_maturity": total_gdd if gdd_applicable else None,
        "accumulated_gdd": accumulated_gdd,
        "gdd_fraction": (
            round(accumulated_gdd / total_gdd, 3)
            if gdd_applicable and accumulated_gdd is not None and total_gdd > 0
            else None
        ),
        "maturity_reached_gdd": (
            bool(gdd_applicable and accumulated_gdd is not None and accumulated_gdd >= total_gdd)
        ),
        "days_stage": days_st["stage"] if days_st else None,
        "days_stage_ar": days_st.get("name_ar") if days_st else None,
        "gdd_stage": gdd_st["stage"] if gdd_st else None,
        "gdd_stage_ar": gdd_st.get("name_ar") if gdd_st else None,
        "note_ar": None,
    }

    # كشف التباعد: يتطلّب توفّر التقديرين معاً.
    if days_st and gdd_st:
        order = ["initial", "development", "mid", "late"]
        try:
            di, gi = order.index(days_st["stage"]), order.index(gdd_st["stage"])
        except ValueError:
            di = gi = 0
        if gi > di:
            direction, note = (
                "ahead",
                "الطقس أحرّ من المتوقّع تقويميّاً ⇒ تقدّم طوريّ أسرع (راجِع التوقيت الحراريّ).",
            )
        elif gi < di:
            direction, note = "behind", "الطقس أبرد من المتوقّع تقويميّاً ⇒ تأخّر طوريّ (النضج أبطأ)."
        else:
            direction, note = "aligned", None
        result["divergence"] = {"diverged": direction != "aligned", "direction": direction}
        result["note_ar"] = note
    else:
        result["divergence"] = {"diverged": False, "direction": "unknown"}
        if not gdd_applicable:
            result["note_ar"] = (
                "الزمن الحراريّ (GDD) غير منطبق لهذا المحصول (لا gdd_to_maturity/مُعمِّر) — "
                "يُعتمَد تقدير الأيّام فقط."
            )

    return result


def _critical_gdd_bounds(crop_id: str | None) -> dict | None:
    """حدّا GDD للمرحلة الحرجة، أو None إن تعذّرت العتبات (مُعمِّر/بطاقة ناقصة)."""
    for th in gdd_stage_thresholds(crop_id):
        if th["stage"] == CRITICAL_STAGE:
            return th
    return None


def _usable_series(forecast_daily_gdd: Sequence[float] | None) -> list[float] | None:
    """سلسلة GDD يوميّة صالحة، أو None إن غابت/فسدت.

    الفساد **يُبطِل السلسلة كلّها** ولا يُصلَح بتخطّي القيمة: قيمةٌ ساقطة من منتصف
    السلسلة تُزيح كلّ الأيّام التالية يوماً، فيخرج زمنٌ قياديّ أقصر من الحقيقة —
    وهو الاتّجاه الخطر (إنذارٌ متأخّر يبدو مبكراً).
    """
    if forecast_daily_gdd is None:
        return None
    values: list[float] = []
    for v in forecast_daily_gdd:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        f = float(v)
        if not math.isfinite(f) or f < 0:
            return None
        values.append(f)
    return values or None


def _calendar_window(crop_id: str | None, sowing_date: date | None, today: date) -> dict | None:
    """صفّ المرحلة الحرجة من خطّ الزمن التقويميّ، أو None إن تعذّر."""
    from core.season_phenology import season_timeline  # تفادي دور الاستيراد

    for row in season_timeline(crop_id, sowing_date, today):
        if row["stage"] == CRITICAL_STAGE:
            return row
    return None


def _window(
    *,
    status: str,
    source: str | None = None,
    confidence: str | None = None,
    stage: str | None = None,
    name_ar: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    lead_days: int | None = None,
    evidence_missing: list[str] | None = None,
    note_ar: str | None = None,
) -> dict:
    """يبني القاموس بمفاتيح ثابتة — الغائب None صراحةً لا محذوفاً."""
    return {
        "status": status,
        "stage": stage,
        "name_ar": name_ar,
        "start_date": start_date,
        "end_date": end_date,
        "lead_days": lead_days,
        "source": source,
        "confidence": confidence,
        "evidence_missing": list(evidence_missing or []),
        "note_ar": note_ar,
    }


def project_next_critical_window(
    crop_id: str | None,
    *,
    accumulated_gdd: float | None = None,
    forecast_daily_gdd: Sequence[float] | None = None,
    sowing_date: date | None = None,
    today: date | None = None,
) -> dict:
    """يُسقِط النافذة الحرجة القادمة (التزهير/التلقيح) بتاريخَين وزمنٍ قياديّ.

    يجيب عن السؤال الذي لم تكن المنصّة تجيبه: **متى** يدخل هذا الحقل طورَه الأضعف —
    لا ما طورُه اليوم. المسار الأدقّ حراريّ (GDD المتراكم المملوك للطقس + سلسلة GDD
    اليوميّة المتوقَّعة)؛ وعند تعذّره يهبط إلى التقويم **مُعلِناً هبوطه** بثقة أدنى.

    المفاتيح: ``status`` (upcoming | in_window | past | insufficient_context) ·
    ``start_date``/``end_date`` (ISO) · ``lead_days`` (أيّام حتّى البداية، 0 داخلها) ·
    ``source`` (gdd_forecast | gdd_accumulated | calendar_fallback) · ``confidence`` ·
    ``evidence_missing`` · ``note_ar``.

    صدق (مفروضٌ باختبارات، لا بالنيّة):
      • **لا يُصدِر ``observed`` أبداً.** هذه الدالّة لا تملك ملاحظةً ميدانيّة ولا
        استشعاراً؛ أقصى ما تملكه قياسُ زمنٍ حراريّ. تحويلُ إسقاطٍ إلى «مرصود» هو
        بعينه ما يمنعه ``api.canonical_phenology_state`` — ولا يُنقَض من هنا.
      • السقف الأعلى للثقة ``medium``: الطقس متوقَّع لا مضمون (عرف المنصّة).
      • أفقُ التنبؤ الأقصر من النافذة **يُعلَن** ولا يُمَدّ بمعدّلٍ مُختلَق.
      • لا مُدخَل ⇒ ``insufficient_context``، لا نافذةٌ مُلفَّقة.
    """
    ref = today or date.today()
    bounds = _critical_gdd_bounds(crop_id)
    series = _usable_series(forecast_daily_gdd)
    missing: list[str] = []
    if forecast_daily_gdd is not None and series is None:
        missing.append("forecast_series_invalid")

    if bounds is not None and accumulated_gdd is not None:
        start_gdd, end_gdd = bounds["gdd_start"], bounds["gdd_end"]
        name_ar = bounds.get("name_ar")

        if accumulated_gdd >= end_gdd:
            return _window(
                status="past",
                source="gdd_accumulated",
                confidence="medium",
                stage=CRITICAL_STAGE,
                name_ar=name_ar,
                evidence_missing=missing,
                note_ar="النافذة الحرجة انقضت حراريّاً — لا إسقاط أماميّ لها هذا الموسم.",
            )

        if accumulated_gdd >= start_gdd:
            # داخل النافذة الآن. بدايتُها وقعت في الماضي ولا تُشتقّ بلا تاريخ حراريّ،
            # فتُترَك None مُعلَنة بدل أن تُقدَّر — والنهاية تُسقَط إن بلغها الأفق.
            end_date, end_missing = _project_day(series, accumulated_gdd, end_gdd)
            return _window(
                status="in_window",
                source="gdd_accumulated" if end_date is None else "gdd_forecast",
                confidence="medium",
                stage=CRITICAL_STAGE,
                name_ar=name_ar,
                start_date=None,
                end_date=(ref + timedelta(days=end_date)).isoformat() if end_date else None,
                lead_days=0,
                evidence_missing=missing + ["window_start_unobserved"] + end_missing,
                note_ar="الحقل داخل نافذته الحرجة الآن — الإجراء وقائيّ لا تحضيريّ.",
            )

        start_day, start_missing = _project_day(series, accumulated_gdd, start_gdd)
        if start_day is not None:
            end_day, end_missing = _project_day(series, accumulated_gdd, end_gdd)
            return _window(
                status="upcoming",
                source="gdd_forecast",
                confidence="medium",
                stage=CRITICAL_STAGE,
                name_ar=name_ar,
                start_date=(ref + timedelta(days=start_day)).isoformat(),
                end_date=(ref + timedelta(days=end_day)).isoformat() if end_day else None,
                lead_days=start_day,
                evidence_missing=missing + end_missing,
                note_ar="نافذة حرجة متوقَّعة حراريّاً — الزمن القياديّ يسمح بإجراء تحضيريّ.",
            )
        missing += start_missing

    elif bounds is None:
        missing.append("gdd_thresholds_unavailable")
    if accumulated_gdd is None:
        missing.append("accumulated_gdd_missing")

    # الهبوط التقويميّ — مُعلَنٌ بثقة أدنى، لا صامتاً.
    row = _calendar_window(crop_id, sowing_date, ref)
    if row is None:
        return _window(
            status="insufficient_context",
            evidence_missing=missing + ["calendar_timeline_unavailable"],
            note_ar="لا زمنَ حراريّاً ولا خطَّ زمنٍ تقويميّاً — لا نافذة تُعلَن.",
        )
    start = date.fromisoformat(row["start_date"])
    status = {"upcoming": "upcoming", "current": "in_window", "past": "past"}[row["status"]]
    return _window(
        status=status,
        source="calendar_fallback",
        confidence="low",
        stage=CRITICAL_STAGE,
        name_ar=row.get("name_ar"),
        start_date=row["start_date"],
        end_date=row["end_date"],
        lead_days=max(0, (start - ref).days) if status != "past" else None,
        evidence_missing=missing,
        note_ar=(
            "نافذة تقويميّة لا حراريّة — تنحرف في المواسم الحارّة/الباردة، "
            "والثقة أدنى بهذا السبب لا بالتحفّظ."
        ),
    )


def _project_day(
    series: list[float] | None, start_gdd: float, target_gdd: float
) -> tuple[int | None, list[str]]:
    """أوّل يومٍ يبلغ فيه التراكمُ الهدفَ ضمن الأفق — أو None مع سبب مُعلَن."""
    if series is None:
        return None, ["forecast_series_missing"]
    cumulative = start_gdd
    for day, increment in enumerate(series, start=1):
        cumulative += increment
        if cumulative >= target_gdd:
            return day, []
    return None, ["forecast_horizon_too_short"]
