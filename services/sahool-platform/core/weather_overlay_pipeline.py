"""core/weather_overlay_pipeline.py — قلب weather-polygon-worker نقيّاً (P0).

السلسلة: تنبّؤ خلايا الشبكة داخل مضلّع الحقل → **سجلّ تراكب** + **سجلّات إشارات** جاهزة
للحفظ في field_weather_overlay/weather_signals (مخطّط v74). يجمع التجميع الساعيّ
(aggregate_cells_to_hourly) + الدرجات (compute_scores) + الإشارات (generate_signals)
في سجلّات قابلة للإدراج مباشرةً — نقيّ حتميّ، بلا I/O. خدمة الـworker غلافٌ رفيع: تجلب
الصفوف بدور sahool_jobs (عابر) وتكتب السجلّات وتنشر الحدث (نمط outbox).
"""

from __future__ import annotations

from .weather_overlay import compute_scores
from .weather_signals import aggregate_cells_to_hourly, generate_signals


def _avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 3) if v else None


def _maxf(vals):
    v = [x for x in vals if x is not None]
    return round(max(v), 3) if v else None


def _minf(vals):
    v = [x for x in vals if x is not None]
    return round(min(v), 3) if v else None


def _sumf(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v), 3) if v else None


def build_overlay_record(field_id: str, tenant_id: str, forecast_rows: list[dict]) -> dict | None:
    """يبني سجلّ field_weather_overlay من صفوف تنبّؤ خلايا الحقل (نقيّ).

    كلّ صفّ dict بمفاتيح (اختياريّة): hour, cell_key, temp_avg/min/max, humidity,
    wind_speed, wind_gust, precip_sum, precip_prob, et0, delta_t.
    يُرجِع None إن لم تُوجَد صفوف (لا حقل بلا تنبّؤ). الأعمدة تطابق مخطّط v74 بالضبط."""
    if not forecast_rows:
        return None

    hourly = aggregate_cells_to_hourly(forecast_rows)
    scores = compute_scores(hourly)
    cells = {r.get("cell_key") for r in forecast_rows if r.get("cell_key") is not None}

    return {
        "field_id": field_id,
        "tenant_id": tenant_id,
        "temperature_min_c": _minf([r.get("temp_min") for r in forecast_rows]),
        "temperature_max_c": _maxf([r.get("temp_max") for r in forecast_rows]),
        "temperature_avg_c": _avg([r.get("temp_avg") for r in forecast_rows]),
        "humidity_avg_percent": _avg([r.get("humidity") for r in forecast_rows]),
        "wind_speed_avg_ms": _avg([r.get("wind_speed") for r in forecast_rows]),
        "wind_gust_max_ms": _maxf([r.get("wind_gust") for r in forecast_rows]),
        "precipitation_sum_mm": _sumf([r.get("precip_sum") for r in forecast_rows]),
        "precipitation_probability": _avg([r.get("precip_prob") for r in forecast_rows]),
        "et0_sum_mm": _sumf([r.get("et0") for r in forecast_rows]),
        "delta_t_avg_c": _avg([r.get("delta_t") for r in forecast_rows]),
        "spray_suitability_score": scores.spray_suitability_score,
        "disease_risk_score": scores.disease_risk_score,
        "heat_stress_hours": scores.heat_stress_hours,
        "frost_risk_hours": scores.frost_risk_hours,
        # **المقامات تُحمَل ولا تُشتقّ.** كان `build_signal_records` يخترعها
        # `max(1, heat, frost)` — أي يُساويها بالبسط — فتخرج نسبةُ الثقة 1.0 دائماً.
        # وهي متاحةٌ هنا مقيسة، فحملُها أسطرٌ ولا يحتاج هجرة: الإدراج يقرأ بالاسم
        # عموداً عموداً، فمفتاحٌ زائد في القاموس لا يمسّه.
        #
        # و`hours_evaluated` يبقى للنَّسَب والتشخيص، **لا مقاماً**: هو الساعاتُ
        # الحاضرة، ومقامُ كلّ حدثٍ هو فرصُه القابلة للرصد وحدها.
        "hours_evaluated": scores.hours_evaluated,
        "frost_evaluable_hours": scores.frost_evaluable_hours,
        "heat_evaluable_hours": scores.heat_evaluable_hours,
        "trafficability_score": scores.trafficability_score,
        "grid_cells_count": len(cells),
        "spatial_coverage": 1.0 if cells else 0.0,
    }


def build_signal_records(field_id: str, tenant_id: str, overlay: dict) -> list[dict]:
    """يبني سجلّات weather_signals من سجلّ التراكب (نقيّ). يعيد بناء الدرجات منه
    ويولّد الإشارات المنفصلة — جاهزة للإدراج (payload يُسلسَل JSON في الـworker)."""
    from .weather_overlay import FieldWeatherScores

    scores = FieldWeatherScores(
        spray_suitability_score=overlay.get("spray_suitability_score", 0.0),
        disease_risk_score=overlay.get("disease_risk_score", 0.0),
        trafficability_score=overlay.get("trafficability_score", 100.0),
        heat_stress_hours=overlay.get("heat_stress_hours", 0),
        frost_risk_hours=overlay.get("frost_risk_hours", 0),
        # المقامات كما قِيست، لا كما تُشتقّ. الاشتقاقُ القديم `max(1, heat, frost)` كان
        # **يُساوي المقامَ بالبسط**، فتخرج نسبةُ الثقة 1.0 حتماً في مسار الإنتاج كلِّه —
        # لا في حالةٍ حدّيّة. وغيابُها ⇒ صفر ⇒ لا إشارة: بلا مقامٍ لا تُقاس نسبة،
        # واختراعُه هو العطلُ بعينه.
        hours_evaluated=overlay.get("hours_evaluated", 0),
        frost_evaluable_hours=overlay.get("frost_evaluable_hours", 0),
        heat_evaluable_hours=overlay.get("heat_evaluable_hours", 0),
    )
    return [
        {
            "field_id": field_id,
            "tenant_id": tenant_id,
            "signal_type": s.signal_type,
            "confidence_score": s.confidence_score,
            "payload": s.payload,
        }
        for s in generate_signals(scores)
    ]
