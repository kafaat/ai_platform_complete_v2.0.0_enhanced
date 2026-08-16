"""Date-window and GeoJSON helpers for raster-service.

Extracted from ``main.py`` to keep the application module from accumulating pure
validation/geometry utilities. Functions accept lightweight request-like objects
so they remain reusable by workers and tests without importing FastAPI app state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException


def parse_ymd(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"{field_name} يجب أن يكون YYYY-MM-DD") from e


def day_window(value: str | None) -> tuple[str, str] | None:
    """يُحوّل تاريخ/طابع اكتساب إلى نافذة **اليوم الكامل** بـUTC، أو ``None`` إن تعذّر.

    كانت هذه الدالّة مُغلَقاً داخل ``raster_cdse_processing.process_cdse_indices``،
    فبقيت سلطتها حبيسة مسار الإدامة بينما يحتاجها مسار البلاطة الحيّة للربط نفسه.
    نسخُها كان سيُنشئ سلطةً ثانية على معنى «اليوم» تنحرف عن الأولى بصمت؛ فرُفِعت إلى
    وحدة التواريخ المشتركة ويستهلكها المساران من موضع واحد.

    ``00:00 → 23:59:59`` لا ``00:00 → 00:00``: النافذة صفريّة الطول تُسبّب ٤٠٠ أو
    نتيجة فارغة من CDSE (مُوثَّق في مُستدعي هذه الدالّة الأصليّ).
    """
    if not value:
        return None
    day = str(value)[:10]
    if len(day) != 10:
        return None
    return f"{day}T00:00:00Z", f"{day}T23:59:59Z"


def _preset_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def backfill_date_range(req: Any, preset_months: dict[Any, int]) -> tuple[datetime, datetime, int]:
    end = parse_ymd(req.to_date, "to_date") if req.to_date else datetime.now(UTC)
    if req.from_date:
        start = parse_ymd(req.from_date, "from_date")
        months = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
    else:
        months = req.months or preset_months.get(req.preset, 12)
        start = end - timedelta(days=31 * months)
    if start >= end:
        raise HTTPException(400, "from_date يجب أن يسبق to_date")
    if months > 60 and _preset_value(req.preset) != "custom":
        raise HTTPException(400, "استخدم preset=custom للفترات الأكبر من 5 سنوات")
    return start, end, months


def bbox_from_geojson(geojson: dict | None) -> list[float] | None:
    if not geojson:
        return None
    coords: list[tuple[float, float]] = []

    def walk(node):
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(isinstance(v, (int, float)) for v in node[:2])
        ):
            lon, lat = float(node[0]), float(node[1])
            coords.append((lon, lat))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(geojson.get("coordinates"))
    if not coords:
        return None
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = datetime(start.year, start.month, 1, tzinfo=UTC)
    while cur < end:
        nxt = datetime(
            cur.year + (1 if cur.month == 12 else 0),
            1 if cur.month == 12 else cur.month + 1,
            1,
            tzinfo=UTC,
        )
        w_start = max(start, cur)
        w_end = min(end, nxt - timedelta(seconds=1))
        if w_start < w_end:
            windows.append((w_start, w_end))
        cur = nxt
    return windows


def bbox_from_geom(geom: dict | None) -> list[float] | None:
    """Return [west, south, east, north] from GeoJSON Polygon/MultiPolygon/Feature."""
    if not geom:
        return None
    try:
        gtype = geom.get("type", "")
        if gtype == "Feature":
            geom = geom.get("geometry") or {}
            gtype = geom.get("type", "")
        coords: list = []
        if gtype == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif gtype == "MultiPolygon":
            for ring in geom.get("coordinates", []):
                coords.extend(ring[0] if ring else [])
        if not coords:
            return None
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return [min(lons), min(lats), max(lons), max(lats)]
    except Exception:  # noqa: BLE001
        return None
