"""التحقّق السباعي + quarantine للإدخال الميدانيّ الخارجيّ (SCOUT-INGEST-01 / B1.1).

القاعدة الحاكمة: **لا دخول للقرار قبل اجتياز الفحوص السبعة كاملةً** (``SEVEN_CHECKS``).
فشل أيّ فحص ⇒ ``accepted=False`` وسبب مُصنَّف؛ الخامّ يبقى محفوظاً ولا يُسقَط شيء إلى
domain. نمط الرفض مُستمَدّ من ``crop_stress_ingestion.normalize_stress_product`` («لا
يُصنَّع دليل زراعيّ عند النقص»).

منطق صرف بحقن سياق (``ValidationContext``) — لا قاعدة/خدمات/شبكة. السياق المدعوم
بقاعدة يُبنى في B1.2؛ هنا يُحقَن كدوالّ ليبقى الفحص قابلاً للاختبار ومستقلّاً.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from shared.contracts.ingest.external_submission_v1 import (
    SEVEN_CHECKS,
    ExternalSubmissionEnvelopeV1,
)


@dataclass(frozen=True)
class ValidationContext:
    """المصادر التي تحتاجها الفحوص السبعة (تُحقَن — تبقى pure/قابلة للاختبار)."""

    is_tenant_known: Callable[[UUID], bool]
    is_provider_allowed: Callable[[str], bool]
    is_form_mapping_registered: Callable[
        [str, str, str], bool
    ]  # provider, form_id, mapping_version
    field_resolves_in_tenant: Callable[[UUID, str], bool]  # tenant_id, field_id
    values_within_bounds: Callable[[dict[str, Any]], bool]  # payload → داخل حدود المجال؟
    is_duplicate: Callable[[str], bool]  # dedup key → رُصد سابقاً؟


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class IngestVerdict:
    """حصيلة التحقّق. ``accepted`` صحيح **فقط** إن اجتاز الفحوص السبعة كاملةً."""

    accepted: bool
    checks: tuple[CheckResult, ...]
    quarantine_reasons: tuple[str, ...]  # check_ids التي فشلت (فارغة إن قُبِل)


def _payload_field_id(payload: dict[str, Any]) -> str | None:
    fid = payload.get("field_id") if isinstance(payload, dict) else None
    return fid if isinstance(fid, str) and fid.strip() else None


def validate_external_submission(
    envelope: ExternalSubmissionEnvelopeV1, ctx: ValidationContext
) -> IngestVerdict:
    """يُشغّل الفحوص السبعة بالترتيب المُعلَن؛ يُبلّغ كلّ نتيجة ويُقبَل فقط إن نجحت كلّها."""
    field_id = _payload_field_id(envelope.payload)

    # كلّ فحص يُقيَّم مرّة واحدة (الدوالّ نقيّة لكن نتجنّب الاستدعاء المزدوج).
    tenant_ok = ctx.is_tenant_known(envelope.tenant_id)
    provider_ok = ctx.is_provider_allowed(envelope.provider)
    mapping_ok = ctx.is_form_mapping_registered(
        envelope.provider, envelope.form_id, envelope.mapping_version
    )
    provenance_ok = field_id is not None
    resolves_ok = provenance_ok and ctx.field_resolves_in_tenant(envelope.tenant_id, field_id)
    bounds_ok = ctx.values_within_bounds(envelope.payload)
    not_dup = not ctx.is_duplicate(envelope.idempotency_key)

    outcomes: dict[str, tuple[bool, str]] = {
        "tenant_known": (tenant_ok, "tenant معروف" if tenant_ok else "tenant غير معروف"),
        "provider_allowlisted": (provider_ok, f"provider={envelope.provider}"),
        "form_mapping_registered": (
            mapping_ok,
            f"{envelope.provider}/{envelope.form_id}@{envelope.mapping_version}",
        ),
        "provenance_complete": (
            provenance_ok,
            "payload.field_id حاضر" if provenance_ok else "payload.field_id مفقود",
        ),
        "field_resolves_in_tenant": (
            resolves_ok,
            "الحقل يُحلّ داخل المستأجِر" if resolves_ok else "الحقل لا يُحلّ داخل المستأجِر (تسرّب/مفقود)",
        ),
        "values_within_domain_bounds": (
            bounds_ok,
            "القيم ضمن الحدود" if bounds_ok else "قيم خارج حدود المجال",
        ),
        "not_duplicate": (not_dup, "غير مكرَّر" if not_dup else "مكرَّر"),
    }

    # نمشي على SEVEN_CHECKS (مصدر الترتيب/الأسماء الوحيد) لضمان التطابق البنيويّ.
    checks: list[CheckResult] = []
    reasons: list[str] = []
    for check in SEVEN_CHECKS:
        passed, detail = outcomes[check.check_id]
        checks.append(CheckResult(check.check_id, passed, detail))
        if not passed:
            reasons.append(check.check_id)

    return IngestVerdict(
        accepted=not reasons,  # لا قبول قبل اجتياز السبعة كاملةً
        checks=tuple(checks),
        quarantine_reasons=tuple(reasons),
    )
