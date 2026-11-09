"""Decision provenance integrity at the decision-service boundary (no database).

Pure functions and the HTTP edge with persistence mocked:
- replay on an existing decision_id with different content is a conflict (409), never a silent
  success;
- a write without decision_id derives a deterministic id from tenant + candidate lineage (or the
  Idempotency-Key), so a producer retry replays instead of duplicating the candidate;
- ``stage`` is an enum (the never-reviewable ``pending_approval`` stage is refused);
- typed ``provenance`` is persisted inside decision_value;
- reviews require a policy version, bound into the idempotency hash;
- separation of duties (DECISION_REQUIRE_SEPARATION_OF_DUTIES) in both flag states.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-00000000f6f6"
OTHER = "00000000-0000-0000-0000-00000000f7f7"
TOKEN = "isolated-test-token"
SOD_ENV = ("DECISION_REQUIRE_SEPARATION_OF_DUTIES", "SAHOOL_ENV", "ENVIRONMENT")


def _headers(**extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "X-Tenant-Id": TENANT, **extra}


@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.setattr(main, "agronomic_context_required", lambda: False)
    return main, TestClient(main.app)


# ── F6: replay comparison ──────────────────────────────────────────────────────────────────
def _stored(value: dict, *, digest: bool = True, **columns):
    from persistence import decision_value_digest

    row = {
        "decision_value_digest": decision_value_digest(value) if digest else None,
        "decision_value": value,
        "field_id": "f1",
        "decision_type": "irrigation",
        "stage": "candidate",
    }
    row.update(columns)
    return row


def _write(value: dict, **over):
    base = {"field_id": "f1", "decision_type": "irrigation", "stage": "candidate"}
    base.update(over)
    return SimpleNamespace(decision_value=value, **base)


def test_identical_replay_is_a_replay():
    from persistence import decision_replay_mismatch

    assert decision_replay_mismatch(_stored({"mm": 10}), _write({"mm": 10})) is None


@pytest.mark.parametrize(
    "write",
    [
        _write({"mm": 25}),
        _write({"mm": 10}, field_id="f2"),
        _write({"mm": 10}, decision_type="other"),
        _write({"mm": 10}, stage="decision"),
    ],
)
def test_a_different_record_under_the_same_id_is_a_conflict(write):
    from persistence import decision_replay_mismatch

    assert decision_replay_mismatch(_stored({"mm": 10}), write) == "decision_id_payload_mismatch"


def test_a_legacy_row_without_digest_is_compared_by_its_stored_evidence():
    import json

    from persistence import decision_replay_mismatch

    legacy = _stored({"mm": 10}, digest=False, decision_value=json.dumps({"mm": 10}))
    assert decision_replay_mismatch(legacy, _write({"mm": 10})) is None
    assert decision_replay_mismatch(legacy, _write({"mm": 11})) == "decision_id_payload_mismatch"


def test_record_endpoint_maps_a_replay_conflict_to_409(client, monkeypatch):
    main, http = client
    writer = AsyncMock(
        return_value={"status": "conflict", "reason": "decision_id_payload_mismatch"}
    )
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = http.post(
        "/v1/decisions/record",
        headers=_headers(),
        json={"decision_id": "dec_x", "stage": "decision", "decision_value": {"v": 2}},
    )
    assert result.status_code == 409, result.text
    assert result.json()["detail"] == "decision_id_payload_mismatch"


# ── F4/F5: stage enum + deterministic decision_id ──────────────────────────────────────────
def test_pending_approval_is_not_a_stage(client, monkeypatch):
    main, http = client
    writer = AsyncMock()
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = http.post(
        "/v1/decisions/record",
        headers=_headers(),
        json={"stage": "pending_approval", "decision_value": {"candidate_lineage_id": "x"}},
    )
    assert result.status_code == 422, result.text
    writer.assert_not_awaited()


def _payload(**over):
    from main import DecisionRecordIn

    return DecisionRecordIn(**over)


def test_candidate_without_id_derives_it_from_tenant_and_lineage():
    from main import derive_decision_id

    cand = _payload(stage="candidate", decision_value={"candidate_lineage_id": "rs8_abc"})
    first = derive_decision_id(tenant_id=TENANT, payload=cand, idempotency_key=None)
    retry = derive_decision_id(tenant_id=TENANT, payload=cand, idempotency_key="other-key")
    assert first == retry and first.startswith("dec_")
    assert derive_decision_id(tenant_id=OTHER, payload=cand, idempotency_key=None) != first


def test_explicit_id_wins_and_idempotency_key_is_honoured():
    from main import derive_decision_id

    explicit = _payload(decision_id="dec_given", stage="candidate")
    assert derive_decision_id(tenant_id=TENANT, payload=explicit, idempotency_key="k") == (
        "dec_given"
    )
    plain = _payload(stage="decision", decision_value={"v": 1})
    keyed = derive_decision_id(tenant_id=TENANT, payload=plain, idempotency_key="idmp-1")
    assert keyed == derive_decision_id(tenant_id=TENANT, payload=plain, idempotency_key="idmp-1")
    assert keyed != derive_decision_id(tenant_id=OTHER, payload=plain, idempotency_key="idmp-1")
    fresh = {derive_decision_id(tenant_id=TENANT, payload=plain, idempotency_key=None)}
    fresh.add(derive_decision_id(tenant_id=TENANT, payload=plain, idempotency_key=None))
    assert len(fresh) == 2, "no identity: a fresh id each time"


def test_a_candidate_retry_reaches_persistence_under_the_same_id(client, monkeypatch):
    main, http = client
    writer = AsyncMock(return_value={"replayed": False, "decision_value_digest": "d"})
    monkeypatch.setattr(main, "persist_decision_record", writer)
    body = {"stage": "candidate", "decision_value": {"candidate_lineage_id": "crop_lin_1"}}
    ids = []
    for key in ("first-attempt", "retry-attempt"):
        result = http.post(
            "/v1/decisions/record", headers=_headers(**{"Idempotency-Key": key}), json=body
        )
        assert result.status_code == 200, result.text
        ids.append(writer.call_args.kwargs["decision_id"])
    assert ids[0] == ids[1]


# ── F2: typed provenance persisted inside decision_value ───────────────────────────────────
_PROVENANCE = {
    "producer_id": "sahool-platform/irrigation-recommendation",
    "model_or_rule_version": "irrigation-recommendation-policy/1",
    "policy_version": "irrigation-policy:water_saving/salinity:net_only",
    "explanation": "depletion reached the trigger",
    "confidence_method": "heuristic_uncalibrated",
    "evidence_refs": ["weather-engine-et0:s1"],
}


def test_provenance_is_persisted_inside_decision_value(client, monkeypatch):
    main, http = client
    writer = AsyncMock(return_value={"replayed": False, "decision_value_digest": "d"})
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = http.post(
        "/v1/decisions/record",
        headers=_headers(),
        json={
            "decision_id": "dec_p",
            "stage": "candidate",
            "decision_value": {"provenance": {"et0": "s1"}, "candidate_lineage_id": "irr_1"},
            "provenance": _PROVENANCE,
        },
    )
    assert result.status_code == 200, result.text
    stored = writer.call_args.kwargs["payload"].decision_value
    assert stored["decision_provenance"] == _PROVENANCE
    assert stored["provenance"] == {"et0": "s1"}, "producer input provenance is untouched"


def test_a_record_without_provenance_is_unchanged(client, monkeypatch):
    main, http = client
    writer = AsyncMock(return_value={"replayed": False, "decision_value_digest": "d"})
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = http.post(
        "/v1/decisions/record",
        headers=_headers(),
        json={"decision_id": "dec_np", "decision_value": {"v": 1}},
    )
    assert result.status_code == 200, result.text
    assert writer.call_args.kwargs["payload"].decision_value == {"v": 1}


@pytest.mark.parametrize(
    "body",
    [
        {"provenance": {**_PROVENANCE, "unknown": 1}},
        {"provenance": {**_PROVENANCE, "producer_id": ""}},
        {
            "provenance": _PROVENANCE,
            "decision_value": {"decision_provenance": {**_PROVENANCE, "producer_id": "other"}},
        },
        {"decision_value": {"decision_provenance": {"producer_id": "only"}}},
    ],
)
def test_malformed_or_contradicting_provenance_is_refused(client, monkeypatch, body):
    main, http = client
    writer = AsyncMock()
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = http.post(
        "/v1/decisions/record", headers=_headers(), json={"decision_id": "d", **body}
    )
    assert result.status_code == 422, result.text
    writer.assert_not_awaited()


# ── F11: review policy version ─────────────────────────────────────────────────────────────
def _review_body(**over):
    body = {
        "action": "approve",
        "candidate_lineage_id": "lin",
        "decision_value_digest": "a" * 64,
        "idempotency_key": "rev-1",
        "policy_version": "rev/1",
    }
    body.update(over)
    return body


@pytest.mark.parametrize("policy", [None, "", "   "])
def test_review_requires_a_policy_version(client, monkeypatch, policy):
    main, http = client
    reviewer = AsyncMock()
    monkeypatch.setattr(main, "review_decision", reviewer)
    result = http.post(
        "/v1/decisions/dec_r/review",
        headers=_headers(**{"X-Reviewed-By": "u-rev"}),
        json=_review_body(policy_version=policy),
    )
    assert result.status_code == 422, result.text
    reviewer.assert_not_awaited()


def test_policy_version_is_part_of_the_review_request_hash():
    from persistence import _request_hash

    semantic = dict(
        decision_id="d",
        action="approve",
        new_state="approved",
        reason="ok",
        candidate_lineage_id="lin",
        decision_value_digest="a" * 64,
    )
    v1 = _request_hash(**semantic, policy_version="rev/1")
    assert v1 != _request_hash(**semantic, policy_version="rev/2")
    assert v1 != _request_hash(**semantic), "the legacy (pre-policy) hash is distinct"


@pytest.mark.asyncio
async def test_review_persistence_refuses_a_missing_policy_version_before_any_io(monkeypatch):
    import persistence

    connect = AsyncMock(side_effect=AssertionError("must not touch the database"))
    monkeypatch.setattr(persistence, "_connect", connect)
    result = await persistence.review_decision(
        tenant_id=TENANT,
        decision_id="d",
        action="approve",
        new_state="approved",
        reason="ok",
        reviewed_by="u",
        candidate_lineage_id="lin",
        idempotency_key="k",
        policy_version="  ",
        decision_value_digest="a" * 64,
    )
    assert result == {"status": "invalid", "reason": "policy_version is required"}


# ── F7: separation of duties ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, False),
        ({"SAHOOL_ENV": "development"}, False),
        ({"SAHOOL_ENV": "production"}, True),
        ({"ENVIRONMENT": "prod"}, True),
        ({"DECISION_REQUIRE_SEPARATION_OF_DUTIES": "true"}, True),
        ({"DECISION_REQUIRE_SEPARATION_OF_DUTIES": "1", "SAHOOL_ENV": "staging"}, True),
        ({"DECISION_REQUIRE_SEPARATION_OF_DUTIES": "false", "SAHOOL_ENV": "production"}, False),
    ],
)
def test_separation_of_duties_flag(monkeypatch, env, expected):
    from persistence import separation_of_duties_required

    for name in SOD_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert separation_of_duties_required() is expected


def test_same_actor_compares_present_identities_only():
    from persistence import same_actor

    assert same_actor("u-1", " U-1 ")
    assert not same_actor("u-1", "u-2")
    assert not same_actor(None, None), "no identity on either side is not a match"
    assert not same_actor("", "u-1")


@pytest.mark.parametrize("flag, violates", [("true", True), ("false", False)])
def test_separation_of_duties_violation_follows_the_flag(monkeypatch, flag, violates):
    from persistence import separation_of_duties_violation

    monkeypatch.setenv("DECISION_REQUIRE_SEPARATION_OF_DUTIES", flag)
    assert separation_of_duties_violation("u-1", "u-1") is violates
    assert separation_of_duties_violation("u-1", "u-2") is False


def test_review_self_approval_is_403(client, monkeypatch):
    main, http = client
    monkeypatch.setattr(
        main,
        "review_decision",
        AsyncMock(return_value={"status": "forbidden", "reason": "separation_of_duties_violation"}),
    )
    result = http.post(
        "/v1/decisions/dec_r/review",
        headers=_headers(**{"X-Reviewed-By": "u-rev"}),
        json=_review_body(),
    )
    assert result.status_code == 403, result.text
    assert result.json()["detail"] == "separation_of_duties_violation"


def test_authorizing_your_own_review_is_403(client, monkeypatch):
    main, http = client
    monkeypatch.setattr(
        main,
        "authorize_dispatch",
        AsyncMock(return_value={"status": "forbidden", "reason": "separation_of_duties_violation"}),
    )
    result = http.post(
        "/v1/execution-plans/xplan_1/authorize-dispatch",
        headers=_headers(**{"X-Authorized-By": "u-rev"}),
        json={
            "decision_id": "d",
            "review_id": "r",
            "candidate_lineage_id": "lin",
            "policy_version": "p",
            "weather_snapshot_id": "w",
            "resource_snapshot_id": "res",
            "idempotency_key": "k",
        },
    )
    assert result.status_code == 403, result.text


def test_approving_your_own_model_activation_is_403(client, monkeypatch):
    main, http = client
    monkeypatch.setattr(
        main,
        "review_model_activation_request",
        AsyncMock(return_value={"status": "forbidden", "reason": "separation_of_duties_violation"}),
    )
    result = http.post(
        "/v1/learning/activation-requests/activate_1/review",
        headers=_headers(**{"X-Reviewed-By": "u-req"}),
        json={
            "review_decision": "approved",
            "registry_alias": "prod",
            "previous_artifact_uri": "s3://m/v1",
            "previous_artifact_digest": "b" * 64,
            "idempotency_key": "k",
        },
    )
    assert result.status_code == 403, result.text
