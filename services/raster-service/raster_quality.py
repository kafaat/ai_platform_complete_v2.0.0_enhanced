"""Raster indicator formulas and quality metadata helpers."""

from __future__ import annotations

INDICATOR_FORMULAS = {
    "ndvi": "(NIR - RED) / (NIR + RED)",
    "evi": "2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1)",
    "savi": "1.5 * (NIR - RED) / (NIR + RED + 0.5)",
    "ndwi": "(GREEN - NIR) / (GREEN + NIR)",
    "ndmi": "(NIR - SWIR1) / (NIR + SWIR1)",
    "gndvi": "(NIR - GREEN) / (NIR + GREEN)",
    "ndre": "(NIR - REDEDGE) / (NIR + REDEDGE)  # النيتروجين/الكلوروفيل (red-edge)",
    "reci": "(NIR / REDEDGE) - 1  # Red-edge chlorophyll index",
    "gci": "(NIR / GREEN) - 1  # Green chlorophyll index",
    "arvi": "(NIR - (2*RED - BLUE)) / (NIR + (2*RED - BLUE))",
    "sipi": "(NIR - BLUE) / (NIR - RED)",
    "nbr": "(NIR - SWIR2) / (NIR + SWIR2)",
    "ccci": "NDRE / NDVI  # Canopy chlorophyll content index",
    "msi": "SWIR1 / NIR  # Moisture Stress Index (الإجهاد المائي)",
    "msavi": "(2*NIR + 1 - sqrt((2*NIR+1)^2 - 8*(NIR-RED))) / 2  # Modified SAVI (L ذاتي)",
    "moisture": "(NIR - SWIR1) / (NIR + SWIR1)  # NDMI رطوبة المحتوى (للواجهة)",
    "fapar": "أساسها NDVI (علاقة تجريبيّة)",
    "vari": "(GREEN - RED) / (GREEN + RED - BLUE)",
    "gli": "(2*GREEN - RED - BLUE) / (2*GREEN + RED + BLUE)",
    "tgi": "GREEN - 0.39*RED - 0.61*BLUE",
    "bsi": "((SWIR2+RED)-(NIR+BLUE)) / ((SWIR2+RED)+(NIR+BLUE))",
    "bi": "sqrt((RED^2+GREEN^2)/2)",
    "bi2": "sqrt((RED^2+GREEN^2+NIR^2)/3)",
    "ndti": "(SWIR1-SWIR2)/(SWIR1+SWIR2)",
    "dbsi": "((SWIR1-GREEN)/(SWIR1+GREEN)) - NDVI",
    "ndsi": "(SWIR1-SWIR2)/(SWIR1+SWIR2)  # salinity — حرج لليمن",
    "satvi": "((SWIR1-RED)/(SWIR1+RED+L))*(1+L) - SWIR2/2",
}


def quality_from_cloud_pct(cloud_pct: float | None, *, masked: bool = True) -> dict:
    """Return a conservative 0..1 quality/confidence score for a raster layer/pixel."""
    if cloud_pct is None:
        return {
            "confidence": 0.55,
            "quality": "unknown",
            "reason": "cloud_quality_unavailable",
        }
    cp = max(0.0, min(100.0, float(cloud_pct)))
    score = max(0.0, min(1.0, 1.0 - (cp / 100.0)))
    if not masked:
        score = min(score, 0.65)
    if cp <= 5:
        label = "high"
    elif cp <= 20:
        label = "medium"
    elif cp <= 50:
        label = "low"
    else:
        label = "very_low"
    return {
        "confidence": round(score, 3),
        "quality": label,
        "cloud_pct": round(cp, 3),
        "reason": "field_aoi_scl_cloud_pct",
    }


def pixel_quality(layer: dict, value: float | None) -> dict:
    """Quality metadata for a single sampled indicator pixel."""
    if value is None:
        return {"confidence": 0.0, "quality": "nodata", "reason": "nodata_or_cloud_masked"}
    q = quality_from_cloud_pct(
        layer.get("cloud_pct"), masked=bool(layer.get("cloud_mask_applied", True))
    )
    if q["quality"] == "unknown" and layer.get("provider") in ("cdse", "sentinelhub", "element84"):
        q["reason"] = "provider_known_but_pixel_qa_unavailable"
    return q
