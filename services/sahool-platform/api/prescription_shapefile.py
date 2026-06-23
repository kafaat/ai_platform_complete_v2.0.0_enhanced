"""api/prescription_shapefile.py — بناء Shapefile من مناطق الوصفة (اقتباس CultiWise، تصدير آلة).

يحوّل مناطق الوصفة (v95: geometry GeoJSON + rate + unit) إلى أرشيف ZIP يحوي Shapefile
(.shp/.shx/.dbf + .prj WGS84) جاهز لمُتحكِّمات الآلات الزراعيّة (John Deere/Amazone/Trimble…).
نقيّ (لا FastAPI/DB) ليُختبَر وحدويّاً — نظير ``nl_sql_validate``. يستعمل ``pyshp`` (نقيّ-Python،
بلا GDAL). صدق: يرفع عند غياب هندسة صالحة (لا shapefile فارغ مُلفَّق). ISOXML مؤجَّل (TODO موثَّق).
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile

import shapefile  # pyshp

# تعريف نظام الإحداثيّات WGS84 (.prj) — تتطلّبه المُتحكِّمات لتحديد المواقع بدقّة.
_WGS84_PRJ = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
)


def _rings_from_geometry(geom: object) -> list[list[list[float]]]:
    """يستخرج حلقات [[lng,lat],...] من GeoJSON Polygon/MultiPolygon (ترتيب shapefile = [x,y] = [lng,lat]).

    يرفع ValueError عند نوع غير مدعوم/هندسة غير صالحة.
    """
    if not isinstance(geom, dict):
        raise ValueError("هندسة غير صالحة")
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list):
        return [list(ring) for ring in coords]  # [خارجيّة, ثقوب…]
    if gtype == "MultiPolygon" and isinstance(coords, list):
        rings: list[list[list[float]]] = []
        for poly in coords:
            for ring in poly:
                rings.append(list(ring))
        if not rings:
            raise ValueError("MultiPolygon فارغ")
        return rings
    raise ValueError(f"نوع هندسة غير مدعوم: {gtype}")


def build_shapefile_zip(name: str, product_type: str, zones: list[dict]) -> bytes:
    """يبني أرشيف ZIP (Shapefile) من مناطق الوصفة. يرفع ValueError إن لا منطقة ذات هندسة صالحة.

    zones: ``[{geometry: GeoJSON Polygon/MultiPolygon, rate: float, unit: str}, …]``.
    حقول DBF (أسماء ≤10 حروف): zone · rate · unit · product · rx_name.
    """
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "prescription")
        writer = shapefile.Writer(base, shapeType=shapefile.POLYGON)
        writer.field("zone", "N", size=6)
        writer.field("rate", "N", size=18, decimal=4)
        writer.field("unit", "C", size=24)
        writer.field("product", "C", size=16)
        writer.field("rx_name", "C", size=48)

        written = 0
        for i, z in enumerate(zones or []):
            try:
                rings = _rings_from_geometry((z or {}).get("geometry"))
            except (ValueError, AttributeError):
                continue  # تخطّ منطقة بهندسة غير صالحة (لا فشل كامل)
            writer.poly(rings)
            rate = (z or {}).get("rate")
            writer.record(
                i,
                float(rate) if isinstance(rate, (int, float)) else 0.0,
                str((z or {}).get("unit") or "")[:24],
                str(product_type or "")[:16],
                str(name or "")[:48],
            )
            written += 1
        writer.close()

        if written == 0:
            raise ValueError("لا مناطق ذات هندسة صالحة للتصدير")

        with open(base + ".prj", "w", encoding="utf-8") as fh:
            fh.write(_WGS84_PRJ)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for ext in (".shp", ".shx", ".dbf", ".prj"):
                zf.write(base + ext, arcname="prescription" + ext)
        return buf.getvalue()
