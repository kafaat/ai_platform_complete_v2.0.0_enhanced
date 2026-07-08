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
import logging
import os
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.decision_lineage import ensure_decision_id, lineage_stage
from api.decision_service_client import (
    record_decision as _record_decision_via_service,
)
from api.decision_service_client import (
    record_outcome as _record_outcome_via_service,
)
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
logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}

# حالات الحَوكمة التي تُقِرّ التوزيع (مطابِقة لـcoordinator/decision_dispatch). أيّ حالة
# أخرى (not_evaluated/error/مجهولة) ⇒ القرار استشاريّ فقط (fail-closed، لا موافقة مُختلقة).
_GOVERNANCE_APPROVED_STATES = frozenset({"approved", "passed", "cleared", "ok"})

# مصدر الملكيّة الموثوق (جدول fields عبر دالّة SECURITY DEFINER). نقرؤه محليّاً —
# لا نعبر استيراداً بين الخدمات (نمط raster-service/db_persist محفوظ، لا مشترك).
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _auto_persist_enabled() -> bool:
    """هل إدامة القرار **الاستشاريّ** التلقائيّة عند المصدر مُفعَّلة؟ (مُطفأة افتراضاً).

    العلم يحكم القرارات الاستشاريّة فقط؛ القرار **القابل للتنفيذ** يُدام دائماً
    (إلزاميّ، fail-closed) بغضّ النظر عن العلم — auditability غير قابلة للتفاوض."""
    return os.getenv("SAHOOL_AUTO_PERSIST_DECISIONS", "").strip().lower() in _TRUTHY


def _decision_is_executable(decision_value: dict, executable: bool | None) -> bool:
    """هل القرار قابل للتنفيذ؟ (executable = actionable AND governance_permits_dispatch).

    يُؤخذ من المُمرَّر صراحةً (executable) إن وُجد، وإلّا يُستنبَط من decision_value
    (مفتاح executable الصريح، أو actionable مع governance.status موافِقة). fail-closed:
    أيّ غموض ⇒ يُعامَل القرار كاستشاريّ في تحديد الإلزاميّة، لكنّ كلّ ما هو executable
    يقيناً يُحجَز للإدامة الإلزاميّة (لا يُتصرَّف به بلا سجلّ دائم)."""
    if executable is not None:
        return bool(executable)
    if not isinstance(decision_value, dict):
        return False
    if isinstance(decision_value.get("executable"), bool):
        return decision_value["executable"]
    gov = decision_value.get("governance")
    status = ""
    if isinstance(gov, dict):
        status = str(gov.get("status", "")).strip().lower()
    actionable = bool(decision_value.get("actionable"))
    return actionable and status in _GOVERNANCE_APPROVED_STATES


class OwnerLookupUnavailable(Exception):
    """تعذّر إثبات ملكيّة الحقل رغم أنّ القاعدة **مُهيّأة** (DATABASE_URL مضبوط) —
    اتّصال/استعلام فاشل أو الدالّة غائبة. يُميَّز عن «وضع بلا قاعدة» (DATABASE_URL غير
    مضبوط) كي يستطيع المسار fail-closed عند تعذّر الإثبات فقط، دون كسر التشغيل بلا قاعدة."""


async def _field_owner_tenant(field_id: str) -> str | None:
    """مالك الحقل (tenant_id نصّاً) من المصدر الموثوق عبر `sahool_field_owner_tenant`.

    تعاقُد الإرجاع (مطابق لـraster-service/db_persist.field_owner_tenant):
    - نصّ المالك إن وُجد الحقل في fields.
    - None إن: (أ) DATABASE_URL غير مضبوط (وضع بلا قاعدة مقصود — لا حجب) أو (ب) الحقل
      غير موجود فعلاً (استعلام نجح بلا صفّ).
    - يرفع OwnerLookupUnavailable إن كان DATABASE_URL **مضبوطاً** لكن تعذّر الاتّصال/
      الاستعلام/الدالّة غائبة ⇒ لا يمكن إثبات الملكيّة ⇒ يقرّر المنادي fail-closed (503)."""
    if not DATABASE_URL:
        return None  # وضع بلا قاعدة مقصود (DB-less/CI) — لا مصدر ملكيّة، لا حجب
    try:
        import asyncpg
    except ImportError:  # القاعدة مضبوطة لكنّ السائق غائب ⇒ لا يمكن الإثبات
        raise OwnerLookupUnavailable("asyncpg غير متاح") from None
    try:
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001 — DATABASE_URL مضبوط لكنّ الاتّصال فشل
        raise OwnerLookupUnavailable(f"connect failed for field {field_id}") from e
    try:
        owner = await conn.fetchval("SELECT sahool_field_owner_tenant($1)", field_id)
        return str(owner) if owner else None  # مالك، أو None = غير موجود فعلاً
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكن الاستعلام/الدالّة تعذّرا
        logger.warning("field_owner_tenant unavailable (%s): %s", field_id, type(e).__name__)
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()


