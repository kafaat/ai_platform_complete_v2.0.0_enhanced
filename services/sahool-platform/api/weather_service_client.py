"""Thin sahool-platform client for weather-service boundary calls.

P3.4 Platform Weather Facade:
- weather-service owns provider calls, cache, tile math, wind grid, and operation scoring;
- sahool-platform may keep auth/rate-limit/BFF routes but must call this facade
  instead of importing Open-Meteo connectors or re-implementing weather runtime logic.
"""

from __future__ import annotations

import asyncio
import functools
import math
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean
from time import monotonic as _monotonic
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.
# This module is reachable from the pure-logic `pytest -m unit` tier (via imagery/raster
# import chains) which runs WITHOUT fastapi installed, so a module-level fastapi import
# would break collection. Keep fastapi out of module import time.

DEFAULT_WEATHER_SERVICE_URL = "http://sahool-weather-service:8000"


def weather_service_url() -> str:
    return os.getenv("WEATHER_SERVICE_URL", DEFAULT_WEATHER_SERVICE_URL).rstrip("/")


def weather_service_headers(
    *, tenant_id: str | None = None, authorization: str | None = None
) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    return headers


# ─── صحّةُ weather-service كما **رصدتها** المنصّة (W1-22) ─────────────────────────────
#
# كانت جاهزيّةُ طبقة الطقس في المنصّة تقرأ قاطعَ موصّل Open-Meteo المحلّيّ. بعد أن صارت كلُّ
# قراءةٍ تمرّ بـweather-service لم يَعُد يمرّ بذلك القاطع طلبٌ، فإعلانُه كان سيقول «سليم» بلا
# قياس، وإعلانُ ``delegated`` وحده يُسقط إشارةَ الصحّة كلّياً. هذا عدّادٌ داخل العمليّة يُبنى من
# حركة المرور الفعليّة وحدها (لا مسبارَ شبكيّاً في readyz): ``service`` لتعذّر الخدمة نفسِها
# (مهلة/شبكة/5xx/جسمٌ غيرُ مقروء)، و``provider`` لِما تُعلنه الخدمةُ عن مزوّدها (عيّنةٌ محايدة أو
# قديمة بخطأٍ منبعيّ). 4xx خطأُ طلبٍ لا عطلُ تبعيّة فلا يُحسَب على أيٍّ منهما.

OBSERVED_FAILURE_THRESHOLD = 3
OBSERVED_FAILURE_WINDOW_S = 60.0


class _ObservedHealth:
    def __init__(self, name: str) -> None:
        self.name = name
        self.reset()

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.last_error: str | None = None
        self.last_failure_at: float | None = None
        self.last_success_at: float | None = None

    def success(self) -> None:
        self.consecutive_failures = 0
        self.last_error = None
        self.last_success_at = _monotonic()

    def failure(self, reason: str) -> None:
        self.consecutive_failures += 1
        self.last_error = str(reason)[:200]
        self.last_failure_at = _monotonic()

    def snapshot(self) -> dict[str, Any]:
        now = _monotonic()
        recent = (
            self.last_failure_at is not None
            and now - self.last_failure_at <= OBSERVED_FAILURE_WINDOW_S
        )
        if self.last_failure_at is None and self.last_success_at is None:
            state = "unobserved"
        elif recent and self.consecutive_failures >= OBSERVED_FAILURE_THRESHOLD:
            state = "open"
        else:
            state = "closed"
        return {
            "state": state,
            "consecutive_failures": self.consecutive_failures,
            "opens_after_failures": OBSERVED_FAILURE_THRESHOLD,
            "window_s": int(OBSERVED_FAILURE_WINDOW_S),
            "last_error": self.last_error,
            "last_success_age_s": (
                None if self.last_success_at is None else round(now - self.last_success_at, 3)
            ),
        }


_SERVICE_HEALTH = _ObservedHealth("service")
_PROVIDER_HEALTH = _ObservedHealth("provider")


def observed_weather_service_health() -> dict[str, Any]:
    """حالةُ weather-service ومزوّدِه كما رصدتها هذه العمليّة — بلا نداء شبكة."""
    service = _SERVICE_HEALTH.snapshot()
    provider = _PROVIDER_HEALTH.snapshot()
    states = {service["state"], provider["state"]}
    if "open" in states:
        state = "open"
    elif states == {"unobserved"}:
        state = "unobserved"
    else:
        state = "closed"
    return {
        "state": state,
        "source": "observed_by_platform",
        "service": service,
        "provider": provider,
    }


def delegated_breaker_state() -> dict[str, Any]:
    """قاطعُ Open-Meteo يملكه weather-service (``/v1/weather/readyz`` هناك): قاطعُ موصّل المنصّة لا
    يمرّ به طلبٌ فيبقى «مغلقاً» أبداً، فعرضُه كان سيقول «المزوّد سليم» بلا قياس. يُعلَن التفويضُ
    ومعه الصحّةُ **المرصودة** من حركة المرور الفعليّة (W1-22)."""
    return {
        "state": "delegated",
        "owner": "weather-service",
        "observed": observed_weather_service_health(),
    }


def observed_degraded_reasons(observed: dict[str, Any]) -> list[str]:
    """تكافؤُ ``openmeteo_breaker_open`` السابق في جاهزيّة المنصّة: إخفاقاتٌ متتالية حديثة مرصودة."""
    reasons: list[str] = []
    if (observed.get("service") or {}).get("state") == "open":
        reasons.append("weather_service_unavailable_observed")
    if (observed.get("provider") or {}).get("state") == "open":
        reasons.append("weather_provider_degraded_observed")
    return reasons


def reset_observed_weather_service_health() -> None:
    """للاختبارات: يُعيد العدّادين إلى «لم يُرصَد»."""
    _SERVICE_HEALTH.reset()
    _PROVIDER_HEALTH.reset()


# weather-service بوّابةٌ إلى مزوّده: 502/503/504 **يُجيب بها هو** تعني أنّ المزوّد خلفه تعذّر، لا
# أنّه هو معطّل. أمّا المهلةُ/الشبكةُ/الجسمُ غيرُ المقروء فتُرفَع هنا في المنصّة (``weather_service_*``).
_PROVIDER_PASSTHROUGH_STATUSES = frozenset({502, 503, 504})


def _passthrough_error(status_code: int, detail: Any) -> Exception:
    """خطأٌ HTTP **أجاب به** weather-service — موسومٌ كي يفصله السجّلُ عن انقطاع الخدمة نفسها."""
    from fastapi import HTTPException

    exc = HTTPException(status_code=status_code, detail=detail)
    exc.weather_service_responded = True  # type: ignore[attr-defined]
    return exc


def _reason_code(detail: Any) -> str | None:
    """``reason_code`` من تفصيل المنصّة أو من مغلّف FastAPI ``{"detail": {...}}`` للخدمة."""
    for candidate in (detail, detail.get("detail") if isinstance(detail, dict) else None):
        if isinstance(candidate, dict) and isinstance(candidate.get("reason_code"), str):
            return candidate["reason_code"]
    return None


