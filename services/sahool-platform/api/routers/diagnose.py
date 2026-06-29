"""api/routers/diagnose.py — التشخيص الأوّلي (Disease Diagnosis)
=============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.disease_diagnosis import diagnose, list_symptoms
from api.main import (
    DiagnoseRequest,
    UserSchema,
    _assert_field_in_tenant,
    get_current_user,
    logger,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/diagnose")
async def diagnose_symptoms(
    req: DiagnoseRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تشخيص أوّلي بقواعد الأعراض (لا قاطع — يوصي بتأكيد بشري/مختبر).

    تغذية آمنة (Stage F): عند تمرير field_id نُرفِق كتلة field_state من الحالة
    القانونيّة الموحّدة (validity/execution_mode/operational_truths) وملاحظة
    مرجعيّة عند ملوحة تربة حرجة — دون تغيير قواعد التشخيص أو أرقامه. fail-safe:
    تعذّر الحالة أو غياب field_id ⇒ يُعاد التشخيص الأصليّ بلا إرفاق.
    """
    result = diagnose(req.crop, req.symptoms).to_dict()

    if req.field_id:
        try:
            from api.field_state_projection import recompute_field_state

            async with tenant_connection(user) as conn:
                # تأكّد أنّ الحقل ضمن المستأجِر قبل الإرفاق — وإلّا 404 يلتقطه except
                # أدناه فلا نُرفِق حالة «حقل شبح» (مراجعة Copilot).
                await _assert_field_in_tenant(conn, req.field_id)
                field_state = (await recompute_field_state(conn, req.field_id))["state"]
            # نُرفِق مقتطفاً من الحالة الموحّدة (لا نغيّر التشخيص).
            _agro = field_state.get("agronomic") or {}
            _truths = _agro.get("operational_truths") or {}
            result["field_state"] = {
                "validity": field_state.get("validity"),
                "execution_mode": field_state.get("execution_mode"),
                "agronomic": {"operational_truths": _truths},
                # Bundle D (D3): قيم المياه الكنسيّة من **مصدر واحد** (كتلة water الموحّدة)
                # بدل قراءة ET0/ETc من مصادر متفرّقة — None إن غابت (صدق).
                "water": field_state.get("water"),
                # Bundle B: ثقة حدّ الحقل الكنسيّة من **مصدر واحد** (كتلة boundary) —
                # None إن لم يُهدَّف الحدّ بعد (صدق). ثقة منخفضة صعّدت execution_mode أعلاه.
                "boundary": field_state.get("boundary"),
                # Bundle D (D2a): الإجهاد المائيّ الكنسيّ (AWF + مستوى) — معلوماتيّ بلا
                # تصعيد؛ None إن لا استنزاف موثوق في دفتر المياه (صدق).
                "water_stress": field_state.get("water_stress"),
                # مؤشّر جاهزيّة بيانات الحقل: درجة واحدة مُفسَّرة «كم نثق بذكاء الحقل
                # الآن؟» + إرشاد عمليّ — معلوماتيّ، لا يغيّر القرار.
                "readiness": field_state.get("readiness"),
            }
            # ملاحظة مرجعيّة فقط عند ملوحة حرجة — إجهاد الملوحة قد يحاكي/يفاقم
            # أعراض الأمراض. لا تغيير لقواعد/نتيجة التشخيص.
            if _truths.get("salinity_class") == "critical":
                result.setdefault("advisory_notes_ar", []).append(
                    "إجهاد الملوحة قد يحاكي/يفاقم أعراض الأمراض — راجِع حالة التربة."
                )
        except Exception:  # noqa: BLE001 — تغذية best-effort، لا تكسر التشخيص
            logger.warning(
                "diagnose: تعذّر إرفاق الحالة الموحّدة للحقل %s — يُعاد التشخيص بلا حالة",
                req.field_id,
                exc_info=True,
            )

    return result


@router.get("/api/v1/diagnose/symptoms")
def diagnosis_symptom_catalog():
    """قائمة الأعراض المتاحة للاختيار في الموبايل."""
    return {"symptoms": list_symptoms()}
