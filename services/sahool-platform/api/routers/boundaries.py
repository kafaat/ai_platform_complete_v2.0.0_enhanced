"""api/routers/boundaries.py — نقاط حدود الحقل (Field Boundaries)
=================================================================
أوّل شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات، نماذج الطلب، الأذونات) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _BOUNDARY_REVIEW_STATES,
    BoundaryCleanRequest,
    BoundaryReviewRequest,
    BoundaryScoreRequest,
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.patch("/api/v1/fields/{field_id}/boundary/review")
async def review_field_boundary(
    field_id: str,
    req: BoundaryReviewRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """مراجعة بشريّة (HIL) لحدّ الحقل: يضبط review_status (approve/reject/needs_edit).

    يتحقّق أنّ الحالة ضمن المجموعة المسموحة (422 وإلّا) قبل القاعدة، ثمّ يُحدِّث
    field_boundaries.review_status للحقل ضمن سياق المستأجِر (RLS). 404 لو لا حدّ
    لهذا الحقل ضمن المستأجِر؛ 503 عند تعذّر القاعدة. يردّ الحالة المُحدَّثة + field_id.

    لا يُصدِر حدث domain في هذا الـPR عمداً: لتفادي خطأ الحدث غير المُسجَّل السابق،
    لا نخترع EventType جديداً غير مُعرَّف — إصدار حدث مراجعة بـEventType صالح متابعة.
    """
    if req.review_status not in _BOUNDARY_REVIEW_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "حالة مراجعة غير صالحة — المسموح: approved|rejected|needs_edit.",
                "code": "invalid_review_status",
            },
        )
    try:
        async with tenant_connection(user) as conn:
            updated = await conn.fetchval(
                "UPDATE field_boundaries SET review_status = $1 "
                "WHERE field_id = $2 RETURNING field_id",
                req.review_status,
                field_id,
            )
            if updated is None:
                raise HTTPException(
                    status_code=404,
                    detail="لا حدّ لهذا الحقل ضمن هذا المستأجِر",
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("مراجعة حدّ الحقل", e) from e
    return {"field_id": field_id, "review_status": req.review_status}


@router.post("/api/v1/fields/{field_id}/boundary/score")
async def score_field_boundary(
    field_id: str,
    req: BoundaryScoreRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يهدّف ثقة حدّ الحقل ويُخزّنها (confidence as first-class).

    يستدعي boundary_confidence.score_boundary (دالّة نقيّة حتميّة لا ترمي)، ثمّ
    يُحدِّث field_boundaries: confidence_score (من النتيجة)، source_type (إن أُرسل)،
    ويضبط review_status='needs_edit' عند review_recommended (وإلّا يُترَك كما هو —
    لا يُلغى قرار مراجِع سابق). كلّه ضمن سياق المستأجِر (RLS).
    404 لو لا حدّ لهذا الحقل؛ 503 عند تعذّر القاعدة. يردّ نتيجة التهديف الكاملة.

    مصدر الـprops (#15):
      - إن أُرسلت props صراحةً في الجسم: تُهدَّف كما هي (توافق خلفيّ، CI-safe).
      - إن لم تُرسَل (None): تُشتقّ الخصائص البنيويّة من geom المخزَّنة عبر استعلام
        PostGIS واحد حتميّ (is_valid, vertex_count, area_ha, ring_count,
        self_intersections) ثمّ تُهدَّف؛ وتُضمَّن الخصائص المُشتقّة في الردّ تحت
        "derived_props" شفافيّةً.

    صدق:
      - self_intersections المُشتقّ هنا مؤشّر أفضل-جهد 0/1 (وجود لا عدد حقيقيّ):
        نستنتجه من ST_IsValidReason ILIKE '%self-intersection%' فقط، وهو كافٍ لأنّ
        score_boundary لا تتفرّع إلّا على >0.
      - temporal_agreement يبقى غائباً (None): التهديف الهندسيّ أحاديّ التاريخ لا
        يحمل أيّ اتّفاق زمنيّ — كما تُنوّه boundary_confidence نفسها.
    """
    from api.boundary_confidence import score_boundary

    # استعلام اشتقاق الخصائص البنيويّة من geom المخزَّنة (PostGIS حتميّ، $1=field_id).
    # self_intersections مؤشّر وجود 0/1 (لا عدد حقيقيّ) مُستنتَج من ST_IsValidReason —
    # كافٍ لأنّ score_boundary لا تتفرّع إلّا على >0 (انظر docstring أعلاه).
    _DERIVED_PROPS_SQL = (
        "SELECT "
        "ST_IsValid(geom) AS is_valid, "
        "ST_NPoints(ST_ExteriorRing(geom)) AS vertex_count, "
        "ST_Area(geom::geography) / 10000.0 AS area_ha, "
        "ST_NRings(geom) AS ring_count, "
        "CASE WHEN NOT ST_IsValid(geom) "
        "AND ST_IsValidReason(geom) ILIKE '%self-intersection%' "
        "THEN 1 ELSE 0 END AS self_intersections "
        "FROM field_boundaries WHERE field_id = $1"
    )

    derived_props: dict | None = None
    try:
        async with tenant_connection(user) as conn:
            if req.props is None:
                # اشتقاق props من الهندسة المخزَّنة (لا توجد props من العميل).
                drow = await conn.fetchrow(_DERIVED_PROPS_SQL, field_id)
                if drow is None:
                    raise HTTPException(
                        status_code=404,
                        detail="لا حدّ لهذا الحقل ضمن هذا المستأجِر",
                    )
                derived_props = {
                    "is_valid": drow["is_valid"],
                    "vertex_count": drow["vertex_count"],
                    "area_ha": drow["area_ha"],
                    "ring_count": drow["ring_count"],
                    "self_intersections": drow["self_intersections"],
                    # temporal_agreement غائب عمداً (None): تهديف أحاديّ التاريخ.
                    "temporal_agreement": None,
                }
                props = derived_props
            else:
                props = req.props

            result = score_boundary(props)
            confidence = result["confidence"]
            new_review_status = "needs_edit" if result["review_recommended"] else None

            # تحديث واحد: confidence_score دائماً؛ source_type عند إرساله؛ و
            # review_status='needs_edit' فقط عند التوصية (COALESCE يُبقي الموجود وإلّا).
            updated = await conn.fetchval(
                "UPDATE field_boundaries SET "
                "confidence_score = $1, "
                "source_type = COALESCE($2, source_type), "
                "review_status = COALESCE($3, review_status) "
                "WHERE field_id = $4 RETURNING field_id",
                confidence,
                req.source_type,
                new_review_status,
                field_id,
            )
            if updated is None:
                raise HTTPException(
                    status_code=404,
                    detail="لا حدّ لهذا الحقل ضمن هذا المستأجِر",
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("تهديف حدّ الحقل", e) from e

    # شفافيّةً: نُضمّن الخصائص المُشتقّة في الردّ عند اشتقاقها من الهندسة.
    if derived_props is not None:
        result["derived_props"] = derived_props
    return result


@router.post("/api/v1/fields/{field_id}/boundary/clean")
async def clean_field_boundary(
    field_id: str,
    req: BoundaryCleanRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يطبّق مرحلة التنظيف الطوبولوجيّ الحتميّة (#15) على حدّ الحقل المخزَّن.

    يستدعي دالّة v59 ``sahool_clean_boundary_geom(geom, tolerance_m)`` (MakeValid +
    إزالة الرؤوس المكرّرة + إبقاء المضلّع الأكبر + تبسيط حافظ للطوبولوجيا) عبر
    UPDATE واحد ضمن سياق المستأجِر (RLS). حتميّ بالكامل (بلا ML): نفس المدخل ينتج
    نفس المخرج. شبه-عديم الأثر عند الإعادة (re-running على مضلّع نظيف ≈ no-op).

    يقرأ ST_NPoints/ST_IsValid قبل وبعد لتقرير التغيّر. 404 لو لا حدّ لهذا الحقل؛
    503 عند تعذّر القاعدة. يردّ {field_id, vertex_count_before, vertex_count_after,
    is_valid_before, is_valid_after, tolerance_m}.

    لا يُصدِر حدث domain عمداً (انضباط #229): لا نخترع EventType غير مُعرَّف.
    """
    try:
        async with tenant_connection(user) as conn:
            # قراءة الحالة قبل التنظيف (تتحقّق أيضاً من وجود الصفّ ⇒ 404).
            before = await conn.fetchrow(
                "SELECT ST_NPoints(geom) AS vertex_count_before, "
                "ST_IsValid(geom) AS is_valid_before "
                "FROM field_boundaries WHERE field_id = $1",
                field_id,
            )
            if before is None:
                raise HTTPException(
                    status_code=404,
                    detail="لا حدّ لهذا الحقل ضمن هذا المستأجِر",
                )
            # التنظيف الحتميّ في عبارة واحدة، مع إرجاع الحالة بعد التحديث.
            after = await conn.fetchrow(
                "UPDATE field_boundaries "
                "SET geom = sahool_clean_boundary_geom(geom, $2) "
                "WHERE field_id = $1 AND geom IS NOT NULL "
                "RETURNING ST_NPoints(geom) AS vertex_count_after, "
                "ST_IsValid(geom) AS is_valid_after",
                field_id,
                req.tolerance_m,
            )
            # geom كانت NULL (لا تحديث) — لا حدّ هندسيّ قابل للتنظيف.
            if after is None:
                raise HTTPException(
                    status_code=404,
                    detail="لا هندسة (geom) لهذا الحدّ — لا شيء لتنظيفه",
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("تنظيف حدّ الحقل طوبولوجيّاً", e) from e
    return {
        "field_id": field_id,
        "vertex_count_before": before["vertex_count_before"],
        "vertex_count_after": after["vertex_count_after"],
        "is_valid_before": before["is_valid_before"],
        "is_valid_after": after["is_valid_after"],
        "tolerance_m": req.tolerance_m,
    }


@router.post("/api/v1/fields/boundary-graph/rebuild")
async def rebuild_boundary_graph(
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يعيد بناء شبكة جوار حدود حقول المستأجر (#15) عبر ST_Touches.

    يستدعي field_boundary_graph.rebuild_graph_for_tenant على الاتّصال المُنطّق
    (RLS مُطبَّقة)، فيملأ جدول field_boundary_graph بعلاقات 'adjacent' مع طول
    الحافّة المشتركة بالمتر، ويُرجع عدد العلاقات المكتوبة. حتميّ بالكامل (PostGIS،
    بلا ML). 503 عند تعذّر القاعدة. يردّ {rebuilt, relations_written}.
    """
    from api.field_boundary_graph import rebuild_graph_for_tenant

    try:
        async with tenant_connection(user) as conn:
            count = await rebuild_graph_for_tenant(conn, str(user.tenant_id))
    except Exception as e:  # noqa: BLE001 — خطأ DB/PostGIS ⇒ 503 لا 500
        raise _db_unavailable("بناء شبكة حدود الحقل", e) from e
    return {"rebuilt": True, "relations_written": count}


@router.get("/api/v1/fields/{field_id}/boundary-graph")
async def get_field_boundary_graph(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يقرأ جيران الحقل من شبكة الجوار (#15) مُرتّبين بطول الحافّة المشتركة.

    SELECT من field_boundary_graph ضمن سياق المستأجِر (RLS). حقل بلا جيران صالح —
    يردّ قائمة فارغة لا 404. 503 عند تعذّر القاعدة. يردّ {field_id, neighbors}.
    """
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT neighbor_field_id, relation_type, shared_edge_length_m "
                "FROM field_boundary_graph WHERE field_id = $1 "
                "ORDER BY shared_edge_length_m DESC NULLS LAST",
                field_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB (هجرة/اتّصال) ⇒ 503 لا 500
        raise _db_unavailable("قراءة شبكة حدود الحقل", e) from e
    return {
        "field_id": field_id,
        "neighbors": [
            {
                "neighbor_field_id": str(r["neighbor_field_id"]),
                "relation_type": r["relation_type"],
                "shared_edge_length_m": r["shared_edge_length_m"],
            }
            for r in rows
        ],
    }
