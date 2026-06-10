"""موصّلات بيانات وهميّة (Mock) لخطّ أبحاث SAHOOL الزراعيّة.

Mock data connectors for the SAHOOL Agronomic Research Pipeline.
All connectors are deterministic and accept injectable params for testing.
No real network calls are made.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

from sahool_ai.research.models import SubQuery

logger = logging.getLogger(__name__)

# ── Mock Connector Functions ────────────────────────────────────────────────


def sentinel_hub_ndvi(params: dict, timeout: float = 10.0) -> dict:
    """جلب بيانات NDVI من Sentinel Hub (وهميّ / Mock).

    Args:
        params: معاملات الاستعلام (region, query, …).
        timeout: مهلة الاتصال بالثواني (غير مستخدمة في النسخة الوهمية).

    Returns:
        dict بمفاتيح: values, trend, change_pct, dates.
    """
    region = params.get("region", "unknown")
    # Deterministic mock data keyed by region
    _region_data: dict[str, dict] = {
        "north_sector": {
            "values": [0.72, 0.68, 0.61, 0.54, 0.49],
            "trend": "declining",
            "change_pct": -32.0,
            "dates": ["2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
        },
        "south_sector": {
            "values": [0.65, 0.66, 0.65, 0.64, 0.63],
            "trend": "stable",
            "change_pct": -3.1,
            "dates": ["2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
        },
        "east_sector": {
            "values": [0.55, 0.58, 0.62, 0.67, 0.70],
            "trend": "improving",
            "change_pct": 27.3,
            "dates": ["2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
        },
        "west_sector": {
            "values": [0.60, 0.57, 0.55, 0.53, 0.51],
            "trend": "declining",
            "change_pct": -15.0,
            "dates": ["2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
        },
    }
    return _region_data.get(
        region,
        {
            "values": [0.60, 0.58, 0.56],
            "trend": "declining",
            "change_pct": -6.7,
            "dates": ["2026-05-01", "2026-05-15", "2026-05-29"],
        },
    )


def weather_api(params: dict, timeout: float = 10.0) -> dict:
    """جلب بيانات الطقس (وهميّ / Mock).

    Args:
        params: معاملات الاستعلام (region, query, …).
        timeout: مهلة الاتصال بالثواني.

    Returns:
        dict بمفاتيح: rainfall_mm, avg_temp_c, anomalies.
    """
    region = params.get("region", "unknown")
    _weather_data: dict[str, dict] = {
        "north_sector": {
            "rainfall_mm": 12.0,
            "avg_temp_c": 34.5,
            "anomalies": [
                {"type": "drought", "severity": "high"},
                {"type": "heat_wave", "severity": "medium"},
            ],
        },
        "south_sector": {
            "rainfall_mm": 55.0,
            "avg_temp_c": 29.0,
            "anomalies": [],
        },
        "east_sector": {
            "rainfall_mm": 90.0,
            "avg_temp_c": 26.0,
            "anomalies": [{"type": "above_average_rain", "severity": "low"}],
        },
        "west_sector": {
            "rainfall_mm": 35.0,
            "avg_temp_c": 31.0,
            "anomalies": [{"type": "below_average_rain", "severity": "medium"}],
        },
    }
    return _weather_data.get(
        region,
        {
            "rainfall_mm": 40.0,
            "avg_temp_c": 30.0,
            "anomalies": [],
        },
    )


def soil_sensors(params: dict, timeout: float = 10.0) -> dict:
    """جلب بيانات مستشعرات التربة (وهميّ / Mock).

    Args:
        params: معاملات الاستعلام.
        timeout: مهلة الاتصال بالثواني.

    Returns:
        dict بمفاتيح: moisture_pct, ph, npk (n, p, k).
    """
    region = params.get("region", "unknown")
    _soil_data: dict[str, dict] = {
        "north_sector": {
            "moisture_pct": 18.0,
            "ph": 7.8,
            "npk": {"n": 12.0, "p": 8.0, "k": 95.0},
        },
        "south_sector": {
            "moisture_pct": 35.0,
            "ph": 6.8,
            "npk": {"n": 28.0, "p": 20.0, "k": 180.0},
        },
        "east_sector": {
            "moisture_pct": 42.0,
            "ph": 6.5,
            "npk": {"n": 35.0, "p": 25.0, "k": 210.0},
        },
        "west_sector": {
            "moisture_pct": 25.0,
            "ph": 7.2,
            "npk": {"n": 20.0, "p": 15.0, "k": 140.0},
        },
    }
    return _soil_data.get(
        region,
        {
            "moisture_pct": 28.0,
            "ph": 7.0,
            "npk": {"n": 22.0, "p": 14.0, "k": 150.0},
        },
    )


def irrigation_logs(params: dict, timeout: float = 10.0) -> dict:
    """جلب سجلّات الري (وهميّ / Mock).

    Args:
        params: معاملات الاستعلام.
        timeout: مهلة الاتصال بالثواني.

    Returns:
        dict بمفاتيح: scheduled_events, actual_events, missed_days, adherence_pct.
    """
    region = params.get("region", "unknown")
    _logs_data: dict[str, dict] = {
        "north_sector": {
            "scheduled_events": 14,
            "actual_events": 6,
            "missed_days": [
                "2026-05-03",
                "2026-05-07",
                "2026-05-10",
                "2026-05-14",
                "2026-05-17",
                "2026-05-21",
                "2026-05-24",
                "2026-05-28",
            ],
            "adherence_pct": 42.9,
        },
        "south_sector": {
            "scheduled_events": 14,
            "actual_events": 13,
            "missed_days": ["2026-05-20"],
            "adherence_pct": 92.9,
        },
        "east_sector": {
            "scheduled_events": 14,
            "actual_events": 14,
            "missed_days": [],
            "adherence_pct": 100.0,
        },
        "west_sector": {
            "scheduled_events": 14,
            "actual_events": 10,
            "missed_days": ["2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
            "adherence_pct": 71.4,
        },
    }
    return _logs_data.get(
        region,
        {
            "scheduled_events": 14,
            "actual_events": 10,
            "missed_days": ["2026-05-10", "2026-05-17", "2026-05-24"],
            "adherence_pct": 71.4,
        },
    )


def qdrant_rag(params: dict, timeout: float = 10.0) -> dict:
    """استرجاع المعرفة من قاعدة Qdrant (وهميّ / Mock).

    Args:
        params: معاملات الاستعلام (query, collection, region, …).
        timeout: مهلة الاتصال بالثواني.

    Returns:
        dict بمفاتيح: documents, sources, confidence.
    """
    return {
        "documents": [
            "انخفاض NDVI يرتبط ارتباطاً وثيقاً بشحّ المياه وارتفاع درجات الحرارة.",
            "انخفاض رطوبة التربة دون 20% يُعيق امتصاص النيتروجين ويُضعف الغطاء النباتي.",
            "عجز الأمطار عن 80 مم/شهر يستدعي زيادة دورات الري الاصطناعي.",
            "التأخّر في الري أكثر من 3 أيام يُسرّع تراجع NDVI خلال موسم الجفاف.",
        ],
        "sources": [
            "agronomic_guidelines_v3",
            "yemen_field_trials_2025",
            "fao_irrigation_manual",
        ],
        "confidence": 0.82,
    }


# ── Connector Registry ──────────────────────────────────────────────────────
CONNECTORS: dict[str, Callable[..., dict]] = {
    "sentinel_hub": sentinel_hub_ndvi,
    "weather_api": weather_api,
    "soil_sensors": soil_sensors,
    "irrigation_logs": irrigation_logs,
    "qdrant_rag": qdrant_rag,
}

# ── Simple File-Based Cache Helper ─────────────────────────────────────────
# Cache is disabled by default; enable by passing use_cache=True.
_CACHE: dict[str, dict] = {}  # in-memory cache (deterministic, no FS writes)


def _cache_key(source: str, params: dict) -> str:
    """توليد مفتاح كاش حتميّ من المصدر والمعاملات."""
    raw = json.dumps({"source": source, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def retrieve_all(
    subqueries: list[SubQuery],
    use_cache: bool = False,
) -> dict[str, dict]:
    """جلب البيانات من جميع المصادر المحدَّدة في الاستعلامات الفرعيّة.

    يُرجع نتائج جزئيّة إذا فشل أحد المصادر (مع تسجيل الخطأ بالعربية).

    Args:
        subqueries: قائمة الاستعلامات الفرعيّة من المُفكِّك.
        use_cache: تفعيل الكاش في الذاكرة (معطَّل افتراضيّاً في الاختبارات).

    Returns:
        قاموس {source: data} — يحتوي {"error": ...} للمصادر الفاشلة.
    """
    results: dict[str, dict] = {}

    for sq in subqueries:
        source = sq.source
        params = sq.params

        # Skip duplicates — use first occurrence
        if source in results:
            continue

        cache_key = _cache_key(source, params) if use_cache else None

        if use_cache and cache_key and cache_key in _CACHE:
            results[source] = _CACHE[cache_key]
            continue

        connector = CONNECTORS.get(source)
        if connector is None:
            msg = f"مصدر بيانات غير معروف: {source}"
            logger.error(msg)
            results[source] = {"error": msg}
            continue

        try:
            data = connector(params)
            results[source] = data
            if use_cache and cache_key:
                _CACHE[cache_key] = data
        except Exception as exc:  # noqa: BLE001
            msg = f"خطأ في جلب البيانات من المصدر '{source}': {exc}"
            logger.error(msg)
            results[source] = {"error": msg}

    return results
