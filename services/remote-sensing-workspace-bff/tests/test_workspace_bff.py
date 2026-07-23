import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location(
    "workspace_bff_main", Path(__file__).parents[1] / "main.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
client = TestClient(mod.app)


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
    # No invented verified-outcome figure while the upstream is a stub — only an
    # honest availability flag derived from the real payload key.
    assert "verified_outcome_count" not in overview
    assert overview["outcome_reconciliation_available"] is True
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
