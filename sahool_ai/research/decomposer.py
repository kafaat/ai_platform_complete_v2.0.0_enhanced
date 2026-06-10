"""تفكيك الاستعلام الزراعي إلى استعلامات فرعيّة موجَّهة للمصادر.

Agronomic query decomposer: keyword-based (Arabic + English),
deterministic, no network calls.
"""

from __future__ import annotations

import re

from sahool_ai.research.models import SubQuery

# ── خريطة المناطق / Region detection map ───────────────────────────────────
_REGION_MAP: dict[str, str] = {
    "شمالي": "north_sector",
    "شمال": "north_sector",
    "north": "north_sector",
    "northern": "north_sector",
    "جنوبي": "south_sector",
    "جنوب": "south_sector",
    "south": "south_sector",
    "southern": "south_sector",
    "شرقي": "east_sector",
    "شرق": "east_sector",
    "east": "east_sector",
    "eastern": "east_sector",
    "غربي": "west_sector",
    "غرب": "west_sector",
    "west": "west_sector",
    "western": "west_sector",
}

# ── أنماط الكلمات المفتاحية / Keyword patterns ─────────────────────────────
# Each entry: (pattern_regex, query_type, primary_sources)
_PATTERNS: list[tuple[str, str, list[str]]] = [
    # 1. NDVI decline / انخفاض NDVI
    (
        r"ndvi|مؤشر\s*الغطاء|انخفض|تراجع\s*ndvi|ndvi\s*decline",
        "ndvi_analysis",
        ["sentinel_hub", "weather_api", "soil_sensors", "irrigation_logs"],
    ),
    # 2. Yield prediction / توقّع الإنتاج
    (
        r"yield|إنتاج|محصول|توقّع\s*الغلّة|غلّة|crop\s*yield",
        "yield_prediction",
        ["sentinel_hub", "weather_api", "soil_sensors"],
    ),
    # 3. Pest alert / تنبيه آفات
    (
        r"pest|آفة|آفات|حشرة|حشرات|تنبيه\s*آفة|pest\s*alert",
        "pest_alert",
        ["sentinel_hub", "weather_api"],
    ),
    # 4. Irrigation optimization / تحسين الري
    (
        r"irrigat|ري|سقي|مياه\s*الري|irrigation\s*optim|تحسين\s*الري",
        "irrigation_optimization",
        ["irrigation_logs", "soil_sensors", "weather_api"],
    ),
    # 5. Soil deficiency / نقص التربة
    (
        r"soil\s*deficien|نقص\s*التربة|نقص\s*المغذّيات|تربة|عناصر\s*غذائية",
        "soil_deficiency",
        ["soil_sensors", "weather_api"],
    ),
    # 6. Water stress / إجهاد مائي
    (
        r"water\s*stress|إجهاد\s*مائي|شحّ\s*المياه|جفاف|drought",
        "water_stress",
        ["soil_sensors", "weather_api", "irrigation_logs"],
    ),
    # 7. Disease / مرض
    (
        r"disease|مرض|أمراض|فطريّات|بكتيريا|pathogen",
        "disease_detection",
        ["sentinel_hub", "weather_api"],
    ),
    # 8. Weed / حشائش
    (
        r"weed|حشائش|حشيشة|أعشاب\s*ضارّة|weed\s*detection",
        "weed_detection",
        ["sentinel_hub"],
    ),
    # 9. Fertilizer / NPK / تسميد
    (
        r"fertiliz|تسميد|سماد|أسمدة|nitrogen|phospho|potassium|نيتروجين|فوسفور|بوتاسيوم|npk",
        "fertilizer_recommendation",
        ["soil_sensors", "weather_api"],
    ),
    # 10. Weather anomaly / شذوذ مناخي
    (
        r"weather\s*anomal|شذوذ\s*مناخي|طقس\s*غير\s*عادي|درجة\s*حرارة\s*مرتفعة|أمطار\s*غير\s*عادية|climate",
        "weather_anomaly",
        ["weather_api"],
    ),
]


def _detect_region(query: str) -> str | None:
    """استخراج المنطقة الجغرافية من نص الاستعلام."""
    q_lower = query.lower()
    for token, region in _REGION_MAP.items():
        if token.lower() in q_lower:
            return region
    return None


def _build_subqueries(
    query_type: str,
    sources: list[str],
    region: str | None,
    query: str,
) -> list[SubQuery]:
    """بناء قائمة الاستعلامات الفرعيّة لنمط محدَّد."""
    base_params: dict = {"query": query}
    if region:
        base_params["region"] = region

    sqs: list[SubQuery] = []
    for src in sources:
        params = dict(base_params)
        sqs.append(SubQuery(type=query_type, source=src, params=params))

    # Always append a RAG knowledge sub-query
    rag_params: dict = {"query": query, "collection": "agronomic_knowledge"}
    if region:
        rag_params["region"] = region
    sqs.append(SubQuery(type="knowledge_retrieval", source="qdrant_rag", params=rag_params))
    return sqs


def decompose_query(query: str) -> list[SubQuery]:
    """تفكيك استعلام زراعي إلى استعلامات فرعيّة موجَّهة للمصادر.

    Decomposes an agronomic query (Arabic or English) into a list of
    :class:`SubQuery` objects by keyword pattern matching.

    Args:
        query: نص الاستعلام (عربي أو إنجليزي).

    Returns:
        قائمة من :class:`SubQuery` مرتَّبة حسب المصدر.
        دائماً تشمل استعلام qdrant_rag للمعرفة.

    Example:
        >>> sqs = decompose_query("لماذا انخفض NDVI في القطاع الشمالي؟")
        >>> {sq.source for sq in sqs}
        {'sentinel_hub', 'weather_api', 'soil_sensors', 'irrigation_logs', 'qdrant_rag'}
    """
    region = _detect_region(query)
    q_lower = query.lower()

    matched: list[SubQuery] = []
    seen_types: set[str] = set()

    for pattern, q_type, sources in _PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            if q_type not in seen_types:
                seen_types.add(q_type)
                sqs = _build_subqueries(q_type, sources, region, query)
                # Avoid duplicate qdrant_rag
                for sq in sqs:
                    if sq.source == "qdrant_rag" and "qdrant_rag" in {m.source for m in matched}:
                        continue
                    matched.append(sq)

    if matched:
        return matched

    # ── Fallback: generic decomposition ────────────────────────────────────
    fallback_sources = ["sentinel_hub", "weather_api"]
    fallback = _build_subqueries("generic_analysis", fallback_sources, region, query)
    return fallback
