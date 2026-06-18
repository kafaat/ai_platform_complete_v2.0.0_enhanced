"""core/weather_signals.py — توليد إشارات الطقس القراريّة من درجات التراكب (نقيّ).

طبقة الإشارات: تحوّل درجات `FieldWeatherScores` المستمرّة إلى **إشارات منفصلة** بثقة،
يستهلكها محرّك التوصية مباشرةً (بدل استدعاء OpenMeteo). كلّ إشارة لها نوع وثقة [0,1]
وحمولة شارحة. نقيّ حتميّ — لا I/O، يُغذّي خدمة الإشارات (التي تكتبها في weather_signals
عبر sahool_app تحت سياق المستأجِر).

كذلك مُجمِّع نقيّ يحوّل صفوف التنبّؤ الساعيّة (من خلايا الشبكة داخل المضلّع) إلى
`HourlyWeather` — قلب عامل التراكب (PolygonOverlayWorker) بلا قاعدة.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .weather_overlay import FieldWeatherScores, HourlyWeather

# عتبات إطلاق الإشارات (قابلة للمعايرة).
_SPRAY_OPEN = 0.5  # نسبة ساعات صالحة ⇒ نافذة رشّ مفتوحة
_DISEASE_HIGH = 0.5  # نسبة ساعات خطر ⇒ تنبيه مرض
_TRAFFIC_POOR = 30.0  # درجة صلاحيّة مرور دونها ⇒ تربة غير سالكة


@dataclass(frozen=True)
class WeatherSignal:
    signal_type: str
    confidence_score: float  # [0,1]
    payload: dict = field(default_factory=dict)


def _conf(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else round(x, 4)


def generate_signals(scores: FieldWeatherScores) -> list[WeatherSignal]:
    """يولّد إشارات منفصلة من درجات التراكب (نقيّ). يُرجِع فقط الإشارات المُطلَقة."""
    out: list[WeatherSignal] = []
    h = max(1, scores.hours_evaluated)

    if scores.spray_suitability_score >= _SPRAY_OPEN:
        out.append(
            WeatherSignal(
                "spray_window_open",
                _conf(scores.spray_suitability_score),
                {"suitable_fraction": scores.spray_suitability_score},
            )
        )
    if scores.disease_risk_score >= _DISEASE_HIGH:
        out.append(
            WeatherSignal(
                "disease_risk_high",
                _conf(scores.disease_risk_score),
                {"risk_fraction": scores.disease_risk_score},
            )
        )
    if scores.frost_risk_hours > 0:
        out.append(
            WeatherSignal(
                "frost_imminent",
                _conf(scores.frost_risk_hours / h),
                {"frost_hours": scores.frost_risk_hours},
            )
        )
    if scores.heat_stress_hours > 0:
        out.append(
            WeatherSignal(
                "heat_stress",
                _conf(scores.heat_stress_hours / h),
                {"heat_hours": scores.heat_stress_hours},
            )
        )
    if scores.trafficability_score < _TRAFFIC_POOR:
        out.append(
            WeatherSignal(
                "trafficability_poor",
                _conf(1.0 - scores.trafficability_score / 100.0),
                {"trafficability": scores.trafficability_score},
            )
        )
    return out


def _avg(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def aggregate_cells_to_hourly(rows: list[dict]) -> list[HourlyWeather]:
    """يُجمّع صفوف تنبّؤ ساعيّة (قد تكون مُجمَّعة مسبقاً بـSQL GROUP BY hour) إلى قائمة
    HourlyWeather مرتّبة زمنيّاً. كلّ صفّ dict بمفاتيح اختياريّة: hour, temp_avg,
    temp_min, temp_max, humidity, wind_speed, precip_sum, delta_t. نقيّ (بلا قاعدة)."""
    by_hour: dict[object, list[dict]] = {}
    for r in rows:
        by_hour.setdefault(r.get("hour"), []).append(r)

    result = []
    for hour in sorted(by_hour, key=lambda x: (x is None, x)):
        cells = by_hour[hour]
        result.append(
            HourlyWeather(
                temp_avg_c=_avg([c.get("temp_avg") for c in cells]),
                temp_min_c=min(
                    (c["temp_min"] for c in cells if c.get("temp_min") is not None), default=None
                ),
                temp_max_c=max(
                    (c["temp_max"] for c in cells if c.get("temp_max") is not None), default=None
                ),
                humidity_pct=_avg([c.get("humidity") for c in cells]),
                wind_speed_ms=_avg([c.get("wind_speed") for c in cells]),
                precip_mm=_avg([c.get("precip_sum") for c in cells]),
                delta_t_c=_avg([c.get("delta_t") for c in cells]),
            )
        )
    return result
