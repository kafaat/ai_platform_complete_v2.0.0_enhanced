"""Server-bound agronomic facts for the supervisor's trusted path (W2-17).

When a request names a ``field_id`` the answer is about that field, so the crop, cultivar,
seeding and weather that drive the crop model and the market lookup come from their owners,
never from the request body:

* crop, cultivar, sowing date and seed rate: the field's active season, read through the
  platform's existing service route ``GET /internal/fields/{id}/state?ai_context=true``
  (``ai_context_pack.active_season``; the season row is owned by the platform);
* weather: ``weather-service`` ``GET /v1/weather/historical`` over the season window
  (sowing date to today, capped at the season end), at the field's stored location.

Body-supplied values for those keys are dropped and named in ``ignored_request_keys``. A fact
the owner cannot supply stays absent (with a reason), so the skill answers "unavailable"
instead of falling back to what the caller sent. Findings: airuntime-4, crop-9, weather-8.

This module is pure apart from the two HTTP reads, which take an injected ``httpx`` client.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

#: Keys a request body may not assert on the trusted path: each is a server fact (season,
#: weather, soil, economics) or a model input derived from one.
SERVER_BOUND_KEYS = frozenset(
    {
        "crop",
        "crops",
        "cultivar",
        "variety",
        "planting_date",
        "sowing_date",
        "seed_rate_kg_ha",
        "season_id",
        "season_end",
        "weather",
        "weather_snapshot",
        "weather_age_hours",
        "climate_profile",
        "agromanagement",
        "agronomic_context",
        "soil",
        "crop_parameters",
        "crop_card",
        "costs",
    }
)

#: Longest season window fetched from weather-service (one annual cycle, the platform season
#: simulation's hard cap). A sowing date further back is reported, not silently truncated.
WEATHER_WINDOW_MAX_DAYS = 366
#: The historical archive lags about five days (the platform season simulation's
#: ``_ERA5_LAG_DAYS``); a window reaching today would always come back short.
ARCHIVE_LAG_DAYS = 5

SEASON_SOURCE = "sahool-platform GET /internal/fields/{field_id}/state?ai_context=true"
WEATHER_SOURCE = "weather-service GET /v1/weather/historical"

_REJECTED_QUALITY = {"insufficient", "invalid"}

#: Which server facts each skill domain reads. A domain that reads none (remote sensing) does
#: not pay for the season and weather reads; its body values for the bound keys are still
#: dropped. An unknown domain gets every fact (the safe default).
DOMAIN_FACT_NEEDS: dict[str, frozenset[str]] = {
    "crop_model": frozenset({"season", "weather"}),
    "optimization": frozenset({"season", "weather"}),
    "market": frozenset({"season"}),
    "advisory": frozenset({"season"}),
    "remote_sensing": frozenset(),
}
ALL_FACTS = frozenset({"season", "weather"})

#: What agriai's PCSE input builder (``pcse_inputs.build_weather``) needs beyond the daily
#: temperatures, rain and radiation. weather-service's historical archive view carries none of
#: the vapour-pressure family and no daily mean wind, so a server-bound series is reported as
#: not PCSE-ready instead of being padded (vapour pressure is never derived here).
_PCSE_DAY_KEYS = ("solar_radiation_mj_m2",)
_PCSE_VAPOUR_KEYS = ("vapour_pressure_hpa", "vapour_pressure_kpa")
_PCSE_WIND_KEYS = ("wind_2m_m_s", "wind_10m_m_s")


def facts_needed(domain: str | None) -> frozenset[str]:
    return DOMAIN_FACT_NEEDS.get(domain or "", ALL_FACTS)


def weather_service_url() -> str:
    return os.getenv("WEATHER_SERVICE_URL", "http://sahool-weather-service:8000").rstrip("/")


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _season_crops(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    return [c.strip().lower() for c in raw if isinstance(c, str) and c.strip()]


def season_facts(pack: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Crop, cultivar, sowing date and seed rate from the pack's active season.

    Returns ``(facts, provenance)``. A season with no crop or with several crops binds no crop:
    one crop's simulation or price is not the season's (mixed cropping needs areas per crop).
    """
    season = pack.get("active_season") if isinstance(pack, dict) else None
    if not isinstance(season, dict) or not season:
        return {}, {"status": "unavailable", "reason": "no_active_season", "source": SEASON_SOURCE}
    facts: dict[str, Any] = {}
    crops = _season_crops(season.get("crops"))
    reason = None
    if len(crops) == 1:
        facts["crop"] = crops[0]
    else:
        reason = "season_crop_missing" if not crops else "multi_crop_season"
    cultivar = _text(season.get("cultivar"))
    if cultivar:
        facts["cultivar"] = cultivar
    sowing = _iso_date(season.get("sowing_date"))
    if sowing:
        facts["planting_date"] = sowing.isoformat()
    season_end = _iso_date(season.get("season_end"))
    if season_end:
        facts["season_end"] = season_end.isoformat()
    seed_rate = _finite(season.get("seed_rate_kg_ha"))
    if seed_rate is not None and seed_rate >= 0:
        facts["seed_rate_kg_ha"] = seed_rate
    season_id = _text(season.get("season_id"))
    if season_id:
        facts["season_id"] = season_id
    provenance: dict[str, Any] = {
        "status": "bound" if "crop" in facts else "partial",
        "source": SEASON_SOURCE,
        "season_id": season_id,
        "bound": sorted(facts),
    }
    if reason:
        provenance["reason"] = reason
    return facts, provenance