def _observed_by_service_health(call):
    """يسجّل نتيجةَ نداءٍ لـweather-service على ``_SERVICE_HEALTH``/``_PROVIDER_HEALTH`` دون لمس جسمه.

    مهلةٌ/شبكةٌ/جسمٌ غيرُ مقروء (504/502 من المنصّة) و500 من الخدمة ⇒ إخفاقُ الخدمة؛ 502/503/504
    **أجابت بها الخدمة** ⇒ الخدمةُ حيّة والمزوّدُ خلفها متعذّر ⇒ إخفاقُ المزوّد (فلا تُسمّي الجاهزيّةُ
    المكوّنَ الخطأ)؛ 4xx خطأُ طلبٍ ⇒ لا يُحسَب؛ نجاحٌ ⇒ يُصفّر عدّادَ الخدمة.
    """

    @functools.wraps(call)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = await call(*args, **kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and status >= 500:
                reason = _reason_code(getattr(exc, "detail", None))
                responded = getattr(exc, "weather_service_responded", False) is True
                if responded and status in _PROVIDER_PASSTHROUGH_STATUSES:
                    _SERVICE_HEALTH.success()
                    _PROVIDER_HEALTH.failure(reason or f"weather_provider_http_{status}")
                else:
                    _SERVICE_HEALTH.failure(reason or f"weather_service_http_{status}")
            raise
        _SERVICE_HEALTH.success()
        return result

    return wrapper


def _detail_from_response(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return getattr(resp, "text", "weather-service returned an error")


@_observed_by_service_health
async def weather_get_json(
    path: str,
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """GET JSON from weather-service with service token + optional tenant/auth forwarding."""
    import httpx
    from fastapi import HTTPException

    url = f"{weather_service_url()}/{path.lstrip('/')}"
    try:
        async with asyncio.timeout(timeout_s), httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers=weather_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "reason_code": "weather_service_timeout",
                "message_ar": "انتهت مهلة انتظار خدمة الطقس؛ أعد المحاولة لاحقاً.",
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "reason_code": "weather_service_unavailable",
                "message_ar": "تعذّر الاتصال بخدمة الطقس؛ أعد المحاولة لاحقاً.",
            },
        ) from exc
    if resp.status_code >= 400:
        raise _passthrough_error(resp.status_code, _detail_from_response(resp))
    try:
        data = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "reason_code": "weather_service_invalid_response",
                "message_ar": "تعذّر قراءة استجابة خدمة الطقس.",
            },
        ) from exc
    return data if isinstance(data, dict) else {"value": data}


@_observed_by_service_health
async def weather_post_json(
    path: str,
    *,
    json_body: dict[str, Any],
    tenant_id: str | None = None,
    authorization: str | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """POST JSON to weather-service with service token + optional tenant/auth forwarding.

    يرفع ``HTTPException(502)`` عند تعذّر المحرّك (شبكة) — ليتمكّن المُستهلِك من
    الفشل مُغلَقاً (dependency_unavailable) بلا حساب محلّيّ بديل صامت.
    """
    import httpx
    from fastapi import HTTPException

    url = f"{weather_service_url()}/{path.lstrip('/')}"
    try:
        async with asyncio.timeout(timeout_s), httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                url,
                json=json_body,
                headers=weather_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "reason_code": "weather_service_timeout",
                "message_ar": "انتهت مهلة انتظار خدمة الطقس؛ أعد المحاولة لاحقاً.",
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "reason_code": "weather_service_unavailable",
                "message_ar": "تعذّر الاتصال بخدمة الطقس؛ أعد المحاولة لاحقاً.",
            },
        ) from exc
    if resp.status_code >= 400:
        raise _passthrough_error(resp.status_code, _detail_from_response(resp))
    try:
        data = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "reason_code": "weather_service_invalid_response",
                "message_ar": "تعذّر قراءة استجابة خدمة الطقس.",
            },
        ) from exc
    return data if isinstance(data, dict) else {"value": data}


def et0_unavailable_http_exception(prod: dict[str, Any] | None):
    """HTTPException حين يعيد المحرّك ``et0_mm=None`` — مكسور ≠ عطل تبعيّة.

    المحرّك يرفض المُدخَل المستحيل فيزيائيّاً ويُسمّيه في ``invalid_inputs``: هذا خطأ
    مُدخَل من المستدعي ⇒ **422** بأسماء الحقول المرفوضة وأسبابها (لا يُعاد المحاولة).
    غيرُ ذلك (مُدخَل مفقود/استجابة بلا ET0) ⇒ **503** fail-closed كما كان (لا ET0 محلّيّ).
    """
    from fastapi import HTTPException

    prod = prod or {}
    invalid = [str(n) for n in (prod.get("invalid_inputs") or [])]
    if invalid:
        return HTTPException(
            status_code=422,
            detail={
                "reason_code": "invalid_weather_inputs",
                "invalid_inputs": invalid,
                "limitations": [str(x) for x in (prod.get("limitations") or [])],
            },
        )
    return HTTPException(
        status_code=503,
        detail="weather-engine returned no ET0 — fail-closed (no local ET0 fallback)",
    )


