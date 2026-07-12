"""Raster-owned vegetation-index explorer boundary.

The former scalar band-math implementation duplicated raster-service kernels and
could accidentally be reused as operational evidence. RIV consolidation keeps
the tool id for compatibility but fails closed: callers must request a validated
Raster product carrying scene and quality lineage.
"""

from __future__ import annotations

from ..registry import Tool, ToolParam, register

_INDEX_OPTIONS = ("NDVI", "NDRE", "EVI", "MSAVI")


def compute(inp: dict) -> dict:
    index = str(inp.get("index") or "").upper()
    if index not in _INDEX_OPTIONS:
        raise ValueError(f"مؤشّر غير مدعوم: {index} — المتاح {_INDEX_OPTIONS}")
    return {
        "index": index,
        "value": None,
        "available": False,
        "owner_service": "raster-service",
        "reason": "validated_raster_product_required",
        "interpretation_ar": "الحساب الطيفي مملوك حصراً لخدمة Raster؛ اطلب منتجاً موثقاً بالمشهد والجودة.",
    }


register(
    Tool(
        id="vegetation_index_explorer",
        name_ar="مستكشف مؤشرات الغطاء النباتي",
        category="remote_sensing",
        description_ar="يعرض حدود ملكية المؤشر ويوجه إلى منتج Raster الموثق؛ لا ينفذ band-math محلياً.",
        params=[ToolParam("index", "select", "المؤشر", options=_INDEX_OPTIONS, default="NDVI")],
        compute=compute,
        result_unit_ar="منتج Raster موثق",
        tags=("استشعار", "مؤشر", "Raster"),
    )
)
