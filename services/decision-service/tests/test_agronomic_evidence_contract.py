"""AC-6 evidence/lineage HTTP contract (pure logic — no DB; mirror-mode fail-closed)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("decision_ac6_main", ROOT / "main.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
client = TestClient(mod.app)
TENANT = {"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"}


def test_strict_decision_rejects_missing_lineage(monkeypatch):
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "true")
    monkeypatch.delenv("DECISION_SERVICE_SOR_ENABLED", raising=False)
    r = client.post("/v1/decisions/record", headers=TENANT, json={"field_id": "f1"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "agronomic_context_required"
    # the FULL lineage is demanded: identity + context triple + vegetation evidence + hash.
    for key in (
        "season_id",
        "crop_id",
        "cultivar_id",
        "agronomic_context_snapshot_id",
        "field_historical_context_snapshot_id",
        "feature_manifest_id",
        "feature_manifest_hash",
        "vegetation_snapshot_id",
    ):
        assert key in detail["missing"]


def test_snapshot_hash_contract_rejects_invalid_hash(monkeypatch):
    monkeypatch.delenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", raising=False)
    r = client.post(
        "/v1/evidence/vegetation-snapshots",
        headers=TENANT,
        json={
            "field_id": "f1",
            "snapshot_hash": "bad",
            "acquisition_at": "2026-01-01T00:00:00Z",
            "data_available_at": "2026-01-01T01:00:00Z",
            "quality_gate": {},
            "feature_manifest": {},
            "payload": {},
        },
    )
    assert r.status_code == 422


def test_evidence_writer_fails_closed_in_mirror_mode(monkeypatch):
    monkeypatch.delenv("DECISION_SERVICE_SOR_ENABLED", raising=False)
    monkeypatch.delenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", raising=False)
    r = client.post(
        "/v1/evidence/vegetation-snapshots",
        headers=TENANT,
        json={
            "field_id": "f1",
            "snapshot_hash": "a" * 64,
            "acquisition_at": "2026-01-01T00:00:00Z",
            "data_available_at": "2026-01-01T01:00:00Z",
            "quality_gate": {},
            "feature_manifest": {},
            "payload": {},
        },
    )
    assert r.status_code == 503  # mirror mode: never silently authoritative