def et0_unavailable_field_response(
    prod: dict[str, Any] | None,
    field_id: str,
    season_id: str | None,
    inputs: dict[str, Any],
    evidence_ids: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    """جسمُ ``dependency_unavailable`` لتوصية ريّ الحقل حين يعيد المحرّك ``et0_mm=None``.

    طقسُ الحقل نفسُه رُفض أو نقص (لا خطأ من المستدعي): فشلٌ مُغلَق بلا توصية، بأسماء
    المرفوض (``invalid_inputs``) وأسباب المحرّك بدل ``float(None)`` ⇒ 500. يعيش هنا لا في
    الراوتر كي يبقى ``routers/irrigation_recommendation.py`` تحت سقف
    ``tests/architecture/test_router_size_ratchet.py``؛ الشكلُ نفسُه حرفيّاً.
    """
    prod = prod or {}
    return {
        "status": "dependency_unavailable",
        "field_id": field_id,
        "season_id": season_id,
        "inputs": inputs,
        "recommendation": None,
        "ownership": "recommendation_candidate → decision-service",
        "confidence": None,
        "evidence_ids": evidence_ids,
        "invalid_inputs": list(prod.get("invalid_inputs") or []),
        "limitations": [
            *limitations,
            "weather-engine returned no ET0 — fail-closed (no local ET0 fallback)",
            *[str(x) for x in (prod.get("limitations") or [])],
        ],
        "calibrated": False,
    }


async def get_et0_product(
    *,
    t_max_c: float | None,
    t_min_c: float | None,
    solar_rad_mj_m2: float | None = None,
    rh_mean_pct: float | None = None,
    wind_2m_ms: float | None = None,
    t_mean_c: float | None = None,
    lat_deg: float | None = None,
    elevation_m: float | None = None,
    day_of_year: int | None = None,
    valid_time: str | None = None,
    weather_snapshot_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """منتج ET0 المرجعيّ (FAO-56) من محرّك الطقس — **مصدر ET0 الوحيد للمنصّة**.

    الصيغة تُنفَّذ في المحرّك لا هنا. يعيد العقد الكامل: et0_mm/method/quality_status/
    formula_version/valid_time/weather_snapshot_id. تعذّر المحرّك ⇒ HTTPException(502)
    (لا يُحسب ET0 محلّيّاً بديلاً — fail-closed).
    """
    body = {
        "t_max_c": t_max_c,
        "t_min_c": t_min_c,
        "solar_rad_mj_m2": solar_rad_mj_m2,
        "rh_mean_pct": rh_mean_pct,
        "wind_2m_ms": wind_2m_ms,
        "t_mean_c": t_mean_c,
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year": day_of_year,
        "valid_time": valid_time,
        "weather_snapshot_id": weather_snapshot_id,
    }
    product = await weather_post_json("/v1/weather/agro/et0", json_body=body, tenant_id=tenant_id)
    return _validated_et0_product(product)


def _validated_et0_product(product: Any) -> dict[str, Any]:
    """Check the ET0 owner contract, without recalculation or quality promotion.

    A valid degraded numeric result remains advisory data. Missing ET0 remains
    None with the owner's rejection details for existing 422/503 handling.
    Malformed successful HTTP responses are dependency failures, not caller
    input errors. This validator deliberately does not apply to other products.
    """
    from fastapi import HTTPException

    def invalid_response():
        return HTTPException(
            status_code=502,
            detail={
                "reason_code": "weather_service_invalid_response",
                "message_ar": "استجابة منتج ET₀ من خدمة الطقس غير صالحة.",
            },
        )

    if not isinstance(product, dict):
        raise invalid_response()
    if product.get("product") != "et0" or product.get("unit") != "mm/day":
        raise invalid_response()
    for key in ("formula_version", "weather_snapshot_id"):
        if not isinstance(product.get(key), str) or not product[key].strip():
            raise invalid_response()
    if "valid_time" not in product or (
        product["valid_time"] is not None and not isinstance(product["valid_time"], str)
    ):
        raise invalid_response()
    for key in ("missing_inputs", "invalid_inputs", "limitations"):
        values = product.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise invalid_response()
    value = product.get("et0_mm")
    method, quality = product.get("method"), product.get("quality_status")
    completeness = product.get("input_completeness")
    try:
        valid_completeness = (
            type(completeness) in (int, float)
            and math.isfinite(completeness)
            and 0 <= completeness <= 1
        )
    except OverflowError:
        valid_completeness = False
    if not valid_completeness:
        raise invalid_response()
    if (
        method == "fao56_penman_monteith"
        and quality == "validated"
        and (completeness != 1 or product["missing_inputs"] or product["invalid_inputs"])
    ):
        raise invalid_response()
    if "et0_mm" not in product:
        raise invalid_response()
    if value is None:
        if method != "insufficient" or quality not in ("insufficient", "invalid"):
            raise invalid_response()
    else:
        try:
            finite_nonnegative = type(value) in (int, float) and math.isfinite(value) and value >= 0
        except OverflowError:
            finite_nonnegative = False
        if not finite_nonnegative:
            raise invalid_response()
        if not (
            (method == "fao56_penman_monteith" and quality in ("validated", "degraded"))
            or (method == "hargreaves_fallback" and quality == "degraded")
        ):
            raise invalid_response()
    return product


async def get_irrigation_et0_product(
    *,
    t_min_c: float,
    t_max_c: float,
    solar_rad_mj_m2: float | None,
    rh_mean_pct: float | None,
    wind_2m_ms: float | None,
    day_of_year: int,
    latitude_deg: float,
    elevation_m: float | None,
    valid_time: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """ET0 من محرّك الطقس — **مصدر ET0 الوحيد**. تعذّره ⇒ HTTPException (لا محلّيّ).

    ``elevation_m=None`` (ارتفاعُ الحقل مجهول) يُمرَّر غائباً: المحرّك يُعلِن الجودة
    ``degraded`` وقيدَ «مستوى البحر» بدل ارتفاعٍ ثابتٍ يُفترَض صامتاً.

    نقطة وصل قابلة للـmonkeypatch في الاختبار (تُثبِت أنّ المسار يستهلك المحرّك فعلاً).
    """
    return await get_et0_product(
        t_max_c=t_max_c,
        t_min_c=t_min_c,
        solar_rad_mj_m2=solar_rad_mj_m2,
        rh_mean_pct=rh_mean_pct,
        wind_2m_ms=wind_2m_ms,
        lat_deg=latitude_deg,
        elevation_m=elevation_m,
        day_of_year=day_of_year,
        valid_time=valid_time,
        tenant_id=tenant_id,
    )


def et0_provenance(prod: dict) -> dict:
    """كتلة نَسَب ET0 للمخرَج — المصدر والعقد (المحرّك مصدر ET0 الوحيد؛ لا إرث محلّيّ)."""
    return {
        "et0_mm": prod.get("et0_mm"),
        "method": prod.get("method"),
        "quality_status": prod.get("quality_status"),
        "formula_version": prod.get("formula_version"),
        "valid_time": prod.get("valid_time"),
        "weather_snapshot_id": prod.get("weather_snapshot_id"),
        "unit": prod.get("unit"),
        "input_completeness": prod.get("input_completeness"),
        "missing_inputs": list(prod.get("missing_inputs") or []),
        "invalid_inputs": list(prod.get("invalid_inputs") or []),
        "limitations": list(prod.get("limitations") or []),
        "source": "weather-engine",
    }


async def get_et0_series(
    *,
    daily_t_min: list,
    daily_t_max: list,
    lat_deg: float | None,
    elevation_m: float | None = None,
    day_of_year_start: int | None = None,
    daily_dates: list | None = None,
    daily_solar_rad_mj_m2: list | None = None,
    daily_rh_mean_pct: list | None = None,
    daily_wind_2m_ms: list | None = None,
    valid_period: dict | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """سلسلة ET0 اليوميّة المرجعيّة من محرّك الطقس — **مصدر ET0 الوحيد للمحاكاة**.

    النواة تُنفَّذ في المحرّك (لا نواة محلّيّة). ``daily_dates`` (تواريخ ISO لكلّ يوم،
    اختياريّ) لها الأولويّة على ``day_of_year_start`` — يحسب المحرّك DOY لكلّ يوم بلا
    انجراف في السجلّات المتفرّقة. يعيد daily_et0_mm (قد يحوي None ليوم ناقص) + methods +
    accumulated. تعذّر المحرّك ⇒ HTTPException(502) (لا Hargreaves محلّيّ).
    """
    body = {
        "daily_t_min": list(daily_t_min),
        "daily_t_max": list(daily_t_max),
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year_start": day_of_year_start,
        "daily_dates": list(daily_dates) if daily_dates is not None else None,
        "daily_solar_rad_mj_m2": daily_solar_rad_mj_m2,
        "daily_rh_mean_pct": daily_rh_mean_pct,
        "daily_wind_2m_ms": daily_wind_2m_ms,
        "valid_period": valid_period,
    }
    return await weather_post_json(
        "/v1/weather/agro/et0/series", json_body=body, tenant_id=tenant_id
    )


async def get_hourly_etc_product(
    *,
    lat: float,
    lon: float,
    horizon_hours: int,
    daily_kc_by_date: dict[str, float],
    daily_runoff_mm_by_date: dict[str, float] | None = None,
    model: str = "best_match",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Provider-native hourly ET0/ETc product from Weather Engine; no local fallback."""
    body = {
        "lat": lat,
        "lon": lon,
        "horizon_hours": horizon_hours,
        "daily_kc_by_date": dict(daily_kc_by_date),
        "daily_runoff_mm_by_date": dict(daily_runoff_mm_by_date or {}),
        "model": model,
    }
    return await weather_post_json(
        "/v1/weather/agro/etc/hourly", json_body=body, tenant_id=tenant_id
    )


async def get_gdd_product(
    *,
    daily_t_min: list,
    daily_t_max: list,
    base_c: float | None,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
    start_date: str | None = None,
    end_date: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """منتج GDD الموحَّد من محرّك الطقس — **مصدر نواة GDD الوحيد للمنصّة**.

    النواة تُنفَّذ في المحرّك؛ السياسة (base_c/upper_cutoff_c/method) من Season وتُمرَّر.
    يعيد العقد الموحَّد (daily_gdd/accumulated_gdd/thresholds_used/calculation_version/
    valid_period). تعذّر المحرّك ⇒ HTTPException(502) (لا حساب GDD محلّيّ بديل).
    """
    body = {
        "daily_t_min": list(daily_t_min),
        "daily_t_max": list(daily_t_max),
        "base_c": base_c,
        "upper_cutoff_c": upper_cutoff_c,
        "method": method,
        "start_date": start_date,
        "end_date": end_date,
    }
    return await weather_post_json("/v1/weather/agro/gdd", json_body=body, tenant_id=tenant_id)


async def get_canonical_field_weather(
    lat: float,
    lon: float,
    *,
    tenant_id: str | None = None,
    model: str = "best_match",
) -> dict[str, Any] | None:
    """Resolve the owner-produced canonical weather state for a field location.

    The platform does not rebuild weather facts.  ``weather-service`` fetches the
    observation and returns a view carrying the canonical state identity.  This
    adapter only reconstructs the *state envelope* from fields already emitted by
    that owner-facing response so ``canonical_field_state`` can bind the evidence.

    Failures and incomplete provenance are absence (``None``), never a fabricated
    healthy product.
    """
    try:
        current = await weather_get_json(
            "/v1/weather/current",
            tenant_id=tenant_id,
            params={"lat": lat, "lon": lon, "model": model},
            timeout_s=8.0,
        )
    except Exception:  # noqa: BLE001 -- field-state composition is fail-closed on absence
        return None
    if current.get("derived_from") != "canonical_weather_state":
        return None
    state_id = current.get("canonical_state_id")
    state_version = current.get("canonical_state_version")
    # هويّةُ المخطَّط يُعلنها المالكُ ولا تُشتقّ هنا. كان هذا الموضع يضع ``state_version`` مكانها،
    # والمالكُ يُصدِره semver (``1.0.0`` — ``canonical_weather_state.STATE_VERSION``) لا اسمَ عائلة،
    # فرفضت ``canonical_field_state`` كلَّ طقسٍ ``validated`` بوصفه ``weather_noncanonical_schema``
    # (مقيسٌ حيّاً 2026-09-29). وشاهدُه القديم مرّ على قاموسٍ منسوخٍ باليد يضع اسمَ العائلة في
    # ``canonical_state_version`` — قيمةٌ لم يُصدِرها المالكُ قطّ. غيابُ الإعلان ⇒ غيابٌ لا تخمين.
    schema_version = current.get("canonical_schema_version")
    source_snapshot_id = current.get("source_snapshot_id") or current.get("weather_snapshot_id")
    if not state_id or not state_version or not schema_version or not source_snapshot_id:
        return None
    quality = current.get("quality_status")
    limitations = list(current.get("limitations") or [])
    return {
        "product_id": "canonical_weather_state",
        "state_id": state_id,
        "state_version": state_version,
        "schema_version": str(schema_version),
        "owner": "weather-service",
        "source_snapshot_id": source_snapshot_id,
        "generated_at": current.get("observed_at")
        or current.get("time")
        or current.get("timestamp"),
        "quality": quality,
        # canonical_field_state uses the cross-owner ``quality_status`` declaration.
        "quality_status": quality,
        "availability": {"current": quality not in {None, "insufficient", "invalid"}},
        "provenance": {
            "current": {
                "quality_status": quality,
                "weather_snapshot_id": source_snapshot_id,
            }
        },
        "evidence": {
            "canonical_state_id": state_id,
            "source_snapshot_id": source_snapshot_id,
            "observed_fields": list(current.get("observed_fields") or []),
        },
        "limitations": limitations,
        "products": {"current": current},
    }


async def get_current_weather(
    lat: float, lon: float, *, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/current", params={"lat": lat, "lon": lon, "model": model}
    )


async def get_weather_forecast(
    lat: float, lon: float, *, days: int = 7, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/forecast", params={"lat": lat, "lon": lon, "days": days, "model": model}
    )


async def get_weather_historical(
    lat: float,
    lon: float,
    *,
    start_date: str,
    end_date: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Canonical weather-service historical view, with tenant-scoped service identity."""
    return await weather_get_json(
        "/v1/weather/historical",
        tenant_id=tenant_id,
        params={"lat": lat, "lon": lon, "start_date": start_date, "end_date": end_date},
    )


def _neutral_tile(z: int, x: int, y: int, *, layer: str) -> dict[str, Any]:
    """Neutral tile payload returned when weather-service is unreachable (502).

    Preserves the "don't flood the map with 502 per tile" guarantee across the
    platform->weather-service network hop: the map draws an empty/neutral tile
    instead of erroring on every request.
    """
    return {
        "tile": {"z": z, "x": x, "y": y},
        "layer": layer,
        "value": None,
        "sample": None,
        "available": False,
        "cache_state": "service_unavailable",
        "upstream_error": "weather-service unreachable",
        "rendered_by": "sahool-client-gridlayer",
    }


async def get_weather_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    layer: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/tile-data/{z}/{x}/{y}",
            params={"layer": layer, "time": time, "model": model, "interpolation": interpolation},
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=layer)
        raise


#: أعلى تكبيرٍ تقبله ``/v1/weather/tile-data`` — مركزُ بلاطته على بُعد عشرات الأمتار من النقطة،
#: أدقّ بكثيرٍ من شبكة نموذج الطقس (~كيلومترات)، فالعيّنةُ هي عيّنةُ النقطة عملياً.
POINT_SAMPLE_ZOOM = 18
_MERCATOR_MAX_LAT = 85.05112878


def point_sample_tile(
    lat: float, lon: float, *, z: int = POINT_SAMPLE_ZOOM
) -> tuple[int, int, int]:
    """بلاطةُ Web-Mercator التي تحوي النقطة عند التكبير ``z`` — حسابٌ نقيّ بلا شبكة."""
    lat_c = max(-_MERCATOR_MAX_LAT, min(_MERCATOR_MAX_LAT, float(lat)))
    n = 2**z
    x = int((float(lon) + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat_c)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return z, max(0, min(n - 1, x)), max(0, min(n - 1, y))


#: مفاتيحُ عيّنة weather-service (``open_meteo.normalize_tile_sample``/``normalize_current``) ⇐
#: مفاتيحُ عيّنة المنصّة التي يقرؤها كلُّ مستهلكٍ فيها والواجهةُ (``temperature_2m_c`` …).
#: الخدمةُ تُسمّي الحرارةَ ``temperature_c`` والمنصّةُ ``temperature_2m_c``: بلا هذا التحويل يقرأ
#: ``_operation_suitability`` و``derive_weather_alerts`` ``None`` فيرجعان إلى افتراضاتهما (25°م، 55٪)
#: ويوصيان بالرشّ في موجة حرّ (W1-22، مراجعة HIGH).
_SERVICE_TO_PLATFORM_SAMPLE_KEYS: dict[str, str] = {
    "temperature_c": "temperature_2m_c",
    "humidity_pct": "relative_humidity_2m_pct",
    "vpd_kpa": "vapour_pressure_deficit_kpa",
    "et0_mm": "et0_fao_evapotranspiration_mm",
}

#: مفاتيحُ يتشاركها المخطّطان بالاسم نفسه — تُنسخ كما هي (``None`` يبقى ``None``).
_SHARED_SAMPLE_KEYS: tuple[str, ...] = (
    "precipitation_mm",
    "cloud_cover_pct",
    "surface_pressure_hpa",
    "wind_speed_10m_kmh",
    "wind_direction_10m_deg",
    "wind_gusts_10m_kmh",
    "wind_direction_source",
    "weather_code",
    "is_day",
    "soil_temperature_6cm_c",
    "soil_temperature_18cm_c",
    "soil_temperature_54cm_c",
    "soil_moisture_1_to_3cm_m3m3",
    "soil_moisture_3_to_9cm_m3m3",
    "time",
    "source",
)

#: مفاتيحُ في مخطّط المنصّة تُنتجها الخدمةُ من متغيّراتٍ مستقلّة (``pressure_msl`` ·
#: ``precipitation_probability`` …) — وما لم تُعِده يبقى ``None`` (غيابٌ لا صفر)، فلا يُشتقّ ضغطُ
#: سطح البحر من ضغط السطح بلا ارتفاع، ولا احتمالُ مطرٍ من مطرٍ مقيس.
_PLATFORM_ONLY_SAMPLE_KEYS: tuple[str, ...] = (
    "pressure_msl_hpa",
    "precipitation_probability_pct",
    "soil_temperature_0cm_c",
    "soil_moisture_0_to_1cm_m3m3",
)


def platform_sample_from_service(sample: dict[str, Any]) -> dict[str, Any]:
    """يحوّل عيّنةَ weather-service إلى مخطّط العيّنة الذي تقرؤه المنصّةُ والواجهة.

    - المفاتيحُ المختلفة الاسم تُترجَم (``temperature_c`` ⇒ ``temperature_2m_c`` …)؛
    - المشتركةُ تُنسخ، والخاصّةُ بالمنصّة تبقى ``None`` — **لا ``or 0``**: ``0`` قراءةٌ صحيحة
      (0°م، 0 ملم) تُحفظ، والغيابُ يبقى غياباً؛
    - VPD وET0 لا يُشتقّان هنا: معادلاتُهما ملكُ محرّك الطقس (``weather_engine_formula_guard``)،
      فما لم تُعِده الخدمة يبقى ``None`` ويُقرأ غياباً؛
    - الحقولُ الأصليّة تبقى تحت ``service_sample`` للتتبّع.
    """
    src = dict(sample or {})
    out: dict[str, Any] = {}
    location = src.get("location") if isinstance(src.get("location"), dict) else {}
    out["lat"] = location.get("lat", src.get("lat"))
    out["lon"] = location.get("lon", src.get("lon"))
    for service_key, platform_key in _SERVICE_TO_PLATFORM_SAMPLE_KEYS.items():
        value = src.get(platform_key)
        out[platform_key] = value if value is not None else src.get(service_key)
    for key in _SHARED_SAMPLE_KEYS:
        out[key] = src.get(key)
    for key in _PLATFORM_ONLY_SAMPLE_KEYS:
        out[key] = src.get(key)
    out["timestamp"] = src.get("timestamp", src.get("time"))
    if isinstance(src.get("time_resolution"), dict):
        # صفُّ الساعة الذي جاءت منه الحقولُ الساعيّة (``hourly_row_time``) وقيودُه يبقى مرئياً.
        out["time_resolution"] = src["time_resolution"]
    # الغيابُ مُعلَنٌ لا مستنتَج: كلُّ قراءةٍ في مخطّط المنصّة لم تُعِدها الخدمة تُسمّى هنا،
    # فيرى المستهلكُ (والواجهة) أنّ ``vapour_pressure_deficit_kpa: null`` غيابٌ لا قيمة.
    out["missing_fields"] = sorted(key for key in _SAMPLE_READING_KEYS if out.get(key) is None)
    out["service_sample"] = src
    return out


#: قراءاتُ العيّنة (لا الهويّة/الزمن) التي يُعلَن غيابُها في ``missing_fields``.
_SAMPLE_READING_KEYS: tuple[str, ...] = tuple(
    sorted(
        {
            *_SERVICE_TO_PLATFORM_SAMPLE_KEYS.values(),
            *(
                k
                for k in _SHARED_SAMPLE_KEYS
                if k not in {"time", "source", "wind_direction_source"}
            ),
            *_PLATFORM_ONLY_SAMPLE_KEYS,
        }
    )
)


@dataclass(frozen=True)
class PointWeatherSample:
    """عيّنةُ نقطة بمخطّط المنصّة + حالةُ مخبّأ weather-service كما أعلنها (لا «refreshed» مُفترَضة)."""

    sample: dict[str, Any]
    cache_state: str | None
    cache_age_s: int | None
    upstream_error: str | None

    @property
    def is_stale(self) -> bool:
        return self.cache_state in {"stale", "stale_fallback"}


async def get_point_weather_sample_with_state(
    lat: float, lon: float, *, time: str = "now", model: str = "best_match"
) -> PointWeatherSample:
    """عيّنةُ الطقس الساعيّة لنقطة — من weather-service لا من موصّل المزوّد (W1-22).

    كانت مساراتُ الخريطة والتنبيهات والمسبار في المنصّة تستورد
    ``api.connectors.openmeteo.fetch_weather_tile_data`` فتخرج إلى المزوّد مباشرةً متجاوزةً
    مخبّأ خدمة الطقس وعقد الواجهة P3.4. الخدمةُ لا تعرض نقطةً بـlat/lon، لكنّ
    ``/v1/weather/tile-data`` يُعيد عيّنةَ مركز البلاطة — فنطلب بلاطةَ النقطة عند أعلى تكبير،
    ثمّ نحوّلها إلى مخطّط المنصّة (``platform_sample_from_service``).

    **والغيابُ يرفع ولا يُختلَق:** بلاطةٌ محايدة (الخدمة غير متاحة) أو بلا ``sample`` ⇒
    ``RuntimeError`` يُسمّي السبب، فيقرّر المستدعي (مخبّأٌ قديم أو 502 صريح) — لا عيّنةَ فارغة
    تُقرأ «لا رياح ولا مطر». و**القِدَمُ يُنقَل ولا يُمحى:** عيّنةٌ قدّمتها الخدمة من مخبّئها القديم
    (``stale_fallback``) تصل بحالتها وعمرها وخطئها، لا بوصفها «refreshed» بعمر صفر.
    """
    z, x, y = point_sample_tile(lat, lon)
    tile = await get_weather_tile_data(z, x, y, layer="temperature", time=time, model=model)
    sample = tile.get("sample") if isinstance(tile, dict) else None
    if not isinstance(sample, dict) or not sample:
        reason = None
        if isinstance(tile, dict):
            reason = tile.get("upstream_error") or tile.get("cache_state")
        _PROVIDER_HEALTH.failure(f"point_sample_unavailable:{reason or 'no sample'}")
        raise RuntimeError(f"weather-service point sample unavailable: {reason or 'no sample'}")
    age = tile.get("cache_age_s")
    try:
        age_s = int(age) if age is not None else None
    except (TypeError, ValueError):
        age_s = None
    upstream_error = tile.get("upstream_error")
    if tile.get("cache_state") in {"stale", "stale_fallback"} and upstream_error:
        # الخدمةُ حيّة لكنّ مزوّدها متعثّر: تخدم من مخبّئها القديم. هذا ما كان قاطعُ الموصّل يقيسه.
        _PROVIDER_HEALTH.failure(f"provider_stale:{upstream_error}")
    else:
        _PROVIDER_HEALTH.success()
    return PointWeatherSample(
        sample=platform_sample_from_service(sample),
        cache_state=tile.get("cache_state"),
        cache_age_s=age_s,
        upstream_error=str(upstream_error) if upstream_error else None,
    )


async def get_point_weather_sample(
    lat: float, lon: float, *, time: str = "now", model: str = "best_match"
) -> dict[str, Any]:
    """العيّنةُ وحدها بمخطّط المنصّة — انظر ``get_point_weather_sample_with_state``."""
    result = await get_point_weather_sample_with_state(lat, lon, time=time, model=model)
    return result.sample


async def get_operation_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    operation: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/operation-tile-data/{z}/{x}/{y}",
            params={
                "operation": operation,
                "time": time,
                "model": model,
                "interpolation": interpolation,
            },
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=operation)
        raise


async def get_operation_window(
    lat: float, lon: float, *, operation: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-window",
        params={"lat": lat, "lon": lon, "operation": operation, "hours": hours, "model": model},
    )


async def get_operation_plan(
    lat: float, lon: float, *, operations: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-plan",
        params={"lat": lat, "lon": lon, "operations": operations, "hours": hours, "model": model},
    )


async def get_thermal_stress(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """منتج الإجهاد الحراريّ المركّب من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/thermal-stress", params=params)


async def get_lodging_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    plant_height_cm: float | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الرقود من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    if plant_height_cm is not None:
        params["plant_height_cm"] = plant_height_cm
    return await weather_get_json("/v1/weather/lodging-risk", params=params)


async def get_pollination_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الطقس على التلقيح من weather-service."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/pollination-risk", params=params)


async def get_chill_accumulation(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """تراكم البرودة الموسميّ من weather-service (نافذة تاريخيّة)."""
    params: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "start_date": start_date,
        "end_date": end_date,
    }
    if crop:
        params["crop"] = crop
    return await weather_get_json("/v1/weather/chill-accumulation", params=params)


async def get_weather_tile_series(
    z: int, x: int, y: int, *, layer: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/tile-series/{z}/{x}/{y}",
        params={"layer": layer, "hours": hours, "model": model},
    )


async def get_wind_grid(
    z: int, x: int, y: int, *, time: str = "now", model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/wind-grid/{z}/{x}/{y}",
        params={"time": time, "model": model},
    )


async def get_tile_cache_stats() -> dict[str, Any]:
    """إحصاءات مخبّأ البلاطات من weather-service.

    **المسار هو `cache-stats` لا `tile-cache/stats`:** الخدمة تُعلن
    `app.get("/v1/weather/cache-stats")` وليس في سطحها كلِّه مسارٌ باسم
    `tile-cache/stats` — فالطلب القديم كان يُنهي 404 حتماً على كلّ نداء.
    والاسمان لدالّةٍ خلفيّةٍ واحدة (`rt.tile_cache_stats`)، فالانحراف كان في
    السلسلة النصّيّة وحدها؛ ولذلك صُحِّح العميلُ ولم يُمَسّ مسارُ الخدمة —
    تغييرُه كان سيكسر أيَّ مستهلكٍ آخر يناديه بالاسم القانونيّ.

    ومسارُ المنصّة العامّ `/api/v1/weather/tile-cache/stats` يبقى كما هو:
    هذه القفزةُ داخليّة بين المنصّة والخدمة، لا عقدٌ مع الواجهة.
    """
    return await weather_get_json("/v1/weather/cache-stats")


async def field_irrigation_weather_snapshot(
    latitude_deg: float, longitude_deg: float, *, forecast_loader=None
) -> dict:
    """لقطة طقس اليوم من محرّك الطقس (المصدر الوحيد) — المسار الأساسيّ لـD.2c.

    يجلب توقّع اليوم لموقع الحقل ويشتقّ day-of-year من ``valid_time``. تعذّر المحرّك
    أو غياب أيّام ⇒ HTTPException (fail-closed؛ لا توصية على طقس مفقود). نقطة وصل
    قابلة للـmonkeypatch.

    weather-5: الرطوبة والريح كانتا مثبّتتين على ``None`` فيسقط ET0 التوصية إلى Hargreaves
    دائماً، مع أنّ التوقّع اليوميّ يُصدِر ``rh_mean_pct`` و``wind_mean_10m_ms``. تُؤخَذان
    الآن بالتحويل الواحد مع دفتر الماء (``et0_weather_inputs``): **المتوسّط** على 10م ⇒ 2م
    بمعادلة FAO-56 47، ولا تُشتقّ الريح من القصوى أبداً؛ غيابُ أيٍّ منهما يبقى ``None``.
    """
    from datetime import date as _date

    from fastapi import HTTPException

    from api.water_ledger_inputs import et0_weather_inputs
    from api.weather_advice import RAIN_RECENT_NOT_OBSERVED, irrigation_rain_window

    # ثلاثةُ أيّامٍ لا يوم: المطرُ جزءٌ من المدخَل لا زينة — كلُّها لـ``forecast_rain_mm``
    # (مجموعُ اليوم توقّعٌ لا رصد، مراجعة #1329)، و``rain_recent_mm`` غيرُ مرصودٍ هنا فلا
    # يُخصَم. ونافذةٌ ثانيةٌ في هذا المسار كانت ستُعطي المزارعَ توصيتين
    # مختلفتين بحسب أيّ مسارٍ سأل.
    loader = forecast_loader or get_weather_forecast
    fc = await loader(latitude_deg, longitude_deg, days=3)
    days = fc.get("days") or []
    if not days:
        raise HTTPException(
            status_code=503,
            detail="weather-engine forecast returned no days — fail-closed (no recommendation)",
        )
    d0 = days[0]
    valid_time = d0.get("date")
    try:
        doy = _date.fromisoformat(valid_time).timetuple().tm_yday if valid_time else None
    except (TypeError, ValueError):
        doy = None
    # G8: ``irrigation_rain_window`` هو التعريفُ الواحد الذي يسأله مسارُ مساحة العمل
    # أيضاً؛ فترةٌ ناقصةٌ ⇒ ``None`` لا صفر، ومطرٌ لم يهطل لا يُخصَم (``rain_recent_source``).
    rain_recent, forecast_rain, _missing = irrigation_rain_window(
        [d.get("precipitation_mm") for d in days[:3]]
    )
    pm_inputs = et0_weather_inputs(d0)
    return {
        "t_min_c": d0.get("temp_min_c"),
        "t_max_c": d0.get("temp_max_c"),
        # The daily mean at 10 m converted to 2 m (FAO-56 Eq. 47); the forecast maximum
        # (wind_max_ms) is never used, so a maximum alone leaves wind absent.
        "wind_2m_ms": pm_inputs["wind_2m_ms"],
        "solar_rad_mj_m2": d0.get("solar_radiation_mj_m2"),
        "rh_mean_pct": pm_inputs["rh_mean_pct"],
        "rain_recent_mm": rain_recent,
        "rain_recent_source": RAIN_RECENT_NOT_OBSERVED,
        "forecast_rain_mm": forecast_rain,
        "day_of_year": doy,
        "valid_time": valid_time,
        "source": "weather-engine-forecast",
    }


# ─── قراءاتٌ مُصنَّفة فوق مشاهدات weather-service (W1-22) ─────────────────────────
#
# كانت التوصياتُ والتنبيهاتُ وETc ولوحةُ الحقل ومساحةُ الموسم وحزمةُ AI تستورد
# ``api.connectors.openmeteo`` فتخرج إلى المزوّد مباشرةً متجاوزةً weather-service (نظامَ السجلّ
# ومخبّأه وحالتَه الكنسيّة). وتلك المساراتُ تقرأ سماتٍ (``today.et0_mm`` · ``current.humidity_pct``)
# بينما هذا العميلُ يُعيد المشاهداتِ قواميس: «الآن» مُسطَّحاً، والأيّامُ تحت ``days``. فهذا هو
# المُحوِّلُ الوحيد بين الشكلين: لا يجلب من مزوّد ولا يحسب طقساً، ينسخ حقولَ المشاهدة إلى
# أصنافٍ مجمّدة بأسماء سمات الموصّل نفسِها.
#
# **والغيابُ يبقى ``None``:** مفتاحٌ غائب أو ``null`` أو غيرُ رقميّ أو منطقيّ أو غيرُ منتهٍ ⇒
# ``None``، لا ``0``. الصفرُ قراءةٌ فيزيائيّة (0 مم = لا مطر)، وقسرُ الغياب إليه يقلب «مجهول»
# إلى «جافّ» أو «ساكن».

READING_SOURCE = "weather-service"


def reading(source: Any, key: str) -> float | None:
    """A finite number from ``source[key]`` or ``None`` — there is no zero default."""
    if not isinstance(source, dict):
        return None
    value = source.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _code(source: dict[str, Any], key: str) -> int | None:
    number = reading(source, key)
    return int(number) if number is not None else None


def _text(source: dict[str, Any], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class CurrentReading:
    temperature_c: float | None
    humidity_pct: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    wind_direction_source: str | None
    wind_gusts_ms: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    weather_code: int | None
    is_day: bool | None
    timestamp: str | None
    quality_status: str | None = None
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
    canonical_state_id: str | None = None
    source: str = READING_SOURCE


@dataclass(frozen=True)
class DailyReading:
    date: str | None
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_mm: float | None
    et0_mm: float | None
    sunshine_hours: float | None
    wind_max_ms: float | None
    weather_code: int | None
    sunrise: str | None = None
    sunset: str | None = None
    daylight_hours: float | None = None
    solar_radiation_mj_m2: float | None = None


def current_from_view(view: Any) -> CurrentReading:
    """``current_view`` dict → :class:`CurrentReading` (absent ⇒ ``None``)."""
    if not isinstance(view, dict):
        raise ValueError("weather-service current view is not an object")
    is_day = view.get("is_day")
    missing = view.get("missing_fields")
    return CurrentReading(
        temperature_c=reading(view, "temperature_c"),
        humidity_pct=reading(view, "humidity_pct"),
        wind_speed_ms=reading(view, "wind_speed_ms"),
        wind_direction_deg=reading(view, "wind_direction_deg"),
        wind_direction_source=_text(view, "wind_direction_source"),
        wind_gusts_ms=reading(view, "wind_gusts_ms"),
        precipitation_mm=reading(view, "precipitation_mm"),
        cloud_cover_pct=reading(view, "cloud_cover_pct"),
        weather_code=_code(view, "weather_code"),
        is_day=is_day if isinstance(is_day, bool) else None,
        timestamp=_text(view, "timestamp") or _text(view, "time"),
        quality_status=_text(view, "quality_status"),
        missing_fields=tuple(str(m) for m in missing) if isinstance(missing, list) else (),
        canonical_state_id=_text(view, "canonical_state_id"),
    )


def daily_from_view(view: Any) -> list[DailyReading]:
    """``forecast_view``/``historical_view`` dict → days in order (absent ⇒ ``None``).

    The days sit under ``days``; reading them from the root yields a silent empty list,
    so a view without a ``days`` list is an error, not "no days".
    """
    if not isinstance(view, dict) or not isinstance(view.get("days"), list):
        raise ValueError("weather-service daily view has no `days` list")
    return [
        DailyReading(
            date=_text(day, "date"),
            temp_max_c=reading(day, "temp_max_c"),
            temp_min_c=reading(day, "temp_min_c"),
            precipitation_mm=reading(day, "precipitation_mm"),
            et0_mm=reading(day, "et0_mm"),
            sunshine_hours=reading(day, "sunshine_hours"),
            wind_max_ms=reading(day, "wind_max_ms"),
            weather_code=_code(day, "weather_code"),
            sunrise=_text(day, "sunrise"),
            sunset=_text(day, "sunset"),
            daylight_hours=reading(day, "daylight_hours"),
            solar_radiation_mj_m2=reading(day, "solar_radiation_mj_m2"),
        )
        for day in view["days"]
        if isinstance(day, dict)
    ]


async def current_reading(lat: float, lon: float, *, model: str = "best_match") -> CurrentReading:
    return current_from_view(await get_current_weather(lat, lon, model=model))


async def forecast_readings(
    lat: float, lon: float, *, days: int = 7, model: str = "best_match"
) -> list[DailyReading]:
    return daily_from_view(await get_weather_forecast(lat, lon, days=days, model=model))


async def historical_readings(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    *,
    tenant_id: str | None = None,
) -> list[DailyReading]:
    view = await get_weather_historical(
        lat, lon, start_date=start_date, end_date=end_date, tenant_id=tenant_id
    )
    return daily_from_view(view)


# ─── ملخّصُ الطقس التاريخيّ لحزمة سياق الحقل (W1-22) — دوالُّ نقيّة بلا شبكة ولا قاعدة ────────
#
# يقرأ ``DailyReading`` المشتقّةَ من ``historical_view`` (``daily_from_view`` أعلاه)، فموضعُه بجانبها
# لا في الراوتر (حدُّ حجم الراوترات) ولا في وحدةٍ جديدة. ``api.routers.field_ai_context`` يستدعيه
# ويُعيد تصديرَه. **الغيابُ يبقى ``None`` في كلّ مستوى**، واليومُ المطلوبُ المحذوفُ من الاستجابة
# غيابٌ كاليوم الفارغ.


def _complete_total(values: list[float | None]) -> float | None:
    """مجموعُ سلسلةٍ **مكتملة** أو ``None`` — الغيابُ لا يُجمَع صفراً.

    كانت الحزمةُ تجمع ``float(d.precipitation_mm or 0)``: يومٌ بلا قراءة مطرٍ يُحسَب
    «يوماً جافّاً»، فيصل المستشارَ مجموعٌ أصغرُ من الواقع موسوماً كاملاً، ويُوصي بالريّ
    على جفافٍ لم يُرصَد (weather-4). عددُ الأيّام الناقصة يُعلَن بجانبه بدل إخفائه.
    """
    if not values or any(v is None for v in values):
        return None
    return round(sum(v for v in values if v is not None), 2)


def _missing_count(values: list[float | None]) -> int:
    return sum(1 for v in values if v is None)


def _observed_total(values: list[float | None]) -> float | None:
    """مجموعُ الأيّام **المرصودة** وحدها — ``None`` إن لم يُرصَد يوم.

    ليس بديلاً عن ``_complete_total``: يُعرَض بجانبه مع عدد الأيّام المرصودة، فيبقى للمستشار
    إشارةُ المطر/ET0 حين يتأخّر أرشيف ERA5 أيّاماً في آخر النافذة، دون أن يُقرأ ناقصاً كاملاً.
    """
    present = [v for v in values if v is not None]
    return round(sum(present), 2) if present else None


def _expected_dates(start: date | None, end: date | None) -> list[str]:
    if start is None or end is None or end < start:
        return []
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def summarize_weather_history(
    records: list[Any],
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
    source_missing_days: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """ملخّصُ الطقس التاريخيّ وأشهرُه — دالّةٌ نقيّة، والغيابُ يبقى ``None`` في كلّ مستوى.

    **اليومُ المحذوف من الاستجابة غيابٌ كاليوم الفارغ:** كان العدُّ يرى ``None`` داخل الأيّام
    المُعادة وحدها، فأرشيفٌ أعاد ٧٠٠ يومٍ كاملة من ٧٣٠ مطلوبة يُجمَع «مكتملاً» ويُقرأ أصغرَ من
    الواقع. تُحسَب الأيّامُ المطلوبة الغائبة من النافذة المطلوبة (``requested_start..end``، شاملةً)
    ومن ``coverage.missing_days`` المعلَن من المالك (``source_missing_days``) أيّهما أكبر، فتُضاف
    إلى ``*_days_missing`` ويصير المجموعُ الكامل ``None``.
    """
    temp_vals = [
        (d.temp_max_c + d.temp_min_c) / 2
        for d in records
        if d.temp_max_c is not None and d.temp_min_c is not None
    ]
    expected = _expected_dates(requested_start, requested_end)
    present = {str(d.date)[:10] for d in records if d.date}
    omitted_dates = [day for day in expected if day not in present]
    omitted = max(len(omitted_dates), int(source_missing_days or 0))
    precip: list[float | None] = [d.precipitation_mm for d in records] + [None] * omitted
    et0: list[float | None] = [d.et0_mm for d in records] + [None] * omitted
    summary = {
        "days": len(records),
        "days_omitted_by_source": omitted,
        "avg_temp_c": round(mean(temp_vals), 2) if temp_vals else None,
        "total_precipitation_mm": _complete_total(precip),
        "precipitation_days_missing": _missing_count(precip),
        "observed_precipitation_mm": _observed_total(precip),
        "precipitation_days_observed": len(precip) - _missing_count(precip),
        "total_et0_mm": _complete_total(et0),
        "et0_days_missing": _missing_count(et0),
        "observed_et0_mm": _observed_total(et0),
        "et0_days_observed": len(et0) - _missing_count(et0),
        "first_date": records[0].date if records else None,
        "last_date": records[-1].date if records else None,
    }
    # Keep context compact for the chat runtime: monthly buckets by YYYY-MM.
    monthly: dict[str, dict[str, list[float | None]]] = {}
    for d in records:
        bucket = monthly.setdefault(str(d.date)[:7], {"precipitation_mm": [], "et0_mm": []})
        bucket["precipitation_mm"].append(d.precipitation_mm)
        bucket["et0_mm"].append(d.et0_mm)
    omitted_by_month: dict[str, int] = {}
    for day in omitted_dates:
        # يومٌ مطلوبٌ غائب يُحسَب على شهره: لا مجموعَ شهريّاً «كاملاً» بأيّامٍ محذوفة.
        bucket = monthly.setdefault(day[:7], {"precipitation_mm": [], "et0_mm": []})
        bucket["precipitation_mm"].append(None)
        bucket["et0_mm"].append(None)
        omitted_by_month[day[:7]] = omitted_by_month.get(day[:7], 0) + 1
    monthly_items = [
        {
            "month": month,
            "days": len(v["precipitation_mm"]) - omitted_by_month.get(month, 0),
            "days_omitted_by_source": omitted_by_month.get(month, 0),
            "precipitation_mm": _complete_total(v["precipitation_mm"]),
            "precipitation_days_missing": _missing_count(v["precipitation_mm"]),
            "et0_mm": _complete_total(v["et0_mm"]),
            "et0_days_missing": _missing_count(v["et0_mm"]),
        }
        for month, v in sorted(monthly.items())
    ]
    return summary, monthly_items


# ─── أوصافُ رموز WMO (محايدةٌ للمزوّد) ────────────────────────────────────────────
#
# انتقلت من ``api.connectors.openmeteo`` (W1-22): وصفُ رمزٍ ليس نداءَ مزوّد، وأتمتةُ الطقس تقرأ من
# weather-service فلا تستورد الموصّلَ لأجل جدول. والموصّلُ يُعيد تصديرَ الاسمين لمستدعيه.

WMO_DESCRIPTIONS_AR = {
    0: "صافٍ",
    1: "غائم جزئياً",
    2: "غائم جزئياً",
    3: "غائم",
    45: "ضباب",
    48: "ضباب جامد",
    51: "رذاذ خفيف",
    53: "رذاذ متوسّط",
    55: "رذاذ كثيف",
    61: "مطر خفيف",
    63: "مطر متوسّط",
    65: "مطر غزير",
    71: "ثلج خفيف",
    73: "ثلج متوسّط",
    75: "ثلج كثيف",
    80: "زخّات مطر خفيفة",
    81: "زخّات مطر متوسّطة",
    82: "زخّات مطر عنيفة",
    95: "عاصفة رعديّة",
    96: "عاصفة مع برَد خفيف",
    99: "عاصفة مع برَد عنيف",
}


def describe_weather_ar(code: int | None) -> str:
    """يحوّل WMO code → وصف عربي؛ والغيابُ (`None`) «غير معروف» لا «صافٍ»."""
    return WMO_DESCRIPTIONS_AR.get(code, "غير معروف")
