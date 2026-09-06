"""HTTP date parsing shared by platform routers.

The functions retain their existing names and error contracts. ``api.main`` re-exports
these exact objects for its current router consumers; there is no fallback parser.
An explicit UTC offset is preserved. UTC is added only to a naive ISO datetime.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import HTTPException


def _parse_date(value: str | None, field: str) -> date | None:
    """يحوّل سلسلة ISO (YYYY-MM-DD) إلى date؛ يرفع 400 واضحة على قيمة غير صالحة
    بدل تمريرها للقاعدة فتُسقِط 500 (ملاحظة المراجعة). فارغة/None ⇒ None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail=f"تاريخ غير صالح في {field} — استخدم صيغة YYYY-MM-DD"
        ) from None


def _parse_iso_utc(value: str) -> datetime:
    """يحلّل تاريخ ISO ويضمن أنّه واعٍ بالمنطقة (UTC افتراضاً).

    H8 FIX: `fromisoformat` لتاريخ بلا إزاحة يُنتج datetime ساذجاً، فطرحه من
    `datetime.now(timezone.utc)` يرمي TypeError (= 500). هنا نطبّع للمنطقة
    ونُرجع 422 للمدخل غير القابل للتحليل بدل 500.
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as err:
        raise HTTPException(status_code=422, detail=f"تاريخ ISO غير صالح: {value!r}") from err
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
