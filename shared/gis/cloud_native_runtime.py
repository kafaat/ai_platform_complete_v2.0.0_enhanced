"""DB-backed cloud-native GIS runtime contracts for SAHOOL Phase 4.

These helpers intentionally keep side effects at the adapter edge.  They build
STAC/MosaicJSON/TileJSON/GeoParquet payloads from durable registry rows so the
API layer is not a static facade and can be exercised with fake rows in tests.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from shared.gis.cloud_native_gis import score_scene_quality


@dataclass(frozen=True)
class RasterRegistryRecord:
    id: str
    tenant_id: str
    field_id: str | None
    product_date: date | str
    index_type: str
    cog_url: str
    scene_id: str | None = None
    cloud_pct: float = 0.0
    quality_score: int | None = None
    resolution_m: float = 10.0
    bbox: list[float] | dict[str, Any] | None = None
    bands: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def _jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001
            return value
    return value


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _bbox_from_row(row: Any) -> list[float] | None:
    bbox = _jsonish(
        row.get("bbox") if isinstance(row, dict) else row["bbox"] if "bbox" in row else None
    )
    if isinstance(bbox, list) and len(bbox) == 4:
        return [float(x) for x in bbox]
    if isinstance(bbox, dict):
        keys = ("minx", "miny", "maxx", "maxy")
        if all(k in bbox for k in keys):
            return [float(bbox[k]) for k in keys]
        if "bbox" in bbox and isinstance(bbox["bbox"], list) and len(bbox["bbox"]) == 4:
            return [float(x) for x in bbox["bbox"]]
    return None


def record_from_db_row(row: Any) -> RasterRegistryRecord:
    get = row.get if isinstance(row, dict) else row.__getitem__
    cloud = float(get("cloud_pct") or 0)
    quality_score = get("quality_score")
    if quality_score is None:
        quality_score = score_scene_quality(cloud_pct=cloud).score
    return RasterRegistryRecord(
        id=str(get("id")),
        tenant_id=str(get("tenant_id")),
        field_id=str(get("field_id")) if get("field_id") is not None else None,
        product_date=get("product_date"),
        index_type=str(get("index_type")),
        cog_url=str(get("cog_url")),
        scene_id=str(get("scene_id")) if get("scene_id") is not None else None,
        cloud_pct=cloud,
        quality_score=int(quality_score),
        resolution_m=float(get("resolution_m") or 10),
        bbox=_bbox_from_row(row),
        bands=_jsonish(get("bands")) if get("bands") is not None else {},
        metadata=_jsonish(get("metadata")) if get("metadata") is not None else {},
    )


def stac_item_from_record(record: RasterRegistryRecord, *, api_base: str = "") -> dict[str, Any]:
    dt = _iso(record.product_date)
    item_id = record.scene_id or f"raster-{record.id}"
    assets = {
        "data": {
            "href": record.cog_url,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "roles": ["data"],
            "title": f"{record.index_type} COG",
        },
        "tilejson": {
            "href": f"{api_base}/api/v1/gis/cloud-native/rasters/{record.id}/tilejson.json",
            "type": "application/json",
            "roles": ["tiles"],
            "title": "TileJSON",
        },
    }
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": f"sahool-{record.index_type}",
        "bbox": record.bbox,
        "geometry": None,
        "properties": {
            "datetime": dt,
            "sahool:tenant_id": record.tenant_id,
            "sahool:field_id": record.field_id,
            "sahool:raster_id": record.id,
            "sahool:index_type": record.index_type,
            "eo:cloud_cover": record.cloud_pct,
            "sahool:quality_score": record.quality_score,
            "gsd": record.resolution_m,
        },
        "assets": assets,
        "links": [
            {"rel": "self", "href": f"{api_base}/api/v1/gis/cloud-native/stac/items/{item_id}"},
            {
                "rel": "collection",
                "href": f"{api_base}/api/v1/gis/cloud-native/stac/collections/sahool-{record.index_type}",
            },
        ],
    }


def stac_collection(
    records: Iterable[RasterRegistryRecord], *, index_type: str | None = None, api_base: str = ""
) -> dict[str, Any]:
    records = list(records)
    idx = index_type or (records[0].index_type if records else "raster")
    bboxes = [r.bbox for r in records if isinstance(r.bbox, list) and len(r.bbox) == 4]
    extent_bbox = (
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
    dates = [_iso(r.product_date) for r in records if _iso(r.product_date)]
    interval = [[min(dates), max(dates)]] if dates else [[None, None]]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": f"sahool-{idx}",
        "title": f"SAHOOL {idx} raster products",
        "description": "DB-backed cloud-native raster registry collection.",
        "extent": {"spatial": {"bbox": extent_bbox}, "temporal": {"interval": interval}},
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


def mosaicjson_from_records(
    records: Iterable[RasterRegistryRecord], *, name: str, minzoom: int = 8, maxzoom: int = 18
) -> dict[str, Any]:
    tiles: dict[str, list[str]] = {}
    for rec in records:
        key = rec.scene_id or rec.id
        tiles.setdefault(str(key), []).append(rec.cog_url)
    return {
        "mosaicjson": "0.0.3",
        "name": name,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "tiles": tiles,
        "asset_type": "cog",
    }


def tilejson_for_cog(
    record: RasterRegistryRecord, *, tiler_base_url: str | None = None, tile_scale: int = 1
) -> dict[str, Any]:
    base = (tiler_base_url or os.getenv("TITILER_BASE_URL") or "/tiler").rstrip("/")
    cog = record.cog_url
    tiles = [f"{base}/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@{tile_scale}x?url={cog}"]
    return {
        "tilejson": "3.0.0",
        "name": f"{record.index_type}:{record.id}",
        "version": "1.0.0",
        "scheme": "xyz",
        "tiles": tiles,
        "minzoom": 8,
        "maxzoom": 18,
        "bounds": record.bbox,
        "attribution": "SAHOOL / source scene registry",
    }


def export_records_to_geoparquet(
    records: Iterable[dict[str, Any]], output_path: str | Path
) -> dict[str, Any]:
    """Write GeoParquet when optional deps exist; otherwise produce a JSONL fallback manifest.

    Production deployments should install geopandas+pyarrow.  The fallback keeps CI and
    local developer machines deterministic while clearly labelling that it is not a
    real GeoParquet file.
    """
    rows = list(records)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import geopandas as gpd  # type: ignore
        from shapely.geometry import shape  # type: ignore

        features = []
        for row in rows:
            geometry = row.get("geometry") or row.get("geom")
            props = {k: v for k, v in row.items() if k not in {"geometry", "geom"}}
            props["geometry"] = shape(geometry) if isinstance(geometry, dict) else geometry
            features.append(props)
        gdf = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")
        gdf.to_parquet(path, index=False)
        return {"format": "geoparquet", "path": str(path), "rows": len(rows), "fallback": False}
    except Exception as exc:  # noqa: BLE001
        fallback = path.with_suffix(path.suffix + ".jsonl")
        with fallback.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return {
            "format": "jsonl-fallback",
            "path": str(fallback),
            "rows": len(rows),
            "fallback": True,
            "reason": str(exc)[:240],
        }