async def _assert_field_ownership(user: UserSchema, field_id: str | None) -> None:
    """يرفض كتابة قرار على حقلٍ لا يملكه المنادي (دفاع عميق فوق RLS، fail-closed).

    - field_id فارغ ⇒ لا حقل لِيُتحقَّق (قرار بلا حقل) — يمرّ.
    - بلا DATABASE_URL (DB-less/CI) ⇒ المالك None ⇒ لا حجب (يحفظ خضرة CI).
    - الحقل غير موجود (None رغم القاعدة) ⇒ 404 (لا نكتب قراراً على حقل مجهول).
    - المالك ≠ مستأجِر المنادي ⇒ 403 (لا نكتب قراراً على حقل غيره — صدق + أمان).
    - OwnerLookupUnavailable ⇒ 503 (تعذّر الإثبات ⇒ fail-closed، لا نكتب على غموض)."""
    if not field_id:
        return
    try:
        owner = await _field_owner_tenant(field_id)
    except OwnerLookupUnavailable as e:
        raise _db_unavailable("إثبات ملكيّة الحقل", e) from e
    if owner is None:
        if not DATABASE_URL:
            return  # وضع بلا قاعدة — لا مصدر ملكيّة، لا حجب (CI)
        raise HTTPException(status_code=404, detail="الحقل غير موجود")
    if str(owner) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="غير مصرَّح: الحقل ليس ضمن مستأجِرك")


async def persist_decision_if_enabled(
    user: UserSchema,
    *,
    decision_id: str,
    decision_type: str,
    decision_value: dict,
    field_id: str | None = None,
    region: str | None = None,
    confidence: float | None = None,
    executable: bool | None = None,
) -> bool:
    """يُدِيم القرار في decision_record — **إلزاميّ للقابل للتنفيذ، اختياريّ للاستشاريّ**.

    قرار قابل للتنفيذ (executable = actionable AND governance_permits_dispatch) **يجب**
    أن يُدام أيّاً كان حال SAHOOL_AUTO_PERSIST_DECISIONS — لا يُتصرَّف بقرارٍ بلا سجلّ دائم
    (صدق: auditability غير قابلة للتفاوض). فشل إدامة قرار قابل للتنفيذ ⇒ fail-closed
    (يُرفع 503 لا يُمضى كأنّه سُجِّل). القرار الاستشاريّ يبقى محكوماً بالعلم (best-effort:
    إطفاء العلم/تعذّر القاعدة لا يكسر إصداره).

    قبل أيّ إدراج: فحص ملكيّة الحقل (`sahool_field_owner_tenant`) — لا يُكتَب قرار على حقلٍ
    لا يملكه المنادي (403/404)، وتعذّر الإثبات ⇒ 503. بلا DATABASE_URL ⇒ لا حجب (CI).
    """
    is_executable = _decision_is_executable(decision_value, executable)
    if not is_executable and not _auto_persist_enabled():
        return False  # استشاريّ والعلم مُطفأ ⇒ لا إدامة (best-effort، لا مسّ بالقاعدة)

    # فحص الملكيّة قبل أيّ كتابة (يرفع 403/404/503). لا يلمس القاعدة بلا DATABASE_URL.
    await _assert_field_ownership(user, field_id)

    conf = confidence if isinstance(confidence, (int, float)) else None
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO decision_record
                    (decision_id, tenant_id, field_id, decision_type, region,
                     stage, decision_value, confidence, created_by)
                   VALUES ($1, $2::uuid, $3, $4, $5, 'decision', $6::jsonb, $7, $8)
                   ON CONFLICT (decision_id) DO NOTHING""",
                decision_id,
                str(user.tenant_id),
                field_id,
                decision_type,
                region,
                _json.dumps(decision_value),
                conf,
                str(user.user_id),
            )
            await _emit_domain_event(
                conn,
                user,
                "DECISION_RECORDED",
                "decision_record",
                decision_id,
                {
                    "decision_type": decision_type,
                    "field_id": field_id,
                    "region": region,
                    "confidence": conf,
                },
                critical=True,  # رأس سلسلة النَّسَب — fail-closed
            )
        return True
    except HTTPException:
        raise  # 403/404/503 من فحص الملكيّة لا يُبتلَع
    except Exception as e:  # noqa: BLE001
        if is_executable:
            # قرار قابل للتنفيذ بلا سجلّ ⇒ fail-closed: لا نُمضي كأنّه سُجِّل (503 موثَّق).
            logger.error("إدامة قرار قابل للتنفيذ %s فشلت — fail-closed: %s", decision_id, e)
            raise _db_unavailable("إدامة قرار قابل للتنفيذ", e) from e
        # استشاريّ: أثر جانبيّ — فشل الإدامة لا يكسر إصدار القرار.
        logger.warning("auto-persist decision %s تخطّي: %s", decision_id, e)
        return False


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
    """BFF/facade write path for decision records.

    P4.5: loop-table ownership moved to decision-service.  The platform still keeps
    authentication and request shaping, but it must not insert into ``decision_record``
    directly on this write path.
    """
    did = ensure_decision_id(req.decision_id)
    lineage = lineage_stage(did, "decision", field_id=req.field_id, region=req.region)
    payload = {
        "decision_id": did,
        "field_id": req.field_id,
        "decision_type": req.decision_type,
        "region": req.region,
        "stage": lineage["stage"],
        "decision_value": req.decision_value,
        "confidence": req.confidence,
        "created_by": str(user.user_id),
    }
    out = await _record_decision_via_service(payload, tenant_id=str(user.tenant_id))
    out.setdefault("decision_id", did)
    out["lineage"] = lineage
    out["recorded_by"] = str(user.user_id)
    out["via"] = "decision-service"
    return out


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
    idempotency_key: str | None = None  # لاتكرار: إعادة POST بنفس المفتاح لا تُكرّر العيّنة


@router.post("/api/v1/outcome/record")
async def record_outcome(
    req: OutcomeRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """BFF/facade write path for measured outcomes.

    The metric calculation remains pure in the platform for response compatibility, but
    persistence is delegated to decision-service, which owns ``outcome_record``.
    """
    metrics = measure_outcome(req.planned.model_dump(), req.actual.model_dump())
    success = _derive_success(metrics["metrics"])
    did = ensure_decision_id(req.decision_id)
    outcome_id = "out_" + _uuid.uuid4().hex[:16]
    lineage = lineage_stage(did, "outcome", field_id=req.field_id, region=req.region)
    payload = {
        "outcome_id": outcome_id,
        "decision_id": did,
        "field_id": req.field_id,
        "region": req.region,
        "planned": req.planned.model_dump(),
        "actual": req.actual.model_dump(),
        "metrics": metrics,
        "success": success,
        "created_by": str(user.user_id),
        "idempotency_key": req.idempotency_key,
    }
    out = await _record_outcome_via_service(payload, tenant_id=str(user.tenant_id))
    out.setdefault("outcome_id", outcome_id)
    out.setdefault("decision_id", did)
    out["lineage"] = lineage
    out["metrics"] = metrics
    out["success"] = success
    out["recorded_by"] = str(user.user_id)
    out["via"] = "decision-service"
    return out


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


@router.get("/api/v1/decision/records")
async def list_decision_records(
    field_id: str | None = None,
    decision_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يسرد قرارات المستأجِر المُدامة (الأحدث أوّلاً) — معزولة بـRLS.

    قراءة فقط. تصفية اختياريّة بـfield_id/decision_type (WHERE ديناميكيّ). 503 عند
    تعذّر القاعدة. مسار القراءة تكامليّ (يتطلّب Postgres، كـdecision_dispatch).
    """
    clauses, args = [], []
    if field_id:
        args.append(field_id)
        clauses.append(f"field_id = ${len(args)}")
    if decision_type:
        args.append(decision_type)
        clauses.append(f"decision_type = ${len(args)}")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(limit)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                f"SELECT * FROM decision_record{where} ORDER BY created_at DESC LIMIT ${len(args)}",
                *args,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سجلّ القرارات", e) from e
    return {"decisions": [_shape_decision_row(r) for r in rows], "count": len(rows)}


