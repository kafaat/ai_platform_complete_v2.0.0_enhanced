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
async def test_a_409_naming_the_anomalys_task_hands_that_task_back(monkeypatch, service_env):
    from ground_verification_bridge import TaskAlreadyExists

    async def handler(request):
        return httpx.Response(
            409, json={"detail": {"code": "anomaly_already_has_task", "task_ref": "t-existing"}}
        )

    _route_to(monkeypatch, handler)
    with pytest.raises(TaskAlreadyExists, match="task_service_rejected:409") as caught:
        await GroundVerificationBridge("http://fm").create_scouting_task(
            anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="f" * 64
        )
    assert caught.value.task_ref == "urn:sahool:task:t-existing", caught.value.task_ref


@pytest.mark.asyncio
async def test_an_unreadable_2xx_body_is_unconfirmed_not_a_crash(monkeypatch, service_env):
    async def handler(request):
        return httpx.Response(201, content=b"<html>proxy</html>")

    _route_to(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="task_service_persistence_unconfirmed"):
        await GroundVerificationBridge("http://fm").create_scouting_task(
            anomaly=ANOMALY, tenant_id=TENANT, idempotency_key="f" * 64
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


def _key(anomaly_ref: str) -> str:
    return hashlib.sha256(f"{anomaly_ref}|verification".encode()).hexdigest()


@pytest.fixture
def route(monkeypatch, tmp_path):
    """The verification route over the real SQLite anomaly store (no stubbed store)."""
    import main
    import routers.anomalies as anomalies
    from anomaly_runtime import AnomalyStoreFacade
    from anomaly_store import AnomalyStore

    backend = AnomalyStore(str(tmp_path / "anomalies.db"))
    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", AnomalyStoreFacade(backend))
    detected = backend.upsert_detected(dict(ANOMALY))
    assert detected["aggregate_version"] == 1, detected
    return anomalies, backend


class _Bridge:
    """The bridge's function, recording calls; ``during`` runs while the task is dispatched."""

    def __init__(self, task_ref="urn:sahool:task:t-1", *, error=None, during=None):
        self.task_ref, self.error, self.during, self.calls = task_ref, error, during, []

    async def create_scouting_task(self, **kwargs):
        self.calls.append(kwargs)
        if self.during is not None:
            self.during()
        if isinstance(self.error, Exception):
            raise self.error
        if self.error is not None:
            raise RuntimeError(self.error)
        return type("R", (), {"task_ref": self.task_ref})()


async def _request(anomalies, version):
    from anomaly_requests import VerificationRequest

    return await anomalies.request_ground_verification(
        ANOMALY["anomaly_ref"],
        VerificationRequest(expected_version=version),
        authorization="Bearer user-jwt",
        token=object(),
    )


async def test_the_verification_route_passes_the_verified_tenant_and_stores_the_task_ref(
    monkeypatch, route
):
    """routers/anomalies.py hands the bridge the JWT-verified tenant and records its task_ref."""
    anomalies, backend = route
    bridge = _Bridge()
    monkeypatch.setattr(anomalies, "_bridge", bridge)
    result = await _request(anomalies, 1)
    (call,) = bridge.calls
    assert call["tenant_id"] == TENANT, call
    assert "authorization" not in call, "the user's bearer is not handed to the bridge"
    assert call["idempotency_key"] == _key(ANOMALY["anomaly_ref"]), (
        "one deterministic key per anomaly, so a retry replays"
    )
    assert result["status"] == "verification_requested", result
    assert result["task_ref"] == "urn:sahool:task:t-1", result
    reservation = result["payload"]["verification_reservation"]
    assert reservation["state"] == "attached", reservation
    assert reservation["prior_status"] == "detected", reservation
    assert backend.get(ANOMALY["anomaly_ref"])["task_ref"] == "urn:sahool:task:t-1", (
        "the task is attached in the store, not only in the response"
    )


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
    from fastapi import HTTPException

    record = {
        "anomaly_ref": ANOMALY["anomaly_ref"],
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

        async def reserve_verification(self, ref, **kwargs):
            calls.append("reserve")
            raise AssertionError("no reservation may be taken for a refused request")

        async def transition(self, ref, status, **kwargs):
            calls.append("transition")
            raise AssertionError("no transition may run for a refused request")

    bridge = _Bridge("urn:sahool:task:t-orphan")
    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", Store())
    monkeypatch.setattr(anomalies, "_bridge", bridge)
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 1)
    assert caught.value.status_code == 409, caught.value.detail
    assert reason in str(caught.value.detail), caught.value.detail
    assert calls == [] and bridge.calls == [], (
        f"no field task, reservation or transition for a refused request: {calls} {bridge.calls}"
    )


def test_the_verification_sources_follow_the_lifecycle():
    import routers.anomalies as anomalies

    assert anomalies._VERIFICATION_SOURCES == {"detected", "triaged", "inconclusive"}, (
        "only states the lifecycle lets move to verification_requested may reach the bridge"
    )


# --- SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01: reserve before dispatch -------------------


async def test_a_concurrent_resolve_during_dispatch_cannot_strand_the_task(monkeypatch, route):
    """The anomaly is reserved against the expected version before the task is dispatched, so
    a resolve racing the dispatch (with the version it read, or with the current one) is refused
    and the stored task ends attached. Before the fix the resolve won and the task was left
    pending in field-management with no anomaly pointing at it."""
    from anomaly_store import InvalidTransition

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    refused = []

    def concurrent_resolve():
        for version in (1, backend.get(ref)["aggregate_version"]):
            try:
                backend.transition(ref, "resolved", expected_version=version, tenant_id=TENANT)
            except InvalidTransition as exc:
                refused.append(str(exc))

    monkeypatch.setattr(
        anomalies, "_bridge", _Bridge("urn:sahool:task:t-raced", during=concurrent_resolve)
    )
    result = await _request(anomalies, 1)
    assert len(refused) == 2, f"both racing resolves must be refused, got {refused}"
    assert "verification_reservation_pending" in refused, refused
    stored = backend.get(ref)
    assert stored["status"] == "verification_requested", stored
    assert stored["task_ref"] == "urn:sahool:task:t-raced", "the dispatched task is attached"
    assert result["task_ref"] == stored["task_ref"], result


async def test_a_verification_result_during_dispatch_is_refused(monkeypatch, route):
    """No result callback may close the anomaly while its task has not been attached yet."""
    from anomaly_store import InvalidTransition

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    seen = []

    def concurrent_result():
        current = backend.get(ref)
        try:
            backend.transition(
                ref, "rejected", expected_version=current["aggregate_version"], tenant_id=TENANT
            )
        except InvalidTransition as exc:
            seen.append(str(exc))

    monkeypatch.setattr(anomalies, "_bridge", _Bridge(during=concurrent_result))
    await _request(anomalies, 1)
    assert seen == ["verification_reservation_pending"], seen
    assert backend.get(ref)["status"] == "verification_requested", "not closed under the dispatch"


@pytest.mark.parametrize(
    "error",
    [
        "task_service_not_configured",
        "task_service_rejected:422",
        "task_service_rejected:403",
        "task_service_tenant_assertion_unavailable",
    ],
)
async def test_a_bridge_failure_that_stored_nothing_restores_the_prior_state(
    monkeypatch, route, error
):
    from fastapi import HTTPException

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    backend.transition(ref, "triaged", expected_version=1, tenant_id=TENANT)
    monkeypatch.setattr(anomalies, "_bridge", _Bridge(error=error))
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 2)
    assert caught.value.status_code == 424, caught.value.detail
    assert caught.value.detail == {
        "code": "verification_dispatch_failed",
        "reason": error,
        "reservation": "released",
    }, caught.value.detail
    stored = backend.get(ref)
    assert stored["status"] == "triaged", f"the prior state returns: {stored}"
    assert not stored["task_ref"], stored
    assert "verification_reservation" not in stored["payload"], stored["payload"]
    assert stored["payload"]["verification_reservation_released"]["reason"] == error, stored
    # The anomaly is open again: it can be resolved, or verified with its current version.
    monkeypatch.setattr(anomalies, "_bridge", _Bridge("urn:sahool:task:t-2"))
    retried = await _request(anomalies, stored["aggregate_version"])
    assert retried["task_ref"] == "urn:sahool:task:t-2", retried


