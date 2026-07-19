#!/usr/bin/env python3
"""SAHOOL scout-ingest-service — owner of external field-submission ingest (SCOUT-INGEST-01 / B1.2b).

**لماذا خدمة مستقلّة لا مسار منصّة (تصحيح قرار (ج)):** حُرّاس المنصّة الأربعة (route-budget-does-not-grow،
route-budget-reduced، route-ownership، mutating-auth) رفضت إضافة مسار للمنصّة — الانضباط: المنصّة تُقلّص
مساراتها. السابقة #201 (field-management-service) حسمت النمط: **مدخل خارجيّ ⇒ خدمة مالكة**. فهذه الخدمة
تملك مسار الإدخال + جدول ``external_submissions`` (db_ownership.yml).

**عقد الأمان (fail-closed، بلا fallback):**
  • **اعتماد لكلّ مصدر لا توكن مشترك:** ``X-Scout-Ingest-Token`` → sha256 → ``resolve_ingest_source``
    (SECURITY DEFINER، v198) → المستأجِر. لا ``SAHOOL_AGENT_TOKEN`` ولا JWT هنا. بلا توكن ⇒ 401 ·
    مصدر مجهول/معطَّل ⇒ 403 (إبطال مصدر = سطر لا يمسّ غيره).
  • **الهويّة لا من المُرسِل:** tenant/provider/server/form من السجلّ المُحلَّل.
  • **RLS فعّال:** الدور المقيَّد ``sahool_ingest`` (NOBYPASSRLS)؛ كلّ عمليّة تضبط ``app.current_tenant``
    (session-scoped ``false`` — نمط raster-service، اتّصال قصير لكلّ عمليّة).
  • DATABASE_URL غير مضبوط ⇒ 503. أيّ خطأ asyncpg ⇒ 503 (لا 500، لا اختلاق).
  • خلف ``SCOUT_INGEST_ENABLED`` (افتراضيّ off ⇒ 404).

المنطق النقيّ (المحوّل + قرار الإدخال) في ``shared/contracts/ingest`` (مُختبَر في tests_v9) — تستهلكه هذه
الخدمة عبر Dockerfile (``COPY shared/`` + PYTHONPATH). لا تكرار منطق.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from shared.contracts.ingest.ingest_handler import IngestPorts, process_submission
from shared.contracts.ingest.odk_adapter import build_envelope_from_odk

VERSION = os.getenv("SERVICE_VERSION", "9.1.0-scout-ingest")
DATABASE_URL = os.getenv("DATABASE_URL", "")
# قناة قراءة نموذج B1.3 المملوك: توكن خدمة **مخصّص** (لا SAHOOL_AGENT_TOKEN المشترك) — يستهلكه
# المستهلك الداخليّ عبر /internal، فلا يكتشف أحدٌ الجدول عبر SQL مباشر (مرض direct-DB في p4).
READ_TOKEN = os.getenv("SCOUT_INGEST_READ_TOKEN", "")
_ENABLED_TRUE = {"1", "true", "yes", "on"}

app = FastAPI(title="SAHOOL Scout Ingest Service", version=VERSION)


def _enabled() -> bool:
    return os.getenv("SCOUT_INGEST_ENABLED", "0").strip().lower() in _ENABLED_TRUE


async def _connect():
    """اتّصال قصير لكلّ عمليّة (نمط raster-service/field-management — لا pool عبر حلقات أحداث).

    DATABASE_URL غير مضبوط ⇒ 503 fail-closed. ``statement_cache_size=0`` آمن خلف pgbouncer.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503, detail="ingest database not configured (DATABASE_URL unset)"
        )
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


def _normalize_odk(raw: dict[str, Any]) -> dict[str, Any]:
    """تعيين v1 (مُصدَّر، أدنى): field_id + خاصّية/قيمة رصد. لا اختلاق: ما غاب يبقى غائباً."""
    out: dict[str, Any] = {}
    fid = raw.get("field_id") or raw.get("fieldId")
    if isinstance(fid, str) and fid.strip():
        out["field_id"] = fid.strip()
    for k in ("observed_property", "value", "note", "observed_at"):
        if k in raw:
            out[k] = raw[k]
    return out


async def _resolve_source(token_hash: str) -> dict[str, Any] | None:
    conn = await _connect()  # بلا سياق مستأجِر — resolve_ingest_source SECURITY DEFINER يتجاوز RLS
    try:
        row = await conn.fetchrow("SELECT * FROM resolve_ingest_source($1)", token_hash)
    finally:
        await conn.close()
    return dict(row) if row else None


