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
    / "fields.py"
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
    assert "cutoff" in b and "timedelta(days=months" in b


def test_items_carry_truecolor_thumbnail_and_real_cog():
    b = _block()
    assert "cdse-thumbnail.png" in b
    assert "index=truecolor" in b
    assert '"thumbnail_url"' in b
    assert '"has_cog"' in b
    # sources from the tenant-verified raster available-dates proxy.
    assert "available-dates" in b
    assert "X-Tenant-Id" in b
