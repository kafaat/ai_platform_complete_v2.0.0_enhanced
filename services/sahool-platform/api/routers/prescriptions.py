"""api/routers/prescriptions.py — وصفات المعدّل المتغيّر اليدويّة (Manual VRT)
==============================================================================
نظير FieldView "manual prescriptions" — وصفة **يدويّة** صرفة: المستخدِم يرسم مناطق
الإدارة (zones) على خريطة الحقل ويضبط لكلّ منطقة معدّلاً + وحدة، ثمّ يسمّيها ويختار
نوع المنتج {seed|fertility} ويحفظها.

صدق منهجيّ (مهمّ): هذا **ليس** توليداً agronomic آليّاً. الـGenerators القائمة
(``api/prescriptions.py`` بقواعد crop/lab، و``core/vrt_manual_maps.py``) تبقى في
الذاكرة (لا إدامة هنا)، و``useFieldPrescription`` في الواجهة قراءةُ تقطيع كمّيّ
(quantile) من الراستر — ليست وصفةً محفوظة. هذا الموجِّه يُديم وصفةً يدويّة قابلة
للقراءة فقط؛ لا اختراع مناطق/معدّلات.

النقاط (v95، جدول ``prescriptions`` معزول بالمستأجِر، RLS):
  • POST /api/v1/fields/{field_id}/prescriptions — حفظ وصفة (FIELD_EDIT).
  • GET  /api/v1/fields/{field_id}/prescriptions — سرد الوصفات (FIELD_VIEW، الأحدث أوّلاً).
  • GET  …/{prescription_id}/export?format=shapefile — Shapefile ZIP.
  • GET  …/{prescription_id}/export?format=isoxml&machine_profile_id=… — INT-004A (شريحة
    المحوِّل، EQUIPMENT_MANAGE): حزمة ISOXML قابلة للرفع تُحلّ من ملفّ تحكّم مُدام (v216)،
    مُدامة append-only مع لقطة غير قابلة للتغيير + checksum، **مُتماثِلة** (إزالة تكرار على
    الـchecksum الحتميّ). لا نقل فيزيائيّ/تنفيذ آلة — إنتاج/إدامة الحزمة عند الحافّة فقط.
  • GET  …/{prescription_id}/export?format=isoxml&artifact_id=… — تنزيل حزمة مُدامة سابقة.

ملاحظة ميزانيّة المسارات (Ratchet): طُوِيَت شريحة الآلات في نقطة ``export`` القائمة (لا مسار
جديد) احتراماً لسقف ``p2_6_route_budget_reduction`` (لا نموّ مسارات). التصدير (GeoJSON/CSV)
يتمّ في الواجهة. المسار المضمّن (``export?format=isoxml`` بوحدات من الاستعلام، بلا
machine_profile_id/artifact_id) تطويريّ/مُميَّز فقط (PLATFORM_MANAGE) ولا يُدام.

نمط الاستيراد من ``api.main`` يطابق ``routers/scouting.py`` (نمط P0): التبعيّات
(``get_current_user``/``UserSchema``/RLS) تبقى في ``main`` ويستوردها هذا الموجِّه؛
و``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات) فيُحلّ
الاستيراد الدائريّ. SQL بارامتريّ بالكامل (لا حقن).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from api.machinery_export import (
    MachineryExportError,
    build_prescription_isoxml,
    generate_export_package,
)
from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    has_permission,
    require_permission,
    tenant_connection,
)
from api.prescription_shapefile import build_shapefile_zip

logger = logging.getLogger(__name__)

router = APIRouter()

# أنواع المنتج المسموحة (يدويّ صرف — لا يتجاوز ما تنتجه الواجهة فعلاً).
_PRODUCT_TYPES = {"seed", "fertility"}

# أعمدة القراءة لجدول prescriptions (v95) — مطابقة لمخرَج الحفظ.
_RX_SELECT_COLS = "prescription_id, field_id, season_id, season_resolution_status, name, product_type, zones, created_by, created_at"


# ─── النماذج ─────────────────────────────────────────────────────


class PrescriptionZone(BaseModel):
    """منطقة إدارة واحدة: هندسة GeoJSON يرسمها المستخدِم + معدّل + وحدة."""

    geometry: dict  # GeoJSON Polygon (يرسمه المستخدِم في الواجهة)
    rate: float  # المعدّل (seeds/m² أو kg/ha) — يضبطه المستخدِم
    unit: str  # الوحدة (مثل "seeds/m2" أو "kg/ha")


class PrescriptionCreateRequest(BaseModel):
    """طلب حفظ وصفة يدويّة. ``prescription_id`` معرّف العميل (idempotency)."""

    prescription_id: str = Field(..., min_length=1, max_length=128)
    season_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=200)
    product_type: str = Field(default="seed")
    zones: list[PrescriptionZone] = Field(default_factory=list)


# أعمدة قراءة ملفّ التحكّم المُدام (v216) — بالترتيب الذي يتوقّعه resolve_persisted_profile.
_PROFILE_SELECT_COLS = (
    "profile_id, equipment_id, vendor, controller_model, task_controller_version, "
    "firmware_version, unit_system, supported_units, supports_isoxml, active"
)


def _profile_row_from_record(rec) -> dict:
    """يحوّل صفّ machine_control_profiles إلى dict؛ ``supported_units`` (jsonb) قد
    يعود نصّاً من asyncpg فيُفكَّك إلى قائمة (وإلّا فشل مُغلَق لاحقاً على الوحدات)."""
    units = rec["supported_units"]
    if isinstance(units, str):
        try:
            units = json.loads(units)
        except (ValueError, TypeError):
            units = []
    return {
        "profile_id": rec["profile_id"],
        "equipment_id": rec["equipment_id"],
        "vendor": rec["vendor"],
        "controller_model": rec["controller_model"],
        "task_controller_version": rec["task_controller_version"],
        "firmware_version": rec["firmware_version"],
        "unit_system": rec["unit_system"],
        "supported_units": units if isinstance(units, list) else [],
        "supports_isoxml": rec["supports_isoxml"],
        "active": rec["active"],
    }


def _prescription_content_digest(
    *, field_id: str, season_id: str | None, name: str, product_type: str, zones: list
) -> str:
    """Stable sha256 over the content-bearing fields — used to tell an idempotent
    replay (same id, same content) from an idempotency CONFLICT (same id, different
    content). Canonical JSON (sorted keys, compact) so it is order-stable."""
    canon = json.dumps(
        {
            "field_id": field_id,
            "season_id": season_id,
            "name": name,
            "product_type": product_type,
            "zones": zones,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _row_to_prescription(row) -> dict:
    """يحوّل صفّ prescriptions إلى dict (مفتاح prescription_id).

    نقيّ (لا I/O) ليُختبَر بـunit بلا قاعدة حيّة. ``zones`` JSONB قد يعود نصّاً
    (asyncpg) فيُفكَّك؛ إن كان قائمةً أصلاً (mock) يُمرَّر كما هو. ``created_at``
    (timestamptz) يُنسَّق ISO؛ نصّاً أصلاً (mock) يُمرَّر كما هو.
    """
    zones = row["zones"]
    if isinstance(zones, str):
        try:
            zones = json.loads(zones)
        except (ValueError, TypeError):
            zones = []
    created = row["created_at"]
    created_iso = created.isoformat() if hasattr(created, "isoformat") else (created or "")
    return {
        "prescription_id": row["prescription_id"],
        "field_id": row["field_id"],
        "season_id": row.get("season_id") if hasattr(row, "get") else row["season_id"],
        "season_resolution_status": (
            row.get("season_resolution_status")
            if hasattr(row, "get")
            else row["season_resolution_status"]
        ),
        "name": row["name"],
        "product_type": row["product_type"],
        "zones": zones if isinstance(zones, list) else [],
        "created_by": row["created_by"],
        "created_at": created_iso,
    }


@router.post("/api/v1/fields/{field_id}/prescriptions")
async def create_prescription(
    req: PrescriptionCreateRequest,
    field_id: str = Path(..., description="معرّف الحقل لحفظ وصفته"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحفظ وصفة معدّل متغيّر **يدويّة** للحقل (معزولة بالمستأجِر، RLS).

    يتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ يُدرِج الوصفة في
    ``prescriptions`` (v95). idempotent عبر ``ON CONFLICT (prescription_id) DO NOTHING``
    (إعادة الإرسال لا تُكرّر). يُرجِع الوصفة المحفوظة. صدق: القاعدة غير مفعّلة
    (``DATABASE_URL``) ⇒ 503 موثَّق (لا ادّعاء حفظ)؛ نوع منتج غير مدعوم ⇒ 422.
    """
    season_mode = os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower()
    if season_mode not in {"audit", "enforce"}:
        season_mode = "audit"
    if not req.season_id and season_mode == "enforce":
        raise HTTPException(status_code=422, detail={"code": "SEASON_CONTEXT_REQUIRED"})
    if not req.season_id:
        logger.warning(
            "fii prescription missing season context field_id=%s mode=%s", field_id, season_mode
        )
    if req.product_type not in _PRODUCT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"نوع المنتج غير مدعوم (المسموح: {sorted(_PRODUCT_TYPES)})",
        )
    if _DB_POOL is None:
        raise HTTPException(
            status_code=503,
            detail="تعذّر حفظ الوصفة (القاعدة غير مفعّلة DATABASE_URL أو الهجرات غير مطبّقة).",
        )
    zones_payload = [z.model_dump() for z in req.zones]
    req_digest = _prescription_content_digest(
        field_id=field_id,
        season_id=req.season_id,
        name=req.name,
        product_type=req.product_type,
        zones=zones_payload,
    )
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            # RETURNING lets us tell an actual insert from a no-op conflict — the
            # ``persisted`` flag must be HONEST (never claim a write that did not happen).
            inserted_id = await conn.fetchval(
                "INSERT INTO prescriptions "
                "(prescription_id, tenant_id, field_id, season_id, season_resolution_status, name, product_type, "
                " zones, created_by, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9, now()) "
                "ON CONFLICT (prescription_id) DO NOTHING "
                "RETURNING prescription_id",
                req.prescription_id,
                str(user.tenant_id),
                field_id,
                req.season_id,
                "resolved" if req.season_id else "unresolved",
                req.name,
                req.product_type,
                json.dumps(zones_payload),
                user.user_id,
            )
            if inserted_id is None:
                # Conflict: a row with this prescription_id already exists. Read it back
                # UNDER RLS (tenant-scoped) to decide idempotent-replay vs a real conflict.
                existing = await conn.fetchrow(
                    f"SELECT {_RX_SELECT_COLS} FROM prescriptions WHERE prescription_id = $1",
                    req.prescription_id,
                )
                if existing is None:
                    # The id exists but is invisible to this tenant ⇒ the (global) PK is
                    # owned by another tenant. Never claim persistence — surface a conflict.
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "IDEMPOTENCY_CONFLICT",
                            "reason": "prescription_id is already in use",
                        },
                    )
                stored = _row_to_prescription(existing)
                stored_digest = _prescription_content_digest(
                    field_id=stored["field_id"],
                    season_id=stored["season_id"],
                    name=stored["name"],
                    product_type=stored["product_type"],
                    zones=stored["zones"],
                )
                if stored_digest != req_digest:
                    # Same id, different content ⇒ a genuine idempotency conflict.
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "IDEMPOTENCY_CONFLICT",
                            "reason": "prescription_id already exists with different content",
                        },
                    )
                # Idempotent replay of identical content: return the STORED row, and be
                # honest that nothing new was written.
                return {**stored, "persisted": False, "idempotent_replay": True}
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) / 409 (تعارض idempotency) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا ادّعاء حفظ)
        raise _db_unavailable("حفظ الوصفة", e) from e
    return {
        "prescription_id": req.prescription_id,
        "field_id": field_id,
        "season_id": req.season_id,
        "season_resolution_status": "resolved" if req.season_id else "unresolved",
        "name": req.name,
        "product_type": req.product_type,
        "zones": zones_payload,
        "created_by": user.user_id,
        "persisted": True,
        "idempotent_replay": False,
    }