def field_elevation_m(pack: Any) -> float | None:
    """The field's stored elevation (``fields.elevation_m``, v37), or None. Never defaulted."""
    profile = pack.get("field_profile") if isinstance(pack, dict) else None
    elev = _finite(profile.get("elevation_m")) if isinstance(profile, dict) else None
    return elev if elev is not None and -500 <= elev <= 9000 else None


def pcse_inputs_missing(weather: dict[str, Any]) -> list[str]:
    """Inputs agriai's PCSE builder would refuse for this series (empty when PCSE-ready)."""
    missing: list[str] = []
    if weather.get("elevation_m") is None:
        missing.append("elevation_m")
    daily = [d for d in weather.get("daily") or [] if isinstance(d, dict)]
    for key in _PCSE_DAY_KEYS:
        if any(d.get(key) is None for d in daily):
            missing.append(key)
    if any(all(d.get(k) is None for k in _PCSE_VAPOUR_KEYS) for d in daily):
        missing.append("|".join(_PCSE_VAPOUR_KEYS))
    if any(all(d.get(k) is None for k in _PCSE_WIND_KEYS) for d in daily):
        missing.append("|".join(_PCSE_WIND_KEYS))
    return missing


def field_location(pack: Any) -> tuple[float, float] | None:
    """The field's stored location: ``fields.lat/lon`` from the pack's field profile."""
    if not isinstance(pack, dict):
        return None
    for block, lat_key, lon_key in (
        (pack.get("field_profile"), "lat", "lon"),
        ((pack.get("weather_history") or {}).get("location"), "lat", "lon"),
    ):
        if not isinstance(block, dict):
            continue
        lat, lon = _finite(block.get(lat_key)), _finite(block.get(lon_key))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


def weather_window(
    planting_date: str | None, season_end: str | None, today: date
) -> tuple[date, date] | str:
    """The season's weather window ``(start, end)``, or the reason there is none.

    The end is the season end or the newest archived day (today minus the archive lag),
    whichever is earlier.
    """
    start = _iso_date(planting_date)
    if start is None:
        return "planting_date_required"
    if start > today:
        return "season_not_started"
    end = today - timedelta(days=ARCHIVE_LAG_DAYS)
    declared_end = _iso_date(season_end)
    if declared_end is not None and declared_end < start:
        return "season_window_invalid"
    if declared_end is not None and declared_end < end:
        end = declared_end
    if end < start:
        return "season_weather_not_yet_archived"
    if (end - start).days + 1 > WEATHER_WINDOW_MAX_DAYS:
        return "season_window_too_long"
    return start, end


