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

from core.crop_cards.loader import load_crop_card

# سقف علويّ افتراضيّ لحساب GDD (فوقه لا يزيد النموّ خطّيّاً) — يُعطَّل بـNone.
_DEFAULT_UPPER_CAP_C = 30.0


def daily_gdd(
    t_min_c: float, t_max_c: float, base_c: float, upper_cap_c: float | None = None
) -> float:
    """درجات نموّ يوم واحد = max(0, متوسّط الحرارة − الأساس). سقف علويّ اختياريّ.

    الأساس الفيزيائيّ: النموّ يتوقّف تحت حرارة الأساس؛ وفوق سقف علويّ لا يتسارع خطّيّاً
    (يُقصَّر tmax إلى السقف قبل المتوسّط). لا سالب.
    """
    tmax = min(t_max_c, upper_cap_c) if upper_cap_c is not None else t_max_c
    tmin = t_min_c
    mean = (tmax + tmin) / 2.0
    return max(0.0, mean - base_c)


def accumulate_gdd(
    daily_t_min: list[float],
    daily_t_max: list[float],
    base_c: float,
    upper_cap_c: float | None = _DEFAULT_UPPER_CAP_C,
) -> float:
    """مجموع GDD عبر سلسلة أيّام (tmin/tmax متوازيتان). يتجاهل الأيّام الزائدة في الأطول."""
    total = 0.0
    for tmin, tmax in zip(daily_t_min, daily_t_max, strict=False):
        total += daily_gdd(tmin, tmax, base_c, upper_cap_c)
    return round(total, 1)


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