@router.get("/api/v1/fields/{field_id}/prescriptions")
async def list_prescriptions(
    field_id: str = Path(..., description="معرّف الحقل لجلب وصفاته"),
    include_legacy: bool = Query(
        False, description="إظهار السجلات القديمة غير المحسومة للإدارة فقط"
    ),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """وصفات الحقل المحفوظة (الأحدث أوّلاً) — معزولة بالمستأجِر (RLS).

    تتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ تُرجِع
    ``{field_id, prescriptions, total}``. صدق: القاعدة غير مفعّلة (``DATABASE_URL``)
    ⇒ قائمة فارغة + سبب (لا وصفات مخترَعة)؛ تعذّر القاعدة أثناء التنفيذ ⇒ 503 موثَّق.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "prescriptions": [],
            "total": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا وصفات مُخزَّنة",
        }
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE field_id = $1 "
                "AND ($2::boolean OR season_resolution_status <> 'unresolved') "
                "ORDER BY created_at DESC",
                field_id,
                # Audit-mode (default) shows legacy 'unresolved' rows so v193 does not
                # silently hide existing prescriptions; only enforce mode hides them
                # unless include_legacy is explicitly requested.
                include_legacy
                or os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower() != "enforce",
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع وصفات)
        raise _db_unavailable("جلب الوصفات", e) from e
    items = [_row_to_prescription(r) for r in rows]
    return {"field_id": field_id, "prescriptions": items, "total": len(items)}


@router.get("/api/v1/fields/{field_id}/prescriptions/{prescription_id}/export")
async def export_prescription(
    field_id: str = Path(..., description="معرّف الحقل"),
    prescription_id: str = Path(..., description="معرّف الوصفة"),
    fmt: str = Query("shapefile", alias="format", description="الصيغة (shapefile | isoxml)"),
    machine_profile_id: str | None = Query(
        None, description="ISOXML القانونيّ: معرّف ملفّ تحكّم مُدام (machine_control_profiles)"
    ),
    artifact_id: str | None = Query(
        None, description="ISOXML: تنزيل حزمة مُدامة سابقة بمعرّفها (لا إعادة توليد)"
    ),
    vendor: str | None = Query(None, description="ISOXML (dev): مورّد المُتحكِّم"),
    controller: str | None = Query(None, description="ISOXML (dev): عائلة المُتحكِّم"),
    task_controller_version: str | None = Query(
        None, description="ISOXML (dev): إصدار Task Controller"
    ),
    supported_units: str | None = Query(
        None, description="ISOXML (dev): وحدات المُتحكِّم (مفصولة بفواصل)"
    ),
    crop: str | None = Query(None, description="ISOXML: المحصول (وصفيّ)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يصدّر الوصفة المحفوظة لأجهزة التنفيذ.

    - ``format=shapefile`` ⇒ ZIP (.shp/.shx/.dbf/.prj) — اقتباس CultiWise.
    - ``format=isoxml&machine_profile_id=…`` ⇒ **المسار الإنتاجيّ القانونيّ لـINT-004A**
      (يتطلّب EQUIPMENT_MANAGE): يحلّ ملفّ تحكّم مُدام (system of record، معزول بالمستأجِر)،
      يتحقّق fail-closed من عقد ISOXMLTask، يولّد ISO11783 TaskData، يغلّفه حتميّاً في حزمة
      ISOXML قابلة للرفع، **ويُديم أثراً append-only غير قابل للتحوير** بلقطة ملفّ تعريف مجمّدة
      + checksum. **مُتماثِل (idempotent):** إعادة الاستدعاء بنفس المدخلات تعيد الأثر نفسه (لا
      صفّ مكرّر — إزالة تكرار على checksum الحتميّ). يعيد ZIP + ترويستَي X-Artifact-Id / X-Package-SHA256.
    - ``format=isoxml&artifact_id=…`` ⇒ تنزيل حزمة مُدامة سابقة (ZIP + X-Package-SHA256)، بلا توليد.
    - ``format=isoxml`` بوحدات مُتحكِّم مضمّنة (vendor/controller/…): مسار تطويريّ/مُميَّز فقط
      (PLATFORM_MANAGE)، لا يُدام — للفحص السريع لا للإنتاج.

    حدّ الصدق: يُنتِج/يُديم الملفّ القابل للرفع عند حافّة المنصّة فقط — لا يتّصل بمُتحكِّم، لا
    ينقل عبر CAN/ISOBUS، ولا يدّعي أنّ آلةً استهلكت/نفّذت المهمّة. معزول بالمستأجِر (RLS)؛
    حقل/وصفة/أثر خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.
    """
    if fmt not in ("shapefile", "isoxml"):
        raise HTTPException(
            status_code=422,
            detail="صيغة غير مدعومة (المتاح: shapefile | isoxml)",
        )
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    rx: dict | None = None
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            # ── ISOXML download of a previously-persisted artifact (no regeneration) ──
            if fmt == "isoxml" and artifact_id:
                art = await conn.fetchrow(
                    "SELECT package_bytes, package_sha256 FROM machinery_export_artifacts "
                    "WHERE artifact_id = $1::uuid AND field_id = $2 AND prescription_id = $3",
                    artifact_id,
                    field_id,
                    prescription_id,
                )
                if art is None:
                    raise HTTPException(status_code=404, detail="الحزمة غير موجودة")
                return Response(
                    content=bytes(art["package_bytes"]),
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": 'attachment; filename="TASKDATA.zip"',
                        "X-Package-SHA256": art["package_sha256"],
                    },
                )
            row = await conn.fetchrow(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE prescription_id = $1 AND field_id = $2",
                prescription_id,
                field_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
            status = (
                row.get("season_resolution_status")
                if hasattr(row, "get")
                else row["season_resolution_status"]
            )
            if status == "unresolved":
                # Audit-only by default (Increment 4): freezing legacy rows from export is an
                # ENFORCE-mode behaviour. In audit mode we log and allow, so applying v193
                # (which defaults every legacy row to 'unresolved') does NOT retroactively
                # freeze existing prescriptions. Flip to enforce only after legacy rows are
                # triaged/backfilled.
                _season_mode = os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower()
                if _season_mode == "enforce":
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "LEGACY_SEASON_UNRESOLVED",
                            "message": "الوصفة القديمة غير المحسومة مجمّدة ولا يمكن تصديرها للتنفيذ",
                        },
                    )
                logger.warning(
                    "fii prescription export of unresolved legacy row (audit mode, allowed) prescription_id=%s",
                    row["prescription_id"] if hasattr(row, "__getitem__") else "?",
                )
            rx = _row_to_prescription(row)
            # ── CANONICAL INT-004A: persisted-profile machinery export ──────────────
            if fmt == "isoxml" and machine_profile_id:
                # Producing + persisting a machine-uploadable artifact is a machinery-
                # management action, above the FIELD_VIEW base scope.
                if not has_permission(user, Permission.EQUIPMENT_MANAGE):
                    raise HTTPException(
                        status_code=403,
                        detail=f"الدور '{user.role.value}' لا يملك صلاحية '{Permission.EQUIPMENT_MANAGE.value}'",
                    )
                # Resolve the controller profile from the persisted system of record,
                # tenant-scoped by RLS. A miss (wrong tenant / no such id) → None → 404;
                # an inactive/ISOXML-incapable profile fails closed 422.
                prof_rec = await conn.fetchrow(
                    f"SELECT {_PROFILE_SELECT_COLS} FROM machine_control_profiles "
                    "WHERE profile_id = $1",
                    machine_profile_id,
                )
                profile_row = _profile_row_from_record(prof_rec) if prof_rec is not None else None
                try:
                    pkg = generate_export_package(
                        rx,
                        profile_row,
                        approved_recommendation_id=prescription_id,
                        crop=crop or "",
                    )
                except MachineryExportError as e:
                    msg = str(e)
                    if "not found or not authorized" in msg:
                        raise HTTPException(status_code=404, detail=f"ملفّ التحكّم: {msg}") from e
                    raise HTTPException(status_code=422, detail=f"تعذّر بناء الحزمة: {msg}") from e
                # Idempotent persistence: packaging is deterministic, so a repeat request
                # for the same (prescription, profile, content) returns the SAME immutable
                # artifact rather than appending a duplicate — keeping this GET safe.
                existing = await conn.fetchval(
                    "SELECT artifact_id FROM machinery_export_artifacts "
                    "WHERE prescription_id = $1 AND machine_profile_id = $2 AND package_sha256 = $3",
                    prescription_id,
                    machine_profile_id,
                    pkg.package_sha256,
                )
                if existing is None:
                    existing = await conn.fetchval(
                        "INSERT INTO machinery_export_artifacts "
                        "(tenant_id, field_id, prescription_id, machine_profile_id, export_format, "
                        " profile_snapshot, package_sha256, package_bytes, package_bytes_len, "
                        " zone_count, metadata, created_by, created_at) "
                        "VALUES ($1::uuid, $2, $3, $4, 'isoxml', $5::jsonb, $6, $7, $8, $9, "
                        " $10::jsonb, $11, now()) RETURNING artifact_id",
                        str(user.tenant_id),
                        field_id,
                        prescription_id,
                        machine_profile_id,
                        json.dumps(pkg.profile_snapshot),
                        pkg.package_sha256,
                        pkg.package_bytes,
                        len(pkg.package_bytes),
                        pkg.zone_count,
                        json.dumps({"product_type": rx["product_type"], "name": rx["name"]}),
                        user.user_id,
                    )
                return Response(
                    content=pkg.package_bytes,
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": 'attachment; filename="TASKDATA.zip"',
                        "X-Artifact-Id": str(existing),
                        "X-Package-SHA256": pkg.package_sha256,
                    },
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تصدير الوصفة", e) from e
    # rx is set for every non-early-return path below.
    assert rx is not None
    if fmt == "isoxml":
        # DEV/PRIVILEGED compatibility path only (no machine_profile_id / artifact_id given).
        # The controller profile comes from unrestricted query params and NOTHING is persisted,
        # so it is gated behind PLATFORM_MANAGE — quick developer/operator checks only. The
        # canonical production path is machine_profile_id (persisted SoR + durable artifact).
        if not has_permission(user, Permission.PLATFORM_MANAGE):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INLINE_ISOXML_PRIVILEGED",
                    "message": (
                        "المسار المضمّن (وحدات المُتحكِّم من الاستعلام) تطويريّ/مُميَّز فقط؛ "
                        "استخدم format=isoxml&machine_profile_id=… بمعرّف ملفّ تحكّم مُدام"
                    ),
                },
            )
        try:
            xml = build_prescription_isoxml(
                rx,
                {
                    "vendor": vendor,
                    "controller": controller,
                    "task_controller_version": task_controller_version,
                    "supported_units": supported_units,
                },
                approved_recommendation_id=prescription_id,
                crop=crop or "",
            )
        except MachineryExportError as e:
            raise HTTPException(status_code=422, detail=f"تعذّر بناء ISOXML: {e}") from e
        return Response(
            content=xml,
            media_type="application/xml",
            headers={"Content-Disposition": 'attachment; filename="TASKDATA.xml"'},
        )
    try:
        data = build_shapefile_zip(rx["name"], rx["product_type"], rx["zones"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"تعذّر بناء Shapefile: {e}") from e
    except ImportError:  # pragma: no cover — مكتبة pyshp غير مُثبَّتة في هذه البيئة
        raise HTTPException(status_code=503, detail="مكتبة تصدير Shapefile غير متاحة") from None
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="prescription.zip"'},
    )
