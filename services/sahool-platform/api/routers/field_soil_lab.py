"""api/routers/field_soil_lab.py — مسارات فحوص مختبر التربة (Soil Lab Tests) للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت المعالِجات الثلاث لدورة حياة فحص التربة حرفيّاً — بنفس المسارات/الطلبات/المخرجات/
الأذونات/مخطّط OpenAPI — دون أيّ تغيير في السلوك:

  • ``POST   /api/v1/fields/{field_id}/soil-lab-tests``             → ``create_soil_lab_test``
  • ``GET    /api/v1/fields/{field_id}/soil-lab-tests``             → ``list_soil_lab_tests``
  • ``PATCH  /api/v1/fields/{field_id}/soil-lab-tests/{test_id}``   → ``update_soil_lab_test``

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``api.main`` للتبعيات/النماذج/المساعِدات؛ والمحرّكات النقيّة تُستورَد محليّاً داخل
الدوال كما كانت). لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا، وحلقة التسجيل
تُنفَّذ في نهاية ``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _SOIL_TEST_SELECT,
    Permission,
    SoilLabTestCreateRequest,
    SoilLabTestSummary,
    SoilLabTestUpdateRequest,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _emit_domain_event,
    _parse_date,
    _row_to_soil_test,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    status_code=201,
    response_model=SoilLabTestSummary,
)
async def create_soil_lab_test(
    field_id: str,
    req: SoilLabTestCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ فحص تربة (حالة requested) — بداية دورة الحياة المخبريّة. يُصدِر SOIL_SAMPLE_RECORDED."""
    import json as _json
    import uuid as _uuid

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة")
    test_id = "soil_" + _uuid.uuid4().hex[:12]
    try:
        result_json = _json.dumps(req.result or {})
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل (JSON)") from e
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO soil_lab_tests "
                    "(test_id, tenant_id, field_id, status, lab_name, sampled_on, result, notes_ar) "
                    "VALUES ($1, $2::uuid, $3, 'requested', $4, $5, $6::jsonb, $7)",
                    test_id,
                    str(user.tenant_id),
                    field_id,
                    req.lab_name,
                    sampled,
                    result_json,
                    req.notes_ar,
                )
                await _emit_domain_event(
                    conn,
                    user,
                    "SOIL_SAMPLE_RECORDED",
                    "soil_lab_test",
                    test_id,
                    {"field_id": field_id, "status": "requested"},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء فحص التربة", e) from e
    return SoilLabTestSummary(
        test_id=test_id,
        field_id=field_id,
        status="requested",
        lab_name=req.lab_name,
        sampled_on=sampled.isoformat() if sampled else None,
        result=req.result or {},
        notes_ar=req.notes_ar,
    )


@router.get(
    "/api/v1/fields/{field_id}/soil-lab-tests",
    response_model=list[SoilLabTestSummary],
)
async def list_soil_lab_tests(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """فحوص تربة الحقل (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS). 503 عند تعذّر القاعدة."""
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests "
                "WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة فحوص التربة", e) from e
    return [_row_to_soil_test(r) for r in rows]


@router.patch(
    "/api/v1/fields/{field_id}/soil-lab-tests/{test_id}",
    response_model=SoilLabTestSummary,
)
async def update_soil_lab_test(
    field_id: str,
    test_id: str,
    req: SoilLabTestUpdateRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحدّث فحص تربة (انتقال حالة محقَّق + بيانات) — يُصدِر SOIL_LAB_RESULT_PUBLISHED عند النشر.

    الانتقال عبر `soil_lab_workflow` (عيّنة→مختبر→نتيجة→اعتماد→نشر؛ المنشور/الملغى
    نهائيّان؛ لا اعتماد/نشر بلا نتيجة — 422). تأكيد ملكيّة الحقل (404)؛ الفحص يخصّ
    الحقل (404). 503 عند تعذّر القاعدة.
    """
    import json as _json

    from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition

    sampled = _parse_date(req.sampled_on, "تاريخ العيّنة") if req.sampled_on is not None else None
    if req.result is not None:
        try:
            result_json = _json.dumps(req.result)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail="نتيجة الفحص غير قابلة للتسلسل") from e

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            async with conn.transaction():
                cur = await conn.fetchrow(
                    "SELECT status, result FROM soil_lab_tests "
                    "WHERE test_id = $1 AND field_id = $2 FOR UPDATE",
                    test_id,
                    field_id,
                )
                if cur is None:
                    raise HTTPException(status_code=404, detail="فحص التربة غير موجود لهذا الحقل")

                set_parts, params = [], []

                def _add(col, value, cast=""):
                    params.append(value)
                    set_parts.append(f"{col} = ${len(params)}{cast}")

                if req.lab_name is not None:
                    _add("lab_name", req.lab_name)
                if req.sampled_on is not None:
                    _add("sampled_on", sampled)
                if req.notes_ar is not None:
                    _add("notes_ar", req.notes_ar)
                if req.result is not None:
                    _add("result", result_json, "::jsonb")

                status_changed = False
                if req.status is not None:
                    # توفّر نتيجة = نتيجة موجودة سابقاً (JSONB غير فارغ) أو ممرَّرة الآن.
                    existing = cur["result"]
                    existing_obj = (
                        _json.loads(existing) if isinstance(existing, str) else (existing or {})
                    )
                    has_result = bool(req.result) or bool(existing_obj)
                    try:
                        status_changed = validate_soil_transition(
                            cur["status"], req.status, has_result=has_result
                        )
                    except SoilWorkflowError as se:
                        raise HTTPException(
                            status_code=se.http_status, detail=se.message_ar
                        ) from se
                    if status_changed:
                        _add("status", req.status)
                        if req.status == "approved":
                            _add("approved_by", str(user.user_id))
                        if req.status == "published":
                            set_parts.append("published_at = now()")  # وقت القاعدة (لا param)

                if not set_parts:
                    raise HTTPException(status_code=422, detail="لا حقول للتحديث")

                params.extend([test_id, field_id])
                await conn.execute(
                    f"UPDATE soil_lab_tests SET {', '.join(set_parts)} "
                    f"WHERE test_id = ${len(params) - 1} AND field_id = ${len(params)}",
                    *params,
                )
                if status_changed and req.status == "published":
                    await _emit_domain_event(
                        conn,
                        user,
                        "SOIL_LAB_RESULT_PUBLISHED",
                        "soil_lab_test",
                        test_id,
                        {"field_id": field_id},
                    )
                    # نشر نتيجة التربة يُدخِل EC جديداً (تقرؤه gather_field_freshness من
                    # soil_lab_tests المنشورة) ⇒ قد تتبدّل الملوحة فالحالة القانونيّة
                    # (نمط التنفيذ/الصلاحيّة). أعِد حساب الإسقاط وأصدِر field.state_changed
                    # إن تبدّل — تغذية حيّة لمستهلكي الحالة، نفس معاملة الكتابة (outbox).
                    from api.field_state_projection import recompute_field_state

                    _fs = await recompute_field_state(conn, field_id)
                    if _fs["changed"]:
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_STATE_CHANGED",
                            "field",
                            field_id,
                            {
                                "validity": _fs["state"]["validity"],
                                "execution_mode": _fs["state"]["execution_mode"],
                                "trigger": "soil_lab.published",
                            },
                        )
                row = await conn.fetchrow(
                    f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests WHERE test_id = $1",
                    test_id,
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تحديث فحص التربة", e) from e
    return _row_to_soil_test(row)
