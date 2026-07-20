"""حارس نواة إسقاط الإدخال المقبول (SCOUT-INGEST-01 / B1.3) + برهان سلبيّ.

منطق صرف — لا قاعدة. يفرض: إسقاط idempotent (نفس المفتاح ⇒ نفس observation_id) · field_id مفقود ⇒
dead_letter بلا صفّ يتيم (ProjectionSkip) · لا اختلاق (حقل غائب ⇒ None) · observed_at يسقط للـsubmitted_at.
قاعدة «المقبولة فقط» تُبرهَن حيّاً في مسار claim (test_projection_live) لأنّها خاصّة SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared.contracts.ingest.projection import (
    ExternalFieldObservation,
    ProjectionSkip,
    derive_observation_id,
    project_submission,
)

pytestmark = pytest.mark.unit

_T = str(uuid4())
_KEY = "a" * 64


def test_maps_accepted_payload_to_observation() -> None:
    obs = project_submission(
        tenant_id=_T,
        idempotency_key=_KEY,
        normalized_payload={"field_id": "f1", "observed_property": "pest_pressure", "value": 3},
        submitted_at=datetime(2026, 7, 19, 8, 0, tzinfo=UTC),
    )
    assert isinstance(obs, ExternalFieldObservation)
    assert obs.field_id == "f1" and obs.observed_property == "pest_pressure" and obs.value == 3
    assert obs.source_submission_key == _KEY and obs.tenant_id == _T
    assert obs.observed_at == datetime(2026, 7, 19, 8, 0, tzinfo=UTC)  # fallback = submitted_at


def test_missing_field_id_is_dead_letter_not_orphan() -> None:
    """برهان سلبيّ: payload بلا field_id ⇒ ProjectionSkip (dead_letter)، لا مشاهدة يتيمة."""
    skip = project_submission(tenant_id=_T, idempotency_key=_KEY, normalized_payload={"value": 1})
    assert isinstance(skip, ProjectionSkip) and skip.reason == "no_field_id"


def test_projection_is_idempotent_same_key_same_id() -> None:
    """إعادة تشغيل العامل لا تُضاعف: نفس (tenant, key) ⇒ نفس observation_id ⇒ ON CONFLICT DO NOTHING."""
    a = derive_observation_id(tenant_id=_T, idempotency_key=_KEY)
    b = derive_observation_id(tenant_id=_T, idempotency_key=_KEY)
    assert a == b and a.startswith("obs-") and len(a) == 44
    # تغيّر المفتاح ⇒ معرّف مختلف؛ تغيّر المستأجِر ⇒ معرّف مختلف (لا تصادم عبر المستأجرين).
    assert a != derive_observation_id(tenant_id=_T, idempotency_key="b" * 64)
    assert a != derive_observation_id(tenant_id=str(uuid4()), idempotency_key=_KEY)


def test_no_fabrication_missing_fields_are_none() -> None:
    obs = project_submission(
        tenant_id=_T, idempotency_key=_KEY, normalized_payload={"field_id": "f1"}
    )
    assert isinstance(obs, ExternalFieldObservation)
    assert obs.observed_property is None and obs.value is None and obs.severity is None
    assert obs.lat is None and obs.lng is None and obs.observed_at is None  # لا submitted_at ممرّر


def test_lat_lng_parsed_only_when_numeric() -> None:
    obs = project_submission(
        tenant_id=_T,
        idempotency_key=_KEY,
        normalized_payload={"field_id": "f1", "lat": "15.3", "lng": 44.2, "severity": "high"},
    )
    assert isinstance(obs, ExternalFieldObservation)
    assert obs.lat == 15.3 and obs.lng == 44.2 and obs.severity == "high"
    bad = project_submission(
        tenant_id=_T, idempotency_key=_KEY, normalized_payload={"field_id": "f1", "lat": "north"}
    )
    assert isinstance(bad, ExternalFieldObservation) and bad.lat is None
