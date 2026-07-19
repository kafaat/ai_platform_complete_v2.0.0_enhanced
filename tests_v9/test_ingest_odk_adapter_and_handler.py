"""حارس محوّل ODK + منطق قرار الإدخال (SCOUT-INGEST-01 / B1.2b) — نقيّ، بلا قاعدة.

المحوّل: الهويّة من سياق المصدر لا من المُرسِل · content_hash مُقنَّن. الحارس: idempotent
(نفس الجسم) · quarantine-divergent (نفس مفتاح جسم مختلف، لا ابتلاع) · accepted (يجتاز السبعة) ·
quarantined (فشل فحص). منافذ DB مزيّفة (لا قاعدة).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared.contracts.ingest.dedup_resolution import DIVERGENT_PAYLOAD_REASON
from shared.contracts.ingest.ingest_handler import IngestPorts, process_submission
from shared.contracts.ingest.odk_adapter import build_envelope_from_odk, canonical_content_hash

pytestmark = pytest.mark.unit

_TENANT = uuid4()


def _envelope(raw=None, payload=None):
    raw = raw if raw is not None else {"meta": {"instanceID": "uuid:abc"}, "pest": 3}
    payload = payload if payload is not None else {"field_id": "f1", "value": 3}
    return build_envelope_from_odk(
        raw=raw,
        tenant_id=_TENANT,
        provider="odk",
        server="central.example.org",
        form_id="scouting_v1",
        mapping_version="1.0.0",
        normalized_payload=payload,
        received_at=datetime(2026, 7, 19, 9, 0, tzinfo=UTC),
        raw_ref="urn:sahool:ingest:abc",
    )


# ── المحوّل ──────────────────────────────────────────────────────
def test_adapter_identity_comes_from_source_not_sender() -> None:
    env = _envelope()
    assert env.provider == "odk" and env.server == "central.example.org"
    assert env.tenant_id == _TENANT  # من السجلّ المُحلَّل
    assert env.instance_id == "uuid:abc"  # من meta.instanceID
    assert env.trust_status == "untrusted"


def test_adapter_content_hash_is_canonical_key_order_independent() -> None:
    assert canonical_content_hash({"a": 1, "b": 2}) == canonical_content_hash({"b": 2, "a": 1})


# ── منافذ مزيّفة ─────────────────────────────────────────────────
class _Ports:
    def __init__(self, existing=None, field_ok=True, bounds_ok=True):
        self._existing = existing
        self._field_ok = field_ok
        self._bounds_ok = bounds_ok
        self.stored: list[dict] = []

    def as_ports(self) -> IngestPorts:
        return IngestPorts(
            fetch_existing_content_hash=self._fetch,
            field_resolves_in_tenant=self._field,
            values_within_bounds=self._bounds,
            store_row=self._store,
        )

    async def _fetch(self, _t, _k):
        return self._existing

    async def _field(self, _t, _fid):
        return self._field_ok

    async def _bounds(self, _p):
        return self._bounds_ok

    async def _store(self, row):
        self.stored.append(row)


async def test_new_valid_submission_is_accepted_and_stored() -> None:
    env = _envelope()
    ports = _Ports(existing=None)
    res = await process_submission(env, {"pest": 3}, ports.as_ports())
    assert res.outcome == "accepted" and res.trust_status == "accepted"
    assert len(ports.stored) == 1 and ports.stored[0]["trust_status"] == "accepted"


async def test_same_key_same_body_is_idempotent_replay_no_store() -> None:
    env = _envelope()
    ports = _Ports(existing=env.content_hash)  # نفس الجسم موجود
    res = await process_submission(env, {"pest": 3}, ports.as_ports())
    assert res.outcome == "idempotent_replay"
    assert ports.stored == []  # لا تخزين مكرّر


async def test_same_key_divergent_body_quarantines_under_derived_key() -> None:
    env = _envelope()
    ports = _Ports(existing="d" * 64)  # جسم مختلف موجود لنفس المفتاح
    res = await process_submission(env, {"pest": 3}, ports.as_ports())
    assert res.outcome == "quarantined"
    assert res.quarantine_reasons == (DIVERGENT_PAYLOAD_REASON,)
    assert ports.stored[0]["idempotency_key"] != env.idempotency_key  # مفتاح مشتقّ
    assert ports.stored[0]["idempotency_key"].startswith(env.idempotency_key + "#dup-")


async def test_field_not_in_tenant_quarantines() -> None:
    env = _envelope()
    ports = _Ports(existing=None, field_ok=False)  # الحقل لا يُحلّ داخل المستأجِر
    res = await process_submission(env, {"pest": 3}, ports.as_ports())
    assert res.outcome == "quarantined"
    assert "field_resolves_in_tenant" in res.quarantine_reasons


async def test_missing_field_id_quarantines_on_provenance() -> None:
    env = _envelope(payload={"value": 3})  # بلا field_id
    ports = _Ports(existing=None)
    res = await process_submission(env, {"pest": 3}, ports.as_ports())
    assert res.outcome == "quarantined"
    assert "provenance_complete" in res.quarantine_reasons
