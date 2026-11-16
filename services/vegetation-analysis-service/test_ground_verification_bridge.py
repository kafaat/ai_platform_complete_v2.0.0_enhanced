import hashlib
import json

import httpx
import pytest
from ground_verification_bridge import SCOUTING_TASKS_PATH, GroundVerificationBridge

from shared.security.service_tenant_assertion import verify_tenant_assertion

TENANT = "11111111-1111-4111-8111-111111111111"
ASSERTION_KEY = "assertion-signing-key-at-least-32-chars"
ANOMALY = {
    "anomaly_ref": "urn:sahool:anomaly:anomaly_1",
    "tenant_id": TENANT,
    "field_id": "fld_demo",
    "season_id": "sea_demo",
    "severity": "high",
    "reason_codes": [],
}


@pytest.fixture
def service_env(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "agent-token")
    monkeypatch.setenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", ASSERTION_KEY)
    monkeypatch.setenv("FIELD_SERVICE_TENANT_ASSERTION_KEY_ID", "current")


def _route_to(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Client(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Client)


@pytest.mark.asyncio
async def test_bridge_creates_reference_only_task(monkeypatch, service_env):
    seen = {}

    async def handler(request):
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        payload = json.loads(request.content)
        assert "anomaly_ref" in payload, payload
        assert "suspected_condition" not in payload, "the task carries no diagnosis"
        return httpx.Response(201, json={"task_id": "tsk_123", "persisted": True})

    _route_to(monkeypatch, handler)
    bridge = GroundVerificationBridge("http://task-service")
    result = await bridge.create_scouting_task(
        anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="a" * 64
    )
    assert result.task_ref == "urn:sahool:task:tsk_123", result
    # W1-20: the owner's route, not the /v1/tasks/scouting no service served.
    assert seen["path"] == SCOUTING_TASKS_PATH == "/internal/field-tasks/scouting", seen["path"]


@pytest.mark.asyncio
async def test_bridge_calls_the_owner_with_service_credentials_not_the_user_token(
    monkeypatch, service_env
):
    seen = {}

    async def handler(request):
        seen.update(request.headers)
        return httpx.Response(201, json={"task_ref": "urn:sahool:task:t1", "persisted": True})

    _route_to(monkeypatch, handler)
    await GroundVerificationBridge("http://fm").create_scouting_task(
        anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="b" * 64
    )
    assert "authorization" not in seen, "the user's bearer token is not forwarded to the owner"
    assert seen["x-agent-token"] == "agent-token", seen
    assert seen["x-service-name"] == "vegetation-analysis-service", seen
    assert seen["x-tenant-id"] == TENANT, seen
    assert seen["idempotency-key"] == "b" * 64, seen
    claims = verify_tenant_assertion(
        seen["x-tenant-assertion"],
        {"current": ASSERTION_KEY},
        "vegetation-analysis-service",
        TENANT,
        expected_method="POST",
        expected_path=SCOUTING_TASKS_PATH,
        expected_request_id=seen["x-request-id"],
    )
    assert claims.tenant_id == TENANT, claims


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unset", "error"),
    [
        ("TASK_SERVICE_URL", "task_service_not_configured"),
        ("SAHOOL_AGENT_TOKEN", "task_service_token_not_configured"),
        ("FIELD_SERVICE_TENANT_ASSERTION_KEY", "task_service_tenant_assertion_unavailable"),
    ],
)
async def test_bridge_fails_closed_before_any_request(monkeypatch, service_env, unset, error):
    monkeypatch.setenv("TASK_SERVICE_URL", "http://fm")
    monkeypatch.delenv(unset, raising=False)

    async def handler(request):
        raise AssertionError("no request may be sent without the full credential set")

    _route_to(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=error):
        await GroundVerificationBridge().create_scouting_task(
            anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="c" * 64
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (409, {"detail": {"code": "anomaly_already_has_task"}}, "task_service_rejected:409"),
        (202, {"task_id": "t"}, "task_service_persistence_unconfirmed"),
        (500, {"task_id": "t", "persisted": True}, "task_service_rejected:500"),
        (201, {"task_id": "t", "persisted": False}, "task_service_persistence_unconfirmed"),
        (201, {"persisted": True}, "task_service_missing_task_ref"),
    ],
)
async def test_only_a_stored_task_is_accepted(monkeypatch, service_env, status, body, error):
    async def handler(request):
        return httpx.Response(status, json=body)

    _route_to(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=error):
        await GroundVerificationBridge("http://fm").create_scouting_task(
            anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="d" * 64
        )


