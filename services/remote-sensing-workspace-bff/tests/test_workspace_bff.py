import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location(
    "workspace_bff_main", Path(__file__).parents[1] / "main.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
client = TestClient(mod.app)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def platform_identity(monkeypatch):
    state = {
        "status": 200,
        "body": {"user": {"tenant_id": "t", "permissions": ["recommendation:view"]}},
        "requests": [],
    }

    def handler(request):
        state["requests"].append(request)
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(state["status"], json=state["body"])
        return httpx.Response(503, json={"detail": "controlled unavailable upstream"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(handler),
            **kw,
        ),
    )
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-only-secret")
    return state


def test_health():
    assert client.get("/healthz").status_code == 200


def test_unknown_section_fails_before_upstream_calls():
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "unknown"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 422


def test_ground_section_is_honest_when_task_service_missing(monkeypatch):
    monkeypatch.setattr(mod, "TASK_URL", "")
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "ground"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 200
    assert response.json()["sections"]["ground"]["configured"] is False


def test_outcomes_is_legal_workspace_section():
    assert "outcomes" in mod._ALLOWED


def test_readyz_reports_optional_task_service():
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["task_service_configured"] is False


def test_overview_counts_use_real_upstream_keys(monkeypatch):
    """Pin the upstream contracts: indicators returns ``entries`` (not ``items``)
    and /v1/outcomes/reconciled returns ``outcome_reconciliation``. A regression to
    the wrong keys silently renders fabricated zeros for real data."""

    async def fake_get(client, url, headers, params=None):
        if "observation-timeline" in url:
            return {"entries": [{"d": 1}, {"d": 2}, {"d": 3}], "latest_observation_refs": {"a": 1}}
        if "signal-anomalies" in url:
            return {"anomalies": [{"status": "open"}, {"status": "resolved"}]}
        if url.endswith("/v1/decisions"):
            return {"decisions": [{"id": "d1"}], "count": 1}
        if "outcomes/reconciled" in url:
            return {"outcome_reconciliation": {"sample_count": 0, "status": "stub"}}
        raise AssertionError(f"unexpected upstream {url}")

    monkeypatch.setattr(mod, "_get", fake_get)
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "overview,timeline,outcomes,compare"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 200
    body = response.json()
    overview = body["sections"]["overview"]
    assert overview["observation_count"] == 3  # from ``entries`` — not a fabricated 0
    assert overview["open_anomaly_count"] == 1
    assert overview["decision_count"] == 1
    # No invented verified-outcome figure while the upstream is a stub: the key is
    # present (the UI contract) but null. An explicit "stub" status is not
    # availability — a non-empty dict of zeros used to read as available=True.
    assert overview["verified_outcome_count"] is None
    assert overview["outcome_reconciliation_status"] == "stub"
    assert overview["outcome_reconciliation_available"] is False
    assert overview["decision_scope"] == "field"
    assert body["sections"]["outcomes"] == {
        "outcome_reconciliation": {"sample_count": 0, "status": "stub"}
    }
    assert len(body["sections"]["compare"]["items"]) == 2
    assert body["partial"] is False


def test_malformed_identifiers_rejected():
    # season_id with URL metacharacters must fail the identifier regex (400),
    # never reach an upstream URL.
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1?x=1#frag"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_season_id"
    # and a whitespace-bearing field segment likewise
    response = client.get(
        "/v1/fields/fld a/remote-sensing-workspace",
        params={"season_id": "s1"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("status", [401, 403, 503])
def test_identity_failure_blocks_before_domain_calls(platform_identity, status):
    platform_identity["status"] = status
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "decisions"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == status
    assert len(platform_identity["requests"]) == 1


@pytest.mark.parametrize(
    "user",
    [
        {"tenant_id": "different-tenant", "permissions": ["recommendation:view"]},
        {"tenant_id": "t", "permissions": []},
    ],
)
def test_tenant_spoof_and_unprivileged_role_are_rejected(platform_identity, user):
    platform_identity["body"] = {"user": user}
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "decisions"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 403
    assert len(platform_identity["requests"]) == 1


def test_verified_tenant_and_service_credential_only_on_decision_calls(platform_identity):
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "decisions,outcomes,anomalies"},
        headers={"Authorization": "Bearer user-jwt", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 200
    assert response.json()["partial"] is True  # domain transport is deliberately unavailable
    requests = platform_identity["requests"]
    assert len(requests) == 4
    assert requests[0].headers["Authorization"] == "Bearer user-jwt"
    assert "X-Tenant-Id" not in requests[0].headers
    for request in requests[1:]:
        expected = (
            "Bearer decision-only-secret"
            if request.url.host == "sahool-decision-service"
            else "Bearer user-jwt"
        )
        assert request.headers["Authorization"] == expected
        assert request.headers["X-Tenant-Id"] == "t"


def test_missing_production_service_token_never_uses_user_token(platform_identity, monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("DECISION_SERVICE_TOKEN")
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "decisions"},
        headers={"Authorization": "Bearer user-jwt", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 503
    assert len(platform_identity["requests"]) == 1
    assert response.json()["detail"] == "decision_service_auth_unavailable"


def _overview_with_outcomes(monkeypatch, outcomes):
    async def fake_get(client, url, headers, params=None):
        if "observation-timeline" in url:
            return {"entries": []}
        if "signal-anomalies" in url:
            return {"anomalies": []}
        if url.endswith("/v1/decisions"):
            return {"decisions": [{"id": "d1"}, {"id": "d2"}], "count": 2}
        if "outcomes/reconciled" in url:
            return outcomes
        raise AssertionError(f"unexpected upstream {url}")

    monkeypatch.setattr(mod, "_get", fake_get)
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "overview"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 200
    return response.json()["sections"]["overview"]


def test_overview_verified_outcome_count_from_explicit_upstream_count(monkeypatch):
    ov = _overview_with_outcomes(
        monkeypatch,
        {"outcome_reconciliation": {"source": "store", "verified_outcome_count": 4}},
    )
    assert ov["verified_outcome_count"] == 4
    assert ov["outcome_reconciliation_available"] is True
    assert ov["outcome_reconciliation_status"] == "store"
    assert ov["decision_count"] == 2
    assert ov["decision_scope"] == "field"


def test_overview_verified_outcome_count_from_list(monkeypatch):
    ov = _overview_with_outcomes(
        monkeypatch,
        {
            "outcome_reconciliation": {"source": "store"},
            "verified_outcomes": [{"id": 1}, {"id": 2}],
        },
    )
    assert ov["verified_outcome_count"] == 2


def test_overview_real_upstream_store_summary_without_verified_count_is_null(monkeypatch):
    # decision-service store summary: counts exist but none is labelled "verified"
    ov = _overview_with_outcomes(
        monkeypatch,
        {
            "outcome_reconciliation": {
                "enabled": True,
                "sample_count": 5,
                "evaluated_count": 3,
                "source": "store",
            }
        },
    )
    assert ov["verified_outcome_count"] is None
    assert ov["outcome_reconciliation_available"] is True


def test_overview_unavailable_source_and_unlabelled_payload(monkeypatch):
    ov = _overview_with_outcomes(
        monkeypatch,
        {"outcome_reconciliation": {"enabled": True, "sample_count": 0, "source": "unavailable"}},
    )
    assert ov["outcome_reconciliation_available"] is False
    assert ov["verified_outcome_count"] is None
    ov = _overview_with_outcomes(monkeypatch, {"outcome_reconciliation": {"sample_count": 0}})
    assert ov["outcome_reconciliation_available"] is None
    assert ov["outcome_reconciliation_status"] is None


def test_overview_rejects_bool_or_negative_verified_count(monkeypatch):
    for bad in (True, -1, "3"):
        ov = _overview_with_outcomes(
            monkeypatch,
            {"outcome_reconciliation": {"source": "store", "verified_outcome_count": bad}},
        )
        assert ov["verified_outcome_count"] is None