async def test_an_ambiguous_bridge_failure_keeps_the_reservation_until_a_replay_attaches(
    monkeypatch, route
):
    """A transport failure may come after the owner stored the task. The reservation is kept, so
    the anomaly cannot be closed under a possibly stored task; a retry with the original version
    replays the same key and attaches the same task."""
    from anomaly_store import InvalidTransition
    from fastapi import HTTPException

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    monkeypatch.setattr(anomalies, "_bridge", _Bridge(error="task_service_unavailable"))
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 1)
    assert caught.value.status_code == 424, caught.value.detail
    assert caught.value.detail["reservation"] == "pending", caught.value.detail
    pending = backend.get(ref)
    assert pending["payload"]["verification_reservation"]["state"] == "pending", pending
    with pytest.raises(InvalidTransition, match="verification_reservation_pending"):
        backend.transition(
            ref, "resolved", expected_version=pending["aggregate_version"], tenant_id=TENANT
        )
    bridge = _Bridge("urn:sahool:task:t-replayed")
    monkeypatch.setattr(anomalies, "_bridge", bridge)
    resumed = await _request(anomalies, 1)
    assert [c["idempotency_key"] for c in bridge.calls] == [_key(ref)], bridge.calls
    assert resumed["task_ref"] == "urn:sahool:task:t-replayed", resumed
    assert resumed["payload"]["verification_reservation"]["state"] == "attached", resumed


