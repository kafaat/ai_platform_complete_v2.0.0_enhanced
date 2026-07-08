"""api/season_calendar_guard.py — حارس تقويم الموسم (Season Calendar Guard) — منطق صرف.

يجيب عن سؤال «هل هذا الموسم داخل نافذة الزراعة/الحصاد المعتادة لهذا المحصول؟» بدمج
تاريخَي البذار والنهاية معاً في حكم واحد — بناءً على نوافذ الزراعة الموثّقة القائمة في
``api.planting_calendar`` (لا تكرار للبيانات، رَبْط لا نسخ).

الفجوة التي يسدّها (تدقيق طبقة المواسم — Season Calendar Guard):
  • ``planting_calendar.check_planting_date`` يقيّم **شهر البذار فقط**.
  • هذا الحارس يقيّم **الموسم كوحدة**: شهر البذار (optimal/window/off) + شهر الحصاد
    (من season_end مقابل harvest_months، بتسامح ±شهر لأنّ النوافذ تقريبيّة) ⇒ حكم موحّد
    ``optimal | valid | unusual | out_of_window | unknown`` + سبب + ثقة + ``requires_review``.

صدق:
  • السقف MEDIUM لا HIGH — النوافذ تقريبيّة وتختلف بالارتفاع (مرتفعات أبرد/تهامة أحرّ)
    والصنف والزراعة (بعليّة تتبع المطر/مرويّة أمرن). توجّه لا يفرض.
  • محصول بلا تقويم مرجعيّ ⇒ ``unknown`` + ``requires_review`` (لا يُختلَق حكم).
  • ``region`` مقبول للتوسعة المستقبليّة لكنّ النوافذ الحاليّة **وطنيّة غير مُفرَّقة إقليميّاً**
    — يُصرَّح بذلك بدل ادّعاء دقّة إقليميّة غير موجودة.

منطق حتميّ بلا I/O — يُستدعى من راوتر المواسم وبطاقة ذكاء الحقل.
"""

from __future__ import annotations

from datetime import date

from api.planting_calendar import _MONTH_AR, _PLANTING, _months_ar, _resolve

# تسامح ±شهر على نافذة الحصاد (النوافذ تقريبيّة، الصنف/الارتفاع يزيحان النضج).
_HARVEST_TOLERANCE_MONTHS = 1


def _adjacent_months(months: list[int], tol: int) -> set[int]:
    """يوسّع مجموعة أشهر بمقدار ±tol (دائريّ 1..12)."""
    out: set[int] = set()
    for m in months:
        for d in range(-tol, tol + 1):
            out.add(((m - 1 + d) % 12) + 1)
    return out


