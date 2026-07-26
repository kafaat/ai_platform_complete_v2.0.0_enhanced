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
  • POST …/{prescription_id}/machinery-export — INT-004 (شريحة المحوِّل): حزمة ISOXML
    قابلة للرفع، تُحلّ من ملفّ تحكّم مُدام (v216)، مُدامة مع لقطة غير قابلة للتغيير +
    checksum (EQUIPMENT_MANAGE). لا نقل فيزيائيّ/تنفيذ آلة — إنتاج الحزمة عند الحافّة فقط.
  • GET  …/machinery-export/{artifact_id}/download — تنزيل الحزمة المُدامة (FIELD_VIEW).

التصدير (GeoJSON/CSV) يتمّ في الواجهة (Blob/URL، بلا اعتماديّة). المسار المضمّن
(``export?format=isoxml`` بوحدات من الاستعلام) تطويريّ/مُميَّز فقط (PLATFORM_MANAGE)
ولا يُدام — المسار الإنتاجيّ هو ``machinery-export`` بمعرّف ملفّ تحكّم مُدام.

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


class MachineryExportRequest(BaseModel):
    """طلب إنتاج حزمة ISOXML قابلة للرفع من وصفة محفوظة + ملفّ تحكّم مُدام (SoR).

    ``machine_profile_id`` يشير إلى صفّ في ``machine_control_profiles`` (v216)
    مملوك للمستأجِر — لا يُقبل ملفّ تعريف حرّ من جسم الطلب كمسار إنتاج.
    """

    machine_profile_id: str = Field(..., min_length=1, max_length=64)
    crop: str | None = Field(default=None, max_length=120)


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
    vendor: str | None = Query(None, description="ISOXML: مورّد المُتحكِّم (مطلوب لـisoxml)"),
    controller: str | None = Query(None, description="ISOXML: عائلة المُتحكِّم"),
    task_controller_version: str | None = Query(None, description="ISOXML: إصدار Task Controller"),
    supported_units: str | None = Query(None, description="ISOXML: وحدات المُتحكِّم (مفصولة بفواصل)"),
    crop: str | None = Query(None, description="ISOXML: المحصول (وصفيّ)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يصدّر الوصفة المحفوظة لأجهزة التنفيذ.

    - ``format=shapefile`` ⇒ ZIP (.shp/.shx/.dbf/.prj) — اقتباس CultiWise.
    - ``format=isoxml`` ⇒ **ISOXML TaskData** حقيقيّ (INT-004): يُبنى من مناطق
      الوصفة المحفوظة + ملفّ قدرات المُتحكِّم المُمرَّر. **يفشل مُغلَقاً** عند ملفّ
      مُتحكِّم ناقص/غير متوافق أو وحدات مختلطة/غير مدعومة ⇒ 422 (لا TaskData جزئيّ).
      لا يقود جهازاً فعليّاً — يُنتِج الملفّ القابل للرفع فقط.

    معزول بالمستأجِر (RLS)؛ حقل/وصفة خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.
    """
    if fmt not in ("shapefile", "isoxml"):
        raise HTTPException(
            status_code=422,
            detail="صيغة غير مدعومة (المتاح: shapefile | isoxml)",
        )
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            row = await conn.fetchrow(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE prescription_id = $1 AND field_id = $2",
                prescription_id,
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تصدير الوصفة", e) from e
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
    if fmt == "isoxml":
        # DEV/PRIVILEGED compatibility path only. The CANONICAL production route is
        # POST .../machinery-export with a persisted machine_profile_id (resolves the
        # controller profile from the system of record, snapshots it, and persists a
        # durable checksummed artifact). This inline query-param profile is unrestricted
        # request input, so it is gated behind PLATFORM_MANAGE and never persists — it
        # exists for quick developer/operator checks, not as the normal production path.
        if not has_permission(user, Permission.PLATFORM_MANAGE):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INLINE_ISOXML_PRIVILEGED",
                    "message": (
                        "المسار المضمّن (وحدات المُتحكِّم من الاستعلام) تطويريّ/مُميَّز فقط؛ "
                        "استخدم POST .../machinery-export بمعرّف ملفّ تحكّم مُدام"
                    ),
                },
            )
        # INT-004: build a real ISOXML TaskData from the saved zones + the operator
        # controller profile. Fail-closed (422) on incomplete/incompatible machine
        # or mixed/unsupported units — never a partial file.
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


def _download_ref(field_id: str, prescription_id: str, artifact_id: str) -> str:
    """المرجع النسبيّ لتنزيل حزمة مُدامة (يُبنى منه العميل رابطاً كاملاً)."""
    return (
        f"/api/v1/fields/{field_id}/prescriptions/{prescription_id}"
        f"/machinery-export/{artifact_id}/download"
    )


@router.post("/api/v1/fields/{field_id}/prescriptions/{prescription_id}/machinery-export")
async def create_machinery_export(
    req: MachineryExportRequest,
    field_id: str = Path(..., description="معرّف الحقل"),
    prescription_id: str = Path(..., description="معرّف الوصفة المحفوظة"),
    user: UserSchema = Depends(require_permission(Permission.EQUIPMENT_MANAGE)),
):
    """المسار الإنتاجيّ القانونيّ لـINT-004 (شريحة المحوِّل، INT-004A).

    يحوّل عمليّةً مُصرَّحاً بها إلى **حزمة ISOXML قابلة للرفع إلى الآلة**، مُدامة مع
    checksum ولقطة ملفّ تحكّم **غير قابلة للتغيير**. الخطوات: (١) حلّ+تخويل الحقل/
    الوصفة/ملفّ التحكّم المُدام (RLS، لكلّ مستأجر)، (٢) تحقّق fail-closed من عقد
    ISOXMLTask، (٣) توليد TaskData، (٤) تغليف حتميّ إلى حزمة نهائيّة، (٥) إدامة
    الحزمة + بيانات وصفيّة/checksum غير قابلة للتحوير (append-only)، (٦) إرجاع مرجع
    تنزيل، (٧) القيد نفسه سجلّ منشأ/تدقيق (created_by/at).

    حدّ الصدق: لا يتّصل بمُتحكِّم، لا ينقل عبر CAN/ISOBUS، ولا يدّعي أنّ آلةً نفّذت
    المهمّة. ملفّ تعريف مفقود/غير نشط/خارج المستأجِر/غير متوافق ⇒ يفشل مُغلَقاً.
    """
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rx_row = await conn.fetchrow(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE prescription_id = $1 AND field_id = $2",
                prescription_id,
                field_id,
            )
            if rx_row is None:
                raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
            status = (
                rx_row.get("season_resolution_status")
                if hasattr(rx_row, "get")
                else rx_row["season_resolution_status"]
            )
            if status == "unresolved":
                _mode = os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower()
                if _mode == "enforce":
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "LEGACY_SEASON_UNRESOLVED",
                            "message": "الوصفة القديمة غير المحسومة مجمّدة ولا يمكن تصديرها",
                        },
                    )
            # Resolve the controller profile from the persisted system of record,
            # tenant-scoped by RLS. A miss (wrong tenant / no such id) returns None and
            # fails closed as 404; an inactive/ISOXML-incapable profile fails closed 422.
            prof_rec = await conn.fetchrow(
                f"SELECT {_PROFILE_SELECT_COLS} FROM machine_control_profiles "
                "WHERE profile_id = $1",
                req.machine_profile_id,
            )
            profile_row = _profile_row_from_record(prof_rec) if prof_rec is not None else None
            rx = _row_to_prescription(rx_row)
            try:
                pkg = generate_export_package(
                    rx,
                    profile_row,
                    approved_recommendation_id=prescription_id,
                    crop=req.crop or "",
                )
            except MachineryExportError as e:
                # "not found or not authorized" ⇒ 404 (profile invisible to tenant);
                # every other fail-closed reason (inactive, incompatible, mixed units) ⇒ 422.
                msg = str(e)
                if "not found or not authorized" in msg:
                    raise HTTPException(status_code=404, detail=f"ملفّ التحكّم: {msg}") from e
                raise HTTPException(status_code=422, detail=f"تعذّر بناء الحزمة: {msg}") from e
            # Persist the immutable, checksummed, machine-uploadable artifact (append-only).
            artifact = await conn.fetchrow(
                "INSERT INTO machinery_export_artifacts "
                "(tenant_id, field_id, prescription_id, machine_profile_id, export_format, "
                " profile_snapshot, package_sha256, package_bytes, package_bytes_len, zone_count, "
                " metadata, created_by, created_at) "
                "VALUES ($1::uuid, $2, $3, $4, 'isoxml', $5::jsonb, $6, $7, $8, $9, $10::jsonb, $11, now()) "
                "RETURNING artifact_id, created_at",
                str(user.tenant_id),
                field_id,
                prescription_id,
                req.machine_profile_id,
                json.dumps(pkg.profile_snapshot),
                pkg.package_sha256,
                pkg.package_bytes,
                len(pkg.package_bytes),
                pkg.zone_count,
                json.dumps({"product_type": rx["product_type"], "name": rx["name"]}),
                user.user_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا ادّعاء إنتاج)
        raise _db_unavailable("إنتاج حزمة التصدير", e) from e
    artifact_id = str(artifact["artifact_id"])
    created = artifact["created_at"]
    return {
        "artifact_id": artifact_id,
        "field_id": field_id,
        "prescription_id": prescription_id,
        "machine_profile_id": req.machine_profile_id,
        "export_format": "isoxml",
        "package_sha256": pkg.package_sha256,
        "package_bytes_len": len(pkg.package_bytes),
        "zone_count": pkg.zone_count,
        "profile_snapshot": pkg.profile_snapshot,
        "download_ref": _download_ref(field_id, prescription_id, artifact_id),
        "created_by": user.user_id,
        "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
        # Honest boundary: the package is produced + persisted at the platform edge.
        # No device delivery / consumption / physical execution is claimed here.
        "delivered_to_device": False,
        "machine_consumed": False,
    }


@router.get(
    "/api/v1/fields/{field_id}/prescriptions/{prescription_id}"
    "/machinery-export/{artifact_id}/download"
)
async def download_machinery_export(
    field_id: str = Path(..., description="معرّف الحقل"),
    prescription_id: str = Path(..., description="معرّف الوصفة"),
    artifact_id: str = Path(..., description="معرّف الحزمة المُدامة"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ينزّل حزمة ISOXML مُدامة (ZIP يحوي TASKDATA.XML) — معزول بالمستأجِر (RLS).

    الـchecksum يُعاد في ترويسة ``X-Package-SHA256`` كي يتحقّق العميل من السلامة.
    حزمة/حقل خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.
    """
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT package_bytes, package_sha256, package_bytes_len "
                "FROM machinery_export_artifacts "
                "WHERE artifact_id = $1::uuid AND field_id = $2 AND prescription_id = $3",
                artifact_id,
                field_id,
                prescription_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تنزيل الحزمة", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحزمة غير موجودة")
    return Response(
        content=bytes(row["package_bytes"]),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="TASKDATA.zip"',
            "X-Package-SHA256": row["package_sha256"],
        },
    )
