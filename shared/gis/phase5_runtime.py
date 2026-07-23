"""Phase 5 GIS runtime helpers.

Pure-Python contracts for production GIS hardening: STAC API completeness,
OGC API payloads, scene ranking, persistent undo/redo, management-zone
summaries, tile cache planning and AI boundary extraction adapters.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from shared.gis.cloud_native_gis import score_scene_quality
from shared.gis.cloud_native_runtime import RasterRegistryRecord

STAC_CONFORMANCE = [
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/item-search",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
]

OGC_CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core",
]


def stac_landing_page(*, api_base: str = "") -> dict[str, Any]:
    base = api_base.rstrip("/")

    def href(path: str) -> str:
        return f"{base}{path}" if base else path

    return {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "sahool-stac",
        "title": "SAHOOL Field Imagery STAC API",
        "description": "Tenant-scoped STAC API for field COGs, derived indices and mosaics.",
        "conformsTo": STAC_CONFORMANCE,
        "links": [
            {
                "rel": "self",
                "type": "application/json",
                "href": href("/api/v1/gis/cloud-native/stac"),
            },
            {
                "rel": "root",
                "type": "application/json",
                "href": href("/api/v1/gis/cloud-native/stac"),
            },
            {
                "rel": "service-desc",
                "type": "application/vnd.oai.openapi+json;version=3.0",
                "href": href("/openapi.json"),
            },
            {
                "rel": "conformance",
                "type": "application/json",
                "href": href("/api/v1/gis/cloud-native/stac/conformance"),
            },
            {
                "rel": "data",
                "type": "application/json",
                "href": href("/api/v1/gis/cloud-native/stac/collections"),
            },
            {
                "rel": "search",
                "type": "application/geo+json",
                "href": href("/api/v1/gis/cloud-native/stac/search"),
                "method": "GET",
            },
            {
                "rel": "search",
                "type": "application/geo+json",
                "href": href("/api/v1/gis/cloud-native/stac/search"),
                "method": "POST",
            },
            {
                "rel": "queryables",
                "type": "application/schema+json",
                "href": href("/api/v1/gis/cloud-native/stac/queryables"),
            },
        ],
    }


def stac_queryables() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2019-09/schema",
        "$id": "https://sahool.local/stac/queryables",
        "type": "object",
        "title": "SAHOOL STAC queryables",
        "properties": {
            "field_id": {"type": "string", "title": "Field identifier"},
            "index_type": {
                "type": "string",
                "enum": ["ndvi", "ndmi", "ndre", "savi", "truecolor", "evi", "all"],
            },
            "datetime": {"type": "string", "format": "date-time"},
            "eo:cloud_cover": {"type": "number", "minimum": 0, "maximum": 100},
            "sahool:quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        },
    }


def stac_collections_response(
    records: Iterable[RasterRegistryRecord], *, api_base: str = ""
) -> dict[str, Any]:
    by_index: dict[str, list[RasterRegistryRecord]] = {}
    for rec in records:
        by_index.setdefault(rec.index_type, []).append(rec)
    collections = []
    for idx, items in sorted(by_index.items()):
        bboxes = [r.bbox for r in items if isinstance(r.bbox, list) and len(r.bbox) == 4]
        bbox = (
            [
                [
                    min(b[0] for b in bboxes),
                    min(b[1] for b in bboxes),
                    max(b[2] for b in bboxes),
                    max(b[3] for b in bboxes),
                ]
            ]
            if bboxes
            else [[-180, -90, 180, 90]]
        )
        dates = [str(r.product_date) for r in items if r.product_date]
        interval = [[min(dates), max(dates)]] if dates else [[None, None]]
        collections.append(
            {
                "type": "Collection",
                "stac_version": "1.0.0",
                "id": f"sahool-{idx}",
                "title": f"SAHOOL {idx.upper()} products",
                "description": f"Tenant-scoped {idx} field raster products.",
                "license": "proprietary",
                "extent": {"spatial": {"bbox": bbox}, "temporal": {"interval": interval}},
                "links": [
                    {
                        "rel": "self",
                        "href": f"{api_base}/api/v1/gis/cloud-native/stac/collections/sahool-{idx}",
                    },
                    {
                        "rel": "items",
                        "href": f"{api_base}/api/v1/gis/cloud-native/stac/search?index_type={idx}",
                    },
                ],
            }
        )
    return {
        "collections": collections,
        "links": [{"rel": "root", "href": f"{api_base}/api/v1/gis/cloud-native/stac"}],
    }


def filter_records_for_stac(
    records: Iterable[RasterRegistryRecord],
    *,
    field_id: str | None = None,
    index_type: str | None = None,
    min_quality: int | None = None,
    max_cloud: float | None = None,
    bbox: list[float] | None = None,
) -> list[RasterRegistryRecord]:
    out = []
    for r in records:
        if field_id and r.field_id != field_id:
            continue
        if index_type and index_type != "all" and r.index_type != index_type:
            continue
        if min_quality is not None and (r.quality_score or 0) < min_quality:
            continue
        if max_cloud is not None and r.cloud_pct > max_cloud:
            continue
        if bbox and r.bbox and not _bbox_intersects(r.bbox, bbox):
            continue
        out.append(r)
    return out


def _bbox_intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


@dataclass(frozen=True)
class RankedScene:
    scene_id: str
    rank: int
    score: int
    accepted: bool
    reason: str
    record: RasterRegistryRecord


def rank_scenes(
    records: Iterable[RasterRegistryRecord],
    *,
    prefer_recent: bool = True,
    max_cloud_pct: float = 35,
) -> list[dict[str, Any]]:
    now_ord = date.today().toordinal()
    scored: list[tuple[float, RasterRegistryRecord, Any]] = []
    for rec in records:
        quality = score_scene_quality(
            cloud_pct=rec.cloud_pct,
            shadow_pct=(rec.metadata or {}).get("shadow_pct", 0),
            nodata_pct=(rec.metadata or {}).get("nodata_pct", 0),
            haze_pct=(rec.metadata or {}).get("haze_pct", 0),
            resolution_m=rec.resolution_m,
            max_cloud_pct=max_cloud_pct,
        )
        rec_date = _to_date(rec.product_date)
        age_penalty = (
            max(0, min(15, (now_ord - rec_date.toordinal()) / 30))
            if prefer_recent and rec_date
            else 0
        )
        final_score = max(0, int(round(quality.score - age_penalty)))
        scored.append((final_score, rec, quality))
    scored.sort(key=lambda x: (x[0], str(x[1].product_date)), reverse=True)
    ranked = []
    for i, (score, rec, quality) in enumerate(scored, start=1):
        ranked.append(
            asdict(
                RankedScene(
                    scene_id=rec.scene_id or rec.id,
                    rank=i,
                    score=int(score),
                    accepted=quality.accepted and score >= 50,
                    reason=",".join(quality.limiting_factors) or "best_available",
                    record=rec,
                )
            )
        )
    return ranked


def _to_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def build_scene_processing_plan(
    records: Iterable[RasterRegistryRecord],
    *,
    field_id: str | None = None,
    index_type: str | None = None,
) -> dict[str, Any]:
    filtered = filter_records_for_stac(records, field_id=field_id, index_type=index_type)
    ranked = rank_scenes(filtered)
    selected = [r for r in ranked if r["accepted"]][:5] or ranked[:1]
    return {
        "pipeline": [
            "discover",
            "cloud_shadow_score",
            "rank",
            "select",
            "mosaic",
            "cog_validate",
            "tilejson",
            "cache_warm",
        ],
        "selected_scene_ids": [r["scene_id"] for r in selected],
        "ranked": ranked,
        "mosaic_ready": bool(selected),
    }


def ogc_landing_page(*, api_base: str = "") -> dict[str, Any]:
    base = api_base.rstrip("/")
    return {
        "title": "SAHOOL OGC API",
        "description": "OGC API Features/Tiles facade over tenant-scoped fields and raster products.",
        "links": [
            {"rel": "self", "href": f"{base}/api/v1/gis/cloud-native/ogc"},
            {"rel": "conformance", "href": f"{base}/api/v1/gis/cloud-native/ogc/conformance"},
            {"rel": "data", "href": f"{base}/api/v1/gis/cloud-native/ogc/collections"},
        ],
    }


def ogc_collections() -> dict[str, Any]:
    return {
        "collections": [
            {
                "id": "fields",
                "title": "Fields",
                "itemType": "feature",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                "links": [
                    {
                        "rel": "items",
                        "href": "/api/v1/gis/cloud-native/ogc/collections/fields/items",
                    }
                ],
            },
            {
                "id": "rasters",
                "title": "Raster products",
                "itemType": "coverage",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                "links": [
                    {
                        "rel": "tiles",
                        "href": "/api/v1/gis/cloud-native/ogc/collections/rasters/tiles",
                    }
                ],
            },
        ]
    }


def ogc_feature_collection(
    rows: Iterable[dict[str, Any]], *, number_matched: int | None = None
) -> dict[str, Any]:
    features = []
    for row in rows:
        geom = row.get("geometry") or row.get("geom")
        props = {k: v for k, v in row.items() if k not in {"geometry", "geom"}}
        fid = str(props.get("field_id") or props.get("id") or _stable_hash(props))
        features.append({"type": "Feature", "id": fid, "geometry": geom, "properties": props})
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
        "numberMatched": number_matched if number_matched is not None else len(features),
    }


def tile_cache_plan(
    records: Iterable[RasterRegistryRecord], *, minzoom: int = 8, maxzoom: int = 14
) -> dict[str, Any]:
    entries = []
    for rec in records:
        cache_key = _stable_hash({"id": rec.id, "cog": rec.cog_url, "z": [minzoom, maxzoom]})
        entries.append(
            {
                "raster_id": rec.id,
                "index_type": rec.index_type,
                "cache_key": cache_key,
                "minzoom": minzoom,
                "maxzoom": maxzoom,
                "ttl_seconds": 86400 if (rec.quality_score or 0) >= 70 else 21600,
            }
        )
    return {
        "strategy": "cdn+nginx+redis",
        "entries": entries,
        "purge_on": ["raster_registry_update", "geometry_revision_rollback"],
    }


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def geometry_bbox(geometry: dict[str, Any]) -> list[float] | None:
    coords = []

    def walk(v: Any):
        if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
            coords.append((float(v[0]), float(v[1])))
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(geometry.get("coordinates"))
    if not coords:
        return None
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def ai_boundary_extraction_plan(
    *, field_id: str, input_type: str, bbox: list[float] | None = None, model: str = "sam2-geosam"
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "model": model,
        "input_type": input_type,
        "bbox": bbox,
        "steps": [
            "load_imagery",
            "prompt_or_auto_segment",
            "polygonize",
            "simplify",
            "topology_validate",
            "human_review",
            "commit_revision",
        ],
        "status": "planned",
        "requires_human_review": True,
    }


def management_zone_summary(values: list[float], *, n_zones: int = 3) -> dict[str, Any]:
    clean = sorted(float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if len(clean) < n_zones:
        return {"zones": [], "error": "not_enough_values", "count": len(clean)}
    cuts = [clean[int(len(clean) * i / n_zones)] for i in range(1, n_zones)]
    labels = (
        ["low", "medium", "high"] if n_zones == 3 else [f"zone_{i + 1}" for i in range(n_zones)]
    )
    counts = [0] * n_zones
    for value in clean:
        z = sum(1 for cut in cuts if value >= cut)
        counts[min(z, n_zones - 1)] += 1
    return {
        "n_zones": n_zones,
        "zones": [
            {"zone": labels[i], "count": counts[i], "pct": round(100 * counts[i] / len(clean), 1)}
            for i in range(n_zones)
        ],
    }


def apply_undo_redo(
    session: dict[str, Any], *, action: str, event: dict[str, Any] | None = None
) -> dict[str, Any]:
    undo = list(session.get("undo_stack") or [])
    redo = list(session.get("redo_stack") or [])
    if action == "push":
        if event is None:
            raise ValueError("event is required for push")
        undo.append({**event, "pushed_at": datetime.now(UTC).isoformat()})
        redo.clear()
    elif action == "undo":
        if undo:
            redo.append(undo.pop())
    elif action == "redo":
        if redo:
            undo.append(redo.pop())
    else:
        raise ValueError(f"unsupported action: {action}")
    return {
        **session,
        "undo_stack": undo,
        "redo_stack": redo,
        "can_undo": bool(undo),
        "can_redo": bool(redo),
    }
