"""حارس محوّل KoboToolbox (SCOUT-INGEST-01 / B1.4 — مزوّد ثانٍ) + برهان سلبيّ.

يفرض: الهويّة (tenant/provider/server/form) **من السجلّ المُحلَّل لا من المُرسِل** · هويّة النسخة من
``meta/instanceID`` المسطّح ثمّ المتداخل ثمّ ``_uuid``/``_id`` · وقت الإرسال من ``_submission_time`` ·
مفتاح dedup = هويّة الخانة (يتشارك مع ODK: نفس (provider,server,form,instance) ⇒ نفس المفتاح) · لا اختلاق.
منطق صرف — لا قاعدة/شبكة.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared.contracts.ingest.external_submission_v1 import derive_dedup_key
from shared.contracts.ingest.kobo_adapter import build_envelope_from_kobo

pytestmark = pytest.mark.unit

_T = uuid4()
_RX = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)


def _build(raw, **over):
    base = dict(
        raw=raw,
        tenant_id=_T,
        provider="kobo",
        server="kf.kobotoolbox.org",
        form_id="scouting_v1",
        mapping_version="1.0.0",
        normalized_payload={"field_id": "f1"},
        received_at=_RX,
        raw_ref="urn:sahool:raw:1",
    )
    base.update(over)
    return build_envelope_from_kobo(**base)


def test_identity_from_source_not_sender() -> None:
    """المُرسِل يزعم provider/tenant مغايرَين ⇒ يُتجاهَلان؛ المظروف من السجلّ المُحلَّل."""
    env = _build({"meta/instanceID": "uuid:k1", "provider": "evil", "tenant_id": "attacker"})
    assert env.provider == "kobo" and env.tenant_id == _T
    assert env.instance_id == "uuid:k1" and env.trust_status == "untrusted"


def test_instance_id_precedence_flat_nested_uuid_id() -> None:
    assert _build({"meta/instanceID": "uuid:a"}).instance_id == "uuid:a"
    assert _build({"meta": {"instanceID": "uuid:b"}}).instance_id == "uuid:b"
    assert _build({"_uuid": "u-c"}).instance_id == "u-c"
    assert _build({"_id": 42}).instance_id == "42"
    assert _build({}).instance_id == "unknown"


def test_submitted_at_from_submission_time() -> None:
    env = _build({"_submission_time": "2026-07-19T08:00:00Z", "_id": 1})
    assert env.submitted_at == datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    # غياب الوقت ⇒ يسقط لوقت الاستلام (لا اختلاق مستقبليّ).
    assert _build({"_id": 2}).submitted_at == _RX


def test_dedup_key_shared_with_odk_slot_identity() -> None:
    """مفتاح Kobo = هويّة الخانة نفسها (لا يُضمِّن content_hash) — متماثل مع ODK للخانة ذاتها."""
    env = _build({"meta/instanceID": "uuid:k1"})
    assert env.idempotency_key == derive_dedup_key(
        provider="kobo", server="kf.kobotoolbox.org", form_id="scouting_v1", instance_id="uuid:k1"
    )
    # نسخة مختلفة ⇒ مفتاح مختلف؛ جسم مختلف نفس الخانة ⇒ **نفس** المفتاح (يُقارَن content_hash منفصلاً).
    assert env.idempotency_key != _build({"meta/instanceID": "uuid:k2"}).idempotency_key
    assert (
        env.idempotency_key == _build({"meta/instanceID": "uuid:k1", "extra": "x"}).idempotency_key
    )


def test_content_hash_deterministic_key_order_independent() -> None:
    a = _build({"meta/instanceID": "uuid:k1", "a": 1, "b": 2}).content_hash
    b = _build({"b": 2, "meta/instanceID": "uuid:k1", "a": 1}).content_hash
    assert a == b and len(a) == 64
