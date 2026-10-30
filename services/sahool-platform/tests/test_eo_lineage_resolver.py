"""Real resolver code with a declared HTTP seam double; no provider is contacted."""

import asyncio
import json

import pytest
from api import canonical_spectral_state as resolver
from api import raster_service_client as transport

pytestmark = pytest.mark.unit


def payloads():
    return {
        key: {
            "real_data": True,
            "source": "cdse",
            "date": "2026-10-27",
            "scene_id": "scene-a",
            "quality_status": "validated",
            "valid_pixel_ratio": 0.95,
            "coverage_ratio": 0.99,
            "stats": {"mean": value},
        }
        for key, value in {"ndvi": 0.5, "ndre": 0.3, "ndmi": -0.1, "msi": 1.3}.items()
    }


def install(monkeypatch, data, calls=None):
    async def fake(field_id, **kwargs):
        if calls is not None:
            calls.append((field_id, kwargs))
        result = data[kwargs["index"]]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(transport, "get_indicator_grid", fake)


def resolve():
    return asyncio.run(
        resolver.resolve_canonical_spectral_state(tenant_id="tenant-a", field_id="field-a")
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 10**400, True, "0.5", None])
def test_invalid_master_has_no_authority(monkeypatch, bad):
    data = payloads()
    data["ndvi"]["stats"]["mean"] = bad
    install(monkeypatch, data)
    assert resolve() is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("real_data", "true"),
        ("real_data", 1),
        ("source", "simulation"),
        ("quality_status", "invalid"),
        ("field_id", "different-field"),
        ("tenant_id", "different-tenant"),
    ],
)
def test_contradictory_or_fake_authority_is_rejected(monkeypatch, key, value):
    data = payloads()
    data["ndvi"][key] = value
    install(monkeypatch, data)
    assert resolve() is None


def test_each_index_keeps_its_own_date_and_scene(monkeypatch):
    data = payloads()
    data["msi"].update(scene_id="scene-b", date="2026-09-01", product_id="product-b")
    install(monkeypatch, data)
    out = resolve()
    assert {"scene-a", "scene-b", "product-b"} <= set(out["evidence_ids"])
    assert out["index_provenance"]["msi"]["acquisition_date"] == "2026-09-01"
    assert out["acquisition_date"] == "2026-10-27"  # legacy master alias, not all dates
    assert out["water_stress"]["confirmed"] is None
    assert out["water_stress"]["temporal_compatible"] is None


def test_missing_identity_is_not_filled_from_master(monkeypatch):
    data = payloads()
    del data["msi"]["scene_id"]
    install(monkeypatch, data)
    assert resolve()["index_provenance"]["msi"]["scene_id"] is None


def test_quality_is_not_inferred_from_service_authority(monkeypatch):
    data = payloads()
    for value in data.values():
        value.pop("quality_status")
    install(monkeypatch, data)
    out = resolve()
    assert out["source_authority"] == "raster-service"
    assert out["quality_status"] == "unknown"
    assert out["status"] == "degraded"
    assert not out["water_stress"]["confirmation_available"]


def test_every_request_keeps_tenant_scope(monkeypatch):
    calls = []
    install(monkeypatch, payloads(), calls)
    resolve()
    assert len(calls) == 4
    assert all(field == "field-a" and args["tenant_id"] == "tenant-a" for field, args in calls)


def test_no_provider_fallback_or_invented_master(monkeypatch):
    data = payloads()
    data["ndvi"] = RuntimeError("provider unavailable")
    install(monkeypatch, data)
    assert resolve() is None


def test_metadata_uses_bounded_safe_fields(monkeypatch):
    data = payloads()
    data["msi"].update(
        valid_pixel_ratio=float("nan"),
        coverage_ratio=2,
        source_uri="https://example.invalid/?token=not-forwarded",
    )
    install(monkeypatch, data)
    out = resolve()
    record = out["index_provenance"]["msi"]
    assert record["valid_pixel_ratio"] is None and record["coverage_ratio"] is None
    assert "source_uri" not in record
    json.dumps(out, allow_nan=False)


def test_empty_field_does_not_call_transport(monkeypatch):
    calls = []
    install(monkeypatch, payloads(), calls)
    assert (
        asyncio.run(resolver.resolve_canonical_spectral_state(tenant_id="tenant-a", field_id=""))
        is None
    )
    assert calls == []
