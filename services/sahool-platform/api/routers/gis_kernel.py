"""api/routers/gis_kernel.py — نواة GIS: buffer/union/split/validate (معاينة dry-run).

أربع نقاط **قراءة/معاينة** للعمليّات الهندسيّة الأساسيّة، محروسة بعلم
`FEATURE_GIS_KERNEL` (مُطفأ افتراضاً ⇒ 404؛ نمط الإغلاق المرن، يطابق
`SAHOOL_DECISION_DISPATCH`). كلّها **dry-run**: تحسب النتيجة في PostGIS وتُرجِعها
للمراجعة — **لا تكتب `fields.geom`** (لا كتابة هندسة صامتة).

  • `POST /api/v1/gis/buffer`   — ST_Buffer(geom, distance_m) على هندسة مُمرَّرة
                                  أو هندسة حقل (fields.geom، معزول RLS).
  • `POST /api/v1/gis/union`    — ST_Union لهندستين/حقلين (الدمج/merge).
  • `POST /api/v1/gis/split`    — ST_Split(geom, blade_line) ⇒ أجزاء.
  • `POST /api/v1/gis/validate` — ST_IsValid + ST_MakeValid (إصلاح طوبولوجيّ)،
                                  يُرجِع صالحاً/مُصلَّحاً + السبب.

التحقّق/التطبيع النقيّ لـGeoJSON في `api.gis_kernel` (مُختبَر وحدويّاً). الحساب في
PostGIS عبر `tenant_connection` (ST_GeomFromGeoJSON/ST_AsGeoJSON). fail-soft: أيّ
خطأ قاعدة ⇒ 503 عبر `_db_unavailable`. الصلاحيّة: `Permission.RECOMMENDATION_VIEW`.

لا `shapely` (غير مُثبَّت) ولا migration (يعمل على عمود fields.geom القائم،
v13_geospatial_core، EPSG:4326).
"""

from __future__ import annotations

