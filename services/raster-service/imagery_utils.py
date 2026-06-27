"""imagery_utils.py — مساعِدات نقيّة للصور/المشاهد (تفكيك المرحلة 2).

مُستخرَجة حرفيّاً من ``main.py``: ترتيب جودة المشاهد + نوافذ التاريخ/الـbbox +
خرائط النطاقات. نقيّة بلا حالة خدمة (لا ``_stac``/``_layers``/``_jobs``/DB) ولا I/O —
تعتمد فقط على datetime/fastapi/models. ``main.py`` يعيد تصديرها عبر الاستيراد.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from models import (
    BandMapping,
    HistoricalBackfillPreset,
    HistoricalBackfillRequest,
    SceneCandidate,
)

_BACKFILL_PRESET_MONTHS = {
    HistoricalBackfillPreset.auto_12_months: 12,
    HistoricalBackfillPreset.extended_3_years: 36,
    HistoricalBackfillPreset.research_5_years: 60,
}


def _parse_ymd(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"{field_name} يجب أن يكون YYYY-MM-DD") from e


def _scene_datetime(scene: dict | SceneCandidate) -> datetime | None:
    val = scene.datetime if isinstance(scene, SceneCandidate) else scene.get("datetime")
    if not val:
        props = (
            scene.properties if isinstance(scene, SceneCandidate) else scene.get("properties") or {}
        )
        val = props.get("datetime") or props.get("acquisition_datetime")
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).astimezone(UTC)
    except Exception:  # noqa: BLE001 — تحليل تاريخ اختياريّ؛ أيّ قيمة غير صالحة تُعاد None بأمان
        return None


def _scene_to_dict(scene: dict | SceneCandidate) -> dict:
    return scene.model_dump() if isinstance(scene, SceneCandidate) else dict(scene)


def _scene_quality_score(
    scene: dict | SceneCandidate,
    *,
    now: datetime | None = None,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> dict:
    """Rank satellite scenes using production-safe, explainable weights.

    Ranking policy:
      • AOI cloud percentage beats scene-level cloud percentage when available.
      • Recent scenes are preferred, but not at the expense of cloudy scenes.
      • Coverage and provider quality are positive signals.
      • View angle is a small penalty when providers expose it.
    """
    d = _scene_to_dict(scene)
    props = d.get("properties") or {}
    cloud = d.get("aoi_cloud_pct")
    cloud_source = "aoi_cloud_pct"
    if cloud is None:
        cloud = d.get("cloud_cover_pct", props.get("eo:cloud_cover", props.get("cloud_cover")))
        cloud_source = "scene_cloud_pct"
    try:
        cloud = float(cloud) if cloud is not None else 100.0
    except Exception:
        cloud = 100.0
    cloud = max(0.0, min(100.0, cloud))
    cloud_score = max(0.0, 1.0 - (cloud / max(float(max_cloud_pct), 1.0)))

    now = now or datetime.now(UTC)
    dt = _scene_datetime(scene)
    if dt:
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        recency_score = max(0.0, 1.0 - age_days / max(float(prefer_recent_days), 1.0))
    else:
        age_days = None
        recency_score = 0.25

    coverage = d.get("coverage_pct", props.get("sahool:coverage_pct", 100.0))
    try:
        coverage_score = max(0.0, min(1.0, float(coverage) / 100.0))
    except Exception:
        coverage_score = 0.75

    provider_quality = d.get("provider_quality", props.get("sahool:quality", None))
    try:
        provider_quality = (
            max(0.0, min(1.0, float(provider_quality))) if provider_quality is not None else 0.75
        )
    except Exception:
        provider_quality = 0.75

    view_angle = d.get("view_angle", props.get("view:off_nadir", 0.0))
    try:
        angle_penalty = min(0.15, max(0.0, float(view_angle)) / 400.0)
    except Exception:
        angle_penalty = 0.0

    score = (
        (0.50 * cloud_score)
        + (0.20 * recency_score)
        + (0.20 * coverage_score)
        + (0.10 * provider_quality)
        - angle_penalty
    )
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "cloud_pct": round(cloud, 3),
        "cloud_source": cloud_source,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "coverage_score": round(coverage_score, 4),
        "recency_score": round(recency_score, 4),
        "provider_quality": round(provider_quality, 4),
        "view_angle_penalty": round(angle_penalty, 4),
    }


def _rank_scenes(
    scenes: list[dict | SceneCandidate],
    *,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> list[dict]:
    ranked = []
    for scene in scenes:
        d = _scene_to_dict(scene)
        q = _scene_quality_score(
            scene, max_cloud_pct=max_cloud_pct, prefer_recent_days=prefer_recent_days
        )
        d["sahool_quality"] = q
        d["quality_score"] = q["score"]
        ranked.append(d)
    return sorted(
        ranked, key=lambda it: (-float(it.get("quality_score", 0)), it.get("datetime") or "")
    )


def _backfill_date_range(req: HistoricalBackfillRequest) -> tuple[datetime, datetime, int]:
    end = _parse_ymd(req.to_date, "to_date") if req.to_date else datetime.now(UTC)
    if req.from_date:
        start = _parse_ymd(req.from_date, "from_date")
        months = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
    else:
        months = req.months or _BACKFILL_PRESET_MONTHS.get(req.preset, 12)
        # approximate month arithmetic without external dependency: 31 days is safe for search coverage.
        start = end - timedelta(days=31 * months)
    if start >= end:
        raise HTTPException(400, "from_date يجب أن يسبق to_date")
    if months > 60 and req.preset != HistoricalBackfillPreset.custom:
        raise HTTPException(400, "استخدم preset=custom للفترات الأكبر من 5 سنوات")
    return start, end, months


def _bbox_from_geojson(geojson: dict | None) -> list[float] | None:
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


def _month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
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


def _scene_band_mapping(bands: dict[str, str]) -> BandMapping:
    keys = ["blue", "green", "red", "nir", "rededge", "swir1", "swir2", "scl"]
    return BandMapping(**{k: i + 1 for i, k in enumerate(keys) if bands.get(k)})


def _band_urls_from_assets(assets: dict) -> dict:
    """يستخرج روابط النطاقات من STAC assets (Sentinel-2 L2A)."""

    def url(key: str) -> str | None:
        a = assets.get(key)
        return a.get("href") if a else None

    return {
        "blue": url("blue"),
        "green": url("green"),
        "red": url("red"),
        "rededge1": url("rededge1"),
        "rededge2": url("rededge2"),
        "rededge3": url("rededge3"),
        "nir": url("nir"),
        "nir08": url("nir08"),
        "swir16": url("swir16"),
        "swir22": url("swir22"),
        "scl": url("scl"),
        "visual": url("visual"),
        "thumbnail": url("thumbnail"),
    }
