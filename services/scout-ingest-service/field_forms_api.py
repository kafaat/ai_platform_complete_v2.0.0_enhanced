#!/usr/bin/env python3
"""GAP-FIELD-FORMS-01 — واجهة النماذج الميدانيّة الديناميكية (الشريحة الأولى، خادميّة).

أنبوب واحد (§12/§12.1): المظروف يدخل external_submissions **بحالة نهائيّة فقط** —
accepted بعد اكتمال (identity resolution + version resolution + sync-proof + DSL + schema)،
وإلّا quarantined. ``external_submissions`` المالك الوحيد للحالة النهائيّة؛ ``field_submissions``
لا يُنشأ إلا لـform_version_id معروف (الإصدار المجهول ⇒ حجر خامّ بلا صفّ، §12.1).

نموذج الأمان (نمط season_api): خلف الراية ``FIELD_FORMS_ENABLED`` (افتراضيّ off ⇒ 404) ·
توكن خدمة مخصّص ``FIELD_FORMS_SERVICE_TOKEN`` (غير مضبوط ⇒ 503 · غير مطابق ⇒ 401) ·
المستأجِر من ``X-Tenant-Id`` المُحقَن من الحافّة (SEC-3) · دور ``sahool_ingest`` مع
``app.current_tenant`` على كلّ اتّصال (RLS فعّال) · أيّ خطأ DB ⇒ 503 (لا 500، لا اختلاق).

stale بإثبات خادميّ فقط (§9): ``definition_sync_token`` HMAC ذاتيّ التحقّق يُصدره تنزيل
النموذج؛ ``local_created_at`` لا يُوثَق أبدًا. superseded+توكن ⇒ stale_proven مقبول ·
withdrawn ⇒ quarantined مهما كان التوكن (نموذج فاسد لا يُغذّى).

تدوير المفاتيح (§9.2): ``FIELD_FORMS_SYNC_HMAC_KEY`` (+``_KEY_ID``) الحاليّ،
و``FIELD_FORMS_SYNC_HMAC_KEY_PREVIOUS`` (+``_PREVIOUS_KEY_ID`` +``_PREVIOUS_UNTIL_EPOCH``)
سابقٌ محتفَظ به بحدّ زمنيّ صريح. نافذة offline القصوى ``FIELD_FORMS_MAX_OFFLINE_SECONDS``
(افتراضيّ 30 يومًا).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from shared.contracts.forms.condition_v1 import ConditionError, ConditionTypeError
from shared.contracts.forms.schema_v1 import (
    NORMALIZER_VERSION,
    SchemaError,
    canonical_answers_hash,
    validate_answers,
    validate_form_schema,
)
from shared.contracts.forms.sync_token import SyncTokenError, issue_token, verify_token
from shared.contracts.ingest.dedup_resolution import resolve_dedup
from shared.contracts.ingest.external_submission_v1 import derive_dedup_key
from shared.security.trusted_tenant import (
    TrustedTenantError,
    resolve_trusted_tenant,
    service_token_ok,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
_ENABLED_TRUE = {"1", "true", "yes", "on"}

FORM_PROVIDER_FORM_ID = "sahool-field-form"
DEFAULT_MAX_OFFLINE_SECONDS = 30 * 24 * 3600

router = APIRouter()


def _require_enabled() -> None:
    if os.getenv("FIELD_FORMS_ENABLED", "0").strip().lower() not in _ENABLED_TRUE:
        raise HTTPException(status_code=404, detail="FIELD-FORMS disabled (FIELD_FORMS_ENABLED)")


def _require_service_token(token: str | None) -> None:
    expected = os.getenv("FIELD_FORMS_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503, detail="field forms not configured (FIELD_FORMS_SERVICE_TOKEN)"
        )
    if not service_token_ok(token, expected):
        raise HTTPException(status_code=401, detail="field_forms_service_token_required")


def _require_tenant(x_tenant_id: str | None) -> str:
    try:
        tenant = resolve_trusted_tenant(x_tenant_id, None)
    except TrustedTenantError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc
    try:
        return str(UUID(tenant))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from None


async def _tenant_conn(tenant_id: str):
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503, detail="field forms database not configured (DATABASE_URL unset)"
        )
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
    return conn


def _db_or_input_error(exc: Exception) -> HTTPException:
    name = type(exc).__name__
    msg = str(exc)
    if any(
        k in name
        for k in ("Check", "Integrity", "NotNull", "Restrict", "Exclusion", "RaiseError", "Unique")
    ):
        return HTTPException(
            status_code=400, detail=f"field_forms_constraint_violation: {msg[:200]}"
        )
    return HTTPException(status_code=503, detail="field forms store unavailable")


def _sync_keypair() -> tuple[str, str]:
    secret = os.getenv("FIELD_FORMS_SYNC_HMAC_KEY", "")
    if not secret:
        raise HTTPException(
            status_code=503, detail="sync token not configured (FIELD_FORMS_SYNC_HMAC_KEY)"
        )
    return secret, os.getenv("FIELD_FORMS_SYNC_HMAC_KEY_ID", "k1")


def _previous_keypair() -> tuple[str | None, str | None, float | None]:
    secret = os.getenv("FIELD_FORMS_SYNC_HMAC_KEY_PREVIOUS") or None
    key_id = os.getenv("FIELD_FORMS_SYNC_HMAC_PREVIOUS_KEY_ID", "k0")
    until_raw = os.getenv("FIELD_FORMS_SYNC_PREVIOUS_UNTIL_EPOCH") or None
    until = float(until_raw) if until_raw else None
    if not secret:
        return None, None, None
    return secret, key_id, until


def _max_offline_seconds() -> int:
    try:
        return int(os.getenv("FIELD_FORMS_MAX_OFFLINE_SECONDS", str(DEFAULT_MAX_OFFLINE_SECONDS)))
    except ValueError:
        return DEFAULT_MAX_OFFLINE_SECONDS


# ── نماذج الطلب ─────────────────────────────────────────────────────────────────
class DefinitionIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None


class VersionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # الاسم الداخليّ schema_ (تفادي تظليل BaseModel.schema)؛ العقد الخارجيّ schema_json
    schema_: dict = Field(alias="schema_json")
    logic_json: dict | None = None
    validation_rules: dict | None = None
    localization: dict | None = None


class RetireIn(BaseModel):
    mode: str  # superseded | withdrawn
    reason: str = Field(min_length=1, max_length=500)


class AssignmentIn(BaseModel):
    form_version_id: str
    field_id: str = Field(min_length=1)
    season_id: str | None = None


class SubmissionIn(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    server: str = Field(min_length=1, max_length=256)
    instance_id: str = Field(min_length=1, max_length=256)
    submitted_at: datetime
    local_created_at: datetime | None = None  # معلوماتيّ فقط — لا يُوثَق زمنيًّا (§9)
    field_id: str = Field(min_length=1)
    form_version_id: str
    schema_hash: str = Field(min_length=1, max_length=128)
    assignment_revision: int | None = None
    definition_sync_token: str | None = None
    answers: dict


# ══ إدارة التعريفات (مسؤول مخوَّل عبر توكن الخدمة؛ لا مصمّم بصريّ — API/JSON فقط، §3) ══
@router.post("/internal/field-forms/definitions", status_code=201)
async def create_definition(
    body: DefinitionIn,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
):
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    conn = await _tenant_conn(tenant)
    try:
        existing = await conn.fetchval(
            "SELECT id FROM field_form_definitions WHERE code = $1", body.code
        )
        if existing:
            return {"definition_id": str(existing), "idempotent": True}
        did = await conn.fetchval(
            "INSERT INTO field_form_definitions (tenant_id, code, title, description, created_by) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            tenant,
            body.code,
            body.title,
            body.description,
            x_actor_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"definition_id": str(did), "idempotent": False}


@router.post("/internal/field-forms/definitions/{code}/versions", status_code=201)
async def create_version(
    code: str,
    body: VersionIn,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """مسودّة إصدار جديد (draft). تحقّق النشر المبكّر (§10): DSL خارج القائمة ⇒ 422 الآن."""
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    try:
        validate_form_schema(body.schema_, body.logic_json)
    except SchemaError as exc:
        raise HTTPException(status_code=422, detail=f"schema_invalid: {exc}") from exc
    schema_hash = hashlib.sha256(
        json.dumps(body.schema_, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    conn = await _tenant_conn(tenant)
    try:
        did = await conn.fetchval("SELECT id FROM field_form_definitions WHERE code = $1", code)
        if did is None:
            raise HTTPException(status_code=404, detail="form definition not found")
        vid = await conn.fetchval(
            "INSERT INTO field_form_versions "
            "(tenant_id, form_definition_id, version_number, status, schema_json, logic_json, "
            " validation_rules, localization, schema_hash) "
            "VALUES ($1,$2,"
            " COALESCE((SELECT max(version_number) FROM field_form_versions "
            "          WHERE form_definition_id = $2), 0) + 1,"
            " 'draft', $3, $4, $5, $6, $7) RETURNING id",
            tenant,
            did,
            json.dumps(body.schema_),
            json.dumps(body.logic_json) if body.logic_json is not None else None,
            json.dumps(body.validation_rules) if body.validation_rules is not None else None,
            json.dumps(body.localization) if body.localization is not None else None,
            schema_hash,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"version_id": str(vid), "schema_hash": schema_hash, "status": "draft"}


@router.post("/internal/field-forms/versions/{version_id}/publish")
async def publish_version(
    version_id: str,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
):
    """النشر معاملة واحدة (§5.2): retire المنشورة الحاليّة (superseded) + publish الجديدة.
    الفهرس الجزئيّ يمنع نشرتين متزامنتين؛ الـtrigger يفرض draft→published فقط."""
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    vid = _as_uuid(version_id, "version id")
    conn = await _tenant_conn(tenant)
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT form_definition_id, status FROM field_form_versions WHERE id = $1 "
                "FOR UPDATE",
                vid,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="form version not found")
            # تقاعد المنشورة الحاليّة بنمط superseded (استُبدلت)
            await conn.execute(
                "UPDATE field_form_versions SET status = 'retired', "
                "retired_at = now(), retired_by = $3, "
                "retirement_reason = 'superseded by new publication', "
                "retirement_mode = 'superseded' "
                "WHERE form_definition_id = $1 AND status = 'published'",
                row["form_definition_id"],
                vid,
                x_actor_id,
            )
            await conn.execute(
                "UPDATE field_form_versions SET status = 'published', "
                "published_at = now(), published_by = $2 WHERE id = $1",
                vid,
                x_actor_id,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"version_id": vid, "status": "published"}


@router.post("/internal/field-forms/versions/{version_id}/retire")
async def retire_version(
    version_id: str,
    body: RetireIn,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
):
    """التقاعد بنمطين (§9.3): superseded (stale بإثبات ⇒ مقبول) / withdrawn (حجر مهما كان)."""
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    if body.mode not in ("superseded", "withdrawn"):
        raise HTTPException(status_code=400, detail="mode must be superseded|withdrawn")
    vid = _as_uuid(version_id, "version id")
    conn = await _tenant_conn(tenant)
    try:
        await conn.execute(
            "UPDATE field_form_versions SET status = 'retired', retired_at = now(), "
            "retired_by = $2, retirement_reason = $3, retirement_mode = $4 WHERE id = $1",
            vid,
            x_actor_id,
            body.reason,
            body.mode,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"version_id": vid, "status": "retired", "retirement_mode": body.mode}


@router.post("/internal/field-forms/assignments", status_code=201)
async def create_assignment(
    body: AssignmentIn,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
):
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    vid = _as_uuid(body.form_version_id, "form_version_id")
    conn = await _tenant_conn(tenant)
    try:
        aid = await conn.fetchval(
            "INSERT INTO field_form_assignments (tenant_id, form_version_id, field_id, season_id, created_by) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            tenant,
            vid,
            body.field_id,
            body.season_id,
            x_actor_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"assignment_id": str(aid), "revision": 1}


# ══ التنزيل (عميل ميدانيّ): نموذج منشور + توكن sync موقّع ══
@router.get("/internal/field-forms/download")
async def download_forms(
    field_id: str,
    actor_id: str,
    device_id: str,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """النماذج الفعّالة لحقل + توكن sync لكلٍّ. **الغموض يفشل** (§5.3): أكثر من assignment
    فعّال لنفس التعريف ⇒ 409 ambiguous_active_assignment (لا اختيار صامت)."""
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    conn = await _tenant_conn(tenant)
    try:
        rows = await conn.fetch(
            "SELECT a.id AS assignment_id, a.revision, v.id AS version_id, v.version_number, "
            "v.schema_json, v.logic_json, v.schema_hash, v.form_definition_id "
            "FROM field_form_assignments a "
            "JOIN field_form_versions v ON v.id = a.form_version_id AND v.tenant_id = a.tenant_id "
            "WHERE a.field_id = $1 AND v.status = 'published' "
            "AND a.active_from <= now() AND (a.active_to IS NULL OR a.active_to > now())",
            field_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="field forms store unavailable") from exc
    finally:
        await conn.close()
    seen: dict[str, int] = {}
    for r in rows:
        key = str(r["form_definition_id"])
        seen[key] = seen.get(key, 0) + 1
    if any(n > 1 for n in seen.values()):
        raise HTTPException(status_code=409, detail="ambiguous_active_assignment")
    secret, key_id = _sync_keypair()
    now = time.time()
    forms = []
    for r in rows:
        token = issue_token(
            {
                "token_version": 1,
                "key_id": key_id,
                "tenant_id": tenant,
                "actor_id": actor_id,
                "device_id": device_id,
                "assignment_id": str(r["assignment_id"]),
                "revision": r["revision"],
                "form_version_id": str(r["version_id"]),
                "schema_hash": r["schema_hash"],
                "issued_at": now,
            },
            secret=secret,
            key_id=key_id,
        )
        forms.append(
            {
                "assignment_id": str(r["assignment_id"]),
                "revision": r["revision"],
                "form_version_id": str(r["version_id"]),
                "version_number": r["version_number"],
                "schema_json": _json_out(r["schema_json"]),
                "logic_json": _json_out(r["logic_json"]),
                "schema_hash": r["schema_hash"],
                "definition_sync_token": token,
            }
        )
    return {"field_id": field_id, "forms": forms, "count": len(forms)}


# ══ الإرسال: §12/§12.1 — حالة نهائيّة واحدة مملوكة لـexternal_submissions ══
@router.post("/internal/field-forms/submissions", status_code=201)
async def submit_form(
    body: SubmissionIn,
    x_field_forms_token: str | None = Header(None, alias="X-Field-Forms-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
):
    """يدخل المظروف ويحسم مصيره في معاملة واحدة (الخيار الأقلّ تغييرًا، §12.1):

    1. dedup بنيويّ (B1): نفس المفتاح+الجسم ⇒ idempotent (يعيد الصفّ القائم)
    2. إصدار/``schema_hash`` مجهول ⇒ مظروف محجور **بلا صفّ field_submissions** (§12.1)
    3. withdrawn ⇒ محجور مهما كان التوكن · توكن مكسور على stale ⇒ invalid_sync_proof
    4. superseded + توكن صالح ⇒ stale_proven (accepted، stale_version=true)
    5. DSL + schema خادميًّا ⇒ invalid ⇒ محجور · valid ⇒ accepted
    """
    _require_enabled()
    _require_service_token(x_field_forms_token)
    tenant = _require_tenant(x_tenant_id)
    vid = _as_uuid(body.form_version_id, "form_version_id")

    raw_payload = body.model_dump(mode="json")
    canonical_raw = json.dumps(raw_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    source_hash = hashlib.sha256(canonical_raw).hexdigest()
    dedup_key = derive_dedup_key(
        provider=body.provider,
        server=body.server,
        form_id=FORM_PROVIDER_FORM_ID,
        instance_id=body.instance_id,
    )
    submission_id = f"ff-{uuid4().hex[:24]}"
    raw_ref = f"urn:sahool:field-form:{dedup_key[:16]}"

    conn = await _tenant_conn(tenant)
    try:
        async with conn.transaction():
            # ① dedup (B1 — نقطة الديدوب الوحيدة)
            existing = await conn.fetchrow(
                "SELECT id, content_hash FROM external_submissions "
                "WHERE tenant_id = $1 AND idempotency_key = $2",
                tenant,
                dedup_key,
            )
            dec = resolve_dedup(
                base_key=dedup_key,
                incoming_content_hash=source_hash,
                existing_content_hash=existing["content_hash"] if existing else None,
            )
            if dec.action == "idempotent_replay":
                prior = await conn.fetchrow(
                    "SELECT id, form_validation_status, version_resolution_status, stale_version "
                    "FROM field_submissions WHERE envelope_id = $1",
                    existing["id"],
                )
                return {
                    "idempotent": True,
                    "envelope_id": existing["id"],
                    "field_submission_id": str(prior["id"]) if prior else None,
                    "form_validation_status": prior["form_validation_status"] if prior else None,
                    "version_resolution_status": (
                        prior["version_resolution_status"] if prior else None
                    ),
                    "stale_version": prior["stale_version"] if prior else None,
                }
            if dec.action == "quarantine_divergent":
                # «نفس مفتاح، جسم مختلف» = حدث يُرى (B1.2) — يُحجَر بمفتاح مشتقّ قبل أيّ منطق نماذج
                env_id = await _insert_envelope(
                    conn,
                    tenant,
                    submission_id,
                    body,
                    dec.storage_key,
                    source_hash,
                    raw_ref,
                    raw_payload,
                    "quarantined",
                    list(dec.quarantine_reasons),
                )
                return _quarantined_response(env_id, dec.quarantine_reasons[0])

            # ② form identity resolution — مجهول ⇒ حجر خامّ بلا صفّ (§12.1)
            version = await conn.fetchrow(
                "SELECT id, form_definition_id, status, retirement_mode, schema_json, logic_json, "
                "schema_hash FROM field_form_versions WHERE id = $1",
                vid,
            )
            if version is None or version["schema_hash"] != body.schema_hash:
                env_id = await _insert_envelope(
                    conn,
                    tenant,
                    submission_id,
                    body,
                    dec.storage_key,
                    source_hash,
                    raw_ref,
                    raw_payload,
                    trust_status="quarantined",
                    reasons=["form_version_unknown"],
                )
                return _quarantined_response(env_id, "form_version_unknown")

            # ③ version resolution (§9)
            claims = None
            resolution = "current"
            stale = False
            if version["status"] == "published":
                resolution = "current"
            elif version["retirement_mode"] == "withdrawn":
                # نموذج مسحوب ⇒ محجور مهما كان التوكن (لا DSL، لا قبول)
                env_id = await _insert_envelope(
                    conn,
                    tenant,
                    submission_id,
                    body,
                    dec.storage_key,
                    source_hash,
                    raw_ref,
                    raw_payload,
                    "quarantined",
                    ["form_version_withdrawn"],
                )
                fs_id = await _insert_field_submission(
                    conn,
                    tenant,
                    vid,
                    None,
                    env_id,
                    raw_payload["answers"],
                    "unknown_schema",
                    "withdrawn_quarantined",
                    False,
                    source_hash,
                    x_actor_id,
                )
                return _quarantined_response(
                    env_id, "form_version_withdrawn", fs_id, "withdrawn_quarantined"
                )
            else:
                # superseded ⇒ يتطلّب إثبات sync صالحًا
                claims = _verify_sync_claims(
                    body.definition_sync_token,
                    tenant=tenant,
                    actor_id=x_actor_id,
                    assignment_revision=body.assignment_revision,
                    form_version_id=vid,
                    schema_hash=body.schema_hash,
                )
                if claims is None:
                    env_id = await _insert_envelope(
                        conn,
                        tenant,
                        submission_id,
                        body,
                        dec.storage_key,
                        source_hash,
                        raw_ref,
                        raw_payload,
                        "quarantined",
                        ["invalid_sync_proof"],
                    )
                    fs_id = await _insert_field_submission(
                        conn,
                        tenant,
                        vid,
                        None,
                        env_id,
                        raw_payload["answers"],
                        "unknown_schema",
                        "invalid_sync_proof",
                        False,
                        source_hash,
                        x_actor_id,
                    )
                    return _quarantined_response(
                        env_id, "invalid_sync_proof", fs_id, "invalid_sync_proof"
                    )
                resolution = "stale_proven"
                stale = True

            # ④ DSL + schema خادميًّا (§10/§12)
            schema_json = _json_out(version["schema_json"])
            logic_json = _json_out(version["logic_json"])
            try:
                normalized, errors = validate_answers(schema_json, logic_json, body.answers)
            except (ConditionError, ConditionTypeError, SchemaError) as exc:
                normalized, errors = {}, [f"validation_engine_error: {exc}"]
            if errors:
                env_id = await _insert_envelope(
                    conn,
                    tenant,
                    submission_id,
                    body,
                    dec.storage_key,
                    source_hash,
                    raw_ref,
                    raw_payload,
                    "quarantined",
                    ["form_validation_failed"],
                )
                fs_id = await _insert_field_submission(
                    conn,
                    tenant,
                    vid,
                    claims.get("assignment_id") if claims else None,
                    env_id,
                    body.answers,
                    "invalid",
                    resolution,
                    stale,
                    source_hash,
                    x_actor_id,
                )
                return _quarantined_response(
                    env_id, "form_validation_failed", fs_id, resolution, errors=errors[:10]
                )

            # ⑤ مقبول: المظروف accepted + الصفّ valid (invariant §12.1 محفوظ بنيويًّا)
            env_id = await _insert_envelope(
                conn,
                tenant,
                submission_id,
                body,
                dec.storage_key,
                source_hash,
                raw_ref,
                raw_payload,
                "accepted",
                [],
            )
            fs_id = await _insert_field_submission(
                conn,
                tenant,
                vid,
                claims.get("assignment_id") if claims else None,
                env_id,
                normalized,
                "valid",
                resolution,
                stale,
                source_hash,
                x_actor_id,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {
        "idempotent": False,
        "envelope_id": env_id,
        "field_submission_id": str(fs_id),
        "trust_status": "accepted",
        "form_validation_status": "valid",
        "version_resolution_status": resolution,
        "stale_version": stale,
        "answers_hash": canonical_answers_hash(normalized),
    }


# ── مساعدات داخليّة ─────────────────────────────────────────────────────────────
def _as_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"{label} must be a UUID") from None


def _json_out(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _verify_sync_claims(
    token: str | None,
    *,
    tenant: str,
    actor_id: str | None,
    assignment_revision: int | None,
    form_version_id: str,
    schema_hash: str,
) -> dict | None:
    """يتحقّق من التوكن + تطابق الهويّة/الوجهة + نافذة offline (§9.2). None ⇒ invalid_sync_proof."""
    if not token:
        return None
    secret, key_id = _sync_keypair()
    prev_secret, prev_key_id, prev_until = _previous_keypair()
    now = time.time()
    try:
        claims = verify_token(
            token,
            current_secret=secret,
            current_key_id=key_id,
            previous_secret=prev_secret,
            previous_key_id=prev_key_id,
            previous_until_epoch=prev_until,
            now_epoch=now,
        )
    except SyncTokenError:
        return None
    if claims["tenant_id"] != tenant:
        return None
    if actor_id and claims["actor_id"] != actor_id:
        return None
    if claims["form_version_id"] != form_version_id or claims["schema_hash"] != schema_hash:
        return None
    if assignment_revision is not None and claims["revision"] != assignment_revision:
        return None
    issued_at = claims["issued_at"]
    if not isinstance(issued_at, (int, float)) or now - issued_at > _max_offline_seconds():
        return None
    return claims


async def _insert_envelope(
    conn,
    tenant: str,
    submission_id: str,
    body: SubmissionIn,
    storage_key: str,
    content_hash: str,
    raw_ref: str,
    raw_payload: dict,
    trust_status: str,
    reasons: list[str],
) -> int:
    """يُثبّت المظروف بحالته النهائيّة (§12.1 — external_submissions مالك الحالة الوحيد)."""
    return await conn.fetchval(
        "INSERT INTO external_submissions "
        "(tenant_id, submission_id, provider, server, form_id, instance_id, content_hash, "
        " idempotency_key, submitted_at, raw_ref, raw_payload, mapping_version, "
        " normalized_payload, trust_status, quarantine_reasons) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING id",
        tenant,
        submission_id,
        body.provider,
        body.server,
        FORM_PROVIDER_FORM_ID,
        body.instance_id,
        content_hash,
        storage_key,
        body.submitted_at,
        raw_ref,
        json.dumps(raw_payload),
        "1.0.0",
        json.dumps({"field_id": body.field_id, "answers": body.answers}),
        trust_status,
        reasons,
    )


async def _insert_field_submission(
    conn,
    tenant: str,
    form_version_id: str,
    assignment_id,
    envelope_id: int,
    answers: dict,
    form_validation_status: str,
    version_resolution_status: str,
    stale: bool,
    source_hash: str,
    actor_id: str | None,
) -> str:
    return await conn.fetchval(
        "INSERT INTO field_submissions "
        "(tenant_id, form_version_id, assignment_id, envelope_id, answers_json, answers_hash, "
        " source_payload_hash, normalizer_version, form_validation_status, "
        " version_resolution_status, stale_version, submitted_by) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id",
        tenant,
        form_version_id,
        assignment_id,
        envelope_id,
        json.dumps(answers),
        canonical_answers_hash(answers if isinstance(answers, dict) else {}),
        source_hash,
        NORMALIZER_VERSION,
        form_validation_status,
        version_resolution_status,
        stale,
        actor_id,
    )


def _quarantined_response(
    envelope_id: int,
    reason: str,
    field_submission_id: str | None = None,
    version_resolution_status: str | None = None,
    errors: list[str] | None = None,
) -> dict:
    return {
        "idempotent": False,
        "envelope_id": envelope_id,
        "field_submission_id": str(field_submission_id) if field_submission_id else None,
        "trust_status": "quarantined",
        "quarantine_reason": reason,
        "version_resolution_status": version_resolution_status,
        "validation_errors": errors or [],
    }
