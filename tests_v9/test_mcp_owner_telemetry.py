"""Live-owner sensor reads, current binding, freshness, no caller fabrication."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit
PATH = Path(__file__).resolve().parents[1] / "services/mcp_servers/shared/owner_telemetry.py"
SPEC = importlib.util.spec_from_file_location("_owner_telemetry_contract", PATH)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)
ARGS = {"field_id": "field-a", "device_id": "device-a", "sensor_type": "soil_moisture"}


class Owner:
    def __init__(
        self,
        *,
        stale=False,
        future=False,
        rows=None,
        different_field=False,
        different_tenant=False,
        move_after_read=False,
        reject=False,
    ):
        self.paths = []
        self.devices_reads = 0
        self.stale, self.future = stale, future
        self.rows, self.different_field, self.different_tenant = (
            rows,
            different_field,
            different_tenant,
        )
        self.move_after_read, self.reject = move_after_read, reject

    def __call__(self, request):
        assert request.headers["authorization"] == "Bearer caller-token"
        assert "x-tenant-id" not in request.headers
        self.paths.append(request.url.path)
        if self.reject:
            return httpx.Response(401)
        if request.url.path == "/api/v1/me":
            data = {"tenant_id": "tenant-b" if self.different_tenant else "tenant-a"}
        elif request.url.path == "/api/v1/fields/field-a":
            data = {"field_id": "field-a"}
        elif request.url.path == "/api/v1/devices":
            self.devices_reads += 1
            mismatch = self.different_field or (self.move_after_read and self.devices_reads > 1)
            data = [{"device_id": "device-a", "field_id": "field-b" if mismatch else "field-a"}]
        elif request.url.path == "/api/v1/devices/device-a/telemetry":
            assert request.url.params["limit"] == "100"
            offset = -30 if self.future else 2000 if self.stale else 10
            data = (
                self.rows
                if self.rows is not None
                else [
                    {
                        "sensor_type": "soil_moisture",
                        "value": 31.25,
                        "unit": "%",
                        "recorded_at": (datetime.now(UTC) - timedelta(seconds=offset)).isoformat(),
                        "stale": self.stale,
                        "stale_after_sec": 900,
                    }
                ]
            )
        else:
            raise AssertionError(request.url)
        return httpx.Response(200, json=data)


async def read(owner, args=None, authorization="Bearer caller-token"):
    async with httpx.AsyncClient(transport=httpx.MockTransport(owner), trust_env=False) as client:
        return await OWNER.sensor_signal(
            args or ARGS,
            "tenant-a",
            authorization,
            client=client,
            base_url="http://sahool-platform",
        )


@pytest.mark.asyncio
async def test_read_is_from_owner_and_has_measured_time_unit_provenance():
    owner = Owner()
    signal = await read(owner)
    assert signal["value"] == 31.25 and signal["unit"] == "%"
    assert signal["status"] == "available" and signal["observed_at"]
    assert signal["source_verified"] is True and signal["verified"] is False
    assert signal["decision_authority"] == "none" and not signal["governing"]
    assert signal["field_binding"] == "current_device_binding_not_measurement_binding"
    assert owner.devices_reads == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "bEaReR"])
async def test_bearer_scheme_is_case_insensitive_and_forwarded_canonically(scheme):
    owner = Owner()  # Its transport asserts exactly "Bearer caller-token".
    signal = await read(owner, authorization=f"{scheme} caller-token")
    assert signal["status"] == "available"
    assert owner.devices_reads == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization", ["Bearer ", "bearer", "Basic caller-token", "Bearer  caller-token"]
)
async def test_missing_or_malformed_bearer_never_contacts_owner(authorization):
    owner = Owner()
    with pytest.raises(HTTPException) as error:
        await read(owner, authorization=authorization)
    assert error.value.status_code == 401
    assert owner.paths == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"stale": True}, {"future": True}])
async def test_stale_and_future_readings_never_report_available(kwargs):
    signal = await read(Owner(**kwargs))
    assert signal["status"] == "stale" and signal["stale"] is True


@pytest.mark.asyncio
async def test_missing_sensor_is_explicitly_unavailable_not_zero():
    signal = await read(Owner(rows=[]))
    assert signal["status"] == "unavailable" and signal["value"] is None
    assert signal["reason"] == "no_reading_in_recent_window"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({"different_tenant": True}, 403),
        ({"different_field": True}, 404),
        ({"move_after_read": True}, 403),
        ({"reject": True}, 401),
    ],
)
async def test_canonical_owner_authorization_and_reassignment_fail_closed(kwargs, status):
    with pytest.raises(HTTPException) as error:
        await read(Owner(**kwargs))
    assert error.value.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {**ARGS, "value": 99},
        {**ARGS, "soil_moisture": 99},
        {**ARGS, "device_id": "../victim"},
        {**ARGS, "tenant_id": "tenant-b"},
        {**ARGS, "sensor_type": True},
    ],
)
async def test_model_arguments_cannot_fabricate_readings_or_select_another_tenant(args):
    owner = Owner()
    with pytest.raises(HTTPException) as error:
        await read(owner, args)
    assert error.value.status_code == 422 and owner.paths == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        {"sensor_type": "soil_moisture", "value": True, "unit": "%"},
        {
            "sensor_type": "soil_moisture",
            "value": 33,
            "unit": "%",
            "recorded_at": "2026-11-21T12:00:00",
            "stale_after_sec": 900,
        },
        {"sensor_type": "soil_moisture", "value": 33, "unit": "%", "recorded_at": None},
    ],
)
async def test_malformed_owner_records_are_rejected(row):
    with pytest.raises(HTTPException) as error:
        await read(Owner(rows=[row]))
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example",
        "https://name:secret@example.com",
        "https://example.com/a",
        "https://example.com?token=x",
    ],
)
def test_owner_origin_cannot_redirect_credentials(url):
    with pytest.raises(HTTPException):
        OWNER.platform_origin(url)
