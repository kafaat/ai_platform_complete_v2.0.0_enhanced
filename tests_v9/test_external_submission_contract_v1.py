"""حارس عقد مظروف الإدخال الخارجيّ (SCOUT-INGEST-01 / B1.0) + برهان سلبيّ.

يفرض المبادئ الحاكمة بنيويّاً: **الوصول ≠ الثقة** (يدخل untrusted فقط) · مفتاح dedup
**مشتقّ لا مُصاغ يدويّاً** (مظروف بمفتاح مزوّر يُرفَض) · طوابع زمنيّة aware-UTC ·
لا حقول زائدة · «التحقّق السباعي» مُعلَن بسبعة فحوص فريدة.

فحص عقد صرف — لا قاعدة/خدمات/شبكة.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.contracts.ingest import (
    SEVEN_CHECKS,
    ExternalSubmissionEnvelopeV1,
    derive_dedup_key,
)

pytestmark = pytest.mark.unit

_H = "a" * 64  # sha256 صالح (64 خانة hex)


def _envelope(**overrides):
    provider = overrides.pop("provider", "odk")
    server = overrides.pop("server", "central.example.org")
    form_id = overrides.pop("form_id", "scouting_v1")
    instance_id = overrides.pop("instance_id", "uuid:abc123")
    content_hash = overrides.pop("content_hash", _H)
    key = overrides.pop(
        "idempotency_key",
        derive_dedup_key(
            provider=provider, server=server, form_id=form_id, instance_id=instance_id
        ),
    )
    base = dict(
        submission_id="sub-1",
        provider=provider,
        server=server,
        form_id=form_id,
        instance_id=instance_id,
        content_hash=content_hash,
        tenant_id=uuid4(),
        submitted_at=datetime(2026, 7, 19, 8, 0, tzinfo=UTC),
        received_at=datetime(2026, 7, 19, 8, 5, tzinfo=UTC),
        raw_ref="urn:sahool:raw:sub-1",
        mapping_version="1.0.0",
        idempotency_key=key,
        payload={"field_id": "f1", "observed_property": "pest_pressure", "value": 3},
    )
    base.update(overrides)
    return ExternalSubmissionEnvelopeV1(**base)


def test_valid_envelope_defaults_to_untrusted() -> None:
    """الوصول ≠ الثقة: كلّ إدخال يدخل untrusted."""
    env = _envelope()
    assert env.trust_status == "untrusted"
    assert env.contract_version == "external-submission.v1"


def test_dedup_key_is_slot_identity_deterministic_hex64() -> None:
    """المفتاح = هويّة الخانة (provider|server|form|instance) — لا يُضمِّن content_hash عمداً."""
    a = derive_dedup_key(provider="odk", server="s", form_id="f", instance_id="i")
    b = derive_dedup_key(provider="odk", server="s", form_id="f", instance_id="i")
    assert a == b and len(a) == 64 and all(c in "0123456789abcdef" for c in a)
    # تغيّر النسخة يغيّر المفتاح؛ لكن تغيّر الجسم (content_hash) لا يغيّره (يُقارَن منفصلاً):
    assert a != derive_dedup_key(provider="odk", server="s", form_id="f", instance_id="i2")


def test_forged_dedup_key_is_rejected() -> None:
    """برهان سلبيّ: مفتاح لا يطابق المشتقّ من المكوّنات ⇒ رفض بنيويّ."""
    with pytest.raises(ValidationError):
        _envelope(idempotency_key="b" * 64)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _envelope(submitted_at=datetime(2026, 7, 19, 8, 0))  # noqa: DTZ001 - مقصود للاختبار


def test_aware_timestamp_is_accepted() -> None:
    """طابع aware مقبول (والساذج مرفوض — أعلاه)."""
    env = _envelope(received_at=datetime(2026, 7, 19, 8, 5, tzinfo=UTC))
    assert env.received_at.utcoffset() is not None


def test_extra_field_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        _envelope(unexpected="x")


def test_trust_status_cannot_be_trusted() -> None:
    """لا يمكن بناء مظروف موثوق عند العقد — الثقة تُكتسَب بالتحقّق (B1.1) لا بالإعلان."""
    with pytest.raises(ValidationError):
        _envelope(trust_status="trusted")


def test_seven_checks_declares_exactly_seven_unique_checks() -> None:
    assert len(SEVEN_CHECKS) == 7
    ids = [c.check_id for c in SEVEN_CHECKS]
    assert len(set(ids)) == 7, "فحوص التحقّق السباعي يجب أن تكون فريدة"
    assert all(c.description_ar.strip() for c in SEVEN_CHECKS)
    assert "not_duplicate" in ids and "provenance_complete" in ids