def _ports(tenant_id: UUID) -> IngestPorts:
    async def _tenant_conn():
        conn = await _connect()
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        return conn

    async def fetch_existing(t: UUID, key: str) -> str | None:
        conn = await _tenant_conn()
        try:
            return await conn.fetchval(
                "SELECT content_hash FROM external_submissions "
                "WHERE tenant_id = $1 AND idempotency_key = $2",
                t,
                key,
            )
        finally:
            await conn.close()

    async def field_in_tenant(_t: UUID, field_id: str) -> bool:
        conn = await _tenant_conn()
        try:
            return bool(await conn.fetchval("SELECT 1 FROM fields WHERE field_id = $1", field_id))
        finally:
            await conn.close()

    async def bounds_ok(_payload: dict[str, Any]) -> bool:
        return True  # v1: حدود المجال الأدنى (تُشدَّد في تعيين مُصدَّر لاحق)

    async def store(row: dict[str, Any]) -> None:
        conn = await _tenant_conn()
        try:
            await conn.execute(
                "INSERT INTO external_submissions "
                "(tenant_id, submission_id, provider, server, form_id, instance_id, content_hash, "
                " idempotency_key, submitted_at, received_at, raw_ref, raw_payload, mapping_version, "
                " normalized_payload, trust_status, quarantine_reasons) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14::jsonb,$15,$16) "
                "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING",
                row["tenant_id"],
                row["submission_id"],
                row["provider"],
                row["server"],
                row["form_id"],
                row["instance_id"],
                row["content_hash"],
                row["idempotency_key"],
                row["submitted_at"],
                row["received_at"],
                row["raw_ref"],
                json.dumps(row["raw_payload"], ensure_ascii=False),
                row["mapping_version"],
                json.dumps(row["normalized_payload"], ensure_ascii=False),
                row["trust_status"],
                row["quarantine_reasons"],
            )
        finally:
            await conn.close()

    return IngestPorts(
        fetch_existing_content_hash=fetch_existing,
        field_resolves_in_tenant=field_in_tenant,
        values_within_bounds=bounds_ok,
        store_row=store,
    )


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "scout-ingest-service", "version": VERSION}


@app.get("/readyz")
async def readyz():
    return {
        "status": "ready" if DATABASE_URL else "degraded",
        "service": "scout-ingest-service",
        "ingest_enabled": _enabled(),
    }


def _require_read_token(token: str | None) -> None:
    """قناة قراءة B1.3: توكن خدمة مخصّص fail-closed. غير مضبوط ⇒ 503 · غير مطابق/غائب ⇒ 401."""
    if not READ_TOKEN:
        raise HTTPException(
            status_code=503, detail="read channel not configured (SCOUT_INGEST_READ_TOKEN)"
        )
    if not token or token != READ_TOKEN:
        raise HTTPException(status_code=401, detail="X-Scout-Ingest-Read-Token required")


@app.get("/internal/scouting/external-observations")
async def read_external_observations(
    field_id: str | None = None,
    x_scout_ingest_read_token: str | None = Header(None, alias="X-Scout-Ingest-Read-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """نموذج القراءة المملوك لـscout-ingest — توكن خدمة + المستأجِر من الترويسة، RLS يقصّ.

    عقد مُعلَن (شرط المالك): المستهلك الداخليّ يقرأ عبر هذا المسار لا عبر SQL مباشر على الجدول.
    """
    _require_read_token(x_scout_ingest_read_token)
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")
    try:
        tenant = str(UUID(x_tenant_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from None
    conn = await _connect()
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
        if field_id:
            rows = await conn.fetch(
                "SELECT observation_id, field_id, observed_property, value, severity, lat, lng, "
                "observed_at, projected_at FROM external_field_observations "
                "WHERE field_id = $1 ORDER BY projected_at DESC LIMIT 500",
                field_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT observation_id, field_id, observed_property, value, severity, lat, lng, "
                "observed_at, projected_at FROM external_field_observations "
                "ORDER BY projected_at DESC LIMIT 500"
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — DB error ⇒ 503, never 500
        raise HTTPException(status_code=503, detail="observations store unavailable") from exc
    finally:
        await conn.close()
    return {"observations": [dict(r) for r in rows], "count": len(rows)}


@app.post("/internal/ingest/submissions/odk")
async def ingest_odk_submission(
    request: Request,
    x_scout_ingest_token: str | None = Header(None, alias="X-Scout-Ingest-Token"),
):
    """يستقبل إدخال ODK، يحلّ المصدر لكلّ توكن، يخزّن بحالته (accepted/quarantined). خلف الراية."""
    if not _enabled():
        raise HTTPException(status_code=404, detail="SCOUT-INGEST disabled (SCOUT_INGEST_ENABLED)")
    if not x_scout_ingest_token:
        raise HTTPException(status_code=401, detail="X-Scout-Ingest-Token required")
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="ODK payload must be an object")

    token_hash = hashlib.sha256(x_scout_ingest_token.encode("utf-8")).hexdigest()
    try:
        source = await _resolve_source(token_hash)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — DB error ⇒ 503, never 500
        raise HTTPException(status_code=503, detail="ingest source registry unavailable") from exc
    if source is None:
        raise HTTPException(status_code=403, detail="unknown or disabled ingest source")

    tenant_id: UUID = source["tenant_id"]
    instance = str(raw.get("meta", {}).get("instanceID") or raw.get("__id") or "unknown")
    envelope = build_envelope_from_odk(
        raw=raw,
        tenant_id=tenant_id,
        provider=source["provider"],
        server=source["server"],
        form_id=source["form_id"],
        mapping_version=source["mapping_version"],
        normalized_payload=_normalize_odk(raw),
        received_at=datetime.now(UTC),
        raw_ref=f"urn:sahool:ingest:{tenant_id}:{instance}",
    )
    try:
        result = await process_submission(envelope, raw, _ports(tenant_id))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="ingest store unavailable") from exc

    code = 202 if result.outcome == "quarantined" else 200
    return JSONResponse(
        status_code=code,
        content={
            "outcome": result.outcome,
            "submission_id": result.submission_id,
            "trust_status": result.trust_status,
            "quarantine_reasons": list(result.quarantine_reasons),
        },
    )