def _group_outcomes_by_decision(decision_ids, orows):
    """يجمع نتائج الحقل تحت قراراتها بمطابقة decision_id (نقيّ، لا قاعدة).

    يعيد (grouped, orphans): grouped قاموس {decision_id: [نتائج مُشكَّلة]}، وorphans
    قائمة النتائج التي لا قرار مُدام لها (decision_id خارج المُمرَّر) — تُكشَف لا تُخفى.
    """
    known = set(decision_ids)
    grouped: dict = {did: [] for did in known}
    orphans: list = []
    for r in orows:
        shaped = _shape_outcome_row(r)
        did = shaped["decision_id"]
        if did in known:
            grouped[did].append(shaped)
        else:
            orphans.append(shaped)
    return grouped, orphans


@router.get("/api/v1/field/{field_id}/lineage")
async def get_field_lineage(
    field_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يجمّع سلسلة حقل: قراراته المُدامة (الأحدث أوّلاً)، ولكلّ قرار نتائجه المربوطة.

    قراءة فقط، معزول بـRLS. النتائج التي لا قرار مُدام لها (حُسِبت عبر المسار النقيّ بلا
    إدامة رأس) تُكشَف تحت orphan_outcomes — صدق: لا تُخفى. 503 عند تعذّر القاعدة. مسار
    القراءة تكامليّ (يتطلّب Postgres، كـdecision_dispatch).
    """
    try:
        async with tenant_connection(user) as conn:
            drows = await conn.fetch(
                "SELECT * FROM decision_record WHERE field_id = $1 "
                "ORDER BY created_at DESC LIMIT $2",
                field_id,
                limit,
            )
            orows = await conn.fetch(
                "SELECT * FROM outcome_record WHERE field_id = $1 ORDER BY created_at ASC",
                field_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سجلّ القرارات", e) from e

    grouped, orphans = _group_outcomes_by_decision([d["decision_id"] for d in drows], orows)
    decisions = [{**_shape_decision_row(d), "outcomes": grouped[d["decision_id"]]} for d in drows]
    return {
        "field_id": field_id,
        "decisions": decisions,
        "orphan_outcomes": orphans,
        "count": len(drows),
    }
