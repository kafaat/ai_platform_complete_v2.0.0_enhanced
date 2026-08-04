"""Guard: production imagery-timeline endpoint assembles the timeline server-side.

`GET /api/v1/fields/{id}/imagery/timeline?months=N` replaces the frontend's multi-source
assembly with one tenant-scoped read: real COG dates (from raster available-dates),
bounded to the last N months server-side, each item carrying a True Color `thumbnail_url`
the UI lazy-loads (instead of fetching all images at once). Honest: no date without a real
COG; the thumbnail service clips to the field geometry and falls back on its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_FIELDS = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "sahool-platform"
    / "api"
    / "routers"
    # UI28-30 cleanup: imagery timeline relocated from fields.py to the workspace imagery facade.
    / "field_workspace_imagery.py"
)


_DECORATOR = '@router.get("/api/v1/fields/{field_id}/imagery/timeline")'


def _block() -> str:
    src = _FIELDS.read_text(encoding="utf-8")
    i = src.index(_DECORATOR)
    return src[i : i + 3500]


def test_route_exists_and_is_month_bounded():
    b = _block()
    assert _DECORATOR in b
    assert "months: int = Query(24, ge=1, le=60)" in b
    # server-side time-window cut (not just proxying everything).
    #
    # كان هذا التأكيد يُثبّت `timedelta(days=months * 31)` — أي **الحساب الخاطئ** لا
    # الخاصّيّة. الشهر ليس ٣١ يوماً: عند months=24 يُرجِع الحدُّ اليوميّ 2024-07-21
    # بينما الشهر التقويميّ يُرجِع 2024-08-04 — أربعةَ عشرَ يوماً من المشاهد خارج
    # النافذة المطلوبة، تدخل بصمت. والنيّة المكتوبة في اسم الاختبار
    # («month bounded») هي الصحيحة؛ صياغتها هي التي جمّدت العطل.
    # التأكيد الآن على الخاصّيّة: قصٌّ بالأشهر التقويميّة، ومرجع زمنيّ UTC صريح
    # (`date.today()` يقرأ توقيت الخادم المحلّيّ بينما كلّ تواريخ هذا المسار مشتقّة
    # بـUTC، فيزيح الحدَّ يوماً حسب أين تعمل العمليّة).
    assert "cutoff" in b
    assert "_subtract_calendar_months(" in b
    assert "datetime.now(UTC).date()" in b
    assert "timedelta(days=months" not in b, "الشهر ليس ٣١ يوماً — لا تُعِد الحدّ اليوميّ"


def test_items_carry_truecolor_thumbnail_and_real_cog():
    b = _block()
    assert "cdse-thumbnail.png" in b
    # سياسة المصغّرة (raw historical trace revalidation 2026-07-12): المؤشّر ليس
    # truecolor مثبَّتاً بل thumbnail_index المُشتقّ (truecolor إن كان محفوظاً لهذا
    # التاريخ، وإلّا أوّل مؤشّر محفوظ) — فلا مصغّرة truecolor فارغة لتاريخ تحليليّ.
    assert "index={thumbnail_index}" in b
    assert '"truecolor" if "truecolor" in indices else' in b
    # تاريخ المزوّد المعلّق (has_cog=false / بلا مؤشّرات) لا يعرض مصغّرة إطلاقاً.
    assert "if has_cog and thumbnail_index" in b
    assert '"thumbnail_url"' in b
    assert '"has_cog"' in b
    # P2 raster facade: the available-dates read + tenant forwarding moved into
    # get_available_dates (raster_service_client). The source stays explicit — it still
    # fetches available dates and forwards the verified tenant — just through the facade.
    assert "get_available_dates" in b
    assert "tenant_id=tenant" in b