async def test_a_replay_after_success_returns_the_same_task(monkeypatch, route):
    anomalies, backend = route
    monkeypatch.setattr(anomalies, "_bridge", _Bridge("urn:sahool:task:t-once"))
    first = await _request(anomalies, 1)
    replay_bridge = _Bridge("urn:sahool:task:t-other")
    monkeypatch.setattr(anomalies, "_bridge", replay_bridge)
    replay = await _request(anomalies, 1)
    assert replay["task_ref"] == first["task_ref"] == "urn:sahool:task:t-once", replay
    assert replay["aggregate_version"] == first["aggregate_version"], "a replay writes nothing"
    assert replay_bridge.calls == [], "a finished request is not dispatched again"


async def test_an_attach_failure_is_an_explicit_409_and_a_retry_attaches(monkeypatch, route):
    """The task is stored but the attach fails (a store failure or a concurrent holder). The
    caller gets the explicit lifecycle conflict naming the task; the reservation stays pending,
    so nothing can close the anomaly, and a retry attaches the same task."""
    from anomaly_store import InvalidTransition
    from fastapi import HTTPException

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    real_attach = backend.attach_verification_task

    def failing_attach(*args, **kwargs):
        raise InvalidTransition("aggregate_version_conflict")

    monkeypatch.setattr(backend, "attach_verification_task", failing_attach)
    monkeypatch.setattr(anomalies, "_bridge", _Bridge("urn:sahool:task:t-stored"))
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 1)
    assert caught.value.status_code == 409, caught.value.detail
    assert caught.value.detail == {
        "code": "verification_lifecycle_conflict",
        "reason": "aggregate_version_conflict",
        "task_ref": "urn:sahool:task:t-stored",
        "task_attached": False,
    }, caught.value.detail
    assert backend.get(ref)["payload"]["verification_reservation"]["state"] == "pending", (
        "the reservation still holds the anomaly"
    )
    monkeypatch.setattr(backend, "attach_verification_task", real_attach)
    resumed = await _request(anomalies, 1)
    assert resumed["task_ref"] == "urn:sahool:task:t-stored", resumed


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


