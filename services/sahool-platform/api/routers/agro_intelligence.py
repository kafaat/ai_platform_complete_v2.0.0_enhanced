"""api/routers/agro_intelligence.py — نقاط ذكاء النظام الزراعيّ-البيئيّ (agro-ecosystem).

غلافٌ رفيع (نمط P0) يعرض النوى النقيّة المُختبَرة عبر HTTP — لا منطق هنا، فقط تحويل
الطلب إلى مدخلات النواة ثمّ تسلسل المخرَج (dataclass ⇐ dict). كلّ النقاط حسابيّة صرفة
(بلا قاعدة بيانات) فتُختبَر باستدعاء المعالِج مباشرةً. `tenant_id` يُؤخَذ من المستخدم
المُصادَق (لا من جسم الطلب) حفظاً لعزل المستأجِر.

النقاط (كلّها POST تحت /api/v1):
  • /agro/crop-risk                     ⇐ core.crop_risk
  • /agro/plant-soil-feedback           ⇐ core.soil_feedback_proxy (محرّك PSFI)
  • /agro/plant-soil-feedback/trend     ⇐ core.soil_feedback_trend
  • /agro/crop-rotation                 ⇐ core.crop_rotation_intelligence
  • /agro/season-comparison             ⇐ core.season_comparison
  • /agro/decision-playbook             ⇐ core.decision_playbook (يركّب السلسلة)
  • /work-orders/from-recommendation    ⇐ core.work_order_from_recommendation (FOES)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from core.crop_risk import assess_crop_risk
from core.crop_rotation_intelligence import SeasonCrop, assess_rotation
from core.decision_playbook import PlaybookContext, build_playbook
from core.season_comparison import SeasonMetrics, compare_seasons
from core.soil_feedback_proxy import SoilFeedbackInputs, assess_plant_soil_feedback
from core.soil_feedback_trend import SeasonFeedback, analyze_feedback_trend
from core.weather_signals import WeatherSignal
from core.work_order_from_recommendation import recommendation_to_work_order
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.main import UserSchema, _emit_domain_event, get_current_user, tenant_connection

router = APIRouter()
logger = logging.getLogger("sahool.agro_intelligence")


# ════════════════════════════════════════════════════════════
# نماذج الطلب (Pydantic v2)
# ════════════════════════════════════════════════════════════
class CropRiskRequest(BaseModel):
    """مدخلات تقييم خطر المحصول."""

    crop: str
    disease_risk_score: float = 0.0
    heat_stress_hours: int = 0
    frost_risk_hours: int = 0
    humidity_avg_percent: float | None = None


class SoilFeedbackInputsRequest(BaseModel):
    """مؤشّرات إدارة الحقل (proxies) — كلّها اختياريّة (None = إشارة غير معروفة)."""

    rotation_diversity: float | None = None
    legume_ratio: float | None = None
    cover_crop_ratio: float | None = None
    host_repeat_risk: float | None = None
    organic_matter_additions_per_yr: float | None = None
    tillage_intensity: float | None = None
    soil_organic_carbon_pct: float | None = None
    salinity_ds_m: float | None = None
    disease_incidents_recent: int | None = None
    synthetic_fertilizer_intensity: float | None = None

    def to_core(self) -> SoilFeedbackInputs:
        return SoilFeedbackInputs(**self.model_dump())


class SeasonFeedbackInputRequest(BaseModel):
    """موسم واحد لتحليل الاتّجاه: معرّفه + مؤشّرات إدارته."""

    season_id: str
    inputs: SoilFeedbackInputsRequest


class FeedbackTrendRequest(BaseModel):
    """سلسلة مواسم زمنيّة (الأقدم → الأحدث) لتحليل اتّجاه التغذية الراجعة."""

    seasons: list[SeasonFeedbackInputRequest] = Field(default_factory=list)


class SeasonCropRequest(BaseModel):
    """زراعة موسم واحد في تاريخ الدورة الزراعيّة."""

    season_id: str
    crop_id: str
    crop_family: str | None = None
    is_legume: bool = False
    is_cover_crop: bool = False
    intercropped_with: list[str] = Field(default_factory=list)


class CropRotationRequest(BaseModel):
    """تاريخ الدورة الزراعيّة (الأقدم → الأحدث)."""

    history: list[SeasonCropRequest] = Field(default_factory=list)


class SeasonMetricsRequest(BaseModel):
    """مقاييس موسم واحد (كلّها اختياريّة)."""

    season_id: str
    crop_id: str
    kc_mid: float | None = None
    yield_t_ha: float | None = None
    water_used_m3: float | None = None
    ndvi_peak: float | None = None
    et0_total_mm: float | None = None
    water_use_efficiency: float | None = None

    def to_core(self) -> SeasonMetrics:
        return SeasonMetrics(**self.model_dump())


class SeasonComparisonRequest(BaseModel):
    """موسمان للمقارنة (الحاليّ مقابل السابق)."""

    current: SeasonMetricsRequest
    previous: SeasonMetricsRequest


class WeatherSignalRequest(BaseModel):
    """إشارة طقس مُولَّدة (نوعها وثقتها وحمولتها)."""

    signal_type: str
    confidence_score: float = 1.0
    payload: dict = Field(default_factory=dict)


class DecisionPlaybookRequest(BaseModel):
    """سياق بناء Playbook القرار — يركّب إشارات الطقس + مخاطر المحصول + التغذية الراجعة."""

    crop: str | None = None
    weather_signals: list[WeatherSignalRequest] = Field(default_factory=list)
    crop_risk_inputs: CropRiskRequest | None = None
    soil_feedback_inputs: SoilFeedbackInputsRequest | None = None
    recommendation_ar: str | None = None


class WorkOrderFromRecommendationRequest(BaseModel):
    """توصية + الحقل المستهدَف؛ المستأجِر يُؤخَذ من المستخدم المُصادَق."""

    field_id: str
    recommendation: dict = Field(default_factory=dict)


# ════════════════════════════════════════════════════════════
# النقاط (thin adapters)
# ════════════════════════════════════════════════════════════
@router.post("/api/v1/agro/crop-risk")
def crop_risk_endpoint(req: CropRiskRequest, user: UserSchema = Depends(get_current_user)):
    """يقيّم مخاطر المحصول (مرض فطريّ/إجهاد حراريّ/ضرر صقيع) من إشارات الطقس."""
    risks = assess_crop_risk(
        req.crop,
        disease_risk_score=req.disease_risk_score,
        heat_stress_hours=req.heat_stress_hours,
        frost_risk_hours=req.frost_risk_hours,
        humidity_avg_percent=req.humidity_avg_percent,
    )
    return {"crop": req.crop, "risks": [asdict(r) for r in risks]}


@router.post("/api/v1/agro/plant-soil-feedback")
def plant_soil_feedback_endpoint(
    req: SoilFeedbackInputsRequest, user: UserSchema = Depends(get_current_user)
):
    """يقدّر التغذية الراجعة نبات-تربة (PSFI) من مؤشّرات الإدارة (بلا مختبر ميكروبيّ)."""
    return asdict(assess_plant_soil_feedback(req.to_core()))


@router.post("/api/v1/agro/plant-soil-feedback/trend")
def plant_soil_feedback_trend_endpoint(
    req: FeedbackTrendRequest, user: UserSchema = Depends(get_current_user)
):
    """يحلّل اتّجاه التغذية الراجعة نبات-تربة عبر المواسم (محسّن/متراجع/ثابت + المحرّكات)."""
    history = [
        SeasonFeedback(
            season_id=s.season_id, feedback=assess_plant_soil_feedback(s.inputs.to_core())
        )
        for s in req.seasons
    ]
    return asdict(analyze_feedback_trend(history))


@router.post("/api/v1/agro/crop-rotation")
def crop_rotation_endpoint(req: CropRotationRequest, user: UserSchema = Depends(get_current_user)):
    """يقيّم جودة الدورة الزراعيّة (تنوّع/بقوليات/تكرار العائل) واتّجاه التغذية الراجعة."""
    history = [
        SeasonCrop(
            season_id=c.season_id,
            crop_id=c.crop_id,
            crop_family=c.crop_family,
            is_legume=c.is_legume,
            is_cover_crop=c.is_cover_crop,
            intercropped_with=tuple(c.intercropped_with),
        )
        for c in req.history
    ]
    return asdict(assess_rotation(history))


@router.post("/api/v1/agro/season-comparison")
def season_comparison_endpoint(
    req: SeasonComparisonRequest, user: UserSchema = Depends(get_current_user)
):
    """يقارن موسمين (الحاليّ مقابل السابق) ويُظهِر اتّجاه الغلّة وكفاءة استخدام الماء."""
    return compare_seasons(req.current.to_core(), req.previous.to_core())


@router.post("/api/v1/agro/decision-playbook")
def decision_playbook_endpoint(
    req: DecisionPlaybookRequest, user: UserSchema = Depends(get_current_user)
):
    """يبني Playbook قرار قابل للتفسير (ماذا أفعل اليوم/أتجنّب/متى أراجع/متى أُصعّد).

    يركّب السلسلة: إشارات الطقس + مخاطر المحصول (من إدخالاتها) + التغذية الراجعة
    نبات-تربة (من مؤشّراتها) ⇐ حُكم واحد مُهيكَل.
    """
    signals = tuple(
        WeatherSignal(
            signal_type=s.signal_type, confidence_score=s.confidence_score, payload=s.payload
        )
        for s in req.weather_signals
    )
    crop_risks: tuple = ()
    if req.crop_risk_inputs is not None:
        cri = req.crop_risk_inputs
        crop_risks = tuple(
            assess_crop_risk(
                cri.crop,
                disease_risk_score=cri.disease_risk_score,
                heat_stress_hours=cri.heat_stress_hours,
                frost_risk_hours=cri.frost_risk_hours,
                humidity_avg_percent=cri.humidity_avg_percent,
            )
        )
    soil_feedback = (
        assess_plant_soil_feedback(req.soil_feedback_inputs.to_core())
        if req.soil_feedback_inputs is not None
        else None
    )
    ctx = PlaybookContext(
        crop=req.crop,
        weather_signals=signals,
        crop_risks=crop_risks,
        soil_feedback=soil_feedback,
        recommendation_ar=req.recommendation_ar,
    )
    return asdict(build_playbook(ctx))


async def _persist_work_order(user: UserSchema, wo: dict) -> str | None:
    """يُثبّت أمر العمل المُشتقّ (INSERT INTO work_orders) ثمّ يُصدِر WORK_ORDER_CREATED.

    persist-first: نُدرِج الصفّ فعليّاً (جدول v75، ضمن سياق RLS عبر tenant_connection
    وWITH CHECK يفرض المستأجِر) ثمّ — **فقط لأنّ صفّاً صار موجوداً** — نُصدِر الحدث عبر
    الـoutbox ضمن نفس المعاملة (مرآة _persist_recommendation). «لا أحداث مُخترَعة»: لا حدث
    بلا تثبيت. القيم تُمرَّر كبارامترات ($1…) لا تُدخَل في نصّ الـSQL.

    يُرجِع work_order_id (نصّاً) عند النجاح، أو None إن تعذّر التثبيت (best-effort —
    لا يكسر استجابة المستخدم؛ wo المُشتقّ يبقى مُعاداً).
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                """INSERT INTO work_orders
                       (tenant_id, field_id, wo_type, status, recommendation_id, payload)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb)
                   RETURNING work_order_id""",
                str(user.tenant_id),
                wo["field_id"],
                wo["wo_type"],
                wo["status"],
                wo.get("recommendation_id"),
                json.dumps(wo.get("payload") or {}, ensure_ascii=False, default=str),
            )
            work_order_id = str(row["work_order_id"])
            # الحدث يُصدَر فقط بعد نجاح الإدراج (صفّ حقيقيّ موجود). best-effort افتراضاً
            # (WORK_ORDER_CREATED ليس في CRITICAL_EVENT_TYPES) فلا يكسر فشلُ الإصدار الكتابةَ.
            await _emit_domain_event(
                conn,
                user,
                "WORK_ORDER_CREATED",
                "work_order",
                work_order_id,
                {
                    "field_id": wo["field_id"],
                    "wo_type": wo["wo_type"],
                    "status": wo["status"],
                    "recommendation_id": wo.get("recommendation_id"),
                },
            )
            return work_order_id
    except Exception:  # noqa: BLE001 — تثبيت/تدقيق أفضل-جهد لا يكسر المسار
        logger.warning("work_order persist/audit failed (best-effort)", exc_info=True)
        return None