@pytest.mark.asyncio
async def test_an_anomaly_of_another_tenant_is_refused(monkeypatch, service_env):
    async def handler(request):
        raise AssertionError("a tenant mismatch must not reach the owner")

    _route_to(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="task_service_tenant_mismatch"):
        await GroundVerificationBridge("http://fm").create_scouting_task(
            anomaly={**ANOMALY, "tenant_id": "22222222-2222-4222-8222-222222222222"},
            tenant_id=TENANT,
            idempotency_key="e" * 64,
        )


@pytest.mark.asyncio
async def test_the_verification_route_passes_the_verified_tenant_and_stores_the_task_ref(
    monkeypatch,
):
    """routers/anomalies.py hands the bridge the JWT-verified tenant and records its task_ref."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import VerificationRequest

    record = {
        "tenant_id": TENANT,
        "payload": ANOMALY,
        "status": "detected",
        "aggregate_version": 1,
        "task_ref": None,
    }
    calls = {}

    class Store:  # the anomaly store's functions, not a database connection
        async def get(self, ref, *, tenant_id):
            return record

        async def transition(self, ref, status, **kwargs):
            calls["transition"] = (ref, status, kwargs)
            return {"status": status, "task_ref": kwargs["task_ref"]}

    class Bridge:
        async def create_scouting_task(self, **kwargs):
            calls["bridge"] = kwargs
            return type("R", (), {"task_ref": "urn:sahool:task:t-1"})()

    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", Store())
    monkeypatch.setattr(anomalies, "_bridge", Bridge())
    result = await anomalies.request_ground_verification(
        ANOMALY["anomaly_ref"],
        VerificationRequest(expected_version=1),
        authorization="Bearer user-jwt",
        token=object(),
    )
    assert calls["bridge"]["tenant_id"] == TENANT, calls["bridge"]
    assert "authorization" not in calls["bridge"], "the user's bearer is not handed to the bridge"
    assert (
        calls["bridge"]["idempotency_key"]
        == hashlib.sha256(f"{ANOMALY['anomaly_ref']}|verification".encode()).hexdigest()
    ), "one deterministic key per anomaly, so a retry replays"
    assert calls["transition"][1] == "verification_requested", calls["transition"]
    assert result["task_ref"] == "urn:sahool:task:t-1", result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "version", "task_ref", "reason"),
    [
        ("resolved", 1, None, "invalid_transition:resolved->verification_requested"),
        ("confirmed", 1, None, "invalid_transition:confirmed->verification_requested"),
        ("rejected", 1, None, "invalid_transition:rejected->verification_requested"),
        ("verification_requested", 1, "urn:sahool:task:t-0", "invalid_transition"),
        ("detected", 2, None, "aggregate_version_conflict"),
        ("inconclusive", 1, "urn:sahool:task:t-0", "reverification_not_supported"),
    ],
)
async def test_a_refused_verification_creates_no_field_task(
    monkeypatch, status, version, task_ref, reason
):
    """Review MEDIUM (W1-20): the lifecycle check runs before the bridge, so a request the
    anomaly lifecycle refuses never stores an orphan scouting task in field-management."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import VerificationRequest
    from fastapi import HTTPException

    record = {
        "tenant_id": TENANT,
        "payload": ANOMALY,
        "status": status,
        "aggregate_version": version,
        "task_ref": task_ref,
    }
    calls = []

    class Store:  # the anomaly store's functions, not a database connection
        async def get(self, ref, *, tenant_id):
            return record

        async def transition(self, ref, status, **kwargs):
            calls.append("transition")
            raise AssertionError("no transition may run for a refused request")

    class Bridge:
        async def create_scouting_task(self, **kwargs):
            calls.append("bridge")
            return type("R", (), {"task_ref": "urn:sahool:task:t-orphan"})()

    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", Store())
    monkeypatch.setattr(anomalies, "_bridge", Bridge())
    with pytest.raises(HTTPException) as caught:
        await anomalies.request_ground_verification(
            ANOMALY["anomaly_ref"],
            VerificationRequest(expected_version=1),
            authorization="Bearer user-jwt",
            token=object(),
        )
    assert caught.value.status_code == 409, caught.value.detail
    assert reason in str(caught.value.detail), caught.value.detail
    assert calls == [], f"no field task and no transition for a refused request: {calls}"


def test_the_verification_sources_follow_the_lifecycle():
    import routers.anomalies as anomalies

    assert anomalies._VERIFICATION_SOURCES == {"detected", "triaged", "inconclusive"}, (
        "only states the lifecycle lets move to verification_requested may reach the bridge"
    )


class _Signal:
    """A required-verification signal as anomaly_engine.detect_signals returns it."""

    def __init__(self, observation):
        self.primary_observation_ref = f"urn:sahool:observation:{observation}"
        self.signal_type = "ndvi_decline"
        self.verification_requirement = "required"

    def to_dict(self):
        return {
            "primary_observation_ref": self.primary_observation_ref,
            "signal_type": self.signal_type,
            "verification_requirement": self.verification_requirement,
        }