async def test_automatic_verification_reports_a_lifecycle_conflict_and_keeps_going(
    monkeypatch, tmp_path
):
    """Review W1-20 (g/B): on the detect route a lifecycle conflict used to escape as an
    unhandled InvalidTransition (HTTP 500) and drop every other anomaly of the call. It is now
    reported on that anomaly, and the next anomaly is still verified. Since the reservation
    comes first, an anomaly moved by someone else is refused before any task is dispatched."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import DetectRequest
    from anomaly_runtime import AnomalyStoreFacade
    from anomaly_store import AnomalyStore

    backend = AnomalyStore(str(tmp_path / "anomalies.db"))
    real_reserve = backend.reserve_verification

    def reserve_after_a_concurrent_triage(ref, **kwargs):
        if ref.endswith(":raced"):
            # Another request moved the anomaly between detection and the reservation.
            backend.transition(ref, "triaged", expected_version=1, tenant_id=TENANT)
        return real_reserve(ref, **kwargs)

    monkeypatch.setattr(backend, "reserve_verification", reserve_after_a_concurrent_triage)

    class Bridge:
        def __init__(self):
            self.calls = []

        async def create_scouting_task(self, *, anomaly, **kwargs):
            name = anomaly["anomaly_ref"].rsplit(":", 1)[1]
            self.calls.append(name)
            return type("R", (), {"task_ref": f"urn:sahool:task:{name}"})()

    async def baselines(field_id, request, token):
        return [{"stub": True}]

    def detect(**kwargs):
        return [_Signal("raced"), _Signal("calm")]

    original_upsert = backend.upsert_detected

    def upsert(payload):
        obs = payload["primary_observation_ref"].rsplit(":", 1)[1]
        return original_upsert({**ANOMALY, **payload, "anomaly_ref": f"urn:sahool:anomaly:{obs}"})

    monkeypatch.setattr(backend, "upsert_detected", upsert)
    bridge = Bridge()
    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", AnomalyStoreFacade(backend))
    monkeypatch.setattr(anomalies, "_bridge", bridge)
    monkeypatch.setattr(anomalies, "_baselines", baselines)
    monkeypatch.setattr(anomalies, "detect_signals", detect)
    result = await anomalies.detect_signal_anomalies(
        "fld_demo",
        DetectRequest(season_id="sea_demo", auto_request_verification=True),
        authorization="Bearer user-jwt",
        token=object(),
    )
    raced, calm = result["anomalies"]
    assert raced["verification_lifecycle_conflict"] == {
        "code": "verification_lifecycle_conflict",
        "reason": "aggregate_version_conflict",
        "task_ref": None,
        "task_attached": False,
    }, raced
    assert not raced["task_ref"], raced
    assert calm["status"] == "verification_requested", calm
    assert calm["task_ref"] == "urn:sahool:task:calm", calm
    assert "current_evaluation" in calm, "the evaluation travels with the attached record"
    assert bridge.calls == ["calm"], f"no task is dispatched for the raced anomaly: {bridge.calls}"


@pytest.mark.parametrize(
    "error",
    [
        "task_service_unavailable",
        "task_service_rejected:503",
        "task_service_rejected:500",
        "task_service_rejected:409",
        "task_service_persistence_unconfirmed",
        "task_service_missing_task_ref",
    ],
)
async def test_a_failure_that_may_have_stored_a_task_keeps_the_reservation(
    monkeypatch, route, error
):
    """A 5xx, a 409 (the owner already holds a task for this anomaly) or a processed 2xx that
    does not confirm the task may each leave a stored task behind: the reservation is kept and
    the detail names the version that resumes it."""
    from fastapi import HTTPException

    anomalies, backend = route
    monkeypatch.setattr(anomalies, "_bridge", _Bridge(error=error))
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 1)
    pending = backend.get(ANOMALY["anomaly_ref"])
    assert caught.value.status_code == 424, caught.value.detail
    assert caught.value.detail == {
        "code": "verification_dispatch_failed",
        "reason": error,
        "reservation": "pending",
        "resume_expected_version": pending["aggregate_version"],
    }, caught.value.detail
    assert pending["payload"]["verification_reservation"]["state"] == "pending", pending


async def test_a_pending_reservation_resumes_with_the_current_version(monkeypatch, route):
    """Review of SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01: the version the reservation was
    taken from was the only way back in, and nothing showed it. A request with the version the
    anomaly has now (the one the 424 detail names) resumes the same reservation and key."""
    from fastapi import HTTPException

    anomalies, backend = route
    ref = ANOMALY["anomaly_ref"]
    monkeypatch.setattr(anomalies, "_bridge", _Bridge(error="task_service_rejected:503"))
    with pytest.raises(HTTPException) as caught:
        await _request(anomalies, 1)
    current = caught.value.detail["resume_expected_version"]
    assert current == backend.get(ref)["aggregate_version"] != 1, caught.value.detail
    bridge = _Bridge("urn:sahool:task:t-resumed")
    monkeypatch.setattr(anomalies, "_bridge", bridge)
    resumed = await _request(anomalies, current)
    assert [c["idempotency_key"] for c in bridge.calls] == [_key(ref)], bridge.calls
    assert resumed["task_ref"] == "urn:sahool:task:t-resumed", resumed
    assert resumed["payload"]["verification_reservation"]["state"] == "attached", resumed
    # A stale version that is neither the reserved nor the current one is still refused.
    with pytest.raises(HTTPException) as stale:
        await _request(anomalies, current)
    assert stale.value.status_code == 409, stale.value.detail


async def test_a_409_naming_the_existing_task_attaches_it(monkeypatch, route):
    """The owner keeps one task per anomaly; when it answers 409 with that task's ref, the
    reservation attaches it instead of staying pending behind a refusal every replay repeats."""
    from ground_verification_bridge import TaskAlreadyExists

    anomalies, backend = route
    monkeypatch.setattr(
        anomalies, "_bridge", _Bridge(error=TaskAlreadyExists("urn:sahool:task:t-existing"))
    )
    attached = await _request(anomalies, 1)
    assert attached["task_ref"] == "urn:sahool:task:t-existing", attached
    assert attached["payload"]["verification_reservation"]["state"] == "attached", attached
    assert backend.get(ANOMALY["anomaly_ref"])["task_ref"] == "urn:sahool:task:t-existing", (
        "the existing task is stored on the anomaly"
    )


async def test_detect_resumes_a_reservation_left_by_a_transient_outage(monkeypatch, tmp_path):
    """Review reproduction: auto-verification met a 503, the reservation stayed pending, and
    the next detect skipped the anomaly because it was already verification_requested, so it
    stayed locked with no task. Detect now resumes the reservation with the same key."""
    import main
    import routers.anomalies as anomalies
    from anomaly_requests import DetectRequest
    from anomaly_runtime import AnomalyStoreFacade
    from anomaly_store import AnomalyStore

    backend = AnomalyStore(str(tmp_path / "anomalies.db"))
    original_upsert = backend.upsert_detected

    def upsert(payload):
        return original_upsert({**ANOMALY, **payload})

    async def baselines(field_id, request, token):
        return [{"stub": True}]

    monkeypatch.setattr(backend, "upsert_detected", upsert)
    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": TENANT})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: claims["tenant_id"])
    monkeypatch.setattr(anomalies, "_store", AnomalyStoreFacade(backend))
    monkeypatch.setattr(anomalies, "_baselines", baselines)
    monkeypatch.setattr(anomalies, "detect_signals", lambda **kwargs: [_Signal("outage")])

    async def detect():
        return await anomalies.detect_signal_anomalies(
            "fld_demo",
            DetectRequest(season_id="sea_demo", auto_request_verification=True),
            authorization="Bearer user-jwt",
            token=object(),
        )

    failing = _Bridge(error="task_service_rejected:503")
    monkeypatch.setattr(anomalies, "_bridge", failing)
    (first,) = (await detect())["anomalies"]
    assert first["verification_reservation_outcome"] == "pending", first
    assert first["status"] == "verification_requested" and not first["task_ref"], first
    healthy = _Bridge("urn:sahool:task:t-after-outage")
    monkeypatch.setattr(anomalies, "_bridge", healthy)
    (second,) = (await detect())["anomalies"]
    ref = ANOMALY["anomaly_ref"]
    assert [c["idempotency_key"] for c in healthy.calls] == [_key(ref)], healthy.calls
    assert failing.calls[0]["idempotency_key"] == _key(ref), "the same key is replayed"
    assert second["task_ref"] == "urn:sahool:task:t-after-outage", second
    stored = backend.get(ref)
    assert stored["payload"]["verification_reservation"]["state"] == "attached", stored
    # The anomaly is no longer locked: its verification result is accepted.
    closed = backend.transition(
        ref, "rejected", expected_version=stored["aggregate_version"], tenant_id=TENANT
    )
    assert closed["status"] == "rejected", closed
    (third,) = (await detect())["anomalies"]
    assert len(healthy.calls) == 1, "a closed anomaly is not dispatched again"
    assert third["status"] == "rejected", third
