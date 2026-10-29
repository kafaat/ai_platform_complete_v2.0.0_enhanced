"""Strict, bounded processing for Earth Search v1 Sentinel-2 Collection 1.

Legacy COGs remain contained: their BOA flag and asset offset are not reliable.
Only catalogue-selected C1 identities, exact provider assets and explicit matching
STAC/TIFF calibration are eligible. This does not repair historical products.
"""

from __future__ import annotations

import math
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import radiometry_containment
import raster_api_models as models
import stac_search

C1_COLLECTION = "sentinel-2-c1-l2a"
C1_HOST = "e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"
BANDS = {
    "red": "B04",
    "nir": "B08",
    "green": "B03",
    "blue": "B02",
    "rededge": "B05",
    "swir1": "B11",
    "swir2": "B12",
    "scl": "SCL",
}


def validate_c1_scene(scene: dict, *, entry_point: str) -> dict:
    """Validate a server-fetched scene before any GDAL open; return exact context."""
    context = scene.get("radiometry_context") or {}
    item_id = scene.get("item_id")
    hrefs = {k: v for k, v in (scene.get("bands_urls") or {}).items() if v}
    try:
        if context.get("collection") != C1_COLLECTION or context.get("id") != item_id:
            raise ValueError("collection_or_item")
        if not isinstance(item_id, str) or not re.fullmatch(
            r"S2[ABC]_T\d{2}[A-Z]{3}_\d{8}T\d{6}_L2A", item_id
        ):
            raise ValueError("item_identity")
        props = context.get("properties", {})
        flag = props.get("earthsearch:boa_offset_applied")
        if flag is not None and not isinstance(flag, bool):
            raise ValueError("invalid_boa_flag")
        baseline = props.get("s2:processing_baseline")
        if not isinstance(baseline, str) or not re.fullmatch(r"\d{2}\.\d{2}", baseline):
            raise ValueError("baseline_identity")
        if baseline < "05.00" or baseline == "05.09":
            raise ValueError("unsupported_baseline")
        if not scene.get("datetime") or props.get("datetime") != scene["datetime"]:
            raise ValueError("capture_identity")
        selected = stac_search.band_urls_from_assets(context.get("assets", {}))
        if set(hrefs) != set(BANDS) or hrefs != selected:
            raise ValueError("asset_identity")
        assets = context["assets"]
        for name, href in hrefs.items():
            parsed = urlsplit(href)
            if (
                parsed.scheme != "https"
                or parsed.netloc != C1_HOST
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("asset_origin")
            if not parsed.path.startswith(f"/{C1_COLLECTION}/") or not parsed.path.endswith(
                f"/{item_id}/{BANDS[name]}.tif"
            ):
                raise ValueError("asset_path")
            matching = [v for v in assets.values() if v.get("href") == href]
            if len(matching) != 1:
                raise ValueError("asset_ambiguity")
            asset = matching[0]
            bands = asset.get("raster:bands")
            if not isinstance(bands, list) or len(bands) != 1:
                raise ValueError("band_declaration")
            if name != "scl":
                if "reflectance" not in asset.get("roles", []):
                    raise ValueError("asset_role")
                for key in ("scale", "offset"):
                    value = bands[0].get(key)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                    ):
                        raise ValueError("calibration_missing")
                if bands[0]["scale"] <= 0:
                    raise ValueError("calibration_scale")
            if (
                props.get("earthsearch:boa_offset_applied") is True
                and bands[0].get("offset", 0) != 0
            ):
                raise ValueError("contradictory_boa")
        return context
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        radiometry_containment.reject_element84_vrt(hrefs, entry_point=entry_point)


def process_c1_scene(
    scene: dict,
    index: str,
    field: str,
    tenant: str,
    geometry_revision,
    clip: dict | None,
    apply_cloud_mask: bool,
    jid: str,
    *,
    run_processing,
    out_dir: str,
    entry_point: str,
) -> None:
    """Keep VRT sidecars alive through the synchronous processing core only."""
    context = validate_c1_scene(scene, entry_point=entry_point)
    if not tenant or not field or not clip or not apply_cloud_mask or index == "truecolor":
        radiometry_containment.reject_element84_vrt(
            scene.get("bands_urls"), entry_point=entry_point
        )
    from stac_vrt import build_band_vrt

    with TemporaryDirectory(prefix="stac_c1_", dir=out_dir) as directory:
        try:
            path, mapping = build_band_vrt(
                scene["bands_urls"],
                directory,
                stac_item=context,
                clip_geometry=clip,
                max_pixels=1_000_000,
                require_tiff_calibration=True,
            )
        except ValueError:
            radiometry_containment.reject_element84_vrt(
                scene.get("bands_urls"), entry_point=entry_point
            )
        request = models.ProcessRequest(
            tenant_id=tenant,
            field_id=field,
            raster_url=path,
            indicator=models.IndicatorKind(index),
            source_format=models.SourceFormat.sentinel2_l2a,
            bands=models.BandMapping(**mapping),
            clip_polygon_geojson=clip,
            apply_cloud_mask=True,
            raw_qa_required=True,
            scene_id=scene["item_id"],
            capture_datetime=scene["datetime"],
            provider="element84",
            geometry_revision=geometry_revision,
        )
        run_processing(jid, request)
