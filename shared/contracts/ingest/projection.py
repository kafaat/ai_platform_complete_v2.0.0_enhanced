"""نواة إسقاط الإدخال الخارجيّ المقبول إلى مشاهدة ميدانيّة (SCOUT-INGEST-01 / B1.3).

دالّة نقيّة (صفّ إدخال مقبول → مشاهدة أو تخطٍّ مُصنَّف) — لا شبكة/قاعدة/FastAPI. تستهلكها عامل
scout-ingest (منافذ DB حقيقيّة) وtests_v9 (بلا قاعدة). **القاعدة الحاكمة تُفرَض في مسار الاستدعاء:
المقبولة فقط تُسقَط** (دالّة claim تُصفّي على trust_status='accepted')؛ وهنا نُصنّف تخطّي المحتوى
(field_id مفقود ⇒ dead_letter بسبب، لا صفّ يتيم).

**idempotency:** ``observation_id`` مشتقّ حتميّاً من (tenant, idempotency_key) ⇒ إعادة تشغيل العامل
تُنتج نفس المعرّف ⇒ ``INSERT … ON CONFLICT DO NOTHING`` لا يُضاعف. لا اختلاق: أيّ حقل غائب يبقى None.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_SEP = "\x1f"


@dataclass(frozen=True)
class ExternalFieldObservation:
    """صفّ نموذج القراءة المملوك لـscout-ingest (يطابق external_field_observations حقلاً بحقل)."""

    observation_id: str
    tenant_id: str
    field_id: str
    source_submission_key: str
    observed_property: str | None
    value: Any | None
    severity: str | None
    lat: float | None
    lng: float | None
    observed_at: datetime | None


@dataclass(frozen=True)
class ProjectionSkip:
    """تخطٍّ مُصنَّف (⇒ dead_letter): لا مشاهدة تُبنى، والسبب يُسجَّل على صفّ الإدخال."""

    reason: str


# Slice 3 (§استبعاد الإسقاط): علامة نوع تُزرع خادميًّا في normalized_payload للنماذج
# الميدانيّة الديناميكية — إسقاطها إلى external_field_observations يُنتج صفوف NULL كلّها
# (لا observed_property/value واحد)، فتُصنّف dead_letter بدل تلويث نموذج القراءة.
FIELD_FORM_KIND = "field_form"


def derive_observation_id(*, tenant_id: str, idempotency_key: str) -> str:
    """معرّف مشاهدة حتميّ من هويّة الخانة ⇒ إسقاط idempotent (نفس المفتاح ⇒ نفس المعرّف)."""
    raw = _SEP.join((str(tenant_id), idempotency_key))
    return "obs-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _num(v: Any) -> float | None:
    """رقم عائم إن أمكن، وإلّا None (لا اختلاق)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _observed_at(payload: dict[str, Any], fallback: datetime | None) -> datetime | None:
    src = payload.get("observed_at")
    if isinstance(src, str) and src.strip():
        try:
            dt = datetime.fromisoformat(src.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    if isinstance(src, datetime):
        return src.astimezone(UTC) if src.tzinfo else src.replace(tzinfo=UTC)
    return fallback


def project_submission(
    *,
    tenant_id: str,
    idempotency_key: str,
    normalized_payload: dict[str, Any],
    submitted_at: datetime | None = None,
) -> ExternalFieldObservation | ProjectionSkip:
    """يُسقِط إدخالاً مقبولاً إلى مشاهدة، أو يُصنّف التخطّي (field_id مفقود ⇒ dead_letter)."""
    payload = normalized_payload if isinstance(normalized_payload, dict) else {}
    # Slice 3: النماذج الميدانيّة الديناميكية ليست مشاهدة نقطيّة — تُستبعَد من الإسقاط
    # (dead_letter مُصنَّف) بدل بناء صفّ مشاهدة كلّه NULL.
    if payload.get("kind") == FIELD_FORM_KIND:
        return ProjectionSkip(reason="field_forms_not_projectable")
    field_id = payload.get("field_id")
    if not isinstance(field_id, str) or not field_id.strip():
        return ProjectionSkip(reason="no_field_id")
    return ExternalFieldObservation(
        observation_id=derive_observation_id(tenant_id=tenant_id, idempotency_key=idempotency_key),
        tenant_id=str(tenant_id),
        field_id=field_id.strip(),
        source_submission_key=idempotency_key,
        observed_property=(payload.get("observed_property") or None),
        value=payload.get("value"),
        severity=(payload.get("severity") or None),
        lat=_num(payload.get("lat")),
        lng=_num(payload.get("lng")),
        observed_at=_observed_at(payload, submitted_at),
    )
