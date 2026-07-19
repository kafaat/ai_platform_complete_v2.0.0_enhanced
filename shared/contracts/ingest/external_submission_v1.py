"""مظروف الإدخال الميدانيّ الخارجيّ المحايد (SCOUT-INGEST-01 / B1.0).

عقد محايد يستقبل إدخالاً ميدانيّاً خارجيّاً (ODK/Kobo/CSV/GeoJSON) خلف مظروف موحّد
**قبل** أيّ إسقاط domain. المبدأ الحاكم: **الوصول ≠ الثقة** — كلّ إدخال يدخل
``trust_status="untrusted"``، يُحفظ خامّاً (``raw_ref``)، ولا يبلغ القرار قبل اجتياز
«التحقّق السباعي» (``SEVEN_CHECKS``؛ يُفرَض في B1.1). مفتاح إزالة التكرار مشتقّ
**بنيويّاً** من (provider+server+form+instance+content_hash) — لا يُصاغ يدويّاً.

يحاذي هذا العنقود «Weather/Soil observation» في ADR-0034 (``sosa:Observation``) —
أقوى نقطة محاذاة مع OCSM. وحدة عقد صرفة (لا FastAPI/قاعدة/شبكة). التخزين/المدخل/العامل
شرائح تالية (B1.1+).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

INGEST_CONTRACT_VERSION = "external-submission.v1"

# أنواع مقيَّدة (طبقة العقد؛ التحقّق السلوكيّ الكامل في B1.1).
_Provider = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{1,31}$")]
_Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
_NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]

_SEP = "\x1f"  # فاصل وحدة لا يظهر في المعرّفات ⇒ مفتاح dedup غير قابل للالتباس


def derive_dedup_key(*, provider: str, server: str, form_id: str, instance_id: str) -> str:
    """مفتاح إزالة تكرار = **هويّة الخانة**: ``sha256(provider|server|form|instance)``.

    **لا يُضمِّن content_hash عمداً:** المفتاح يعرّف «خانة الإدخال» (المزوّد/الخادم/الاستمارة/النسخة)
    كي تُقارَن hash الجسم **منفصلةً** ⇒ نفس الخانة بنفس الجسم = idempotent، ونفس الخانة بجسم مختلف
    (جهاز أعاد الإرسال بعد تعديل) = **متباين يُرى** (لا يُبتلع). لو أُدرِج content_hash في المفتاح لصار
    كلّ جسم مفتاحاً جديداً واستحالت الحالة المتباينة (كشفه برهان B1.2b الحيّ). يعيد 64 خانة hex.
    """
    raw = _SEP.join((provider, server, form_id, instance_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IngestCheck:
    """فحص إدخال مفرد (يُفرَض في B1.1)."""

    check_id: str
    description_ar: str


# «التحقّق السباعي» — لا دخول للقرار قبل اجتيازه كاملاً (يُعلَن هنا، يُفرَض في B1.1).
SEVEN_CHECKS: tuple[IngestCheck, ...] = (
    IngestCheck("tenant_known", "المستأجِر معروف ومفعّل"),
    IngestCheck("provider_allowlisted", "المزوّد ضمن قائمة السماح"),
    IngestCheck("form_mapping_registered", "تعيين الاستمارة مُسجَّل ومُصدَّر (mapping_version)"),
    IngestCheck(
        "provenance_complete",
        "provenance كامل (provider/server/form/instance/content_hash/submitted_at)",
    ),
    IngestCheck(
        "field_resolves_in_tenant", "الحقل/الموقع يُحلّ داخل المستأجِر (لا تسرّب عبر المستأجرين)"
    ),
    IngestCheck("values_within_domain_bounds", "القيم ضمن حدود المجال (لا اختلاق/خارج نطاق)"),
    IngestCheck("not_duplicate", "غير مكرَّر (dedup على idempotency_key)"),
)


class ExternalSubmissionEnvelopeV1(BaseModel):
    """مظروف موحّد لإدخال ميدانيّ خارجيّ — محايد المزوّد، **غير موثوق حتى التحقّق**."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, validate_default=True)

    contract_version: Literal["external-submission.v1"] = INGEST_CONTRACT_VERSION
    submission_id: _NonEmpty
    provider: _Provider
    server: _NonEmpty
    form_id: _NonEmpty
    instance_id: _NonEmpty
    content_hash: _Sha256  # sha256 للحمولة الخامّة
    tenant_id: UUID
    submitted_at: datetime
    received_at: datetime
    raw_ref: _NonEmpty  # مؤشّر للخامّ المحفوظ (الوصول ≠ الثقة)
    mapping_version: _SemVer  # نسخة التعيين المُصدَّرة
    idempotency_key: _Sha256  # = derive_dedup_key(...) — يُفرَض بنيويّاً
    payload: dict[str, Any]  # حمولة مطبَّعة بشكل رصد (محاذاة العنقود 4 في ADR-0034)
    trust_status: Literal["untrusted"] = "untrusted"  # لا يدخل موثوقاً — الوصول ≠ الثقة

    @model_validator(mode="after")
    def _dedup_key_is_structural(self) -> ExternalSubmissionEnvelopeV1:
        expected = derive_dedup_key(
            provider=self.provider,
            server=self.server,
            form_id=self.form_id,
            instance_id=self.instance_id,
        )
        if self.idempotency_key != expected:
            raise ValueError("idempotency_key_must_equal_derived_dedup_key")
        return self

    @model_validator(mode="after")
    def _timestamps_aware_utc(self) -> ExternalSubmissionEnvelopeV1:
        for name in ("submitted_at", "received_at"):
            value: datetime = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name}_must_be_timezone_aware")
        return self