def evaluate_season_calendar(
    crop: str | None,
    sowing_date: date | None,
    season_end: date | None = None,
    *,
    region: str | None = None,
) -> dict:
    """يقيّم موسماً مقابل نافذة الزراعة/الحصاد المعتادة للمحصول.

    يُعيد قاموساً موحّداً: ``status`` (optimal/valid/unusual/out_of_window/unknown)،
    ``requires_review``، ``confidence`` (medium/low)، ``reason_ar``، وتفاصيل النافذة.
    نقيّ — لا شبكة ولا قاعدة.
    """
    base = {
        "supported": False,
        "status": "unknown",
        "requires_review": True,
        "confidence": "low",
        "region_note_ar": (
            "النوافذ وطنيّة عامّة لليمن — ليست مُفرَّقة إقليميّاً بعد (تحسين مستقبليّ)." if region else None
        ),
        "disclaimer_ar": (
            "نوافذ تقريبيّة تختلف بالارتفاع والصنف والزراعة (بعليّة/مرويّة). توجّه لا يفرض؛ "
            "السقف MEDIUM لأنّ الطقس والموعد المحلّيّ يزيحان النافذة."
        ),
    }

    key = _resolve(crop) if crop else None
    if key is None:
        return {
            **base,
            "reason_ar": (
                f"لا تقويم زراعة مرجعيّ للمحصول «{crop or '—'}» — يتعذّر التحقّق التقويميّ "
                "(لا يُختلَق حكم). المدعوم حاليّاً: "
                + "، ".join(v["name_ar"] for v in _PLANTING.values())
            ),
        }

    if sowing_date is None:
        return {
            **base,
            "supported": True,
            "crop": key,
            "reason_ar": "لا تاريخ بذار للموسم — يتعذّر تقييم موقعه من نافذة الزراعة.",
        }

    c = _PLANTING[key]
    window, optimal, harvest = c["window_months"], c["optimal_months"], c["harvest_months"]
    sow_m = sowing_date.month

    # ── حكم البذار ──
    if sow_m in optimal:
        sow_status, sow_reason = "optimal", f"البذار في {_MONTH_AR[sow_m]} ضمن النافذة المثلى."
    elif sow_m in window:
        sow_status = "valid"
        sow_reason = (
            f"البذار في {_MONTH_AR[sow_m]} ضمن النافذة لكن ليس الأمثل "
            f"(المثلى: {_months_ar(optimal)})."
        )
    else:
        sow_status = "out_of_window"
        before = sow_m < window[0]
        risk = c["early_risk_ar"] if before else c["late_risk_ar"]
        sow_reason = (
            f"البذار في {_MONTH_AR[sow_m]} خارج نافذة زراعة {c['name_ar']} "
            f"({_months_ar(window)}). {risk}"
        )

    # ── حكم الحصاد (اختياريّ: من season_end مقابل harvest_months ±تسامح) ──
    harvest_status = None
    harvest_reason = None
    if season_end is not None:
        end_m = season_end.month
        harvest_ok = _adjacent_months(harvest, _HARVEST_TOLERANCE_MONTHS)
        if end_m in harvest:
            harvest_status, harvest_reason = "valid", None
        elif end_m in harvest_ok:
            harvest_status = "unusual"
            harvest_reason = (
                f"نهاية الموسم في {_MONTH_AR[end_m]} قرب نافذة الحصاد المعتادة "
                f"({_months_ar(harvest)}) لكن ليست ضمنها تماماً."
            )
        else:
            harvest_status = "out_of_window"
            harvest_reason = (
                f"نهاية الموسم في {_MONTH_AR[end_m]} بعيدة عن نافذة الحصاد المعتادة "
                f"({_months_ar(harvest)}) — راجِع تاريخ النهاية أو الصنف."
            )

    # ── الحكم الموحّد (الأسوأ يحكم) ──
    # حكم الحصاد «valid» (داخل النافذة) لا يخفض حكم بذار مثاليّ؛ الحصاد يصعّد القلق فقط
    # (unusual/out_of_window) لا ينزل ببذارٍ ممتاز من optimal إلى valid.
    order = {"optimal": 0, "valid": 1, "unusual": 2, "out_of_window": 3}
    statuses = [sow_status]
    if harvest_status in ("unusual", "out_of_window"):
        statuses.append(harvest_status)
    overall = max(statuses, key=lambda s: order[s])
    requires_review = order[overall] >= order["unusual"]
    # السقف MEDIUM لكلّ المحاصيل المدعومة — النوافذ تقريبيّة (لا HIGH مهما طابق الموعد).
    confidence = "medium"

    reasons = [sow_reason] + ([harvest_reason] if harvest_reason else [])
    return {
        **base,
        "supported": True,
        "status": overall,
        "requires_review": requires_review,
        "confidence": confidence,
        "crop": key,
        "crop_ar": c["name_ar"],
        "sowing_status": sow_status,
        "harvest_status": harvest_status,
        "reason_ar": " ".join(r for r in reasons if r),
        "window_ar": _months_ar(window),
        "optimal_ar": _months_ar(optimal),
        "harvest_ar": _months_ar(harvest),
        "yemen_note_ar": c["yemen_note_ar"],
    }