@pytest.mark.asyncio
async def test_a_concurrent_lifecycle_change_after_the_task_is_stored_is_an_explicit_409(
    monkeypatch,
):
    """Review W1-20 (g/B): the anomaly is resolved by another request while its task is being
    stored. The versioned transition then fails; the caller gets an explicit lifecycle conflict
    naming the stored task, not a bare version conflict that hides it."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import VerificationRequest
    from anomaly_store import InvalidTransition
    from fastapi import HTTPException

    record = {
        "tenant_id": TENANT,
        "payload": ANOMALY,
        "status": "detected",
        "aggregate_version": 1,
        "task_ref": None,
    }

    class Store:  # the anomaly store's functions, not a database connection
        async def get(self, ref, *, tenant_id):
            return record

        async def transition(self, ref, status, **kwargs):
            # Another request resolved the anomaly after the pre-check passed.
            raise InvalidTransition("aggregate_version_conflict")

    class Bridge:
        async def create_scouting_task(self, **kwargs):
            return type("R", (), {"task_ref": "urn:sahool:task:t-raced"})()

    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", Store())
    monkeypatch.setattr(anomalies, "_bridge", Bridge())
    with pytest.raises(HTTPException) as caught:
        await anomalies.request_ground_verification(
            ANOMALY["anomaly_ref"],
            VerificationRequest(expected_version=1),
            authorization="Bearer user-jwt",
            token=object(),
        )
    assert caught.value.status_code == 409, caught.value.detail
    assert caught.value.detail == {
        "code": "verification_lifecycle_conflict",
        "reason": "aggregate_version_conflict",
        "task_ref": "urn:sahool:task:t-raced",
        "task_attached": False,
    }, caught.value.detail


@pytest.mark.asyncio
async def test_automatic_verification_reports_a_lifecycle_conflict_and_keeps_going(monkeypatch):
    """Review W1-20 (g/B): on the detect route, a lifecycle conflict after the task is stored used
    to escape as an unhandled InvalidTransition (HTTP 500) and drop every other anomaly of the
    call. It is now reported on that anomaly, and the next anomaly is still verified."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import DetectRequest
    from anomaly_store import InvalidTransition

    records = {
        obs: {
            "anomaly_ref": f"urn:sahool:anomaly:{obs}",
            "tenant_id": TENANT,
            "payload": {**ANOMALY, "anomaly_ref": f"urn:sahool:anomaly:{obs}"},
            "status": "detected",
            "aggregate_version": 1,
            "task_ref": None,
        }
        for obs in ("raced", "calm")
    }
    transitions = []

    class Store:  # the anomaly store's functions, not a database connection
        async def list(self, tenant_id, field_id, season_id):
            return []

        async def upsert_detected(self, payload):
            obs = payload["primary_observation_ref"].rsplit(":", 1)[1]
            return dict(records[obs])

        async def transition(self, ref, status, **kwargs):
            transitions.append(ref)
            if ref.endswith(":raced"):
                raise InvalidTransition("invalid_transition:resolved->verification_requested")
            return {**records["calm"], "status": status, "task_ref": kwargs["task_ref"]}

    class Bridge:
        async def create_scouting_task(self, *, anomaly, **kwargs):
            name = anomaly["anomaly_ref"].rsplit(":", 1)[1]
            return type("R", (), {"task_ref": f"urn:sahool:task:{name}"})()

    async def baselines(field_id, request, token):
        return [{"stub": True}]

    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", Store())
    monkeypatch.setattr(anomalies, "_bridge", Bridge())
    monkeypatch.setattr(anomalies, "_baselines", baselines)
    monkeypatch.setattr(
        anomalies, "detect_signals", lambda **kwargs: [_Signal("raced"), _Signal("calm")]
    )
    result = await anomalies.detect_signal_anomalies(
        "fld_demo",
        DetectRequest(season_id="sea_demo", auto_request_verification=True),
        authorization="Bearer user-jwt",
        token=object(),
    )
    raced, calm = result["anomalies"]
    assert raced["verification_lifecycle_conflict"] == {
        "code": "verification_lifecycle_conflict",
        "reason": "invalid_transition:resolved->verification_requested",
        "task_ref": "urn:sahool:task:raced",
        "task_attached": False,
    }, raced
    assert raced["status"] == "detected" and not raced["task_ref"], raced
    assert calm["status"] == "verification_requested", calm
    assert calm["task_ref"] == "urn:sahool:task:calm", calm
    assert transitions == ["urn:sahool:anomaly:raced", "urn:sahool:anomaly:calm"], transitions
