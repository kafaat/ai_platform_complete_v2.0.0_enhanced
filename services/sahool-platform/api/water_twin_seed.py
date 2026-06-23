"""api/water_twin_seed.py — تغذية Water Twin من دفتر المياه اليوميّ (v98).

المرحلة الثانية من Water Twin (``decisions/water-intelligence-direction.md``): بدل تمرير الحالة
الابتدائيّة يدويّاً، **نستثمر دفتر المياه v98** لاشتقاق:
  - **النضوب الابتدائيّ** (``Dr0``) من أحدث صفّ دفتر (``depletion_mm`` مباشرةً، أو من
    ``soil_moisture_pct`` عبر ``Dr = TAW·(1 − SM/100)``).
  - **تقدير ETc اليوميّ** للأفق الأماميّ من **متوسّط** ETc الأخيرة المسجَّلة.

صدق منهجيّ صارم (نمط الدفتر/``decision_record``):
  - **لا تخترع أرقاماً.** إن غاب مصدر الاشتقاق (لا دفتر، لا قيم) ⇒ نُعيد ``None`` مع **مصدر
    صريح** (``"unavailable"``) فيردّ الراوتر بصدق (لا حالة مُلفّقة).
  - **TAW/RAW لا يُشتقّان من الدفتر** (يحتاجان قوام التربة وعمق الجذور) — يُمرَّران صراحةً من
    المستدعي (إقرار زراعيّ)، فلا نخمّن سعة التربة.
  - **مصدر كلّ قيمة مُعلَن** (``sources``) للشفافيّة والتدقيق.

نقيّ بالكامل (بلا I/O/قاعدة) ⇒ يُختبَر بـunit؛ الراوتر يقرأ الدفتر ويستدعي هذه الدوالّ.
"""

from __future__ import annotations


def average_recent_etc(recent_rows: list[dict]) -> float | None:
    """متوسّط ``etc_mm`` غير الفارغة من صفوف الدفتر الأخيرة (None إن لا قيم — لا تلفيق)."""
    vals = [r["etc_mm"] for r in recent_rows if r.get("etc_mm") is not None]
    if not vals:
        return None
    return sum(float(v) for v in vals) / len(vals)


def seed_initial_depletion(
    latest_row: dict | None,
    taw_mm: float,
    override: float | None = None,
) -> tuple[float | None, str]:
    """يشتقّ النضوب الابتدائيّ ``Dr0`` (مم) ومصدره من أحدث صفّ دفتر.

    أولويّة: تجاوز صريح في الطلب → ``depletion_mm`` المُسجَّل → اشتقاق من
    ``soil_moisture_pct`` (``Dr = TAW·(1 − SM/100)``). غياب الكلّ ⇒ ``(None, "unavailable")``.
    يُقصَر الناتج إلى ``[0, TAW]`` (فيزيائيّ). لا تلفيق.
    """
    if override is not None:
        return _clamp(float(override), taw_mm), "request"
    if latest_row:
        dep = latest_row.get("depletion_mm")
        if dep is not None:
            return _clamp(float(dep), taw_mm), "ledger.depletion_mm"
        sm = latest_row.get("soil_moisture_pct")
        if sm is not None:
            return _clamp(taw_mm * (1.0 - float(sm) / 100.0), taw_mm), "ledger.soil_moisture_pct"
    return None, "unavailable"


def _clamp(value: float, taw_mm: float) -> float:
    return max(0.0, min(value, taw_mm))


def seed_daily_etc(
    recent_rows: list[dict],
    override: float | None = None,
) -> tuple[float | None, str]:
    """يشتقّ تقدير ETc اليوميّ ومصدره: تجاوز صريح → متوسّط الدفتر الأخير → ``(None,"unavailable")``."""
    if override is not None:
        if override < 0:
            raise ValueError("daily_etc_mm يجب ألّا يكون سالباً.")
        return float(override), "request"
    avg = average_recent_etc(recent_rows)
    if avg is None:
        return None, "unavailable"
    return avg, "ledger.recent_etc_avg"