def weather_from_view(
    view: Any,
    *,
    lat: float,
    lon: float,
    start: date,
    end: date,
    elevation_m: float | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Turn weather-service's ``historical_view`` into the crop model's ``weather`` input.

    Fail closed: a view without canonical identity, with a rejected quality, with missing
    days, or with a day lacking its temperatures or its precipitation is absence, never a
    series with zeros in it (agriai's fallback reads an absent season rain total as 0 mm).
    The provenance says whether the series is complete enough for agriai's PCSE builder and,
    if not, which inputs are missing (``pcse_inputs_missing``).
    """
    provenance: dict[str, Any] = {
        "source": WEATHER_SOURCE,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "location": {"lat": lat, "lon": lon},
    }
    if not isinstance(view, dict) or not isinstance(view.get("days"), list):
        return None, {**provenance, "status": "unavailable", "reason": "weather_view_invalid"}
    provenance.update(
        {
            "canonical_state_id": view.get("canonical_state_id"),
            "source_snapshot_id": view.get("source_snapshot_id"),
            "quality_status": view.get("quality_status"),
            "coverage": view.get("coverage"),
        }
    )
    if view.get("derived_from") != "canonical_weather_state" or not view.get("canonical_state_id"):
        return None, {**provenance, "status": "unavailable", "reason": "weather_not_canonical"}
    if view.get("quality_status") in _REJECTED_QUALITY:
        return None, {**provenance, "status": "unavailable", "reason": "weather_quality_rejected"}
    coverage = view.get("coverage") if isinstance(view.get("coverage"), dict) else {}
    expected = (end - start).days + 1
    days = [d for d in view["days"] if isinstance(d, dict)]
    if (_finite(coverage.get("missing_days")) or 0) > 0 or len(days) < expected:
        return None, {
            **provenance,
            "status": "unavailable",
            "reason": "weather_coverage_incomplete",
        }
    daily: list[dict[str, Any]] = []
    rain_total = 0.0
    for day in days:
        tmax, tmin = _finite(day.get("temp_max_c")), _finite(day.get("temp_min_c"))
        if tmax is None or tmin is None:
            return None, {
                **provenance,
                "status": "unavailable",
                "reason": "weather_day_temperature_missing",
            }
        item: dict[str, Any] = {"date": day.get("date"), "tmax": tmax, "tmin": tmin}
        rain = _finite(day.get("precipitation_mm"))
        if rain is None or rain < 0:
            # A day without rain is not a dry day: the season total would be understated and
            # the water-limited yield computed as if that rain never fell.
            return None, {
                **provenance,
                "status": "unavailable",
                "reason": "weather_day_precipitation_missing",
                "date": day.get("date"),
            }
        item["rain_mm"] = rain
        rain_total += rain
        for src, dst in (
            ("et0_mm", "et0_mm"),
            ("solar_radiation_mj_m2", "solar_radiation_mj_m2"),
            # Daily mean wind at its declared 10 m height (``wind_max_ms`` is a maximum, not a
            # mean, and is never passed as one).
            ("wind_mean_10m_ms", "wind_10m_m_s"),
        ):
            value = _finite(day.get(src))
            if value is not None:
                item[dst] = value
        daily.append(item)
    weather: dict[str, Any] = {
        "daily": daily,
        "latitude": lat,
        "longitude": lon,
        "source": "weather-service",
        "canonical_state_id": view.get("canonical_state_id"),
        "total_rain_mm": round(rain_total, 3),
    }
    if elevation_m is not None:
        weather["elevation_m"] = elevation_m
    pcse_missing = pcse_inputs_missing(weather)
    return weather, {
        **provenance,
        "status": "bound",
        "days": len(daily),
        "elevation_source": "fields.elevation_m" if elevation_m is not None else None,
        "pcse_ready": not pcse_missing,
        "pcse_inputs_missing": pcse_missing,
    }


async def fetch_ai_context_pack(
    client, *, platform_url: str, field_id: str, tenant_id: str, signed_headers
) -> dict[str, Any] | None:
    """The platform's AI context pack for the field, through the existing service route.

    ``signed_headers(tenant_id, path)`` returns the W0-05 tenant assertion headers or None.
    Any failure is absence (None); the caller then binds no server facts and says why.
    """
    path = f"/internal/fields/{quote(str(field_id), safe='')}/state"
    signed = signed_headers(tenant_id, path)
    if signed is None:
        return None
    try:
        resp = await client.get(
            f"{platform_url}{path}",
            params={"tenant_id": str(tenant_id), "ai_context": "true"},
            headers={"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", ""), **signed},
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
    except Exception:  # noqa: BLE001 — absence, reported by the caller
        return None
    pack = body.get("ai_context_pack") if isinstance(body, dict) else None
    return pack if isinstance(pack, dict) else None


async def fetch_season_weather(
    client, *, lat: float, lon: float, start: date, end: date, tenant_id: str
) -> Any:
    """weather-service's canonical historical view (the platform client's headers pattern)."""
    resp = await client.get(
        f"{weather_service_url()}/v1/weather/historical",
        params={
            "lat": lat,
            "lon": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers={
            "X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", ""),
            "X-Tenant-Id": str(tenant_id),
        },
    )
    resp.raise_for_status()
    return resp.json()


async def resolve_server_facts(
    client,
    *,
    field_id: str,
    tenant_id: str,
    platform_url: str,
    signed_headers,
    today: date | None = None,
    needs: frozenset[str] = ALL_FACTS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Season and weather facts for the field, and where each came from (or why it did not).

    ``needs`` (see ``facts_needed``) limits the reads to the facts the skill uses; a fact not
    needed is not read and is recorded as ``not_requested``.
    """
    today = today or date.today()
    not_requested = {"status": "not_requested", "reason": "domain_does_not_use_fact"}
    if "season" not in needs and "weather" not in needs:
        return {}, {
            "season": {**not_requested, "source": SEASON_SOURCE},
            "weather": {**not_requested, "source": WEATHER_SOURCE},
        }
    pack = await fetch_ai_context_pack(
        client,
        platform_url=platform_url,
        field_id=field_id,
        tenant_id=tenant_id,
        signed_headers=signed_headers,
    )
    if pack is None:
        unavailable = {"status": "unavailable", "reason": "platform_season_context_unavailable"}
        return {}, {
            "season": {**unavailable, "source": SEASON_SOURCE},
            "weather": {**unavailable, "source": WEATHER_SOURCE},
        }
    facts, season_prov = season_facts(pack)
    window = weather_window(facts.get("planting_date"), facts.get("season_end"), today)
    location = field_location(pack)
    if "weather" not in needs:
        weather_prov = {**not_requested, "source": WEATHER_SOURCE}
    elif isinstance(window, str):
        weather_prov = {"status": "unavailable", "reason": window, "source": WEATHER_SOURCE}
    elif location is None:
        weather_prov = {
            "status": "unavailable",
            "reason": "field_location_missing",
            "source": WEATHER_SOURCE,
        }
    else:
        start, end = window
        lat, lon = location
        try:
            view = await fetch_season_weather(
                client, lat=lat, lon=lon, start=start, end=end, tenant_id=tenant_id
            )
        except Exception as exc:  # noqa: BLE001 — absence, named
            weather_prov = {
                "status": "unavailable",
                "reason": "weather_service_unavailable",
                "error_type": type(exc).__name__,
                "source": WEATHER_SOURCE,
            }
        else:
            weather, weather_prov = weather_from_view(
                view,
                lat=lat,
                lon=lon,
                start=start,
                end=end,
                elevation_m=field_elevation_m(pack),
            )
            if weather is not None:
                facts["weather"] = weather
    return facts, {"season": season_prov, "weather": weather_prov}


def bind_server_facts(
    context: dict[str, Any] | None,
    facts: dict[str, Any],
    provenance: dict[str, Any],
    field_state: dict[str, Any] | None = None,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace every body-asserted server fact with what the owners supplied.

    ``context`` is the output of ``bind_field_context`` (credentials and field_state already
    handled). Keys in ``SERVER_BOUND_KEYS`` are dropped whatever the owners returned; a fact the
    owners did not supply stays absent. The record of what was bound, ignored and why is put
    under ``_facts_provenance`` (an underscore key, which no request body can set).
    """
    source = dict(context or {})
    # Name the keys the *request* asserted (bind_field_context may already have copied
    # weather_age_hours from the field state, which is not a body value).
    asserted = request_context if isinstance(request_context, dict) else source
    ignored = sorted(k for k in asserted if k in SERVER_BOUND_KEYS)
    out = {k: v for k, v in source.items() if k not in SERVER_BOUND_KEYS}
    out.update(facts)
    inputs = (field_state or {}).get("inputs") if isinstance(field_state, dict) else None
    if isinstance(inputs, dict) and inputs.get("weather_age_hours") is not None:
        out["weather_age_hours"] = inputs["weather_age_hours"]
    out["_facts_provenance"] = {
        "trusted_path": True,
        "crop_source": "active_season" if "crop" in facts else None,
        "weather_source": "weather-service" if "weather" in facts else None,
        **provenance,
        "ignored_request_keys": ignored,
    }
    return out


def request_facts_provenance(context: dict[str, Any] | None) -> dict[str, Any]:
    """Provenance for a request with no field: every agronomic value is the caller's."""
    present = sorted(k for k in (context or {}) if k in SERVER_BOUND_KEYS)
    return {
        "trusted_path": False,
        "crop_source": "request_body" if "crop" in (context or {}) else None,
        "weather_source": "request_body" if "weather" in (context or {}) else None,
        "request_supplied_keys": present,
    }
