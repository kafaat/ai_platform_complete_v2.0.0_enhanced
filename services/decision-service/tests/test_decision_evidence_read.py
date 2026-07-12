"""Phase E: authoritative read of one decision's full agronomic evidence chain.

Proofs on real Postgres: a governed decision returns its composed context, historical
window, PIT-stamped feature manifest (with the decision-pinned hash cross-check), and
linked vegetation snapshot; a legacy_unbound decision returns honest nulls; an unknown
decision is 404; mirror mode is a fail-closed 503 (never a fake "no evidence").
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")

TENANT = "00000000-0000-0000-0000-000000009191"


def _run(c):
    return asyncio.run(c)


def _now():
    return datetime.now(UTC).replace(microsecond=0)


def _compose(field_id: str):
    from agronomic_context.contracts import ContextComposeIn, FeatureEntryIn, HistoricalContextIn
    from persistence import compose_agronomic_context

    now = _now()
    payload = ContextComposeIn(
        field_id=field_id,
        season_id="s2026",
        as_of_time=now,
        decision_cutoff_time=now,
        context={
            "crop": {"crop_id": "wheat", "cultivar_id": "yecora", "crop_card_version": "v3"},
            "soil": {"ph": 7.1},
            "irrigation": {"type": "drip"},
            "weather": {"et0_mm": 5.2},
            "climate": {"drought_index": 0.2},
            "terrain": {"slope_pct": 2.0},
            "operations": {},
        },
        historical=HistoricalContextIn(
            history_from=now - timedelta(days=30),
            history_to=now - timedelta(hours=1),
            history={"ndvi_trend_14d": -0.03},
        ),
        features=[
            FeatureEntryIn(
                name="ndvi_mean",
                value=0.61,
                unit="index",
                source_service="raster-service",
                observed_at=now - timedelta(days=2),
                available_at=now - timedelta(hours=6),
                quality_status="verified",
            )
        ],
        idempotency_key="ev_" + uuid4().hex,
    )
    result = _run(
        compose_agronomic_context(tenant_id=TENANT, created_by="certifier", payload=payload)
    )
    assert result["status"] == "ok", result
    return result


def _record_decision(field_id: str, composed: dict) -> str:
    from persistence import persist_decision_record

    decision_id = "dec_ev_" + uuid4().hex[:12]
    payload = SimpleNamespace(
        field_id=field_id,
        decision_type="recommendation",
        region=None,
        stage="decision",
        decision_value={"recommendation": "irrigate", "amount_mm": 12},
        confidence=0.9,
        created_by="certifier",
        season_id="s2026",
        crop_id="wheat",
        cultivar_id="yecora",
        agronomic_context_snapshot_id=composed["snapshot_id"],
        field_historical_context_snapshot_id=composed["historical_snapshot_id"],
        feature_manifest_id=composed["feature_manifest_id"],
    )
    result = _run(
        persist_decision_record(tenant_id=TENANT, payload=payload, decision_id=decision_id)
    )
    assert result.get("decision_id") == decision_id, result
    return decision_id


def test_evidence_chain_read_is_complete_and_pit_stamped():
    from persistence import get_decision_agronomic_evidence

    field = "f_ev_" + uuid4().hex[:6]
    composed = _compose(field)
    decision_id = _record_decision(field, composed)

    ev = _run(get_decision_agronomic_evidence(tenant_id=TENANT, decision_id=decision_id))
    assert ev["status"] == "ok" and ev["authoritative"] is True and ev["read_only"] is True
    assert ev["decision"]["decision_id"] == decision_id
    assert ev["decision"]["crop_id"] == "wheat"

    ctx = ev["context_snapshot"]
    assert ctx and ctx["snapshot_id"] == composed["snapshot_id"]
    assert set(ctx["context"]) >= {"crop", "soil", "weather"}
    assert ctx["content_hash"] == composed["content_hash"]

    hist = ev["historical_snapshot"]
    assert hist and hist["history"]["ndvi_trend_14d"] == -0.03

    manifest = ev["feature_manifest"]
    assert manifest and manifest["feature_manifest_id"] == composed["feature_manifest_id"]
    assert manifest["hash_matches_decision"] is True
    entries = manifest["entries"]
    assert len(entries) == 1 and entries[0]["name"] == "ndvi_mean"
    # PIT stamps must be present and consistent: available_at ≤ cutoff for accepted features.
    assert entries[0]["available_at"] <= manifest["decision_cutoff_time"]

    assert ev["evidence_complete"] is True


def test_legacy_unbound_decision_returns_honest_nulls():
    from persistence import get_decision_agronomic_evidence, persist_decision_record

    decision_id = "dec_legacy_" + uuid4().hex[:12]
    payload = SimpleNamespace(
        field_id="f_legacy_" + uuid4().hex[:6],
        decision_type="recommendation",
        region=None,
        stage="decision",
        decision_value={"recommendation": "scout"},
        confidence=None,
        created_by="certifier",
    )
    result = _run(
        persist_decision_record(tenant_id=TENANT, payload=payload, decision_id=decision_id)
    )
    assert result.get("decision_id") == decision_id, result

    ev = _run(get_decision_agronomic_evidence(tenant_id=TENANT, decision_id=decision_id))
    assert ev["status"] == "ok"
    assert ev["context_snapshot"] is None
    assert ev["historical_snapshot"] is None
    assert ev["feature_manifest"] is None
    assert ev["vegetation_snapshot"] is None
    assert ev["evidence_complete"] is False


def test_unknown_decision_is_not_found():
    from persistence import get_decision_agronomic_evidence

    ev = _run(
        get_decision_agronomic_evidence(tenant_id=TENANT, decision_id="dec_missing_" + uuid4().hex)
    )
    assert ev == {"status": "not_found"}


def test_http_contract_ok_404_and_mirror_503(monkeypatch):
    import importlib.util

    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("decision_ev_main", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    client = TestClient(mod.app)

    field = "f_ev_http_" + uuid4().hex[:6]
    composed = _compose(field)
    decision_id = _record_decision(field, composed)

    ok = client.get(
        f"/v1/decisions/{decision_id}/agronomic-evidence", headers={"X-Tenant-Id": TENANT}
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["decision_id"] == decision_id and body["evidence_complete"] is True

    missing = client.get(
        "/v1/decisions/dec_missing/agronomic-evidence", headers={"X-Tenant-Id": TENANT}
    )
    assert missing.status_code == 404

    # mirror mode: evidence cannot be proven → fail-closed 503, never an empty payload.
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "false")
    mirror = client.get(
        f"/v1/decisions/{decision_id}/agronomic-evidence", headers={"X-Tenant-Id": TENANT}
    )
    assert mirror.status_code == 503
