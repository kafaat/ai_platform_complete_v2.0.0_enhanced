"""api/routers/decision_record.py — إدامة سلسلة النَّسَب (Decision→Outcome، P0-1/P0-3)

الفجوة المركزيّة (من تدقيق المعماريّة): المنصّة **تعرف كيف تتّخذ القرار** وتُسَكّ لكلّ
قرار `decision_id` ونَسَباً (طبقة المرحلة ١، نقيّة)، لكنّ القرار ونتيجته الميدانيّة
**لا يُدامان** في قاعدة البيانات — فلا سلسلة قابلة للتدقيق والتراكم المعرفيّ تربط القرار
بأثره (Decision→Outcome→Evidence→Learning). هذا الموجِّه يُغلق رأس السلسلة بالإدامة:

  • `POST …/decision/record` — يُدِيم رأس القرار في `decision_record` (v78) + حدث
    `DECISION_RECORDED` عبر outbox ضمن المعاملة (تدقيق/بثّ).
  • `POST …/outcome/record` — يقيس النتيجة (الطبقة النقيّة `measure_outcome`) **ثمّ**
    يُدِيمها في `outcome_record` (v79) مربوطةً بـ`decision_id` + حدث `OUTCOME_MEASURED`.
  • `GET …/decision/{decision_id}/lineage` — يُعيد بناء السلسلة المُدامة (القرار +
    نتائجه) للمستأجِر — معزولة بـRLS.

**النمط محفوظ** (كـdecision_dispatch): كتابة async عبر `tenant_connection` (معاملة +
RLS) + `_emit_domain_event` (outbox، best-effort داخل savepoint) + `_db_unavailable`
(503 موثَّق) + `require_permission`. الصدق: لا يستبدل المنطق النقيّ (الحساب يبقى نقيّاً)؛
يُدِيم ناتجه. `success`/`confidence` الناقصان ⇒ NULL لا تلفيق. مسار الكتابة يتطلّب
Postgres (مُختبَر تكامليّاً كـdecision_dispatch، لا وحدويّاً).
"""

from __future__ import annotations

import json as _json
import uuid as _uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.decision_lineage import ensure_decision_id, lineage_stage
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)
from api.outcome_measurement import measure_outcome

router = APIRouter()

# حالات المقاييس السلبيّة (انحراف عن هدف القرار) — أيّ مقياس مُقيَّم فيها ⇒ ليس نجاحاً.
# المحايد/الإيجابيّ: followed | better | as_predicted | above | met | within.
_NEGATIVE_STATUSES = frozenset({"under", "over", "worse", "below", "exceeded"})


def _derive_success(metrics: list[dict]) -> bool | None:
    """خلاصة نجاح صادقة من المقاييس: None إن لا مقياس مُقيَّم (لا حكم مُختلق)، وإلا
    True إن لم ينحرف أيّ مقياس مُقيَّم سلبيّاً عن هدف القرار."""
    evaluated = [m["status"] for m in metrics if m.get("status") != "needs_data"]
    if not evaluated:
        return None
    return all(s not in _NEGATIVE_STATUSES for s in evaluated)


def _shape_decision_row(row) -> dict:
    """يحوّل صفّ decision_record إلى dict عرض — يفكّ JSONB ويُنسّق الوقت (نقيّ)."""
    val = row["decision_value"]
    if isinstance(val, str):
        val = _json.loads(val)
    created = row["created_at"]
    return {
        "decision_id": row["decision_id"],
        "field_id": row["field_id"],
        "decision_type": row["decision_type"],
        "region": row["region"],
        "stage": row["stage"],
        "decision_value": val,
        "confidence": row["confidence"],
        "created_by": row["created_by"],
        "created_at": created.isoformat() if created is not None else None,
    }


def _shape_outcome_row(row) -> dict:
    """يحوّل صفّ outcome_record إلى dict عرض — يفكّ JSONB ويُنسّق الوقت (نقيّ)."""

    def _loads(v):
        if v is None:
            return None
        return _json.loads(v) if isinstance(v, str) else v

    created = row["created_at"]
    return {
        "outcome_id": row["outcome_id"],
        "decision_id": row["decision_id"],
        "field_id": row["field_id"],
        "region": row["region"],
        "stage": row["stage"],
        "planned": _loads(row["planned"]),
        "actual": _loads(row["actual"]),
        "metrics": _loads(row["metrics"]),
        "success": row["success"],
        "created_by": row["created_by"],
        "created_at": created.isoformat() if created is not None else None,
    }


class DecisionRecordRequest(BaseModel):
    """مدخلات إدامة رأس قرار: نوعه + قيمته الكاملة (الناتج النقيّ) + سياق اختياريّ.

    `decision_id` يُمرَّر لإعادة استخدام السلسلة (قرار سبق سَكّه عبر المسار النقيّ)
    أو يُسَكّ جديداً. `decision_value` هو ناتج القرار كما عُرِض (يُدام كما هو، JSONB).
    """

    decision_type: str  # crop_twin | irrigation_plan | profit_aware …
    decision_value: dict
    field_id: str | None = None
    region: str | None = None
    confidence: float | None = None
    decision_id: str | None = None


