"""api/irrigation_state_guard.py — بوّابة اتّساق/نضارة حالة الريّ (WS-D.2) — نقيّة.

قبل إنتاج توصية ريّ مُثراة تلقائيّاً من حالة الحقل (دفتر المياه + بارامترات التربة)،
يجب التحقّق صراحةً — لا قصّ صامت، لا استبدال صفر للنقص:

  • الاكتمال: غياب Dr أو TAW ⇒ ``insufficient_data`` (مفقود ≠ صفر؛ لا تُختلَق قيمة).
  • الاتّساق: ``0 ≤ Dr ≤ TAW`` (الاستنزاف لا يتجاوز الماء المتاح الكلّيّ). تجاوز Dr
    لـTAW (اختلاف طوابع زمنيّة/خطأ تسوية) ⇒ ``inconsistent_state`` والتوصية
    **unavailable** — ولا يُقصّ Dr صامتاً إلى TAW.
  • النضارة: عمر دفتر المياه ≤ عتبة؛ أقدم ⇒ قيدٌ مُعلَن (``stale_water_ledger``) لا
    حجب (استنزاف قديم يبقى إشارة مع تحذير صريح).
  • مصدر TAW: يُعلَن (مختبر/نسيج/افتراضيّ محصول) — غير المُعايَر يُوسَم قيداً.

نقيّة حتميّة (لا I/O، لا وصول env) — كلّ المدخلات تُمرَّر صراحةً؛ تُختبَر بلا قاعدة.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from shared.contracts.soil.moisture_policy import WATER_LEDGER_MAX_AGE_HOURS

# نضارة دفتر المياه الافتراضيّة (ساعات) — استنزاف أقدم منها يقود قراراً حاضراً بحذر.
# القيمة من السياسة المشتركة (shared/contracts/soil/moisture_policy.py)؛ وفي المنصّة
# يستوردها canonical_water_state وwater_twin وfield_state_projection من هنا (لا نسخ موازية).
DEFAULT_MAX_LEDGER_AGE_HOURS = WATER_LEDGER_MAX_AGE_HOURS

LIMIT_STALE_WATER_LEDGER = "stale_water_ledger"
LIMIT_WATER_LEDGER_DATE_UNPROVEN = "water_ledger_date_unproven"
LIMIT_WATER_LEDGER_DATE_IN_FUTURE = "water_ledger_date_in_future"


def _as_ledger_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def water_ledger_row_freshness(
    ledger_date: object,
    now: datetime,
    *,
    max_age_hours: float = DEFAULT_MAX_LEDGER_AGE_HOURS,
) -> dict:
    """هل صفّ الدفتر حاضرٌ بما يكفي ليُعامَل حالةً جارية؟ — نقيّة، fail-closed.

    العمر = ``now`` − بداية ``ledger_date`` بتوقيت UTC (نفس اصطلاح
    ``canonical_water_state``). تاريخ مفقود/غير صالح ⇒ غير مُثبَت؛ تاريخ في
    المستقبل ⇒ لا يُثبت شيئاً؛ أقدم من العتبة ⇒ قديم. في الثلاث ``current=False``
    والقيد مُعلَن — المستهلك يعامل الصفّ غير متاح لا حالة حاضرة.

    Returns: ``{"current": bool, "age_hours": float|None, "limitation": str|None,
    "max_age_hours": float}``.
    """
    d = _as_ledger_date(ledger_date)
    if d is None:
        return {
            "current": False,
            "age_hours": None,
            "limitation": LIMIT_WATER_LEDGER_DATE_UNPROVEN,
            "max_age_hours": max_age_hours,
        }
    now_aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    start = datetime.combine(d, datetime.min.time(), tzinfo=UTC)
    age_hours = (now_aware - start).total_seconds() / 3600.0
    if age_hours < 0:
        limitation: str | None = LIMIT_WATER_LEDGER_DATE_IN_FUTURE
    elif age_hours > max_age_hours:
        limitation = LIMIT_STALE_WATER_LEDGER
    else:
        limitation = None
    return {
        "current": limitation is None,
        "age_hours": round(age_hours, 2),
        "limitation": limitation,
        "max_age_hours": max_age_hours,
    }


# مصادر TAW التي تُعدّ غير مُعايَرة يمنيّاً (تُوسَم قيداً على الثقة، لا تحجب).
_UNCALIBRATED_TAW_SOURCES = frozenset({None, "texture_fallback", "crop_default", "model_estimate"})


def current_ledger_row(
    latest_row: dict | None,
    now: datetime,
    *,
    max_age_hours: float = DEFAULT_MAX_LEDGER_AGE_HOURS,
) -> tuple[dict | None, dict | None, list[str]]:
    """أحدث صفّ دفتر (``ORDER BY ledger_date DESC LIMIT``) كحالة حاضرة أو لا شيء — نقيّة.

    يُرجِع ``(row_or_None, freshness_or_None, limitations)``: صفٌّ غير حاضر (قديم/بلا
    تاريخ/مستقبليّ) يُستبدَل بـ``None`` فلا يبذر حالةً جارية، وقيده في ``limitations``.
    """
    if not latest_row:
        return None, None, []
    freshness = water_ledger_row_freshness(
        latest_row.get("ledger_date"), now, max_age_hours=max_age_hours
    )
    if freshness["current"]:
        return latest_row, freshness, []
    return None, freshness, [freshness["limitation"]]


def assess_irrigation_state(
    *,
    depletion_mm: float | None,
    taw_mm: float | None,
    ledger_age_hours: float | None = None,
    taw_source: str | None = None,
    max_ledger_age_hours: float = DEFAULT_MAX_LEDGER_AGE_HOURS,
) -> dict:
    """يُقيّم صلاحيّة حالة الماء لإنتاج توصية ريّ — نقيّ، fail-closed، لا قصّ.

    Returns dict:
        ``status`` (recommendation_ready | insufficient_data | inconsistent_state) ·
        ``available`` (bool: هل يجوز إنتاج توصية) · ``limitations`` (قائمة أسباب مُعلَنة) ·
        ``depletion_fraction`` (Dr/TAW أو None) · ``taw_source``.
    """
    # (1) الاكتمال — مفقود ليس صفراً.
    missing = []
    if depletion_mm is None:
        missing.append("missing_depletion_mm")
    if taw_mm is None:
        missing.append("missing_taw_mm")
    if missing:
        return {
            "status": "insufficient_data",
            "available": False,
            "limitations": missing,
            "depletion_fraction": None,
            "taw_source": taw_source,
        }

    dr = float(depletion_mm)
    taw = float(taw_mm)

    # (2) الاتّساق — 0 ≤ Dr ≤ TAW، بلا قصّ صامت.
    if taw <= 0 or dr < 0 or dr > taw:
        reason = "depletion_exceeds_taw" if (taw > 0 and dr > taw) else "invalid_depletion_or_taw"
        return {
            "status": "inconsistent_state",
            "available": False,
            "limitations": [reason],
            "depletion_fraction": (round(dr / taw, 3) if taw > 0 else None),
            "taw_source": taw_source,
        }

    # (3) قيود لا تحجب (نضارة + معايرة TAW).
    limitations: list[str] = []
    if ledger_age_hours is not None and ledger_age_hours > max_ledger_age_hours:
        limitations.append(LIMIT_STALE_WATER_LEDGER)
    if taw_source in _UNCALIBRATED_TAW_SOURCES:
        limitations.append("taw_uncalibrated")

    return {
        "status": "recommendation_ready",
        "available": True,
        "limitations": limitations,
        "depletion_fraction": round(dr / taw, 3),
        "taw_source": taw_source,
    }
