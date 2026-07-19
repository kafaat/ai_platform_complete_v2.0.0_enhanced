"""محوّل KoboToolbox → ExternalSubmissionEnvelopeV1 (SCOUT-INGEST-01 / B1.4 — مزوّد ثانٍ).

Kobo مبنيّ على ODK (XForms) فيتشارك المظروف المحايد ومفتاح dedup نفسه؛ يختلف فقط في **استخلاص
هويّة النسخة ووقت الإرسال** من حمولة Kobo `/data`: النسخة من ``meta/instanceID`` المسطّح (أو
``meta.instanceID`` المتداخل، أو ``_uuid``/``_id``)، والوقت من ``_submission_time``. الهويّة
(tenant/provider/server/form) تأتي **من السجلّ المُحلَّل لا من المُرسِل** — كنمط ODK تماماً. لا اختلاق:
ما غاب يبقى غائباً. يُعيد استخدام ``canonical_content_hash``/``derive_dedup_key`` (لا تكرار منطق).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared.contracts.ingest.external_submission_v1 import (
    ExternalSubmissionEnvelopeV1,
    derive_dedup_key,
)
from shared.contracts.ingest.odk_adapter import canonical_content_hash


def _kobo_instance_id(raw: dict[str, Any]) -> str:
    """هويّة نسخة Kobo — meta/instanceID المسطّح، ثمّ meta.instanceID المتداخل، ثمّ _uuid/_id."""
    for key in ("meta/instanceID", "meta/instanceId"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    for key in ("instanceID", "instanceId"):
        v = meta.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for key in ("_uuid", "_id"):
        v = raw.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return "unknown"


def _kobo_submitted_at(raw: dict[str, Any], received_at: datetime) -> datetime:
    """وقت إرسال Kobo (_submission_time) — وإلّا وقت الاستلام (لا اختلاق مستقبليّ)."""
    for src in (raw.get("_submission_time"), raw.get("submissionDate"), raw.get("today")):
        if isinstance(src, str) and src.strip():
            try:
                dt = datetime.fromisoformat(src.replace("Z", "+00:00"))
            except ValueError:
                continue
            return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    return received_at


def build_envelope_from_kobo(
    *,
    raw: dict[str, Any],
    tenant_id: UUID,
    provider: str,
    server: str,
    form_id: str,
    mapping_version: str,
    normalized_payload: dict[str, Any],
    received_at: datetime,
    raw_ref: str,
) -> ExternalSubmissionEnvelopeV1:
    """يبني المظروف المحايد من إدخال Kobo + سياق المصدر المُحلَّل (لا من المُرسِل)."""
    content_hash = canonical_content_hash(raw)
    instance_id = _kobo_instance_id(raw)
    key = derive_dedup_key(
        provider=provider, server=server, form_id=form_id, instance_id=instance_id
    )
    return ExternalSubmissionEnvelopeV1(
        submission_id=instance_id,
        provider=provider,
        server=server,
        form_id=form_id,
        instance_id=instance_id,
        content_hash=content_hash,
        tenant_id=tenant_id,
        submitted_at=_kobo_submitted_at(raw, received_at),
        received_at=received_at,
        raw_ref=raw_ref,
        mapping_version=mapping_version,
        idempotency_key=key,
        payload=normalized_payload,
    )
