"""حارس انحدار: مسار /available-dates?include_provider=true يبني نوافذ الأشهر
بـdatetime واعٍ بالمنطقة الزمنيّة لا date خام.

عيب تاريخيّ (قبل RIV) عاد: ``month_windows`` يقارن cursor (datetime بـUTC) بـ``end``؛
تمرير ``datetime.date`` يرفع "can't compare datetime.datetime to datetime.date"
ويُسقِط دمج تواريخ المزوّد ⇒ ``provider_dates_error`` وشريط زمنيّ فارغ. هذان
اختباران نقيّان بلا شبكة: (أ) عقد ``month_windows``، (ب) حارس ساكن على مصدر
``routers/fields.py`` يمنع عودة ``date.today()`` قبل ``_month_windows``.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

HERE = Path(__file__).resolve().parent


def test_month_windows_requires_tz_aware_datetime():
    import sys

    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import raster_date_geo as g

    # date خام يرفع (هذا سبب العيب) — نُثبت العقد صراحةً.
    end_date = _dt.date.today()
    start_date = end_date - _dt.timedelta(days=93)
    with pytest.raises(TypeError):
        g.month_windows(start_date, end_date)

    # datetime واعٍ بالمنطقة يعمل ويعيد نوافذ شهريّة.
    end = _dt.datetime.now(_dt.UTC)
    start = end - _dt.timedelta(days=24 * 31)
    windows = g.month_windows(start, end)
    assert len(windows) >= 24
    assert all(isinstance(a, _dt.datetime) and isinstance(b, _dt.datetime) for a, b in windows)


def test_available_dates_provider_path_uses_datetime_not_date():
    """حارس ساكن: كتلة include_provider تُنشئ end بـdatetime.now(UTC) لا date.today()
    قبل استدعاء _month_windows — فلا تعود مقارنة date↔datetime مطلقاً."""
    src = (HERE / "routers" / "fields.py").read_text(encoding="utf-8")
    marker = "for w_start, w_end in _month_windows(start, end):"
    assert marker in src
    prefix = src[: src.index(marker)]
    tail = prefix.rsplit("if include_provider:", 1)[-1]
    assert "_dt.datetime.now(_dt.UTC)" in tail, "provider window must use tz-aware datetime"
    assert "end = _dt.date.today()" not in tail, (
        "raw date.today() reintroduces the datetime/date bug"
    )


def test_timeline_window_bounds_processed_dates_by_months():
    """حارس انحدار (MAPHUB-PERIOD): عند include_provider، الشريط الزمنيّ يُقصّ **كلّ**
    التواريخ (المعالَجة + المزوّد) بنافذة months لا المزوّد وحده.

    العيب: التواريخ المعالَجة من backfill سابق (24 شهراً) كانت تُعاد بلا قصّ رغم اختيار
    3/6/12 ⇒ الشريط يعرض 24 شهراً دائماً. الإصلاح: عتبة cutoff = now - months*31 تُطبَّق
    على حلقة بناء ``dates`` حين include_provider فقط (منتقي المشهد بلا provider يبقى كاملاً).
    """
    src = (HERE / "routers" / "fields.py").read_text(encoding="utf-8")
    # عتبة زمنيّة مُشتقّة من months محكومة بـinclude_provider.
    assert "if include_provider:" in src
    assert "timedelta(days=months * 31)" in src, "timeline cutoff must derive from months"
    # القصّ يُطبَّق على حلقة بناء dates (لا المزوّد وحده).
    assert 'if cutoff is not None and rec["date"] < cutoff:' in src, (
        "processed dates must be dropped below the months window"
    )
