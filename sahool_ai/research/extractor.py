"""استخراج القيم الرقميّة والأنماط الزمنيّة والروابط السببيّة من نتائج المصادر.

Numeric values extractor, temporal pattern extractor, and causal link inferrer
for the SAHOOL Agronomic Research Pipeline. All logic is deterministic.
"""

from __future__ import annotations

from datetime import date

from sahool_ai.research.models import CausalLink

# ── ثوابت خطّ الأساس / Baseline constants ──────────────────────────────────
_RAINFALL_BASELINE_MM: float = 80.0  # الحدّ الأدنى المتوقَّع للأمطار شهريّاً (مم)
_MOISTURE_LOW_THRESHOLD: float = 25.0  # حدّ انخفاض رطوبة التربة (%)
_ADHERENCE_LOW_THRESHOLD: float = 60.0  # حدّ الالتزام الضعيف بالري (%)
_NDVI_DECLINE_THRESHOLD: float = -10.0  # عتبة انخفاض NDVI المعتبَرة (%)


def extract_numeric_values(results: dict) -> dict:
    """استخراج القيم الرقميّة الجوهريّة من نتائج المصادر.

    يُنتج مؤشّرات قابلة للمقارنة لمرحلة التوليف.

    Args:
        results: قاموس {source: data} من ``retrieve_all``.

    Returns:
        قاموس يحتوي على:

        - ``ndvi_change_pct``: نسبة التغيّر في NDVI (سالبة = انخفاض).
        - ``ndvi_trend``: "declining" | "stable" | "improving" | "unknown".
        - ``rainfall_mm``: كمّية الأمطار المرصودة (مم).
        - ``rainfall_deficit_mm``: عجز الأمطار عن الخطّ الأساسي (مم، سالب = فائض).
        - ``avg_temp_c``: متوسّط درجة الحرارة.
        - ``soil_moisture_pct``: رطوبة التربة (%).
        - ``soil_ph``: درجة حموضة التربة.
        - ``npk``: قاموس N/P/K (فارغ إذا لم تتوفّر).
        - ``irrigation_adherence_pct``: نسبة الالتزام بجدول الري (%).
        - ``irrigation_missed``: عدد أيّام الري الفائتة.
        - ``weather_anomalies``: قائمة الشذوذات المناخيّة.
        - ``rag_confidence``: مستوى ثقة قاعدة المعرفة.
    """
    numeric: dict = {}

    # ── Sentinel Hub / NDVI ───────────────────────────────────────────────
    sentinel = results.get("sentinel_hub", {})
    if "error" not in sentinel and sentinel:
        numeric["ndvi_change_pct"] = sentinel.get("change_pct", 0.0)
        numeric["ndvi_trend"] = sentinel.get("trend", "unknown")
    else:
        numeric["ndvi_change_pct"] = 0.0
        numeric["ndvi_trend"] = "unknown"

    # ── Weather API ────────────────────────────────────────────────────────
    weather = results.get("weather_api", {})
    if "error" not in weather and weather:
        rainfall = weather.get("rainfall_mm", 0.0)
        numeric["rainfall_mm"] = rainfall
        numeric["rainfall_deficit_mm"] = _RAINFALL_BASELINE_MM - rainfall
        numeric["avg_temp_c"] = weather.get("avg_temp_c", 0.0)
        numeric["weather_anomalies"] = weather.get("anomalies", [])
    else:
        numeric["rainfall_mm"] = 0.0
        numeric["rainfall_deficit_mm"] = _RAINFALL_BASELINE_MM
        numeric["avg_temp_c"] = 0.0
        numeric["weather_anomalies"] = []

    # ── Soil Sensors ────────────────────────────────────────────────────────
    soil = results.get("soil_sensors", {})
    if "error" not in soil and soil:
        numeric["soil_moisture_pct"] = soil.get("moisture_pct", 0.0)
        numeric["soil_ph"] = soil.get("ph", 7.0)
        numeric["npk"] = soil.get("npk", {})
    else:
        numeric["soil_moisture_pct"] = 0.0
        numeric["soil_ph"] = 7.0
        numeric["npk"] = {}

    # ── Irrigation Logs ─────────────────────────────────────────────────────
    irrigation = results.get("irrigation_logs", {})
    if "error" not in irrigation and irrigation:
        numeric["irrigation_adherence_pct"] = irrigation.get("adherence_pct", 100.0)
        numeric["irrigation_missed"] = len(irrigation.get("missed_days", []))
    else:
        numeric["irrigation_adherence_pct"] = 100.0
        numeric["irrigation_missed"] = 0

    # ── Qdrant RAG ─────────────────────────────────────────────────────────
    rag = results.get("qdrant_rag", {})
    if "error" not in rag and rag:
        numeric["rag_confidence"] = rag.get("confidence", 0.0)
    else:
        numeric["rag_confidence"] = 0.0

    return numeric


