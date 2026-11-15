"""stac_vrt.py — جسر الاستيراد→المعالجة لمصادر STAC متعدّدة الملفّات.

Sentinel-2 L2A على Element84 (وأغلب STAC) يقدّم **COG منفصلاً لكلّ نطاق**
(red.tif, nir.tif, …)، بينما /process يتوقّع راستر واحداً متعدّد النطاقات +
فهارس أعداد. هذا المُولّد يبني VRT (XML) يكدّس النطاقات المنفصلة كـ-separate،
ويلفّ الروابط البعيدة بـ/vsicurl/ (قراءة بلا تنزيل، مناسب للمزوّد بلا مفتاح).
الناتج (مسار .vrt + خريطة الأسماء→الفهارس) يُمرَّر كـraster_url + bands لـ/process.
"""

from __future__ import annotations

import logging
import math
import os
import uuid
from contextlib import ExitStack, suppress
from xml.sax.saxutils import escape

import rasterio
from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.features import geometry_window
from rasterio.shutil import copy as copy_raster
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom

logger = logging.getLogger("raster-service.stac_vrt")

# ترتيب أسماء النطاقات المدعومة في BandMapping (الفهرس = موضعها في الـVRT)
_BAND_ORDER = ["red", "nir", "green", "blue", "swir1", "swir2", "rededge", "scl"]


def _validate_declared_crs(item: dict, asset: dict, src) -> None:
    """Check each effective STAC projection declaration against the actual TIFF.

    Asset properties override item properties. Missing/null declarations do not
    invent a CRS; the existing TIFF CRS requirement still applies. Reprojection
    remains supported when a source truthfully declares a different target CRS.
    """
    properties = item.get("properties", {})
    for key in ("proj:epsg", "proj:code", "proj:wkt2", "proj:projjson"):
        # epsg is the legacy spelling of code. An asset declaration using
        # either spelling supersedes the item's authority-code declaration.
        authority_override = key in {"proj:epsg", "proj:code"} and any(
            name in asset for name in ("proj:epsg", "proj:code")
        )
        value = asset.get(key) if authority_override else asset.get(key, properties.get(key))
        if value is None:
            continue
        try:
            if key == "proj:epsg":
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError("invalid EPSG declaration")
                declared = rasterio.crs.CRS.from_epsg(value)
            elif key == "proj:projjson":
                if not isinstance(value, dict):
                    raise ValueError("invalid PROJJSON declaration")
                declared = rasterio.crs.CRS.from_dict(value)
            else:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("invalid CRS declaration")
                declared = rasterio.crs.CRS.from_user_input(value)
        except (ValueError, TypeError, OverflowError, rasterio.errors.CRSError) as exc:
            raise ValueError(f"Invalid STAC {key} declaration") from exc
        if declared != src.crs:
            raise ValueError(f"STAC {key} conflicts with TIFF CRS")


def _as_gdal_source(href: str) -> str:
    """يحوّل href إلى مصدر يقرؤه GDAL: http(s) → /vsicurl/؛ s3:// → /vsis3/."""
    if href.startswith(("http://", "https://")):
        return f"/vsicurl/{href}"
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://") :]
    return href.replace("file://", "")


def _stac_calibration(
    item: dict, href: str, src, *, categorical: bool = False
) -> tuple[float, float]:
    """Resolve declared coefficients for one exact asset, never infer DN semantics.

    Legacy Earth Search COGs have documented inconsistent BOA metadata (#66).
    Reject that collection regardless of the flag. Other explicit declarations
    support explicit per-asset calibration. Production C1 processing additionally
    requires TIFF agreement and its strict scene contract. No collection-wide
    scale/offset is assumed; legacy containment remains in force.
    """
    if not item.get("id") or not item.get("collection"):
        raise ValueError("STAC calibration requires item and collection identity")
    if item["collection"] == "sentinel-2-l2a":
        raise ValueError("Legacy STAC collection radiometry remains unresolved")
    matches = [asset for asset in item.get("assets", {}).values() if asset.get("href") == href]
    if len(matches) != 1 or src.count != 1:
        raise ValueError("STAC calibration requires one matching single-band asset")
    _validate_declared_crs(item, matches[0], src)
    bands = matches[0].get("raster:bands")
    if not isinstance(bands, list) or len(bands) != 1 or not isinstance(bands[0], dict):
        raise ValueError("STAC calibration requires one raster:bands declaration")
    if categorical:
        if any(
            bands[0].get(key, default) != default for key, default in (("scale", 1), ("offset", 0))
        ):
            raise ValueError("Categorical STAC band must not carry reflectance calibration")
        if (src.scales[0], src.offsets[0]) != (1.0, 0.0):
            raise ValueError("Categorical TIFF band must not carry reflectance calibration")
        return 1.0, 0.0
    calibration = []
    for key in ("scale", "offset"):
        value = bands[0].get(key)
        try:
            finite = (
                not isinstance(value, bool)
                and isinstance(value, (float, int))
                and math.isfinite(value)
            )
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError(f"STAC calibration requires finite explicit {key}")
        calibration.append(float(value))
    scale, offset = calibration
    if scale <= 0:
        raise ValueError("STAC reflectance scale must be positive")
    flag = item.get("properties", {}).get("earthsearch:boa_offset_applied")
    if flag is not None and not isinstance(flag, bool):
        raise ValueError("STAC BOA flag must be a boolean when present")
    if flag is True and offset != 0:
        raise ValueError("STAC BOA flag conflicts with nonzero asset offset")
    declared_tiff = (src.scales[0], src.offsets[0])
    if declared_tiff != (1.0, 0.0) and declared_tiff != (scale, offset):
        raise ValueError("STAC calibration conflicts with TIFF calibration")
    return scale, offset


