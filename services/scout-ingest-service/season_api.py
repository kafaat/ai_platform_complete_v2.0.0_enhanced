#!/usr/bin/env python3
"""SEASON-RECORD-ENTRY-01 — واجهة إدخال سجلّ الموسم (النقاط الستّ، مالكها scout-ingest).

الجسر الذي يحوّل أساس v201/v202 إلى **أداة ترقيم**. كلّ النقاط على هذه الخدمة المالكة —
**صفر مسار منصّة** (المواصفة §2؛ حارس route-residual للمنصّة يبقى دون تغيير).

**نموذج الأمان (fail-closed، المواصفة §4):**
  • خلف الراية ``SEASON_ENTRY_ENABLED`` (افتراضيّ off ⇒ 404).
  • **الهويّة والمستأجِر من الحافّة لا من الجسم:** ``X-Tenant-Id`` (مُحقَن من nginx بعد التحقّق، SEC-3) هو
    مصدر المستأجِر الوحيد؛ الجسم قد يُصدّقه فقط (resolve_trusted_tenant).
  • **توكن خدمة مخصّص** ``SEASON_ENTRY_SERVICE_TOKEN`` (لا SAHOOL_AGENT_TOKEN المشترك — فلسفة سكاوت-إنجست):
    غير مضبوط ⇒ 503 · غير مطابق ⇒ 401.
  • **القبول فعل حسّاس (§4-①):** فوق التوكن، هويّة **مُصدَّقة من الحافّة (HMAC)** + دور ``season-reviewer``.
    توكن الخدمة يُثبِت «خدمة في الشبكة» لا «أيّ إنسان راجَع»؛ التوقيع يُثبِت الإنسان (nginx يوقّع، الخدمة تتحقّق).
  • **RLS فعّال:** الدور المقيَّد ``sahool_ingest`` (NOBYPASSRLS)؛ كلّ عمليّة تضبط ``app.current_tenant``.
  • DATABASE_URL غير مضبوط ⇒ 503 · أيّ خطأ asyncpg ⇒ 503 (لا 500، لا اختلاق).

**الاقتران بالحقل فضفاض (قرار v201، §1.3):** الموسم يلتقط ``field_id`` نصّاً فقط — **لا تحقّق وجود الحقل هنا**
(الحقل ملك المنصّة؛ التحقّق يتطلّب منح قراءة عابراً للعزل). الحقل يُنشأ أوّلاً عبر API الحقول، والموسم يشير إليه.

**المنطق النقيّ لا يُكرَّر:** تصديق الحافّة في ``shared.security.trusted_tenant``؛ سلامة المرفق ومفتاحه في
``shared.security.season_logbook``؛ مخزن الكائنات في ``shared.storage.blob_store`` (مُختبَرة في tests_v9).
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from shared.security.season_logbook import (
    ERROR_LOGBOOK_MISSING,
    MAX_LOGBOOK_BYTES,
    PRESIGN_TTL_S,
    content_sha256,
    derive_logbook_key,
    detect_content_type,
    key_belongs_to,
)
from shared.security.trusted_tenant import (
    ERROR_REVIEWER_ROLE_REQUIRED,
    SEASON_REVIEWER_ROLE,
    TrustedTenantError,
    edge_body_sha256,
    has_reviewer_role,
    resolve_trusted_tenant,
    service_token_ok,
    verify_edge_attestation,
)
from shared.storage import blob_store

DATABASE_URL = os.getenv("DATABASE_URL", "")
_ENABLED_TRUE = {"1", "true", "yes", "on"}

router = APIRouter()


def _enabled() -> bool:
    return os.getenv("SEASON_ENTRY_ENABLED", "0").strip().lower() in _ENABLED_TRUE


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="SEASON-ENTRY disabled (SEASON_ENTRY_ENABLED)")


def _require_service_token(token: str | None) -> None:
    """توكن خدمة مخصّص fail-closed: غير مضبوط ⇒ 503 · غير مطابق/غائب ⇒ 401."""
    expected = os.getenv("SEASON_ENTRY_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503, detail="season entry not configured (SEASON_ENTRY_SERVICE_TOKEN)"
        )
    if not service_token_ok(token, expected):
        raise HTTPException(status_code=401, detail="season_entry_service_token_required")


def _require_tenant(x_tenant_id: str | None) -> str:
    """المستأجِر من الحافّة (SEC-3) — UUID صالح إلزاميّ (tenant_id في الجداول UUID)."""
    try:
        tenant = resolve_trusted_tenant(x_tenant_id, None)
    except TrustedTenantError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc
    try:
        return str(UUID(tenant))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from None


async def _connect():
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503, detail="season database not configured (DATABASE_URL unset)"
        )
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


async def _tenant_conn(tenant_id: str):
    """اتّصال قصير يضبط app.current_tenant (RLS فعّال — نمط scout-ingest/raster)."""
    conn = await _connect()
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
    return conn


# ── نماذج الطلب ─────────────────────────────────────────────────────────────────
class SeasonCropIn(BaseModel):
    variety_name: str = Field(min_length=1)
    crop_registry_ref: str | None = None
    sowing_date: date
    sowing_precision: str = "day"
    seed_rate_kg_ha: float | None = None


class SeasonDraftIn(BaseModel):
    field_id: str = Field(min_length=1)
    observed_at_from: date
    observed_at_to: date
    season_label: str | None = None
    source: str = "manual_logbook"
    notes: str | None = None
    draft_key: str | None = None
    crop: SeasonCropIn | None = None


class SeasonPatchIn(BaseModel):
    season_label: str | None = None
    observed_at_from: date | None = None
    observed_at_to: date | None = None
    notes: str | None = None


async def _load_status(conn, season_id: str) -> str | None:
    """trust_status للموسم ضمن مستأجِر الاتّصال (RLS)؛ None إن غاب/لمستأجِر آخر."""
    return await conn.fetchval("SELECT trust_status FROM season_records WHERE id = $1", season_id)


def _season_uuid(season_id: str) -> str:
    try:
        return str(UUID(season_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="season id must be a UUID") from None


# ── ١) POST /internal/seasons — إنشاء مسودّة (untrusted) ─────────────────────────
@router.post("/internal/seasons", status_code=201)
async def create_season_draft(
    body: SeasonDraftIn,
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """مسودّة untrusted لحقل موجود. idempotent على draft_key (لا نسخة عند إعادة الإرسال)."""
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    conn = await _tenant_conn(tenant)
    try:
        async with conn.transaction():
            # idempotency: نفس (tenant, field_id, draft_key) ⇒ أعِد الموجود لا نسخة (ux فريد v202)
            if body.draft_key:
                existing = await conn.fetchval(
                    "SELECT id FROM season_records WHERE field_id = $1 AND draft_key = $2",
                    body.field_id,
                    body.draft_key,
                )
                if existing:
                    return {"season_id": str(existing), "idempotent": True}
            season_id = await conn.fetchval(
                "INSERT INTO season_records "
                "(tenant_id, field_id, season_label, observed_at_from, observed_at_to, "
                " source, notes, draft_key, trust_status) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'untrusted') RETURNING id",
                tenant,
                body.field_id,
                body.season_label,
                body.observed_at_from,
                body.observed_at_to,
                body.source,
                body.notes,
                body.draft_key,
            )
            if body.crop is not None:
                await conn.execute(
                    "INSERT INTO season_crop "
                    "(season_id, tenant_id, variety_name, crop_registry_ref, sowing_date, "
                    " sowing_precision, seed_rate_kg_ha) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                    season_id,
                    tenant,
                    body.crop.variety_name,
                    body.crop.crop_registry_ref,
                    body.crop.sowing_date,
                    body.crop.sowing_precision,
                    body.crop.seed_rate_kg_ha,
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — DB/constraint error ⇒ 400 (bad input) or 503
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"season_id": str(season_id), "idempotent": False}


# ── ٢) PATCH /internal/seasons/{id} — تحديث ما دام untrusted؛ accepted ⇒ 409 ─────
@router.patch("/internal/seasons/{season_id}")
async def patch_season_draft(
    season_id: str,
    body: SeasonPatchIn,
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """تحديث تدريجيّ للمسودّة. **على موسم accepted ⇒ 409** (النقطة نفسها ترفض، §4-④).

    الحارس الذي لا يُختبَر من مدخله نصف حارس: تجميد v201 يحمي أعمدة المعايرة، لكن ترويسة الموسم
    (label/notes/dates) ليست منها — فالرفض هنا صريح على مستوى النقطة لا يُترَك للـtrigger.
    """
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    sid = _season_uuid(season_id)
    conn = await _tenant_conn(tenant)
    try:
        status = await _load_status(conn, sid)
        if status is None:
            raise HTTPException(status_code=404, detail="season not found")
        if status != "untrusted":
            raise HTTPException(status_code=409, detail="season_not_editable_after_accept")
        fields = body.model_dump(exclude_none=True)
        if not fields:
            raise HTTPException(status_code=400, detail="no updatable fields provided")
        cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
        await conn.execute(
            f"UPDATE season_records SET {cols}, updated_at = now() WHERE id = $1",
            sid,
            *fields.values(),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"season_id": sid, "updated": sorted(fields)}


# ── ٣) POST /internal/seasons/{id}/logbook — رفع المرفق (خدميّ، فحص محتوى) ───────
@router.post("/internal/seasons/{season_id}/logbook")
async def upload_logbook(
    season_id: str,
    request: Request,
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """رفع مرفق الدفتر (شرط القبول). **الرفع خدميّ لا presigned-PUT** (المالك اعتمد النمط):
    الخدمة تقرأ التدفّق إلى ملفّ مؤقّت (لا الذاكرة)، تفحص magic bytes + الحجم بعد الاستلام،
    تشتقّ المفتاح (خادميّاً، يضمّ season_id)، ترفع، وتخزّن logbook_image_ref. accepted ⇒ 409."""
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    sid = _season_uuid(season_id)
    conn = await _tenant_conn(tenant)
    try:
        status = await _load_status(conn, sid)
        if status is None:
            raise HTTPException(status_code=404, detail="season not found")
        if status != "untrusted":
            raise HTTPException(status_code=409, detail="season_not_editable_after_accept")

        # تدفّق إلى ملفّ مؤقّت مع حدّ صارم (لا Content-Length المزعوم؛ يُقاس بعد الاستلام)
        head = b""
        total = 0
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_LOGBOOK_BYTES:
                    raise HTTPException(status_code=413, detail="logbook_too_large")
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                tmp.write(chunk)
            if total == 0:
                raise HTTPException(status_code=400, detail="empty_logbook_body")
            detected = detect_content_type(head)
            if detected is None:
                raise HTTPException(status_code=415, detail="logbook_unsupported_type")
            content_type, ext = detected
            tmp.seek(0)
            data = tmp.read()
        sha = content_sha256(data)
        key = derive_logbook_key(tenant, sid, sha, ext)
        try:
            ref = blob_store.upload_bytes(key, data, content_type)
        except blob_store.BlobStoreError as exc:
            raise HTTPException(status_code=503, detail="logbook_store_unavailable") from exc
        await conn.execute(
            "UPDATE season_records SET logbook_image_ref = $2, updated_at = now() WHERE id = $1",
            sid,
            ref,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"season_id": sid, "content_type": content_type, "bytes": total}


# ── ٤) GET /internal/seasons/{id}/logbook — رابط presigned قصير العمر ────────────
@router.get("/internal/seasons/{season_id}/logbook")
async def get_logbook_url(
    season_id: str,
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """رابط presigned قصير العمر (≤300ث). المفتاح داخليّ لا يُسرَّب؛ فحص ملكيّة المفتاح
    (tenant+season) دفاع عمق خلف RLS ضدّ تسريب presigned عابر للمستأجِر/الموسم."""
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    sid = _season_uuid(season_id)
    conn = await _tenant_conn(tenant)
    try:
        ref = await conn.fetchval("SELECT logbook_image_ref FROM season_records WHERE id = $1", sid)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="season store unavailable") from exc
    finally:
        await conn.close()
    if ref is None:
        raise HTTPException(status_code=404, detail="season or logbook not found")
    # المفتاح المُشتقّ داخل الـref يجب أن يقع تحت مستأجِر+موسم المُتّصِل (دفاع عمق)
    obj_key = ref.split("://", 1)[-1].split("/", 1)[-1] if "://" in ref else ref
    # للـfile:// المفتاح يقع تحت LOCAL_DIR؛ نلتقط جزء season-logbooks/... للفحص
    idx = obj_key.find("season-logbooks/")
    check_key = obj_key[idx:] if idx >= 0 else obj_key
    if not key_belongs_to(check_key, tenant, sid):
        raise HTTPException(status_code=403, detail="logbook_ref_ownership_mismatch")
    try:
        url = blob_store.presigned_get_url(ref, PRESIGN_TTL_S)
    except blob_store.BlobStoreError as exc:
        raise HTTPException(status_code=503, detail="logbook_store_unavailable") from exc
    return {"url": url, "expires_in": PRESIGN_TTL_S}


# ── ٥) POST /internal/seasons/{id}/accept — القبول الحسّاس ───────────────────────
@router.post("/internal/seasons/{season_id}/accept")
async def accept_season(
    season_id: str,
    request: Request,
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_roles: str | None = Header(None, alias="X-Roles"),
    x_edge_attestation: str | None = Header(None, alias="X-Edge-Attestation"),
    x_edge_timestamp: str | None = Header(None, alias="X-Edge-Timestamp"),
):
    """القبول (يحرّر calibration_eligible). هويّة **مُصدَّقة من الحافّة** + دور season-reviewer + مرفق موجود.

    البرهان العاشر (تعديل المالك المُلزِم): مرجع دفتر ميّت (لا كائن خلفه) ⇒ القبول يُرفَض ``logbook_missing``.

    التصديق **مقيَّد بالوجهة** (شرط المالك ①): يُوقَّع على (الهويّة + method + path + body_hash + الوقت)
    فتصديق مسار بريء لا يُعاد لعبه على القبول. الخدمة تحسب method/path/body من طلبها المُستلَم لا من ترويسة.
    """
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    sid = _season_uuid(season_id)

    # §4-①: هويّة مُصدَّقة من الحافّة (HMAC مقيَّد بالوجهة) — بلا توقيع صالح لهذا المسار ⇒ 401
    body = await request.body()  # القبول بلا جسم ⇒ sha256(b"")؛ لكن نحسبه من المُستلَم لا نفترضه
    try:
        reviewer = verify_edge_attestation(
            user_id=x_user_id,
            roles=x_roles,
            method=request.method,
            path=request.url.path,
            body_sha256=edge_body_sha256(body),
            timestamp=x_edge_timestamp,
            attestation=x_edge_attestation,
            secret=os.getenv("SEASON_EDGE_HMAC_KEY"),
            now_epoch=datetime.now(UTC).timestamp(),
        )
    except TrustedTenantError as exc:
        raise HTTPException(status_code=401, detail=exc.code) from exc
    if not has_reviewer_role(x_roles, SEASON_REVIEWER_ROLE):
        raise HTTPException(status_code=403, detail=ERROR_REVIEWER_ROLE_REQUIRED)

    conn = await _tenant_conn(tenant)
    try:
        row = await conn.fetchrow(
            "SELECT trust_status, logbook_image_ref FROM season_records WHERE id = $1", sid
        )
        if row is None:
            raise HTTPException(status_code=404, detail="season not found")
        if row["trust_status"] == "accepted":
            raise HTTPException(status_code=409, detail="season_already_accepted")
        ref = row["logbook_image_ref"]
        # القبول يتطلّب مرفقاً صالحاً موجوداً فعلاً (HEAD) — مرجع ميّت ⇒ رفض
        if not ref or not blob_store.object_exists(ref):
            raise HTTPException(status_code=422, detail=ERROR_LOGBOOK_MISSING)
        await conn.execute(
            "UPDATE season_records "
            "SET trust_status = 'accepted', accepted_by = $2, accepted_at = now(), updated_at = now() "
            "WHERE id = $1",
            sid,
            reviewer,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_or_input_error(exc) from exc
    finally:
        await conn.close()
    return {"season_id": sid, "trust_status": "accepted", "accepted_by": reviewer}


# ── ٦) GET /internal/seasons?status=untrusted — استئناف المسودّات ────────────────
@router.get("/internal/seasons")
async def list_seasons(
    status: str = "untrusted",
    x_season_entry_token: str | None = Header(None, alias="X-Season-Entry-Token"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    """استئناف المسودّات (أو تصفية بالحالة). RLS يقصّ على مستأجِر الاتّصال."""
    _require_enabled()
    _require_service_token(x_season_entry_token)
    tenant = _require_tenant(x_tenant_id)
    if status not in ("untrusted", "accepted", "quarantined"):
        raise HTTPException(status_code=400, detail="invalid status filter")
    conn = await _tenant_conn(tenant)
    try:
        rows = await conn.fetch(
            "SELECT id, field_id, season_label, observed_at_from, observed_at_to, "
            "trust_status, logbook_image_ref IS NOT NULL AS has_logbook, "
            "accepted_by, accepted_at, created_at, updated_at "
            "FROM season_records WHERE trust_status = $1 ORDER BY updated_at DESC LIMIT 500",
            status,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="season store unavailable") from exc
    finally:
        await conn.close()
    return {"seasons": [dict(r) for r in rows], "count": len(rows)}


def _db_or_input_error(exc: Exception) -> HTTPException:
    """CHECK/trigger violation ⇒ 400 (مدخل غير صالح)؛ غيرها ⇒ 503 (لا 500، لا اختلاق)."""
    name = type(exc).__name__
    # asyncpg يرفع أخطاء قيود بأسماء *Error تنتهي بـIntegrityConstraint/Check/RaiseError
    msg = str(exc)
    if any(
        k in name
        for k in ("Check", "Integrity", "NotNull", "Restrict", "Exclusion", "RaiseError", "Unique")
    ):
        return HTTPException(status_code=400, detail=f"season_constraint_violation: {msg[:200]}")
    return HTTPException(status_code=503, detail="season store unavailable")