def extract_temporal_patterns(results: dict) -> dict:
    """استخراج الأنماط الزمنيّة من سجلّات الري والطقس.

    Args:
        results: قاموس {source: data} من ``retrieve_all``.

    Returns:
        قاموس يحتوي على:

        - ``delay_events``: قائمة أحداث التأخّر ``[{"type","days","start_date"}]``.
        - ``seasonal_deviation``: "below_average" | "normal" | "above_average".
        - ``ndvi_dates``: تواريخ قياسات NDVI (قائمة نصوص).
        - ``missed_days``: قائمة أيّام الري الفائتة.
    """
    patterns: dict = {}

    # ── Irrigation delay events ─────────────────────────────────────────────
    irrigation = results.get("irrigation_logs", {})
    missed_days: list[str] = []
    delay_events: list[dict] = []

    if "error" not in irrigation and irrigation:
        missed_days = irrigation.get("missed_days", [])
        adherence = irrigation.get("adherence_pct", 100.0)

        # Group runs of calendar-consecutive missed days into delay events.
        # (A new group starts whenever two sorted days are not exactly one day
        # apart; unparseable dates also break the run.)
        if missed_days:
            sorted_days = sorted(missed_days)
            current_group: list[str] = [sorted_days[0]]
            groups: list[list[str]] = []

            for day in sorted_days[1:]:
                try:
                    consecutive = (
                        date.fromisoformat(day) - date.fromisoformat(current_group[-1])
                    ).days == 1
                except ValueError:
                    consecutive = False
                if consecutive:
                    current_group.append(day)
                else:
                    groups.append(current_group)
                    current_group = [day]

            groups.append(current_group)

            for group in groups:
                delay_events.append(
                    {
                        "type": "irrigation_delay",
                        "days": len(group),
                        "start_date": group[0],
                    }
                )

        # Single-event summary for low-adherence case
        if adherence < _ADHERENCE_LOW_THRESHOLD and not delay_events:
            scheduled = irrigation.get("scheduled_events", 0)
            actual = irrigation.get("actual_events", 0)
            delay_events.append(
                {
                    "type": "irrigation_delay",
                    # clamp: actual > scheduled (or missing) must not yield negative days
                    "days": max(0, scheduled - actual),
                    "start_date": missed_days[0] if missed_days else "unknown",
                }
            )

    patterns["delay_events"] = delay_events
    patterns["missed_days"] = missed_days

    # ── Seasonal deviation (rainfall-based) ─────────────────────────────────
    weather = results.get("weather_api", {})
    if "error" not in weather and weather:
        rainfall = weather.get("rainfall_mm", _RAINFALL_BASELINE_MM)
        if rainfall < _RAINFALL_BASELINE_MM * 0.6:
            patterns["seasonal_deviation"] = "below_average"
        elif rainfall > _RAINFALL_BASELINE_MM * 1.4:
            patterns["seasonal_deviation"] = "above_average"
        else:
            patterns["seasonal_deviation"] = "normal"
    else:
        patterns["seasonal_deviation"] = "normal"

    # ── NDVI dates ─────────────────────────────────────────────────────────
    sentinel = results.get("sentinel_hub", {})
    if "error" not in sentinel and sentinel:
        patterns["ndvi_dates"] = sentinel.get("dates", [])
    else:
        patterns["ndvi_dates"] = []

    return patterns


