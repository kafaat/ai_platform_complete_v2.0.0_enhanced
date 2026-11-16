"""core/weather_signals.py — توليد إشارات الطقس القراريّة من درجات التراكب (نقيّ).

طبقة الإشارات: تحوّل درجات `FieldWeatherScores` المستمرّة إلى **إشارات منفصلة** بثقة،
يستهلكها محرّك التوصية مباشرةً (بدل استدعاء OpenMeteo). كلّ إشارة لها نوع وثقة [0,1]
وحمولة شارحة. نقيّ حتميّ — لا I/O، يُغذّي خدمة الإشارات (التي تكتبها في weather_signals
عبر sahool_app تحت سياق المستأجِر).

كذلك مُجمِّع نقيّ يحوّل صفوف التنبّؤ الساعيّة (من خلايا الشبكة داخل المضلّع) إلى
`HourlyWeather` — قلب عامل التراكب (PolygonOverlayWorker) بلا قاعدة.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

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


# z لفترة Wilson أحاديّة الطرف عند 95% — نحتاج الحدّ الأدنى وحده، لا فترةً متماثلة.
_WILSON_Z = 1.645


def _wilson_lower_bound(successes: int, trials: int) -> float | None:
    """الحدّ الأدنى لفترة Wilson على ``successes/trials`` — ثقةٌ تعرف حجم عيّنتها.

    **لماذا لا النسبة الخام:** ساعةُ صقيعٍ من ساعةٍ واحدة نسبتُها 1.0، وأربعٌ وعشرون
    من أربعٍ وعشرين نسبتُها 1.0 — والدليلان ليسا سواءً بحال. والنسبةُ الخام لا تملك
    ما تُفرّق به، فتُبلِّغ يقيناً كاملاً عن مشاهدةٍ واحدة.

    وWilson يُدخِل حجمَ العيّنة في الحساب: 1/1 ⇒ ~0.21 · 24/24 ⇒ ~0.86. فيبقى الترتيبُ
    صحيحاً (الأكثرُ ساعاتٍ أعلى ثقة) بلا ادّعاء يقينٍ من مشاهدةٍ يتيمة. وهو المعياريّ
    عند نسبةٍ من عيّنة صغيرة، حيث ينهار تقريبُ Wald عند ``p̂ = 1`` (طولُ فترته صفر).

    **ومدخلٌ غير متماسك يُرَدّ ``None`` لا يُقَصّ:** ``successes > trials`` تعني عدّاً
    مستحيلاً — ساعاتُ صقيعٍ أكثرُ من الساعات المرصودة. وقصُّها إلى 1.0 يُحوّل التناقضَ
    إلى **أقوى** جملةِ ثقة ممكنة. والصمتُ أصدق.
    """
    if trials <= 0 or successes < 0 or successes > trials:
        return None
    p = successes / trials
    z2 = _WILSON_Z * _WILSON_Z
    denominator = 1.0 + z2 / trials
    centre = p + z2 / (2 * trials)
    margin = _WILSON_Z * math.sqrt(p * (1.0 - p) / trials + z2 / (4 * trials * trials))
    return max(0.0, (centre - margin) / denominator)


def generate_signals(scores: FieldWeatherScores) -> list[WeatherSignal]:
    """يولّد إشارات منفصلة من درجات التراكب (نقيّ). يُرجِع فقط الإشارات المُطلَقة.

    **بلا ساعاتٍ مُقيَّمة لا إشارة إطلاقاً.** ``compute_scores([])`` يُرجِع
    ``trafficability_score=0.0``، و0.0 دون عتبة ``_TRAFFIC_POOR`` — فكانت تُطلَق
    «التربةُ غير سالكة» بثقة **1.0** من **صفر مشاهدة**. مقيسٌ بالتنفيذ لا بالقراءة.
    والدرجاتُ الصفريّة هناك تعني «لا شيء رُصِد»، لا «رُصِد صفر».
    """
    if scores.hours_evaluated <= 0:
        return []

    out: list[WeatherSignal] = []
    h = scores.hours_evaluated

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
    # الإشارتان الساعيّتان: لكلٍّ **مقامُها المخصوص** — الساعاتُ التي كان حدثُها
    # قابلاً للرصد فيها. و``hours_evaluated`` (الساعاتُ الحاضرة) لا يصلح مقاماً:
    # ساعةٌ بلا ``temp_min`` تدخله ولا يمكنها دخولُ بسطِ الصقيع أبداً، فيصير
    # الكسرُ بين فضاءَي ملاحظةٍ مختلفَين. وWilson فوق مقامٍ كهذا يُحسِّن تقديرَ
    # اللايقين على كسرٍ لا معنى له — وهو ما نهى عنه العقد صراحةً.
    #
    # ويُنشَر المقامُ المستعمَل باسمه في الحمولة، لا ``hours_evaluated`` — وإلّا
    # نُشِر رقمٌ لم يُقسَم عليه شيء، وصارت المراجعةُ مستحيلة على قارئها.
    if scores.frost_risk_hours > 0:
        confidence = _wilson_lower_bound(scores.frost_risk_hours, scores.frost_evaluable_hours)
        if confidence is not None:
            out.append(
                WeatherSignal(
                    "frost_imminent",
                    _conf(confidence),
                    {
                        "frost_hours": scores.frost_risk_hours,
                        "frost_evaluable_hours": scores.frost_evaluable_hours,
                        "hours_present": h,
                        "confidence_basis": "wilson_lower_bound_95",
                    },
                )
            )
    if scores.heat_stress_hours > 0:
        confidence = _wilson_lower_bound(scores.heat_stress_hours, scores.heat_evaluable_hours)
        if confidence is not None:
            out.append(
                WeatherSignal(
                    "heat_stress",
                    _conf(confidence),
                    {
                        "heat_hours": scores.heat_stress_hours,
                        "heat_evaluable_hours": scores.heat_evaluable_hours,
                        "hours_present": h,
                        "confidence_basis": "wilson_lower_bound_95",
                    },
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


# ════════════════════════════════════════════════════════════════════════════
# W1-17 — إشارات دليل القرار المربوط بالحقل من منتجات weather-service
# ════════════════════════════════════════════════════════════════════════════
# W1-17 / finding ``weather-2``: the decision playbook took its weather signals from keys the
# UI sent (``weather_signals`` in the request body). A client that sent nothing got a playbook
# with no weather at all, and a client could send ``spray_window_open`` on a day of strong wind.
#
# This section derives ``WeatherSignal`` values from the products the weather owner publishes
# (``weather-service``), so the field-bound playbook never reads weather from the caller:
#
# * ``/v1/weather/operation-plan`` (spraying frames)  ⇒ ``spray_unsafe`` / ``spray_window_open``
# * ``/v1/weather/thermal-stress``                    ⇒ ``heat_stress`` / ``frost_imminent``
# * disease risk (``api.weather_advice.disease_risk`` over weather-service current + forecast)
#                                                      ⇒ ``disease_risk_high``
#
# Pure and deterministic: no I/O. The caller fetches the products and passes them in.
#
# Fail-closed on spraying: a missing plan, a missing "now" frame, an ``insufficient_data``
# frame or a frame whose limiting factors include wind or rain gives ``spray_unsafe``, never
# silence and never an open window. Drift above the weather-service wind threshold
# (``wind_speed_high`` > 18 km/h, ``wind_gust_high`` > 29 km/h) is a safety limit, not a
# quality penalty, so it blocks spraying even when the service score is still "acceptable".

SPRAY_UNSAFE = "spray_unsafe"
SPRAY_WINDOW_OPEN = "spray_window_open"

# Limiting factors (weather-service ``operations.operation_suitability``) that make spraying
# unsafe now, not merely less efficient: drift (wind/gust) and wash-off (rain).
SPRAY_BLOCKING_FACTORS = frozenset({"wind_speed_high", "wind_gust_high", "rain_present"})
_SPRAY_BLOCKING_SUITABILITY = frozenset({"unsafe", "insufficient_data"})
# Same threshold the weather-service uses for ``recommended`` in the operation plan.
_SPRAY_OPEN_SCORE = 0.55

# The disease rule (three weather factors) is not a calibrated probability; its confidence
# is a declared constant, labelled as such in the payload, not a measured value.
_DISEASE_RULE_CONFIDENCE = 0.5

SNAPSHOT_SCHEME = "sahool-decision-weather:v1"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else round(x, 4)


def _spraying_item(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    for item in plan.get("operations") or []:
        if isinstance(item, dict) and item.get("operation") == "spraying":
            return item
    return None


def _frames(item: dict[str, Any]) -> list[dict[str, Any]]:
    frames = [f for f in item.get("frames") or [] if isinstance(f, dict)]
    return sorted(frames, key=lambda f: (_num(f.get("hour_offset")) is None, f.get("hour_offset")))


def _decision(frame: dict[str, Any]) -> dict[str, Any]:
    decision = frame.get("operation")
    return decision if isinstance(decision, dict) else {}


def _blocking_reasons(decision: dict[str, Any]) -> list[str]:
    factors = [str(f) for f in decision.get("limiting_factors") or []]
    reasons = [f for f in factors if f in SPRAY_BLOCKING_FACTORS or f.startswith("missing_")]
    if decision.get("status") == "insufficient_data" or decision.get("suitability") in (
        _SPRAY_BLOCKING_SUITABILITY
    ):
        reasons.append(str(decision.get("suitability") or decision.get("status")))
    if not decision:
        reasons.append("no_operation_decision")
    return list(dict.fromkeys(reasons))


def _frame_facts(frame: dict[str, Any]) -> dict[str, Any]:
    sample = frame.get("sample") if isinstance(frame.get("sample"), dict) else {}
    decision = _decision(frame)
    return {
        "hour_offset": frame.get("hour_offset"),
        "weather_time": frame.get("weather_time"),
        "score": _num(decision.get("score")),
        "suitability": decision.get("suitability"),
        "limiting_factors": list(decision.get("limiting_factors") or []),
        "wind_speed_10m_kmh": _num(sample.get("wind_speed_10m_kmh")),
        "wind_gusts_10m_kmh": _num(sample.get("wind_gusts_10m_kmh")),
        "precipitation_mm": _num(sample.get("precipitation_mm")),
    }


def spray_signals_from_operation_plan(plan: dict[str, Any] | None) -> list[WeatherSignal]:
    """``spray_unsafe`` for the first (nearest) frame when spraying is not safe now, and
    ``spray_window_open`` for the best later frame that is safe and scores >= 0.55.

    No plan, no spraying item or no frames ⇒ ``spray_unsafe`` with ``basis="unconfirmed"``
    and confidence 0.0: the playbook says "do not spray now" without claiming the weather
    was measured as bad, and the zero confidence lowers the overall playbook confidence.
    """
    item = _spraying_item(plan)
    frames = _frames(item) if item is not None else []
    if not frames:
        return [
            WeatherSignal(
                SPRAY_UNSAFE,
                0.0,
                {
                    "basis": "unconfirmed",
                    "reasons": ["operation_plan_unavailable"],
                    "confidence_basis": "fail_closed_no_forecast",
                },
            )
        ]

    out: list[WeatherSignal] = []
    now = frames[0]
    now_decision = _decision(now)
    now_reasons = _blocking_reasons(now_decision)
    if now_reasons:
        score = _num(now_decision.get("score"))
        insufficient = now_decision.get("status") == "insufficient_data" or not now_decision
        out.append(
            WeatherSignal(
                SPRAY_UNSAFE,
                0.0 if insufficient or score is None else _clamp01(1.0 - score),
                {
                    "basis": "unconfirmed" if insufficient else "forecast",
                    "reasons": now_reasons,
                    "confidence_basis": "fail_closed_missing_inputs"
                    if insufficient
                    else "one_minus_operation_score",
                    **_frame_facts(now),
                },
            )
        )

    open_frames = []
    for frame in frames:
        decision = _decision(frame)
        score = _num(decision.get("score"))
        if score is None or score < _SPRAY_OPEN_SCORE or _blocking_reasons(decision):
            continue
        open_frames.append((score, frame))
    if open_frames:
        # Highest score wins; on a tie the nearer frame (frames are sorted by offset).
        best_score, best = max(open_frames, key=lambda pair: pair[0])
        out.append(
            WeatherSignal(
                SPRAY_WINDOW_OPEN,
                _clamp01(best_score),
                {
                    "suitable_fraction": best_score,
                    "confidence_basis": "operation_score",
                    "opens_now": best is now,
                    **_frame_facts(best),
                },
            )
        )
    return out


def thermal_signals(product: dict[str, Any] | None) -> list[WeatherSignal]:
    """``heat_stress`` / ``frost_imminent`` from the weather-service thermal-stress product.

    ``status != "ok"`` (for instance ``insufficient_context`` without crop or stage) gives no
    signal: the product declined to judge, and the playbook must not invent a judgement.
    The confidence is the one the product computed, not a constant.
    """
    if not isinstance(product, dict) or product.get("status") != "ok":
        return []
    confidence = _num(product.get("confidence"))
    if confidence is None:
        return []
    common = {
        "risk": product.get("risk"),
        "horizon_days": product.get("horizon_days"),
        "thresholds_applied": product.get("thresholds_applied"),
        "confidence_basis": "weather_service_thermal_stress",
    }
    out: list[WeatherSignal] = []
    frost_nights = int(_num(product.get("frost_nights")) or 0)
    if frost_nights > 0:
        out.append(
            WeatherSignal(
                "frost_imminent",
                _clamp01(confidence),
                {**common, "frost_nights": frost_nights, "night_min_c": product.get("night_min_c")},
            )
        )
    heat_days = int(_num(product.get("heat_stress_days")) or 0)
    heat_hours = int(_num(product.get("day_heat_stress_hours")) or 0)
    if heat_days > 0 or heat_hours > 0:
        payload = {**common, "heat_stress_days": heat_days, "day_max_c": product.get("day_max_c")}
        if "day_heat_stress_hours" in product:
            payload["heat_hours"] = heat_hours
        out.append(WeatherSignal("heat_stress", _clamp01(confidence), payload))
    return out


def disease_signals(risk: dict[str, Any] | None) -> list[WeatherSignal]:
    """``disease_risk_high`` when the weather disease rule says ``high``; otherwise nothing."""
    if not isinstance(risk, dict) or risk.get("risk_level") != "high":
        return []
    return [
        WeatherSignal(
            "disease_risk_high",
            _DISEASE_RULE_CONFIDENCE,
            {
                "risk_level": "high",
                "temperature_c": risk.get("temperature_c"),
                "humidity_pct": risk.get("humidity_pct"),
                "rain_mm_3d": risk.get("rain_mm_3d"),
                "confidence_basis": "uncalibrated_three_factor_rule",
            },
        )
    ]


def decision_weather_snapshot_id(facts: dict[str, Any]) -> str:
    """Deterministic identity of the exact weather facts the signals were derived from.

    The weather-service products used here do not carry a snapshot identity of their own,
    so the identity is a fingerprint (sha1 of canonical JSON, 16 hex) of the facts that
    were consumed: same weather ⇒ same id; any changed reading ⇒ a different id. Same
    scheme shape as ``weather-service/et0.py::weather_snapshot_id``.
    """

    def _canon(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, dict):
            return {str(k): _canon(v) for k, v in sorted(value.items()) if v is not None}
        if isinstance(value, (list, tuple)):
            return [_canon(v) for v in value]
        return value

    digest = hashlib.sha1(
        json.dumps(_canon(facts), sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        ),
        usedforsecurity=False,
    ).hexdigest()[:16]
    return f"{SNAPSHOT_SCHEME}:{digest}"


def spraying_frames_for_snapshot(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The spraying frames reduced to the readings that decided them (for the snapshot id)."""
    item = _spraying_item(plan)
    if item is None:
        return []
    return [
        {
            "hour_offset": f.get("hour_offset"),
            "weather_time": f.get("weather_time"),
            "sample": f.get("sample") if isinstance(f.get("sample"), dict) else None,
        }
        for f in _frames(item)
    ]
