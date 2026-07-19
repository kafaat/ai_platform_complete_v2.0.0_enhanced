"""محوّل ODK Central → ExternalSubmissionEnvelopeV1 (SCOUT-INGEST-01 / B1.2b).

دالّة نقيّة قابلة للاختبار (submission in → envelope out) — لا شبكة/قاعدة/FastAPI. المستأجِر و
provider/server/form/mapping_version تأتي **من سجلّ التعيين المُحلَّل** (resolve_ingest_source)
لا من المُرسِل (الهويّة لا تُقبل من المُرسِل). ``content_hash=sha256(الخامّ المُقنَّن)``؛ الخامّ
يُحفَظ كما وصل. طبقة العقد (repo-root) لتبقى قابلة للاستيراد من tests_v9 وruntime المنصّة (shared مُضمَّن).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared.contracts.ingest.external_submission_v1 import (
    ExternalSubmissionEnvelopeV1,
    derive_dedup_key,
)


def canonical_content_hash(raw: dict[str, Any]) -> str:
    """sha256 لتمثيل مُقنَّن (مفاتيح مرتّبة) — ثابت لنفس المحتوى بصرف النظر عن ترتيب المفاتيح."""
    blob = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _instance_id(raw: dict[str, Any]) -> str:
    """معرّف نسخة ODK — من meta/instanceID القياسيّ، وإلّا __id."""
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    for key in ("instanceID", "instanceId"):
        v = meta.get(key) or raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = raw.get("__id")
    return str(v).strip() if v is not None and str(v).strip() else "unknown"


def _submitted_at(raw: dict[str, Any], received_at: datetime) -> datetime:
    """وقت الإرسال من ODK (submissionDate/__system) — وإلّا وقت الاستلام (لا اختلاق مستقبليّ)."""
    sys_meta = raw.get("__system") if isinstance(raw.get("__system"), dict) else {}
    for src in (sys_meta.get("submissionDate"), raw.get("submissionDate"), raw.get("today")):
        if isinstance(src, str) and src.strip():
            try:
                dt = datetime.fromisoformat(src.replace("Z", "+00:00"))
            except ValueError:
                continue
            return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    return received_at


def build_envelope_from_odk(
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
    """يبني المظروف المحايد من إدخال ODK + سياق المصدر المُحلَّل (لا من المُرسِل)."""
    content_hash = canonical_content_hash(raw)
    instance_id = _instance_id(raw)
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
        submitted_at=_submitted_at(raw, received_at),
        received_at=received_at,
        raw_ref=raw_ref,
        mapping_version=mapping_version,
        idempotency_key=key,
        payload=normalized_payload,
    )