@router.post("/api/v1/work-orders/from-recommendation")
async def work_order_from_recommendation_endpoint(
    req: WorkOrderFromRecommendationRequest, user: UserSchema = Depends(get_current_user)
):
    """يحوّل توصية إلى أمر عمل (FOES) ويُثبّته ثمّ يُصدِر WORK_ORDER_CREATED.

    `inferred=false` إن تعذّر استنتاج نوع أمر العمل من التوصية (لا نخترع نوعاً) ⇒ لا
    تثبيت ولا حدث. عند الاستنتاج: يُدرَج صفّ work_orders فعليّاً (persist-first) ثمّ
    يُصدَر الحدث عبر outbox — «لا حدث بلا تثبيت»."""
    wo = recommendation_to_work_order(
        req.recommendation, field_id=req.field_id, tenant_id=str(user.tenant_id)
    )
    work_order_id = None
    if wo is not None:
        work_order_id = await _persist_work_order(user, wo)
    return {
        "inferred": wo is not None,
        # persisted=true فقط حين أُدرِج صفّ فعليّاً (وأُصدِر حدثه). الاستنتاج بلا قاعدة
        # مفعّلة أو بفشل إدراج ⇒ inferred=true لكن persisted=false (صدق: لا ادّعاء تثبيت).
        "persisted": work_order_id is not None,
        "work_order_id": work_order_id,
        "work_order": wo,
    }