def _native_spacing_m(src) -> float:
    """C1 delivery grids are north-up, square, and projected in metres."""
    if (
        not src.crs.is_projected
        or not math.isclose(src.crs.linear_units_factor[1], 1)
        or src.transform.b != 0
        or src.transform.d != 0
        or src.transform.a <= 0
        or not math.isclose(src.transform.a, -src.transform.e)
    ):
        raise ValueError("Expected a north-up square metric C1 grid")
    return src.transform.a


def _masked_native_source(src, path: str) -> None:
    """Expose the union of the dataset mask and numeric nodata before averaging.

    GDAL versions differ in whether the warp honours an explicit mask together
    with source nodata. Map mask-invalid native samples to the numeric sentinel
    on a 1:1 source VRT, then have the warp ignore that one sentinel.
    """
    nodata = src.nodata if src.nodata is not None else float("nan")
    source = src.name if src.name.startswith("/vsi") else os.path.abspath(src.name)
    gt = ", ".join(str(value) for value in src.transform.to_gdal())
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f'<VRTDataset rasterXSize="{src.width}" rasterYSize="{src.height}">'
            f"<SRS>{escape(src.crs.to_wkt())}</SRS><GeoTransform>{gt}</GeoTransform>"
            f'<VRTRasterBand dataType="Float32" band="1"><NoDataValue>{nodata}</NoDataValue>'
            f'<ComplexSource><SourceFilename relativeToVRT="0">{escape(source)}</SourceFilename>'
            "<SourceBand>1</SourceBand><UseMaskBand>true</UseMaskBand></ComplexSource>"
            "</VRTRasterBand></VRTDataset>"
        )


