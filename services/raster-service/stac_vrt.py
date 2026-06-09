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
from xml.sax.saxutils import escape

import rasterio

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
    """
    ordered = [(b, band_hrefs[b]) for b in _BAND_ORDER if band_hrefs.get(b)]
    # أيّ أسماء إضافيّة غير قياسيّة تُلحَق بعد القياسيّة
    for b, h in band_hrefs.items():
        if b not in _BAND_ORDER and h:
            ordered.append((b, h))
    if not ordered:
        raise ValueError("band_hrefs فارغة — لا نطاقات لبناء VRT")

    sources = [_as_gdal_source(h) for _, h in ordered]
    # اقرأ الأبعاد/الإسقاط/التحويل من النطاق الأوّل (كلّها بنفس الشبكة في L2A)
    with rasterio.open(sources[0]) as s0:
        w, h = s0.width, s0.height
        gt = s0.transform
        wkt = s0.crs.to_wkt() if s0.crs else ""
        dtype = s0.dtypes[0]
    gdal_dtype = {
        "uint8": "Byte",
        "uint16": "UInt16",
        "int16": "Int16",
        "uint32": "UInt32",
        "int32": "Int32",
        "float32": "Float32",
        "float64": "Float64",
    }.get(str(dtype), "Float32")

    bands_xml = []
    index_map: dict[str, int] = {}
    for i, (name, src) in enumerate(zip([b for b, _ in ordered], sources, strict=True), start=1):
        index_map[name] = i
        bands_xml.append(
            f'  <VRTRasterBand dataType="{gdal_dtype}" band="{i}">\n'
            f"    <SimpleSource>\n"
            f'      <SourceFilename relativeToVRT="0">{escape(src)}</SourceFilename>\n'
            f"      <SourceBand>1</SourceBand>\n"
            f'      <SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>\n'
            f'      <DstRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/>\n'
            f"    </SimpleSource>\n"
            f"  </VRTRasterBand>"
        )
    gt6 = f"{gt.c}, {gt.a}, {gt.b}, {gt.f}, {gt.d}, {gt.e}"
    xml = (
        f'<VRTDataset rasterXSize="{w}" rasterYSize="{h}">\n'
        f"  <SRS>{escape(wkt)}</SRS>\n"
        f"  <GeoTransform>{gt6}</GeoTransform>\n" + "\n".join(bands_xml) + "\n</VRTDataset>\n"
    )
    os.makedirs(out_dir, exist_ok=True)
    vrt_path = os.path.join(out_dir, f"stac_stack_{uuid.uuid4().hex[:10]}.vrt")
    with open(vrt_path, "w", encoding="utf-8") as f:
        f.write(xml)
    logger.info("بُني VRT من %d نطاق: %s", len(ordered), vrt_path)
    return vrt_path, index_map