def extract_causal_links(results: dict) -> list[CausalLink]:
    """استنتاج الروابط السببيّة بين العوامل الزراعيّة.

    يعتمد على عتبات حتميّة ثابتة لا على نماذج احتماليّة.

    Args:
        results: قاموس {source: data} من ``retrieve_all``.

    Returns:
        قائمة من :class:`~sahool_ai.research.models.CausalLink`.
    """
    links: list[CausalLink] = []

    numeric = extract_numeric_values(results)
    rainfall_deficit = numeric.get("rainfall_deficit_mm", 0.0)
    ndvi_change = numeric.get("ndvi_change_pct", 0.0)
    adherence = numeric.get("irrigation_adherence_pct", 100.0)
    moisture = numeric.get("soil_moisture_pct", 30.0)

    # Source presence guards — require actual (non-error, non-empty) source data
    has_weather = bool(results.get("weather_api")) and "error" not in results.get("weather_api", {})
    has_sentinel = bool(results.get("sentinel_hub")) and "error" not in results.get(
        "sentinel_hub", {}
    )
    has_soil = bool(results.get("soil_sensors")) and "error" not in results.get("soil_sensors", {})
    has_irrigation = bool(results.get("irrigation_logs")) and "error" not in results.get(
        "irrigation_logs", {}
    )

    # 1. عجز مطري → انخفاض NDVI
    if has_weather and has_sentinel and rainfall_deficit > 20.0 and ndvi_change < _NDVI_DECLINE_THRESHOLD:
        conf = min(0.95, 0.5 + (rainfall_deficit / 200.0) + abs(ndvi_change) / 200.0)
        links.append(
            CausalLink(
                cause="عجز مطري",
                effect="انخفاض NDVI",
                confidence=conf,
                evidence=["weather_api", "sentinel_hub"],
            )
        )

    # 2. تأخّر الري → انخفاض NDVI
    if (
        has_irrigation
        and has_sentinel
        and adherence < _ADHERENCE_LOW_THRESHOLD
        and ndvi_change < _NDVI_DECLINE_THRESHOLD
    ):
        conf = min(0.90, 0.4 + (1.0 - adherence / 100.0) + abs(ndvi_change) / 200.0)
        links.append(
            CausalLink(
                cause="تأخّر الري",
                effect="انخفاض NDVI",
                confidence=conf,
                evidence=["irrigation_logs", "sentinel_hub"],
            )
        )

    # 3. جفاف التربة → ضعف امتصاص المغذّيات
    if has_soil and moisture < _MOISTURE_LOW_THRESHOLD:
        conf = min(0.85, 0.45 + (_MOISTURE_LOW_THRESHOLD - moisture) / 50.0)
        links.append(
            CausalLink(
                cause="جفاف التربة",
                effect="ضعف امتصاص المغذّيات",
                confidence=conf,
                evidence=["soil_sensors", "qdrant_rag"],
            )
        )

    # 4. عجز مطري → جفاف التربة
    if has_weather and has_soil and rainfall_deficit > 30.0 and moisture < _MOISTURE_LOW_THRESHOLD:
        conf = min(0.88, 0.5 + rainfall_deficit / 200.0)
        links.append(
            CausalLink(
                cause="عجز مطري",
                effect="جفاف التربة",
                confidence=conf,
                evidence=["weather_api", "soil_sensors"],
            )
        )

    # 5. شذوذ مناخي → إجهاد حراري
    weather = results.get("weather_api", {})
    if "error" not in weather and weather:
        anomalies = weather.get("anomalies", [])
        high_severity = [a for a in anomalies if a.get("severity") in ("high", "medium")]
        if high_severity:
            conf = 0.75 if any(a["severity"] == "high" for a in high_severity) else 0.60
            links.append(
                CausalLink(
                    cause="شذوذ مناخي",
                    effect="إجهاد حراري على المحصول",
                    confidence=conf,
                    evidence=["weather_api"],
                )
            )

    return links
