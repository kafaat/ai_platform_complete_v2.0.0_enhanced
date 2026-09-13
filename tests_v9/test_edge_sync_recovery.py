"""Transport-to-schema witnesses with real HTTPX and durable temporary files."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sync(tmp_path, monkeypatch):
    for key in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        monkeypatch.delenv(key, raising=False)
    mod = load("edge_transport_recovery", "services/edge-inference/sync_service.py")
    monkeypatch.setenv("EDGE_DEVICE_ID", "edge-device-1")
    return mod.CloudSyncService("https://edge.example.test", "synthetic", str(tmp_path))


def observation():
    return {"field_id": "field-1", "timestamp": "2026-09-01T10:30:00+00:00", "value": 0.75}


@pytest.mark.asyncio
async def test_timeout_restart_replay_keeps_entire_envelope(sync, respx_mock):
    route = respx_mock.post("https://edge.example.test/v1/edge/sync")
    route.mock(side_effect=httpx.ReadTimeout("synthetic timeout"))
    assert await sync.sync_result("pest_detection", observation()) is False
    original = json.loads(route.calls[0].request.content)
    saved = json.loads(next(Path(sync.sync_dir).glob("*.json")).read_text(encoding="utf-8"))
    assert saved == original
    model = load(
        "edge_ingress_model", "services/sahool-platform/api/edge_models.py"
    ).EdgeSyncRequest
    parsed = model.model_validate(saved)
    assert parsed.field_id == "field-1"
    assert parsed.device_id == "edge-device-1"
    assert parsed.occurred_at.isoformat() == observation()["timestamp"]
    route.mock(
        return_value=httpx.Response(
            200, json={"status": "duplicate_ignored", "idempotency_key": saved["idempotency_key"]}
        )
    )
    restarted = type(sync)(sync.cloud_url, sync.token, sync.sync_dir)
    assert await restarted.process_queue() == 1
    assert json.loads(route.calls[-1].request.content) == original
    assert restarted.queue_size() == 0


@pytest.mark.asyncio
async def test_http_200_without_matching_receipt_is_not_sync_success(sync, respx_mock):
    respx_mock.post("https://edge.example.test/v1/edge/sync").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    assert await sync.sync_result("pest_detection", observation()) is False
    assert sync.queue_size() == 1


def test_offline_envelope_has_identity_and_distinct_measurements(sync):
    sync.queue_result("pest_detection", observation())
    sync.queue_result("pest_detection", observation())
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in Path(sync.sync_dir).glob("*.json")]
    assert len({r["idempotency_key"] for r in rows}) == 2
    assert all(r["field_id"] == "field-1" and r["device_id"] == "edge-device-1" for r in rows)
    assert all(r["occurred_at"] == observation()["timestamp"] for r in rows)


@pytest.mark.parametrize(
    "changed", [{"field_id": None}, {"field_id": ""}, {"timestamp": "2026-09-01T10:00:00"}]
)
def test_invalid_identity_or_time_cannot_enter_queue(sync, changed):
    with pytest.raises(ValueError):
        sync.queue_result("pest_detection", {**observation(), **changed})
    assert sync.queue_size() == 0


@pytest.mark.asyncio
async def test_write_failure_never_sends(sync, monkeypatch, respx_mock):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(sync, "_persist", broken)
    with pytest.raises(OSError):
        await sync.sync_result("pest_detection", observation())
    assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_legacy_queue_file_without_stored_device_identity_is_retained_not_relabelled(
    sync, monkeypatch, respx_mock
):
    """A pre-envelope queue file carries no device identity; the current process env
    must not supply one at replay (a replaced device would inherit old readings)."""
    route = respx_mock.post("https://edge.example.test/v1/edge/sync").mock(
        return_value=httpx.Response(200, json={"status": "stored", "idempotency_key": "x" * 32})
    )
    legacy = {
        "type": "pest_detection",
        "data": {"field_id": "field-1", "timestamp": "2026-09-01T10:30:00+00:00"},
        "idempotency_key": "x" * 32,
    }
    (Path(sync.sync_dir) / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("EDGE_DEVICE_ID", "replacement-device")
    assert await sync.process_queue() == 0
    assert route.call_count == 0
    assert sync.queue_size() == 1
    retained = json.loads((Path(sync.sync_dir) / "legacy.json").read_text(encoding="utf-8"))
    assert "replacement-device" not in json.dumps(retained)


@pytest.mark.asyncio
async def test_legacy_queue_file_with_stored_device_identity_replays_that_identity(
    sync, monkeypatch, respx_mock
):
    route = respx_mock.post("https://edge.example.test/v1/edge/sync").mock(
        return_value=httpx.Response(200, json={"status": "stored", "idempotency_key": "y" * 32})
    )
    legacy = {
        "type": "pest_detection",
        "data": {
            "field_id": "field-1",
            "device_id": "original-device",
            "timestamp": "2026-09-01T10:30:00+00:00",
        },
        "idempotency_key": "y" * 32,
    }
    (Path(sync.sync_dir) / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("EDGE_DEVICE_ID", "replacement-device")
    assert await sync.process_queue() == 1
    sent = json.loads(route.calls[0].request.content)
    assert sent["device_id"] == "original-device"
    assert sync.queue_size() == 0


def test_ingress_rejects_missing_top_level_identity():
    model = load(
        "edge_ingress_validation", "services/sahool-platform/api/edge_models.py"
    ).EdgeSyncRequest
    with pytest.raises(ValueError):
        model.model_validate({"type": "pest_detection", "data": observation()})
