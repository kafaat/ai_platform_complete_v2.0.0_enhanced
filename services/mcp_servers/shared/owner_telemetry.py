"""Read-only telemetry from the canonical owner, never model-supplied values.

FIELD_VIEW and DEVICE_VIEW, current token revocation and tenant RLS are checked
by Platform using the same caller bearer. This module has no database authority.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import re
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException

SENSOR_SCHEMA = {
    "type": "object",
    "properties": {
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "device_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "sensor_type": {"type": "string", "minLength": 1, "maxLength": 64},
    },
    "required": ["field_id", "device_id", "sensor_type"],
    "additionalProperties": False,
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")


def platform_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        internal = host == "sahool-platform" or host.endswith(".railway.internal")
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or (parsed.scheme == "http" and not (loopback or internal))
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(ord(c) < 33 for c in value)
            or parsed.port == 0
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(503, "telemetry_owner_not_configured") from None
    return value.rstrip("/")


async def sensor_signal(
    arguments: dict,
    tenant_id: str,
    authorization: str,
    *,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> dict:
    if (
        set(arguments) != {"field_id", "device_id", "sensor_type"}
        or any(
            not isinstance(value, str) or not _IDENTIFIER.fullmatch(value)
            for value in arguments.values()
        )
        or len(arguments["sensor_type"]) > 64
    ):
        raise HTTPException(422, "sensor_identifiers_required_no_caller_values")
    scheme, separator, token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not token
        or len(authorization) > 16391
        or any(c.isspace() for c in token)
    ):
        raise HTTPException(401, "authentication_required")
    # HTTP authentication schemes are case-insensitive. Keep the same credential,
    # normalized for the owner request, after the outer MCP dependency validates it.
    authorization = "Bearer " + token
    origin = platform_origin(
        base_url if base_url is not None else os.getenv("PLATFORM_API_URL", "")
    )
    owned_client = client is None
    client = client or httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False)

    async def read(path: str):
        async with client.stream(
            "GET",
            origin + path,
            headers={"Authorization": authorization},
            follow_redirects=False,
            timeout=3,
        ) as response:
            if response.status_code in {401, 403, 404}:
                raise HTTPException(response.status_code, "telemetry_access_denied")
            if response.status_code != 200:
                raise HTTPException(503, "telemetry_owner_unavailable")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > 256 * 1024:
                    raise HTTPException(503, "telemetry_owner_response_invalid")
                data.extend(chunk)
            return json.loads(data)

    try:
        # Bound the entire read sequence, not just each socket operation.
        async with asyncio.timeout(12):
            identity = await read("/api/v1/me")
            if not isinstance(identity, dict) or identity.get("tenant_id") != tenant_id:
                raise HTTPException(403, "telemetry_identity_mismatch")
            field_id, device_id = arguments["field_id"], arguments["device_id"]
            field = await read("/api/v1/fields/" + quote(field_id, safe=""))
            if not isinstance(field, dict) or field.get("field_id") != field_id:
                raise HTTPException(403, "telemetry_field_mismatch")
            devices = await read("/api/v1/devices")
            if not isinstance(devices, list):
                raise HTTPException(503, "telemetry_owner_response_invalid")
            matches = [
                item
                for item in devices
                if isinstance(item, dict) and item.get("device_id") == device_id
            ]
            if len(matches) != 1 or matches[0].get("field_id") != field_id:
                raise HTTPException(404, "telemetry_device_not_in_field")
            rows = await read(
                "/api/v1/devices/" + quote(device_id, safe="") + "/telemetry?limit=100"
            )
            # Re-read owner binding after the telemetry read. A device reassigned
            # during the request must not be reported as a reading of the old field.
            current = await read("/api/v1/devices")
            matches = (
                [
                    item
                    for item in current
                    if isinstance(item, dict) and item.get("device_id") == device_id
                ]
                if isinstance(current, list)
                else []
            )
            if len(matches) != 1 or matches[0].get("field_id") != field_id:
                raise HTTPException(403, "telemetry_device_binding_changed")
        if not isinstance(rows, list) or len(rows) > 100:
            raise HTTPException(503, "telemetry_owner_response_invalid")
        base = {
            "type": "signal",
            "service": "iot",
            "name": "sensor_snapshot",
            "tenant_id": tenant_id,
            "field_id": field_id,
            "device_id": device_id,
            "sensor_type": arguments["sensor_type"],
            "decision_authority": "none",
            "governing": False,
            "source": "platform.device_telemetry",
            "query_limit": 100,
            "source_verified": True,
            "field_binding": "current_device_binding_not_measurement_binding",
            # Owner-authenticated provenance does not certify sensor calibration.
            "verified": False,
        }
        candidates = [
            row
            for row in rows
            if isinstance(row, dict) and row.get("sensor_type") == arguments["sensor_type"]
        ]
        if not candidates:
            return {
                **base,
                "status": "unavailable",
                "reason": "no_reading_in_recent_window",
                "value": None,
                "observed_at": None,
                "stale": True,
            }
        row = candidates[0]  # Owner contract orders newest first.
        value, recorded = row.get("value"), row.get("recorded_at")
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not isinstance(row.get("unit"), str)
        ):
            raise HTTPException(503, "telemetry_owner_response_invalid")
        age = None
        if recorded is not None:
            timestamp = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
            age = (datetime.now(UTC) - timestamp).total_seconds()
        stale_after = row.get("stale_after_sec")
        if (
            type(stale_after) not in (int, float)
            or not math.isfinite(stale_after)
            or stale_after <= 0
        ):
            raise HTTPException(503, "telemetry_owner_response_invalid")
        stale = row.get("stale") is not False or age is None or age < 0 or age > stale_after
        return {
            **base,
            "status": "stale" if stale else "available",
            "value": value,
            "unit": row["unit"],
            "observed_at": recorded,
            "age_sec": age,
            "stale": stale,
            "stale_after_sec": stale_after,
        }
    except (httpx.HTTPError, TimeoutError):
        raise HTTPException(503, "telemetry_owner_unavailable") from None
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise HTTPException(503, "telemetry_owner_response_invalid") from None
    finally:
        if owned_client:
            await client.aclose()
