"""منطق قرار الإدخال الخارجيّ (SCOUT-INGEST-01 / B1.2b) — نقيّ بحقن منافذ DB.

يجمع resolve_dedup (B1.2a) + التحقّق السباعي (B1.1) في قرار واحد على المظروف (B1.0)، دون
FastAPI/asyncpg مباشرة: المنافذ (``IngestPorts``) تُحقَن كـawaitables. الراوتر يربط المنافذ
بقاعدة المنصّة الحقيقيّة ويُخطّط النتيجة إلى HTTP؛ هذا المنطق يبقى قابلاً للاختبار بلا قاعدة.

القاعدة: بعد نجاح resolve_ingest_source، الفحوص الثلاثة الأولى (tenant/provider/form) مُستوفاة
بنيويّاً؛ يبقى provenance/field-in-tenant/bounds. والـdedup يُحسَم بـresolve_dedup (لا ابتلاع صامت).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from shared.contracts.ingest.dedup_resolution import resolve_dedup
from shared.contracts.ingest.external_submission_v1 import ExternalSubmissionEnvelopeV1
from shared.contracts.ingest.validation import ValidationContext, validate_external_submission


@dataclass(frozen=True)
class IngestPorts:
    """منافذ DB المحقونة (الراوتر يربطها بالقاعدة الحقيقيّة؛ الاختبار يحقن مزيّفات)."""

    fetch_existing_content_hash: Callable[
        [UUID, str], Awaitable[str | None]
    ]  # (tenant, key)→hash|None
    field_resolves_in_tenant: Callable[[UUID, str], Awaitable[bool]]
    values_within_bounds: Callable[[dict[str, Any]], Awaitable[bool]]
    store_row: Callable[[dict[str, Any]], Awaitable[None]]  # يُثبّت صفّاً (idempotent على storage_key)


@dataclass(frozen=True)
class IngestResult:
    outcome: Literal["accepted", "quarantined", "idempotent_replay"]
    submission_id: str
    trust_status: str
    quarantine_reasons: tuple[str, ...]


def _row(
    env: ExternalSubmissionEnvelopeV1,
    raw_payload: dict[str, Any],
    *,
    storage_key: str,
    trust_status: str,
    reasons: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "tenant_id": env.tenant_id,
        "submission_id": env.submission_id,
        "provider": env.provider,
        "server": env.server,
        "form_id": env.form_id,
        "instance_id": env.instance_id,
        "content_hash": env.content_hash,
        "idempotency_key": storage_key,  # مشتقّ للصفّ المتباين
        "submitted_at": env.submitted_at,
        "received_at": env.received_at,
        "raw_ref": env.raw_ref,
        "raw_payload": raw_payload,  # الخامّ كما وصل
        "mapping_version": env.mapping_version,
        "normalized_payload": env.payload,
        "trust_status": trust_status,
        "quarantine_reasons": list(reasons),
    }


async def process_submission(
    envelope: ExternalSubmissionEnvelopeV1,
    raw_payload: dict[str, Any],
    ports: IngestPorts,
) -> IngestResult:
    """يقرّر مصير إدخال مُحلَّل المصدر: idempotent / quarantine-divergent / accepted|quarantined."""
    existing = await ports.fetch_existing_content_hash(envelope.tenant_id, envelope.idempotency_key)
    dec = resolve_dedup(
        base_key=envelope.idempotency_key,
        incoming_content_hash=envelope.content_hash,
        existing_content_hash=existing,
    )

    if dec.action == "idempotent_replay":
        return IngestResult("idempotent_replay", envelope.submission_id, "accepted", ())

    if dec.action == "quarantine_divergent":
        await ports.store_row(
            _row(
                envelope,
                raw_payload,
                storage_key=dec.storage_key,
                trust_status="quarantined",
                reasons=dec.quarantine_reasons,
            )
        )
        return IngestResult(
            "quarantined", envelope.submission_id, "quarantined", dec.quarantine_reasons
        )

    # insert_new ⇒ التحقّق السباعي (الأوّليّة مُستوفاة بالحلّ؛ dedup مُحسَم).
    field_id = envelope.payload.get("field_id") if isinstance(envelope.payload, dict) else None
    resolves = bool(field_id) and await ports.field_resolves_in_tenant(
        envelope.tenant_id, str(field_id)
    )
    bounds = await ports.values_within_bounds(envelope.payload)
    ctx = ValidationContext(
        is_tenant_known=lambda _t: True,
        is_provider_allowed=lambda _p: True,
        is_form_mapping_registered=lambda _p, _f, _v: True,
        field_resolves_in_tenant=lambda _t, _fid: resolves,
        values_within_bounds=lambda _payload: bounds,
        is_duplicate=lambda _key: False,  # مُحسَم بـresolve_dedup (insert_new)
    )
    verdict = validate_external_submission(envelope, ctx)
    trust = "accepted" if verdict.accepted else "quarantined"
    await ports.store_row(
        _row(
            envelope,
            raw_payload,
            storage_key=dec.storage_key,
            trust_status=trust,
            reasons=verdict.quarantine_reasons,
        )
    )
    return IngestResult(
        "accepted" if verdict.accepted else "quarantined",
        envelope.submission_id,
        trust,
        verdict.quarantine_reasons,
    )