import json as _json
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.gis_kernel import (
    GeoJSONError,
    normalize_geometry,
    require_lineal_blade,
    validate_distance_m,
)
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _gis_kernel_enabled() -> bool:
    """هل نواة GIS مُفعَّلة؟ (مُطفأة افتراضاً — إغلاق مرن، إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_GIS_KERNEL", "").strip().lower() in _TRUTHY


def _require_enabled() -> None:
    """يرفع 404 إن كانت الميزة مُطفأة (الإغلاق المرن — لا تسريب وجود النقطة)."""
    if not _gis_kernel_enabled():
        raise HTTPException(
            status_code=404,
            detail="نواة GIS غير مُفعَّلة (اضبط FEATURE_GIS_KERNEL).",
        )


def _http422(exc: GeoJSONError) -> HTTPException:
    """يحوّل خطأ تحقّق GeoJSON النقيّ إلى 422 برسالته العربيّة."""
    return HTTPException(status_code=422, detail=str(exc))


def _loads_geojson(value: Any) -> Any:
    """يفكّ ناتج ST_AsGeoJSON (asyncpg يعيده نصّاً خاماً بلا codec) إلى dict."""
    if value is None:
        return None
    return _json.loads(value) if isinstance(value, str) else value


async def _resolve_geometry(conn, *, geometry: Any, field_id: str | None, what_ar: str) -> dict:
    """يحلّ هندسة المُدخَل: إمّا GeoJSON مُمرَّر (مُطبَّع نقيّاً) أو fields.geom لحقل (RLS).

    أحدهما إلزاميّ تماماً (لا كلاهما، لا لا شيء). جلب الحقل معزول بـRLS عبر
    tenant_connection — لا يُرى إلّا حقل المستأجِر. الحقل بلا geom ⇒ 422 صريح.
    """
    if (geometry is None) == (field_id is None):
        raise HTTPException(
            status_code=422,
            detail=f"مرّر إمّا {what_ar} كـGeoJSON أو field_id لحقل — أحدهما تماماً.",
        )
    if geometry is not None:
        try:
            return normalize_geometry(geometry)
        except GeoJSONError as e:
            raise _http422(e) from e
    # field_id: نجلب هندسة الحقل كـGeoJSON (RLS يحصرها على المستأجِر).
    row = await conn.fetchrow(
        "SELECT ST_AsGeoJSON(geom) AS gj FROM fields WHERE field_id = $1",
        field_id,
    )
    if row is None or row["gj"] is None:
        raise HTTPException(
            status_code=422,
            detail="الحقل غير موجود (أو لمستأجِر آخر) أو بلا هندسة.",
        )
    return _loads_geojson(row["gj"])


# ─── buffer ──────────────────────────────────────────────────────────────


class BufferRequest(BaseModel):
    """مُدخَل buffer: هندسة GeoJSON أو field_id + مسافة بالأمتار (قد تكون سالبة)."""

    geometry: dict | None = None
    field_id: str | None = None
    distance_m: float


@router.post("/api/v1/gis/buffer")
async def gis_buffer(
    req: BufferRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """معاينة ST_Buffer لهندسة (مُمرَّرة أو fields.geom) بمسافة بالأمتار. 404 إن أُطفئ العلم.

    dry-run: يُرجِع الهندسة المُوسَّعة (GeoJSON) دون كتابة. المسافة بالأمتار تُطبَّق
    على geography (دقّة متريّة بصرف النظر عن خطّ العرض). 422 مُدخَل فاسد، 503 قاعدة.
    """
    _require_enabled()
    try:
        distance = validate_distance_m(req.distance_m)
    except GeoJSONError as e:
        raise _http422(e) from e
    try:
        async with tenant_connection(user) as conn:
            geom = await _resolve_geometry(
                conn, geometry=req.geometry, field_id=req.field_id, what_ar="الهندسة"
            )
            result = await conn.fetchval(
                "SELECT ST_AsGeoJSON(  ST_Buffer(ST_GeomFromGeoJSON($1)::geography, $2)::geometry)",
                _json.dumps(geom),
                distance,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ قاعدة/PostGIS ⇒ 503 صريح (fail-soft)
        raise _db_unavailable("حساب الـbuffer", e) from e
    return {
        "operation": "buffer",
        "dry_run": True,
        "distance_m": distance,
        "result": _loads_geojson(result),
    }


# ─── union (merge) ───────────────────────────────────────────────────────


class UnionRequest(BaseModel):
    """مُدخَل union: هندستان GeoJSON و/أو حقلان (geometry_a/field_id_a، geometry_b/field_id_b)."""

    geometry_a: dict | None = None
    field_id_a: str | None = None
    geometry_b: dict | None = None
    field_id_b: str | None = None


@router.post("/api/v1/gis/union")
async def gis_union(
    req: UnionRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """معاينة ST_Union (دمج/merge) لهندستين/حقلين. 404 إن أُطفئ العلم.

    dry-run: يُرجِع الهندسة المُوحَّدة (GeoJSON) دون كتابة. 422 مُدخَل فاسد، 503 قاعدة.
    """
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            geom_a = await _resolve_geometry(
                conn, geometry=req.geometry_a, field_id=req.field_id_a, what_ar="الهندسة الأولى"
            )
            geom_b = await _resolve_geometry(
                conn, geometry=req.geometry_b, field_id=req.field_id_b, what_ar="الهندسة الثانية"
            )
            result = await conn.fetchval(
                "SELECT ST_AsGeoJSON(  ST_Union(ST_GeomFromGeoJSON($1), ST_GeomFromGeoJSON($2)))",
                _json.dumps(geom_a),
                _json.dumps(geom_b),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حساب الـunion", e) from e
    return {"operation": "union", "dry_run": True, "result": _loads_geojson(result)}


# ─── split ───────────────────────────────────────────────────────────────


class SplitRequest(BaseModel):
    """مُدخَل split: هندسة مُستهدَفة (GeoJSON/field_id) + شفرة قطع خطّيّة (blade)."""

    geometry: dict | None = None
    field_id: str | None = None
    blade: dict


@router.post("/api/v1/gis/split")
async def gis_split(
    req: SplitRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """معاينة ST_Split لهندسة (مُمرَّرة أو fields.geom) بشفرة خطّيّة ⇒ أجزاء. 404 إن أُطفئ العلم.

    dry-run: يُرجِع مجموعة الأجزاء (GeometryCollection GeoJSON) + عددها دون كتابة.
    الشفرة يجب أن تكون خطّاً (يُفرَض نقيّاً). 422 مُدخَل فاسد، 503 قاعدة.
    """
    _require_enabled()
    try:
        blade = require_lineal_blade(req.blade)
    except GeoJSONError as e:
        raise _http422(e) from e
    try:
        async with tenant_connection(user) as conn:
            geom = await _resolve_geometry(
                conn, geometry=req.geometry, field_id=req.field_id, what_ar="الهندسة"
            )
            result = await conn.fetchval(
                "SELECT ST_AsGeoJSON(  ST_Split(ST_GeomFromGeoJSON($1), ST_GeomFromGeoJSON($2)))",
                _json.dumps(geom),
                _json.dumps(blade),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("حساب الـsplit", e) from e
    parsed = _loads_geojson(result)
    parts = parsed.get("geometries", []) if isinstance(parsed, dict) else []
    return {
        "operation": "split",
        "dry_run": True,
        "part_count": len(parts),
        "result": parsed,
    }


# ─── validate (topology) ─────────────────────────────────────────────────


class ValidateRequest(BaseModel):
    """مُدخَل validate: هندسة GeoJSON أو field_id لفحص/إصلاح الطوبولوجيا."""

    geometry: dict | None = None
    field_id: str | None = None


@router.post("/api/v1/gis/validate")
async def gis_validate(
    req: ValidateRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """معاينة ST_IsValid + ST_MakeValid (إصلاح طوبولوجيّ). 404 إن أُطفئ العلم.

    dry-run: يُرجِع صالحاً/غير صالح + سبب عدم الصلاحيّة (ST_IsValidReason) + الهندسة
    المُصلَّحة (GeoJSON) دون كتابة. 422 مُدخَل فاسد، 503 قاعدة.
    """
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            geom = await _resolve_geometry(
                conn, geometry=req.geometry, field_id=req.field_id, what_ar="الهندسة"
            )
            row = await conn.fetchrow(
                "SELECT "
                "  ST_IsValid(g) AS is_valid, "
                "  ST_IsValidReason(g) AS reason, "
                "  ST_AsGeoJSON(ST_MakeValid(g)) AS repaired "
                "FROM (SELECT ST_GeomFromGeoJSON($1) AS g) s",
                _json.dumps(geom),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("فحص/إصلاح الطوبولوجيا", e) from e
    return {
        "operation": "validate",
        "dry_run": True,
        "is_valid": row["is_valid"],
        "reason": row["reason"],
        "repaired": _loads_geojson(row["repaired"]),
    }