def build_band_vrt(
    band_hrefs: dict[str, str],
    out_dir: str = "/tmp",
    *,
    stac_item: dict | None = None,
    clip_geometry: dict | None = None,
    max_pixels: int | None = None,
    require_tiff_calibration: bool = False,
    target_band: str | None = None,
    native_band_resolution_m: dict[str, float] | None = None,
) -> tuple[str, dict[str, int]]:
    """يبني VRT يكدّس COGs المنفصلة لكلّ نطاق ويُرجِع (مسار_vrt، خريطة_فهارس).

    band_hrefs: {"red": url|path, "nir": ..., ...} — أسماء من _BAND_ORDER.
    يُرجِع (vrt_path, {band_name: index_1based}) جاهزة لـProcessRequest.bands.
    يرمي ValueError إن لم يوجد أيّ نطاق صالح أو تعذّر فتح النطاق الأوّل.

    The returned root VRT depends on sibling ``<stem>_band_N.vrt`` files and
    the original sources; it is not a standalone raster. Retain the whole
    bundle until all readers close, then remove the root and its sidecars.
    Partial bundles are removed if construction fails. This helper does not
    lift the Element84 production containment or certify provider calibration.
    ``stac_item`` optionally supplies exact asset-bound raster:bands calibration;
    missing/contradictory metadata is rejected. The production C1 caller requires
    matching TIFF metadata and a polygon-limited pixel budget.
    Without it, only existing TIFF metadata is preserved (not guessed).
    """
    ordered = [(b, band_hrefs[b]) for b in _BAND_ORDER if band_hrefs.get(b)]
    # أيّ أسماء إضافيّة غير قياسيّة تُلحَق بعد القياسيّة
    for b, h in band_hrefs.items():
        if b not in _BAND_ORDER and h:
            ordered.append((b, h))
    if not ordered:
        raise ValueError("band_hrefs فارغة — لا نطاقات لبناء VRT")

    sources = [_as_gdal_source(h) for _, h in ordered]
    # Preserve the legacy grid for callers without a mixed-resolution measurement.
    if target_band is not None and target_band not in dict(ordered):
        raise ValueError(f"Missing VRT target band {target_band}")
    target_source = _as_gdal_source(band_hrefs[target_band]) if target_band else sources[0]
    with rasterio.open(target_source) as first:
        w, h, gt, crs = first.width, first.height, first.transform, first.crs
        if crs is None:
            raise ValueError("VRT target band has no CRS")
        if clip_geometry is not None:
            geometry = (
                clip_geometry.get("geometry")
                if clip_geometry.get("type") == "Feature"
                else clip_geometry
            )
            if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                raise ValueError("STAC processing requires a polygon clip")
            try:
                window = geometry_window(first, [transform_geom("EPSG:4326", crs, geometry)])
            except WindowError as exc:
                raise ValueError("STAC processing clip does not intersect the target band") from exc
            w, h, gt = (
                int(window.width),
                int(window.height),
                first.window_transform(window),
            )
        if max_pixels is not None and w * h > max_pixels:
            raise ValueError("STAC processing clip exceeds pixel budget")
        wkt = crs.to_wkt()
        if target_band:
            target_spacing = _native_spacing_m(first)
            if not math.isclose(target_spacing, 20):
                raise ValueError("Expected native 20 m C1 target band")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(os.path.abspath(out_dir), f"stac_stack_{uuid.uuid4().hex[:10]}")
    bands_xml = []
    index_map: dict[str, int] = {}
    created = []
    resolutions = {}
    try:
        for i, ((name, _href), source) in enumerate(zip(ordered, sources, strict=True), start=1):
            aligned_path = f"{stem}_band_{i}.vrt"
            with ExitStack() as stack:
                src = stack.enter_context(rasterio.open(source))
                if src.crs is None:
                    raise ValueError(f"VRT source band {name} has no CRS")
                # Preserve declared calibration as metadata. Do not infer a provider
                # scale or offset from digital numbers or a collection name.
                scale, offset = (
                    _stac_calibration(stac_item, _href, src, categorical=name == "scl")
                    if stac_item is not None
                    else (src.scales[0], src.offsets[0])
                )
                if require_tiff_calibration:
                    if (src.scales[0], src.offsets[0]) != (scale, offset):
                        raise ValueError("C1 TIFF calibration must agree with its STAC asset")
                    declaration = next(
                        a["raster:bands"][0]
                        for a in stac_item["assets"].values()
                        if a.get("href") == _href
                    )
                    if (
                        declaration.get("nodata") != src.nodatavals[0]
                        or declaration.get("data_type") != src.dtypes[0]
                    ):
                        raise ValueError("C1 TIFF sample declaration conflicts with STAC asset")
                source_nodata = src.nodatavals[0]
                warp_source = src
                warp_nodata = None
                resampling = Resampling.nearest
                if native_band_resolution_m is not None or target_band is not None:
                    spacing = _native_spacing_m(src)
                    resolutions[name] = spacing
                    if require_tiff_calibration and "spatial_resolution" in declaration:
                        if declaration["spatial_resolution"] != spacing:
                            raise ValueError("C1 TIFF resolution conflicts with STAC asset")
                if target_band:
                    expected_spacing = 10 if name in {"red", "nir", "green", "blue"} else 20
                    if src.crs != crs or not math.isclose(spacing, expected_spacing):
                        raise ValueError(f"Unexpected native C1 grid for {name}")
                    if name != "scl" and spacing < target_spacing:
                        native_path = f"{stem}_band_{i}_native.vrt"
                        created.append(native_path)
                        _masked_native_source(src, native_path)
                        warp_source = stack.enter_context(rasterio.open(native_path))
                        warp_nodata = warp_source.nodata
                        resampling = Resampling.average
                        # The warp already excluded the sentinel in native samples.
                        source_nodata = float("nan")
                with WarpedVRT(
                    warp_source,
                    crs=crs,
                    transform=gt,
                    width=w,
                    height=h,
                    dtype="float32",
                    # Nearest preserves the mask first, then excludes numeric nodata
                    # below. Average consumes both via the native source wrapper.
                    src_nodata=warp_nodata,
                    nodata=float("nan"),
                    resampling=resampling,
                ) as aligned:
                    created.append(aligned_path)
                    copy_raster(aligned, aligned_path, driver="VRT")
            index_map[name] = i
            bands_xml.append(
                f'  <VRTRasterBand dataType="Float32" band="{i}">\n'
                f"    <NoDataValue>nan</NoDataValue>\n"
                f"    <Scale>{scale}</Scale><Offset>{offset}</Offset>\n"
                f"    <ComplexSource>\n"
                f'      <SourceFilename relativeToVRT="0">{escape(aligned_path)}</SourceFilename>\n'
                f"      <SourceBand>1</SourceBand><NODATA>{source_nodata if source_nodata is not None else 'nan'}</NODATA>\n"
                f'      <SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>\n'
                f'      <DstRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>\n'
                f"    </ComplexSource>\n"
                f"  </VRTRasterBand>"
            )
        gt6 = f"{gt.c}, {gt.a}, {gt.b}, {gt.f}, {gt.d}, {gt.e}"
        xml = (
            f'<VRTDataset rasterXSize="{w}" rasterYSize="{h}">\n'
            f"  <SRS>{escape(wkt)}</SRS>\n"
            f"  <GeoTransform>{gt6}</GeoTransform>\n" + "\n".join(bands_xml) + "\n</VRTDataset>\n"
        )
        vrt_path = f"{stem}.vrt"
        created.append(vrt_path)
        with open(vrt_path, "w", encoding="utf-8") as f:
            f.write(xml)
    except Exception:
        for path in created:
            with suppress(OSError):
                os.unlink(path)
        raise
    if native_band_resolution_m is not None:
        native_band_resolution_m.update(resolutions)
    logger.info("بُني VRT من %d نطاق: %s", len(ordered), vrt_path)
    return vrt_path, index_map
