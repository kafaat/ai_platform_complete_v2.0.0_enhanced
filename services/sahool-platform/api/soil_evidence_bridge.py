"""ناشرُ المنصّة إلى حدّ التربة القانونيّ — أدلّةُ المختبر وقراءاتُ الحسّاسات.

Publish approved laboratory evidence to soil-service's canonical evidence boundary.

**ولماذا يسكن تحويلُ الحسّاس هنا لا في وحدةٍ جديدة:** الاتّجاهُ والحدُّ نفسُهما —
المنصّةُ تنشر إلى `soil-service` الذي يملك `soil_observations` ويكتبه وحدَه
(`docs/architecture/db_ownership.yml`). ووحدةٌ جديدة كانت تُنمّي عدّادَ وحدات
المنصّة (٦٨٠ ⇒ ٦٨١) فيحمرّ `platform_module_budget`؛ ورفعُ الأساس لتمريرِ شريحةٍ
هو ما تنهى عنه قاعدةُ الميزانيّات. فالموضعُ الصحيح وحدةٌ قائمةٌ تملك هذا الحدّ.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any

import httpx

_ANALYTE_MAP = {
    "ph": ("ph", "1"),
    "ec_dsm": ("electrical_conductivity", "dS/m"),
    "organic_matter_pct": ("organic_matter", "%"),
    "nitrogen_mg_kg": ("nitrogen", "mg/kg"),
    "phosphorus_mg_kg": ("phosphorus", "mg/kg"),
    "potassium_mg_kg": ("potassium", "mg/kg"),
    "cec_cmol_kg": ("cec", "cmol(+)/kg"),
    "calcium_carbonate_pct": ("calcium_carbonate", "%"),
    "texture": ("texture_class", None),
}


async def publish_soil_lab_evidence(
    *,
    tenant_id: str,
    field_id: str,
    sample: dict[str, Any],
    results: dict[str, Any],
    result_rows: list[dict[str, Any]] | None = None,
    correction_reason: str | None = None,
) -> dict[str, Any]:
    # Canonical default must match compose/service_proxy/field_intelligence_adapters
    # (sahool-soil-service:8000). The old "soil-service:8134" default was only masked
    # because SOIL_SERVICE_URL is always set in compose; unset, it dialed a dead host.
    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000").rstrip("/")
    token = (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("SOIL_SERVICE_TOKEN")
        or os.getenv("SAHOOL_AGENT_TOKEN")
    )
    if not token:
        raise RuntimeError(
            "INTERNAL_SERVICE_TOKEN/SOIL_SERVICE_TOKEN/SAHOOL_AGENT_TOKEN is required"
        )
    properties: dict[str, Any] = {}
    units: dict[str, str] = {}
    for source_name, (canonical, unit) in _ANALYTE_MAP.items():
        value = results.get(source_name)
        if value is not None:
            properties[canonical] = value
            if unit:
                units[canonical] = unit
    if not properties:
        raise RuntimeError("no publishable soil analytes")
    supersedes_observation_ids: dict[str, str] = {}
    result_by_canonical: dict[str, str] = {}
    for row in result_rows or []:
        mapped = _ANALYTE_MAP.get(row.get("analyte"))
        if not mapped:
            continue
        canonical = mapped[0]
        result_by_canonical[canonical] = str(row.get("result_id"))
        prior = row.get("supersedes_result_id")
        if prior:
            prior_observation = row.get("superseded_published_observation_id")
            if prior_observation:
                supersedes_observation_ids[canonical] = prior_observation
    payload = {
        "source_type": "laboratory",
        "source_id": sample["sample_id"],
        "properties": properties,
        "observed_at": datetime.now(UTC).isoformat(),
        "depth_from_cm": float(sample.get("depth_cm_from") or 0),
        "depth_to_cm": float(sample.get("depth_cm_to") or 30),
        "approved": True,
        "procedure_id": "platform-lab-workflow.v1",
        "supersedes_observation_ids": supersedes_observation_ids,
        "supersession_reason": correction_reason,
        "provenance": {
            "sample_id": sample["sample_id"],
            "units": units,
            "workflow_status": "published",
        },
    }
    headers = {"X-Agent-Token": token, "X-Tenant-Id": tenant_id}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base}/v1/fields/{field_id}/soil/evidence", json=payload, headers=headers
        )
    response.raise_for_status()
    receipt = response.json()
    receipt["result_by_canonical"] = result_by_canonical
    return receipt


#: الخصائصُ التي لها مستهلكٌ زراعيٌّ مقيسٌ يقرأ `soil_observations`. غيرُها يبقى نبضةَ
#: صحّةِ جهازٍ ولا يُحوَّل — فالتحويلُ بلا قارئٍ يصنع مساراً ثانياً ميّتاً.
AGRONOMIC_PROPERTIES = frozenset({"soil_moisture"})

_TIMEOUT_SECONDS = 8.0


def _token() -> str | None:
    return (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("SOIL_SERVICE_TOKEN")
        or os.getenv("SAHOOL_AGENT_TOKEN")
    )


def idempotency_key(*, device_id: str, property_name: str, observed_at: datetime) -> str:
    """مفتاحٌ مشتقٌّ من هويّة القراءة — فإعادةُ الدفع لا تُضاعِف ملاحظة.

    مبنيٌّ على (الجهاز · الخاصّيّة · لحظةُ القياس) لا على وقت الوصول: دفعتان لقراءةٍ
    واحدة تحملان اللحظةَ نفسَها، ومفتاحٌ من `now()` كان سيجعلهما ملاحظتَين.
    """
    raw = f"{device_id}|{property_name}|{observed_at.astimezone(UTC).isoformat()}"
    return f"dev_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:48]}"


def build_observation(
    *,
    tenant_id: str,
    field_id: str,
    device_id: str,
    property_name: str,
    value: Any,
    unit: str | None,
    observed_at: datetime,
) -> dict[str, Any]:
    """جسمُ الملاحظة كما يقبله عقدُ المالك — بلا حقلٍ يُعلِن ما لم يُقَس."""
    return {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "property": property_name,
        "value": value,
        "unit": unit,
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "source_type": "sensor",
        "source_id": device_id,
        "idempotency_key": idempotency_key(
            device_id=device_id, property_name=property_name, observed_at=observed_at
        ),
        "provenance": {"ingest_path": "platform.devices.telemetry", "device_id": device_id},
    }


async def forward_observation(
    *,
    tenant_id: str,
    field_id: str,
    device_id: str,
    property_name: str,
    value: Any,
    unit: str | None,
    observed_at: datetime,
) -> dict[str, Any]:
    """يُحوّل القراءةَ إلى مالكها ويُعيد نتيجةً **مُسمّاة** لا منطقيّةً عارية.

    الردُّ يحمل `reached` و`reason`؛ و`reason` يظهر في ردّ النقطة كي يعلم الدافعُ
    أنّ قراءتَه لم تبلغ قراراً — وهو ما كان غائباً فصار الصمتُ نجاحاً.
    """
    token = _token()
    if not token:
        return {"reached": False, "reason": "service_token_unset"}

    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000").rstrip("/")
    body = build_observation(
        tenant_id=tenant_id,
        field_id=field_id,
        device_id=device_id,
        property_name=property_name,
        value=value,
        unit=unit,
        observed_at=observed_at,
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base}/v1/soil/observations",
                headers={"X-Agent-Token": token, "X-Tenant-Id": tenant_id},
                json=body,
            )
    except httpx.HTTPError as exc:
        return {"reached": False, "reason": f"transport_error:{type(exc).__name__}"}

    if response.status_code not in (200, 201):
        return {"reached": False, "reason": f"owner_rejected:{response.status_code}"}
    try:
        payload = response.json()
    except ValueError:
        return {"reached": False, "reason": "owner_response_not_json"}
    if not isinstance(payload, dict):
        return {"reached": False, "reason": "owner_response_not_object"}
    return {
        "reached": True,
        "status": payload.get("status"),
        "observation_id": payload.get("observation_id"),
    }