@router.post("/api/v1/decision/record")
async def record_decision(
    req: DecisionRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """يُدِيم رأس القرار في decision_record + حدث DECISION_RECORDED (تدقيق/بثّ).

    يُغلق فجوة «قرار يُحسَب ويُنسى»: يجعل القرار متتبَّعاً بمعرّف موحّد ليُربَط به القياس
    لاحقاً. 503 عند تعذّر القاعدة. مسار كتابة (يتطلّب Postgres). الصدق: confidence الناقص
    يُدام NULL لا يُفبرَك؛ decision_value يُدام كما عُرِض دون إعادة حساب.
    """
    did = ensure_decision_id(req.decision_id)
    lineage = lineage_stage(did, "decision", field_id=req.field_id, region=req.region)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO decision_record
                    (decision_id, tenant_id, field_id, decision_type, region,
                     stage, decision_value, confidence, created_by)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9)
                   ON CONFLICT (decision_id) DO NOTHING""",
                did,
                str(user.tenant_id),
                req.field_id,
                req.decision_type,
                req.region,
                lineage["stage"],
                _json.dumps(req.decision_value),
                req.confidence,
                str(user.user_id),
            )
            await _emit_domain_event(
                conn,
                user,
                "DECISION_RECORDED",
                "decision_record",
                did,
                {
                    "decision_type": req.decision_type,
                    "field_id": req.field_id,
                    "region": req.region,
                    "confidence": req.confidence,
                },
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة القرار", e) from e

    return {
        "decision_id": did,
        "lineage": lineage,
        "persisted": True,
        "recorded_by": str(user.user_id),
    }


class OutcomePlannedIn(BaseModel):
    recommended_irrigation_mm: float | None = None
    predicted_stress_days: int | None = None
    expected_yield_t_ha: float | None = None
    season_budget_mm: float | None = None


class OutcomeActualIn(BaseModel):
    actual_irrigation_mm: float | None = None
    observed_stress_days: int | None = None
    actual_yield_t_ha: float | None = None
    actual_water_used_mm: float | None = None


class OutcomeRecordRequest(BaseModel):
    """مدخلات إدامة نتيجة قرار: المُخطَّط + المرصود، مربوطان بـdecision_id (نَسَب).

    `decision_id` يربط القياس بالقرار المُدام (إن وُجد) — وإن غاب يُسَكّ (قياس مستقلّ).
    """

    decision_id: str | None = None
    field_id: str | None = None
    region: str | None = None
    planned: OutcomePlannedIn = Field(default_factory=OutcomePlannedIn)
    actual: OutcomeActualIn = Field(default_factory=OutcomeActualIn)


@router.post("/api/v1/outcome/record")
async def record_outcome(
    req: OutcomeRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """يقيس نتيجة قرار (نقيّاً) **ثمّ** يُدِيمها في outcome_record مربوطةً بـdecision_id.

    يُغلق P0-1 (إدامة النتيجة): يجعل أثر القرار يتراكم كدليل ميدانيّ — الأساس الذي يبني
    عليه evidence_registry لاحقاً. + حدث OUTCOME_MEASURED. 503 عند تعذّر القاعدة. مسار
    كتابة (يتطلّب Postgres). الصدق: القياس نقيّ (measure_outcome)؛ success الناقص ⇒ NULL.
    """
    metrics = measure_outcome(req.planned.model_dump(), req.actual.model_dump())
    success = _derive_success(metrics["metrics"])
    did = ensure_decision_id(req.decision_id)
    outcome_id = "out_" + _uuid.uuid4().hex[:16]
    lineage = lineage_stage(did, "outcome", field_id=req.field_id, region=req.region)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO outcome_record
                    (outcome_id, tenant_id, decision_id, field_id, region,
                     stage, planned, actual, metrics, success, created_by)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6,
                     $7::jsonb, $8::jsonb, $9::jsonb, $10, $11)""",
                outcome_id,
                str(user.tenant_id),
                did,
                req.field_id,
                req.region,
                lineage["stage"],
                _json.dumps(req.planned.model_dump()),
                _json.dumps(req.actual.model_dump()),
                _json.dumps(metrics),
                success,
                str(user.user_id),
            )
            await _emit_domain_event(
                conn,
                user,
                "OUTCOME_MEASURED",
                "outcome_record",
                outcome_id,
                {"decision_id": did, "field_id": req.field_id, "success": success},
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة نتيجة القرار", e) from e

    return {
        "outcome_id": outcome_id,
        "decision_id": did,
        "lineage": lineage,
        "metrics": metrics,
        "success": success,
        "persisted": True,
        "recorded_by": str(user.user_id),
    }


@router.get("/api/v1/decision/{decision_id}/lineage")
async def get_decision_lineage(
    decision_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يُعيد بناء سلسلة النَّسَب المُدامة لقرار: القرار (إن أُدِيم) + نتائجه — معزولة بـRLS.

    قراءة فقط. القرار المفقود (لم يُدَم/لمستأجِر آخر) ⇒ decision=None لا 404 (النتائج قد
    تكون أُدِيمت عبر المسار النقيّ). 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            drow = await conn.fetchrow(
                "SELECT * FROM decision_record WHERE decision_id = $1", decision_id
            )
            orows = await conn.fetch(
                "SELECT * FROM outcome_record WHERE decision_id = $1 "
                "ORDER BY created_at ASC LIMIT $2",
                decision_id,
                limit,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سلسلة النَّسَب", e) from e

    outcomes = [_shape_outcome_row(r) for r in orows]
    stages_present = []
    if drow is not None:
        stages_present.append("decision")
    if outcomes:
        stages_present.append("outcome")
    return {
        "decision_id": decision_id,
        "decision": _shape_decision_row(drow) if drow is not None else None,
        "outcomes": outcomes,
        "outcome_count": len(outcomes),
        "stages_present": stages_present,
    }
