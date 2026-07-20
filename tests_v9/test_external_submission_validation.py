"""حارس التحقّق السباعي للإدخال الخارجيّ (SCOUT-INGEST-01 / B1.1) + برهان سلبيّ.

يفرض القاعدة الحاكمة: **لا قبول قبل اجتياز الفحوص السبعة كاملةً**. كلّ فحص فاشل يُبلَّغ
كسبب quarantine مُصنَّف؛ اجتياز 6/7 لا يكفي. أسماء/ترتيب الفحوص من ``SEVEN_CHECKS`` حصراً.

منطق صرف بحقن سياق — لا قاعدة/خدمات.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared.contracts.ingest import (
    SEVEN_CHECKS,
    ExternalSubmissionEnvelopeV1,
    derive_dedup_key,
)
from shared.contracts.ingest.validation import (
    ValidationContext,
    validate_external_submission,
)

pytestmark = pytest.mark.unit

_H = "c" * 64
_TENANT = uuid4()


def _env(**overrides) -> ExternalSubmissionEnvelopeV1:
    provider = overrides.pop("provider", "odk")
    server = overrides.pop("server", "central.example.org")
    form_id = overrides.pop("form_id", "scouting_v1")
    instance_id = overrides.pop("instance_id", "uuid:xyz")
    content_hash = overrides.pop("content_hash", _H)
    key = derive_dedup_key(
        provider=provider, server=server, form_id=form_id, instance_id=instance_id
    )
    base = dict(
        submission_id="sub-1",
        provider=provider,
        server=server,
        form_id=form_id,
        instance_id=instance_id,
        content_hash=content_hash,
        tenant_id=_TENANT,
        submitted_at=datetime(2026, 7, 19, 8, 0, tzinfo=UTC),
        received_at=datetime(2026, 7, 19, 8, 5, tzinfo=UTC),
        raw_ref="urn:sahool:raw:sub-1",
        mapping_version="1.0.0",
        idempotency_key=key,
        payload={"field_id": "f1", "observed_property": "pest_pressure", "value": 3},
    )
    base.update(overrides)
    return ExternalSubmissionEnvelopeV1(**base)


def _ctx(**overrides) -> ValidationContext:
    defaults = dict(
        is_tenant_known=lambda t: t == _TENANT,
        is_provider_allowed=lambda p: p in {"odk", "kobo"},
        is_form_mapping_registered=lambda p, f, v: (p, f, v) == ("odk", "scouting_v1", "1.0.0"),
        field_resolves_in_tenant=lambda t, fid: t == _TENANT and fid == "f1",
        values_within_bounds=lambda payload: True,
        is_duplicate=lambda key: False,
    )
    defaults.update(overrides)
    return ValidationContext(**defaults)


def test_all_seven_pass_accepts() -> None:
    v = validate_external_submission(_env(), _ctx())
    assert v.accepted is True
    assert v.quarantine_reasons == ()
    assert [c.check_id for c in v.checks] == [c.check_id for c in SEVEN_CHECKS]
    assert all(c.passed for c in v.checks)


@pytest.mark.parametrize(
    ("ctx_override", "expected_reason"),
    [
        ({"is_tenant_known": lambda t: False}, "tenant_known"),
        ({"is_provider_allowed": lambda p: False}, "provider_allowlisted"),
        ({"is_form_mapping_registered": lambda p, f, v: False}, "form_mapping_registered"),
        ({"field_resolves_in_tenant": lambda t, fid: False}, "field_resolves_in_tenant"),
        ({"values_within_bounds": lambda payload: False}, "values_within_domain_bounds"),
        ({"is_duplicate": lambda key: True}, "not_duplicate"),
    ],
)
def test_each_failing_check_quarantines(ctx_override, expected_reason) -> None:
    v = validate_external_submission(_env(), _ctx(**ctx_override))
    assert v.accepted is False
    assert expected_reason in v.quarantine_reasons


def test_missing_field_id_fails_provenance_and_resolution() -> None:
    """payload بلا field_id ⇒ provenance_complete و field_resolves_in_tenant يفشلان."""
    v = validate_external_submission(_env(payload={"value": 1}), _ctx())
    assert v.accepted is False
    assert "provenance_complete" in v.quarantine_reasons
    assert "field_resolves_in_tenant" in v.quarantine_reasons


def test_six_of_seven_is_still_rejected() -> None:
    """برهان "لا قبول قبل السبعة": فحص واحد فاشل ⇒ رفض رغم نجاح الستّة."""
    v = validate_external_submission(_env(), _ctx(is_duplicate=lambda key: True))
    passed = sum(1 for c in v.checks if c.passed)
    assert passed == 6 and v.accepted is False


def test_duplicate_key_is_the_dedup_gate() -> None:
    """برهان سلبيّ: نفس المفتاح مرصود سابقاً ⇒ not_duplicate يحجب."""
    seen = {_env().idempotency_key}
    v = validate_external_submission(_env(), _ctx(is_duplicate=lambda key: key in seen))
    assert v.accepted is False and "not_duplicate" in v.quarantine_reasons
