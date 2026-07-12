"""AC-6 producer contract: vegetation pushes immutable snapshots to decision-service.

Pure logic — a capturing transport stands in for decision-service; the contract
(URL, tenant header, content-addressed body) is asserted exactly, plus the
fail-soft behavior when the store is unreachable or the tenant is not a UUID.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vegetation_runtime as vr

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-1111-1111-111111111111"


def _snapshot():
    return {
        "field_id": "f1",
        "season_id": "s2026",
        "contract_version": "vegetation-snapshot.v2",
        "snapshot_hash": "a" * 64,
        "acquisition_date": "2026-07-01",
        "data_available_at": "2026-07-01T01:00:00Z",
        "quality_gate": {"executable": True},
        "feature_manifest": {"id": "vegetation-core", "version": "indicator-registry.v1"},
        "indices": {"ndvi": {"value": 0.6}},
        "source": "raster-service",
    }


class _CapturingClient:
    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _CapturingClient.captured = {"url": url, "json": json, "headers": headers}

        class _R:
            status_code = 200

            @staticmethod
            def json():
                return {"persisted": True, "snapshot_id": "veg_x", "created": True}

        return _R()


def test_push_contract_url_tenant_and_content_addressed_body(monkeypatch):
    monkeypatch.setattr(vr.httpx, "AsyncClient", _CapturingClient)
    out = asyncio.run(vr._push_vegetation_evidence(_snapshot(), TENANT))
    assert out == {"pushed": True, "snapshot_id": "veg_x", "created": True}
    cap = _CapturingClient.captured
    assert cap["url"].endswith("/v1/evidence/vegetation-snapshots")
    assert cap["headers"]["X-Tenant-Id"] == TENANT
    body = cap["json"]
    assert body["snapshot_hash"] == "a" * 64  # the hash IS the idempotency key
    assert body["acquisition_at"] == "2026-07-01T00:00:00Z"
    assert body["data_available_at"] == "2026-07-01T01:00:00Z"
    assert body["quality_gate"] == {"executable": True}
    assert body["payload"]["indices"]["ndvi"]["value"] == 0.6


def test_non_uuid_tenant_is_honestly_skipped(monkeypatch):
    monkeypatch.setattr(vr.httpx, "AsyncClient", _CapturingClient)
    out = asyncio.run(vr._push_vegetation_evidence(_snapshot(), "default"))
    assert out == {"pushed": False, "reason": "tenant_not_uuid"}


def test_unreachable_store_is_fail_soft(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise ConnectionError("down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(vr.httpx, "AsyncClient", _Boom)
    out = asyncio.run(vr._push_vegetation_evidence(_snapshot(), TENANT))
    assert out["pushed"] is False and out["reason"].startswith("unreachable:")


def test_mirror_mode_503_is_reported_not_hidden(monkeypatch):
    class _Mirror(_CapturingClient):
        async def post(self, url, json=None, headers=None):
            class _R:
                status_code = 503

            return _R()

    monkeypatch.setattr(vr.httpx, "AsyncClient", _Mirror)
    out = asyncio.run(vr._push_vegetation_evidence(_snapshot(), TENANT))
    assert out == {"pushed": False, "reason": "http_503"}


def test_push_is_opt_in_and_off_by_default():
    assert os.getenv("VEGETATION_EVIDENCE_PUSH_ENABLED") is None
    assert vr.VEGETATION_EVIDENCE_PUSH_ENABLED is False
