"""stac_vrt.py — جسر الاستيراد→المعالجة لمصادر STAC متعدّدة الملفّات.

Sentinel-2 L2A على Element84 (وأغلب STAC) يقدّم **COG منفصلاً لكلّ نطاق**
(red.tif, nir.tif, …)، بينما /process يتوقّع راستر واحداً متعدّد النطاقات +
فهارس أعداد. هذا المُولّد يبني VRT (XML) يكدّس النطاقات المنفصلة كـ-separate،
ويلفّ الروابط البعيدة بـ/vsicurl/ (قراءة بلا تنزيل، مناسب للمزوّد بلا مفتاح).
الناتج (مسار .vrt + خريطة الأسماء→الفهارس) يُمرَّر كـraster_url + bands لـ/process.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import suppress
from xml.sax.saxutils import escape

import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as copy_raster
from rasterio.vrt import WarpedVRT

logger = logging.getLogger("raster-service.stac_vrt")

# ترتيب أسماء النطاقات المدعومة في BandMapping (الفهرس = موضعها في الـVRT)
_BAND_ORDER = ["red", "nir", "green", "blue", "swir1", "swir2", "rededge", "scl"]


def _as_gdal_source(href: str) -> str:
    """يحوّل href إلى مصدر يقرؤه GDAL: http(s) → /vsicurl/؛ s3:// → /vsis3/."""
    if href.startswith(("http://", "https://")):
        return f"/vsicurl/{href}"
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://") :]
    return href.replace("file://", "")


def build_band_vrt(band_hrefs: dict[str, str], out_dir: str = "/tmp") -> tuple[str, dict[str, int]]:
    """يبني VRT يكدّس COGs المنفصلة لكلّ نطاق ويُرجِع (مسار_vrt، خريطة_فهارس).

    band_hrefs: {"red": url|path, "nir": ..., ...} — أسماء من _BAND_ORDER.
    يُرجِع (vrt_path, {band_name: index_1based}) جاهزة لـProcessRequest.bands.
    يرمي ValueError إن لم يوجد أيّ نطاق صالح أو تعذّر فتح النطاق الأوّل.

    The returned root VRT depends on sibling ``<stem>_band_N.vrt`` files and
    the original sources; it is not a standalone raster. Retain the whole
    bundle until all readers close, then remove the root and its sidecars.
    Partial bundles are removed if construction fails. This helper does not
    lift the Element84 production containment or certify provider calibration.
    """
    ordered = [(b, band_hrefs[b]) for b in _BAND_ORDER if band_hrefs.get(b)]
    # أيّ أسماء إضافيّة غير قياسيّة تُلحَق بعد القياسيّة
    for b, h in band_hrefs.items():
        if b not in _BAND_ORDER and h:
            ordered.append((b, h))
    if not ordered:
        raise ValueError("band_hrefs فارغة — لا نطاقات لبناء VRT")

    sources = [_as_gdal_source(h) for _, h in ordered]
    # The first band defines the target grid, not the grid of every source.
    with rasterio.open(sources[0]) as first:
        w, h, gt, crs = first.width, first.height, first.transform, first.crs
        if crs is None:
            raise ValueError("VRT target band has no CRS")
        wkt = crs.to_wkt()
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(os.path.abspath(out_dir), f"stac_stack_{uuid.uuid4().hex[:10]}")
    bands_xml = []
    index_map: dict[str, int] = {}
    created = []
    try:
        for i, ((name, _href), source) in enumerate(zip(ordered, sources, strict=True), start=1):
            aligned_path = f"{stem}_band_{i}.vrt"
            with rasterio.open(source) as src:
                if src.crs is None:
                    raise ValueError(f"VRT source band {name} has no CRS")
                # Preserve declared calibration as metadata. Do not infer a provider
                # scale or offset from digital numbers or a collection name.
                scale, offset = src.scales[0], src.offsets[0]
                source_nodata = src.nodatavals[0]
                with WarpedVRT(
                    src,
                    crs=crs,
                    transform=gt,
                    width=w,
                    height=h,
                    dtype="float32",
                    # GDAL >= 3.12 ignores a dataset mask when warp source
                    # nodata is configured. Keep that mask here; exclude the
                    # original numeric nodata separately after nearest sampling.
                    src_nodata=None,
                    nodata=float("nan"),
                    # Nearest preserves categorical SCL values and avoids inventing
                    # interpolated spectral samples in this conservative bridge.
                    resampling=Resampling.nearest,
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
    logger.info("بُني VRT من %d نطاق: %s", len(ordered), vrt_path)
    return vrt_path, index_map
