import httpx
import pytest
from ground_verification_bridge import GroundVerificationBridge


@pytest.mark.asyncio
async def test_bridge_creates_reference_only_task(monkeypatch):
    async def handler(request):
        assert request.url.path == "/v1/tasks/scouting"
        payload = __import__("json").loads(request.content)
        assert "anomaly_ref" in payload
        assert "suspected_condition" not in payload
        return httpx.Response(201, json={"task_id": "tsk_123"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Client(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    bridge = GroundVerificationBridge("http://task-service")
    result = await bridge.create_scouting_task(
        anomaly={
            "anomaly_ref": "urn:sahool:anomaly:anomaly_1",
            "field_id": "fld_demo",
            "season_id": "sea_demo",
            "severity": "high",
            "reason_codes": [],
        },
        authorization="Bearer test",
        idempotency_key="a" * 64,
    )
    assert result.task_ref == "urn:sahool:task:tsk_123"
