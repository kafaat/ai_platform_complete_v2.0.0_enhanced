"""
field_intelligence_coordinator.py — مسار التنفيذ الكامل (الربط).

يحقّق المنهجيّة التي أقرّتها المراجعتان:

  collectors → normalize → fusion (maestro) → policy (decision) → guardrails

هذا هو "الغراء التنفيذي" الذي يربط:
  - مصادر المؤشّرات الخام (طقس/تربة/استشعار/ميدانيّة)
  - المايسترو (agronomic_state_engine → CanonicalFieldState)
  - منطق القرار (decision_engine كـ policy-over-state)
  - القواعد الحاكمة (guardrails — قبل إصدار أيّ توصية)

مبدأ حاكم (من المراجعة): الدمج مرّة واحدة. decision لا يعيد تفسير الخام،
بل يعمل فوق الحالة الموحّدة. لا ربط مباشر بين الخدمات (لا spaghetti).

الصدق: كلّ مصدر متعذّر يُعلَن (لا اختراع). المصادر الحيّة (HTTP) تُجلب على
جهاز التشغيل؛ هنا منطق التنسيق + التطبيع، مع حقن المصادر للاختبار.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from core.agronomic_state_engine import (CanonicalFieldState, CropContext,
                                         EconomicContext, SignalInput,
                                         assess_economics, compose_field_state)


# ── الطبقة ١: Collectors — جلب الحقائق الخام فقط (ممنوع اتّخاذ قرار) ──
# كلّ collector دالّة تُرجِع dict خام أو None (متعذّر). تُحقَن للاختبار،
# وعلى جهاز التشغيل تكون نداءات HTTP للخدمات (weather/soil/raster).
@dataclass
class FieldRequest:
    field_id: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    crop: Optional[str] = None
    tenant_id: Optional[str] = None  # سيادة البيانات (multi-tenant)
    farm_id: Optional[str] = None


@dataclass
class CollectorResult:
    """نتيجة جمع المصادر الخام — مع إعلان المتعذّر بصدق."""
    raw: dict = field(default_factory=dict)
    unavailable: list = field(default_factory=list)


def collect_signals(
    req: FieldRequest,
    weather_fn: Optional[Callable] = None,
    soil_fn: Optional[Callable] = None,
    sensing_fn: Optional[Callable] = None,
    field_obs_fn: Optional[Callable] = None,
) -> CollectorResult:
    """يجمع الحقائق الخام من المصادر. صدق: المتعذّر يُعلَن لا يُختلق."""
    result = CollectorResult()
    for name, fn in (("weather", weather_fn), ("soil", soil_fn),
                     ("sensing", sensing_fn), ("field_obs", field_obs_fn)):
        if fn is None:
            result.unavailable.append(name)
            continue
        try:
            data = fn(req)
            if data is None:
                result.unavailable.append(name)
            else:
                result.raw[name] = data
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع
            result.unavailable.append(f"{name} (خطأ: {e})")
    return result


# ── الطبقة ٢: Normalizers — تحويل كلّ مصدر لـSignalInput موحّد ──
def normalize_signals(collected: CollectorResult) -> list[SignalInput]:
    """يطبّع المصادر الخام لإشارات موحّدة (NormalizedSignal من المراجعة).

    كلّ مصدر يحمل: القيمة، الثقة (من نوع المصدر)، الحداثة، الدقّة، التغطية.
    """
    signals: list[SignalInput] = []
    raw = collected.raw
    now = datetime.now(timezone.utc).isoformat()

    # الاستشعار → ndvi/ndre/ndsi/ndwi (دقّة 10م، تغطية من نسبة البكسلات السليمة)
    sensing = raw.get("sensing", {})
    for idx in ("ndvi", "ndre", "ndsi", "ndwi", "bsi", "si"):
        if idx in sensing and sensing[idx] is not None:
            signals.append(SignalInput(
                source=idx, value=sensing[idx], confidence="medium",
                observed_at=sensing.get("observed_at", now),
                spatial_resolution_m=sensing.get("resolution_m", 10.0),
                field_coverage=sensing.get("field_coverage")))

    # التربة → soil_ec (تحليل مخبري — ثقة عالية، لكن قد يكون قديماً)
    soil = raw.get("soil", {})
    if soil.get("ec_dsm") is not None:
        signals.append(SignalInput(
            source="soil_ec", value=soil["ec_dsm"], confidence="high",
            observed_at=soil.get("sampled_at")))

    # الطقس → إشارة سياقيّة (لا قيمة عدديّة مباشرة للدمج الطيفي، لكن للسياق)
    weather = raw.get("weather", {})
    if weather.get("heat_risk") is not None:
        signals.append(SignalInput(
            source="weather", value=weather["heat_risk"], confidence="medium",
            observed_at=weather.get("forecast_at", now)))

    # الميدانيّة → ملاحظة المزارع (ثقة اجتماعيّة — سقفها منخفض)
    fobs = raw.get("field_obs", {})
    if fobs.get("stress_observed") is not None:
        signals.append(SignalInput(
            source="farmer", value=fobs["stress_observed"], confidence="low",
            observed_at=fobs.get("observed_at", now)))

    return signals


# ── الطبقة ٣+٤+٥: Fusion → Policy → Guardrails (المسار الكامل) ──
@dataclass
class FieldIntelligenceResult:
    """ناتج المسار الكامل: الحالة الموحّدة + القرار + حالة الحَوكمة."""
    field_id: str
    canonical_state: CanonicalFieldState
    policy_decision: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    generated_at: str = ""


def run_field_intelligence(
    req: FieldRequest,
    weather_fn: Optional[Callable] = None,
    soil_fn: Optional[Callable] = None,
    sensing_fn: Optional[Callable] = None,
    field_obs_fn: Optional[Callable] = None,
    ndvi_history: Optional[list] = None,
    guardrails_fn: Optional[Callable] = None,
    crop_context: Optional[CropContext] = None,
    economic_context: Optional[EconomicContext] = None,
) -> FieldIntelligenceResult:
    """المسار الكامل: جمع → تطبيع → دمج (مايسترو) → سياسة → حَوكمة.

    الدمج يحدث مرّة واحدة في compose_field_state. منطق القرار يعمل فوق
    الحالة الموحّدة (policy-over-state)، ثمّ يمرّ بالقواعد الحاكمة قبل الإصدار.
    crop_context يضيف: مرحلة النمو + Kc/GDD + التقويم النجمي + المكان + الصنف.
    economic_context يضيف: قيد اقتصادي (قد يجعل 'لا تدخّل' أصحّ).
    """
    now = datetime.now(timezone.utc).isoformat()

    # ① جمع ② تطبيع
    collected = collect_signals(req, weather_fn, soil_fn, sensing_fn, field_obs_fn)
    signals = normalize_signals(collected)

    # ③ الدمج (المايسترو) — مرّة واحدة → الحالة الموحّدة (+ تقويم/فينولوجيا)
    state = compose_field_state(req.field_id, signals,
                                ndvi_trend_values=ndvi_history,
                                crop_context=crop_context,
                                tenant_id=req.tenant_id, farm_id=req.farm_id)
    # نقل المصادر المتعذّرة لإعلان الصدق في الحالة
    for u in collected.unavailable:
        if u not in state.missing_signals:
            state.missing_signals.append(u)

    # ④ السياسة (policy-over-state) — قرار من الحالة الموحّدة لا من الخام
    economics = assess_economics(economic_context) if economic_context else {}
    decision = _derive_policy(state, economics)

    # ⑤ الحَوكمة — لا توصية تصدر بلا مرور بالقواعد الحاكمة
    governance = {"status": "not_evaluated",
                  "note": "القواعد الحاكمة تُطبَّق على جهاز التشغيل (guardrails حيّ)"}
    if guardrails_fn is not None and decision.get("actionable"):
        try:
            governance = guardrails_fn(decision, state)
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن لا نخترع موافقة
            governance = {"status": "error", "note": f"تعذّر التحقّق: {e}"}

    return FieldIntelligenceResult(
        field_id=req.field_id, canonical_state=state,
        policy_decision=decision, governance=governance, generated_at=now)


def _derive_policy(state: CanonicalFieldState, economics: Optional[dict] = None) -> dict:
    """يشتقّ توصية من الحالة الموحّدة (policy-over-state، لا تفسير خام).

    يحترم حلّ التعارض الذي حسمه المايسترو (effective_status).
    economics قيد اقتصادي: قد يحوّل 'تدخّل' إلى 'لا تدخّل' إن لم يُجدِ.
    """
    truths = state.operational_truths
    effective = truths.get("effective_status")
    decision: dict = {"actionable": False, "recommendations_ar": []}

    # القرار يتبع الحالة الفعليّة (بعد حلّ التعارض في المايسترو)
    if effective == "salinity_limited":
        decision["actionable"] = True
        decision["action_type"] = "soil_remediation"
        decision["recommendations_ar"].append(
            "الملوحة حرجة (تتجاوز المؤشّر الطيفي الإيجابي): "
            "غسيل + صرف + تجنّب اعتماد NDVI وحده.")
        decision["structured"] = {"issue": "salinity", "severity": "critical"}
    elif effective == "vigor_led":
        vigor = truths.get("crop_vigor", 0)
        if vigor < 0.4:
            decision["actionable"] = True
            decision["action_type"] = "investigate_stress"
            decision["recommendations_ar"].append(
                f"الحيويّة منخفضة ({vigor}): افحص الريّ/التغذية ميدانيّاً.")

    # التحليل الزمني يضيف إنذاراً مبكراً (trend > snapshot)
    if truths.get("ndvi_trend") == "decreasing":
        decision["actionable"] = True
        decision["recommendations_ar"].append(
            "اتّجاه NDVI هابط (إنذار مبكر) — تابع عن قرب حتّى لو القيمة طبيعيّة.")

    # مرحلة النمو تُخصّص التوصية (القرار بلا مرحلة نموّ أعمى)
    stage = truths.get("growth_stage") or truths.get("fao56_stage")
    if stage:
        decision["growth_stage"] = stage
        kc = truths.get("kc")
        if kc:
            decision["recommendations_ar"].append(
                f"الطلب المائي للمرحلة الحاليّة: Kc={kc} (FAO-56) — اضبط الريّ وفقه.")
        # الإنبات حسّاس للملوحة (germination_ece أدنى)
        if stage in ("emergence", "initial", "INITIAL") and \
                truths.get("salinity_class") in ("moderate", "critical"):
            decision["actionable"] = True
            decision["recommendations_ar"].append(
                "⚠ مرحلة الإنبات حسّاسة للملوحة — الملوحة الحاليّة قد تضرّ الإنبات.")

    # التوقيت النجمي كقرينة (لا حاكم)
    if truths.get("timing_context_ar"):
        decision["recommendations_ar"].append(
            f"سياق توقيت تقليدي: {truths['timing_context_ar'][:60]}")

    # الثقة المنخفضة تُرفق صراحةً بالقرار (لا قرار واثق ببيانات ضعيفة)
    decision["confidence"] = state.confidence
    decision["confidence_reason"] = state.confidence_reason
    if state.confidence in ("none", "low"):
        decision["recommendations_ar"].append(
            "⚠ ثقة منخفضة (بيانات ناقصة/قديمة) — تحقّق ميداني قبل التنفيذ.")
    # القيد الاقتصادي — قد يحوّل قراراً قابلاً للتنفيذ إلى "لا تدخّل" مُبرّر
    if economics:
        decision["economics"] = economics
        # إن كان الإجراء غير مُجدٍ اقتصاديّاً، نُبقي الإنذار لكن نوصي بالتريّث
        if decision.get("actionable") and economics.get("economically_justified") is False:
            decision["recommendations_ar"].append(
                "⚖ اقتصاديّاً: " + economics.get("economic_note_ar",
                "العائد لا يبرّر التكلفة — وازِن قبل التنفيذ."))
            decision["economic_caution"] = True
        # تقلّب السعر العالي يُضاف كسياق
        if economics.get("price_risk") in ("high", "HIGH"):
            decision["recommendations_ar"].append(
                "⚠ تقلّب سعري عالٍ — راعِ المخاطر السوقيّة في التوقيت.")

    # نيّة المزارع تُعدّل وزن القرار (تحويله من علميّ إلى تشغيلي)
    objective = truths.get("farmer_objective")
    if objective:
        decision["farmer_objective"] = objective
        if objective == "minimize_cost":
            decision["recommendations_ar"].append(
                "🎯 هدفك تقليل التكلفة — فضّل التدخّلات منخفضة التكلفة وراجع الجدوى.")
        elif objective == "water_saving":
            decision["recommendations_ar"].append(
                "🎯 هدفك توفير الماء — اضبط الريّ على Kc بدقّة وتجنّب الإفراط.")
        elif objective == "risk_reduction":
            decision["recommendations_ar"].append(
                "🎯 هدفك تقليل المخاطر — تدخّل وقائيّ مبكر مفضّل حتّى بكلفة أعلى.")
        elif objective == "maximize_yield":
            decision["recommendations_ar"].append(
                "🎯 هدفك أقصى إنتاج — لا تؤخّر معالجة الإجهاد.")

    return decision
