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

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.agronomic_state_engine import (
    CanonicalFieldState,
    CropContext,
    EconomicContext,
    SignalInput,
    assess_economics,
    compose_field_state,
)


# ── الطبقة ١: Collectors — جلب الحقائق الخام فقط (ممنوع اتّخاذ قرار) ──
# كلّ collector دالّة تُرجِع dict خام أو None (متعذّر). تُحقَن للاختبار،
# وعلى جهاز التشغيل تكون نداءات HTTP للخدمات (weather/soil/raster).
@dataclass
class FieldRequest:
    field_id: str
    lat: float | None = None
    lon: float | None = None
    crop: str | None = None
    tenant_id: str | None = None  # سيادة البيانات (multi-tenant)
    farm_id: str | None = None


@dataclass
class CollectorResult:
    """نتيجة جمع المصادر الخام — مع إعلان المتعذّر بصدق."""

    raw: dict = field(default_factory=dict)
    unavailable: list = field(default_factory=list)


def collect_signals(
    req: FieldRequest,
    weather_fn: Callable | None = None,
    soil_fn: Callable | None = None,
    sensing_fn: Callable | None = None,
    field_obs_fn: Callable | None = None,
) -> CollectorResult:
    """يجمع الحقائق الخام من المصادر. صدق: المتعذّر يُعلَن لا يُختلق."""
    result = CollectorResult()
    for name, fn in (
        ("weather", weather_fn),
        ("soil", soil_fn),
        ("sensing", sensing_fn),
        ("field_obs", field_obs_fn),
    ):
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
    now = datetime.now(UTC).isoformat()

    # الاستشعار → ndvi/ndre/ndsi/ndwi (دقّة 10م، تغطية من نسبة البكسلات السليمة)
    sensing = raw.get("sensing", {})
    # rvi = مؤشّر الغطاء الراداري ([0,1]) — يُدمج كـSAR (مقاومة السحاب)
    for idx in ("ndvi", "ndre", "ndsi", "ndwi", "bsi", "si", "rvi"):
        if idx in sensing and sensing[idx] is not None:
            signals.append(
                SignalInput(
                    source=idx,
                    value=sensing[idx],
                    confidence="medium",
                    observed_at=sensing.get("observed_at", now),
                    spatial_resolution_m=sensing.get("resolution_m", 10.0),
                    field_coverage=sensing.get("field_coverage"),
                )
            )

    # غطاء السحب → إشارة منفصلة (لا تدخل الدمج الطيفي، لكنّها تُفعّل تحويل الوزن
    # إلى SAR في fuse_health). كانت مفقودة ⇒ cloud دائماً 0 في المسار الحيّ.
    if sensing.get("cloud_cover") is not None:
        signals.append(
            SignalInput(
                source="cloud_cover",
                value=sensing["cloud_cover"],
                confidence="high",
                observed_at=sensing.get("observed_at", now),
                spatial_resolution_m=sensing.get("resolution_m", 10.0),
                field_coverage=sensing.get("field_coverage"),
            )
        )

    # التربة → soil_ec (تحليل مخبري — ثقة عالية، لكن قد يكون قديماً)
    soil = raw.get("soil", {})
    if soil.get("ec_dsm") is not None:
        signals.append(
            SignalInput(
                source="soil_ec",
                value=soil["ec_dsm"],
                confidence="high",
                observed_at=soil.get("sampled_at"),
            )
        )

    # الطقس → إشارة سياقيّة (لا قيمة عدديّة مباشرة للدمج الطيفي، لكن للسياق)
    weather = raw.get("weather", {})
    if weather.get("heat_risk") is not None:
        signals.append(
            SignalInput(
                source="weather",
                value=weather["heat_risk"],
                confidence="medium",
                observed_at=weather.get("forecast_at", now),
            )
        )

    # الميدانيّة → ملاحظة المزارع (ثقة اجتماعيّة — سقفها منخفض)
    fobs = raw.get("field_obs", {})
    if fobs.get("stress_observed") is not None:
        signals.append(
            SignalInput(
                source="farmer",
                value=fobs["stress_observed"],
                confidence="low",
                observed_at=fobs.get("observed_at", now),
            )
        )

    return signals


# ── الطبقة ٣+٤+٥: Fusion → Policy → Guardrails (المسار الكامل) ──

# حالات الحَوكمة التي تَسمح بتنفيذ/توزيع القرار. أيّ حالة أخرى (وبخاصّة
# not_evaluated/error) ⇒ القرار **استشاريّ فقط** ولا يُوزَّع (fail-closed:
# لا نُخلّص ما لم تمرّ عليه القواعد الحاكمة فعليّاً).
GOVERNANCE_APPROVED_STATES = frozenset({"approved", "passed", "cleared", "ok"})

_TRUTHY = {"1", "true", "yes", "on"}


def _direct_executable_enabled() -> bool:
    """Escape hatch (DECISION-CENTER-UNIFY-01, fail-closed default).

    Default **False**: a field-intelligence policy is never ``executable`` on guardrails
    clearance alone — execution requires a decision-center pass. Set
    ``FIELD_INTELLIGENCE_DIRECT_EXECUTABLE_ENABLED=true`` to restore the legacy
    guardrails-only executability. (Note: ``executable`` here is display/evidence only;
    the real actuator path runs through decision_dispatch's human-approval tiers.)
    """
    return os.getenv("FIELD_INTELLIGENCE_DIRECT_EXECUTABLE_ENABLED", "").strip().lower() in _TRUTHY


def governance_permits_dispatch(governance: dict | None) -> bool:
    """هل حالة الحَوكمة تسمح بتوزيع/تنفيذ القرار؟ (fail-closed، نقيّ).

    تُرجِع True فقط إذا كانت `governance.status` ضمن الحالات الموافِقة المعلومة.
    not_evaluated / error / مجهول ⇒ False (لا تُختلق موافقة — صدق + أمان).
    """
    if not governance:
        return False
    status = str(governance.get("status", "")).strip().lower()
    return status in GOVERNANCE_APPROVED_STATES


@dataclass
class FieldIntelligenceResult:
    """ناتج المسار الكامل: الحالة الموحّدة + القرار + حالة الحَوكمة.

    Runtime Cohesion: يضمّ الآن السياق التاريخي (farm_memory) والمحاكاة
    (simulation) في graph قرار واحد — لا أنظمة فرعيّة منفصلة.

    حَوكمة (enforcement): القرار **لا يكون قابلاً للتنفيذ/التوزيع** ما لم تمرّ
    الحَوكمة فعليّاً بحالة موافِقة. `executable=False` عند governance.status ==
    not_evaluated (لم تُطبَّق القواعد الحاكمة) — لا تُختلق موافقة. هذا العَلَم
    (لا `policy_decision["actionable"]` الزراعيّ) هو ما تستهلكه طبقة التوزيع.
    """

    field_id: str
    canonical_state: CanonicalFieldState
    policy_decision: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    generated_at: str = ""
    farm_memory_context: dict = field(default_factory=dict)  # السياق التاريخي
    simulation: dict = field(default_factory=dict)  # أثر what-if المتوقّع
    forecast: dict = field(default_factory=dict)  # توقّع جوّي حيّ (Open-Meteo) — إثراء
    # بوّابة التنفيذ المحكومة (تُحسَب في run_field_intelligence). صدق: القرار
    # الزراعيّ قد يكون actionable لكنّه **غير قابل للتنفيذ** حتى تُقَرّ الحَوكمة.
    executable: bool = False
    dispatch_block_reason: str | None = "governance_not_evaluated"


def run_field_intelligence(
    req: FieldRequest,
    weather_fn: Callable | None = None,
    soil_fn: Callable | None = None,
    sensing_fn: Callable | None = None,
    field_obs_fn: Callable | None = None,
    ndvi_history: list | None = None,
    guardrails_fn: Callable | None = None,
    crop_context: CropContext | None = None,
    economic_context: EconomicContext | None = None,
    memory_fn: Callable | None = None,
    simulate_fn: Callable | None = None,
    forecast_fn: Callable | None = None,
) -> FieldIntelligenceResult:
    """# DECISION-PATH: canonical — خطّ القرار المُعتمَد للمنصّة.

    المسار الكامل: جمع → تطبيع → دمج (مايسترو) → سياسة → حَوكمة → بوّابة التنفيذ.
    هذا هو **مسار القرار القانونيّ (canonical)**: كلّ قرار قابل للتوزيع يجب أن
    يمرّ به (compose_field_state → policy → guardrails → executable gate → dispatch).

    الدمج يحدث مرّة واحدة في compose_field_state. منطق القرار يعمل فوق
    الحالة الموحّدة (policy-over-state)، ثمّ يمرّ بالقواعد الحاكمة قبل الإصدار.
    crop_context يضيف: مرحلة النمو + Kc/GDD + التقويم النجمي + المكان + الصنف.
    economic_context يضيف: قيد اقتصادي (قد يجعل 'لا تدخّل' أصحّ).

    حَوكمة (enforcement): إن لم يُمرَّر `guardrails_fn` تبقى الحَوكمة
    not_evaluated ⇒ القرار **استشاريّ فقط** (executable=False،
    dispatch_block_reason="governance_not_evaluated"). لا يصير القرار قابلاً
    للتنفيذ إلّا إذا أقرّت الحَوكمة بحالة موافِقة فعليّاً — لا تُختلق موافقة.
    """
    now = datetime.now(UTC).isoformat()

    # ① جمع ② تطبيع
    collected = collect_signals(req, weather_fn, soil_fn, sensing_fn, field_obs_fn)
    signals = normalize_signals(collected)

    # ③ الدمج (المايسترو) — مرّة واحدة → الحالة الموحّدة (+ تقويم/فينولوجيا)
    state = compose_field_state(
        req.field_id,
        signals,
        ndvi_trend_values=ndvi_history,
        crop_context=crop_context,
        tenant_id=req.tenant_id,
        farm_id=req.farm_id,
    )
    # نقل المصادر المتعذّرة لإعلان الصدق في الحالة
    for u in collected.unavailable:
        if u not in state.missing_signals:
            state.missing_signals.append(u)

    # ④ السياسة (policy-over-state) — قرار من الحالة الموحّدة لا من الخام
    economics = assess_economics(economic_context) if economic_context else {}
    decision = _derive_policy(state, economics)

    # ⑤ الحَوكمة — لا توصية تصدر بلا مرور بالقواعد الحاكمة
    governance = {
        "status": "not_evaluated",
        "note": "القواعد الحاكمة تُطبَّق على جهاز التشغيل (guardrails حيّ)",
    }
    if guardrails_fn is not None and decision.get("actionable"):
        try:
            governance = guardrails_fn(decision, state)
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن لا نخترع موافقة
            governance = {"status": "error", "note": f"تعذّر التحقّق: {e}"}

    # ⑥ السياق التاريخي (farm_memory) — يُغني القرار بذاكرة الحقل الزمنيّة.
    # Runtime Cohesion: الذاكرة تدخل graph القرار، لا نظام منفصل. fail-safe:
    # فشلها لا يُسقط القرار (السياق إثراء لا شرط).
    farm_memory_context: dict = {}
    if memory_fn is not None:
        try:
            mem = memory_fn(req)
            if mem:
                farm_memory_context = mem
                # إن كشفت الذاكرة تكراراً (مثلاً ملوحة متكرّرة) نرفعه للقرار
                recurring = mem.get("recurring_issues")
                if recurring:
                    decision.setdefault("historical_context_ar", [])
                    decision["historical_context_ar"].append(
                        f"سياق تاريخي: {', '.join(recurring)} — يتكرّر في هذا الحقل."
                    )
        except Exception as e:  # noqa: BLE001 — صدق: الذاكرة إثراء لا شرط
            farm_memory_context = {"error": f"تعذّر جلب الذاكرة: {e}"}

    # ⑦ المحاكاة (what-if) — تُغني القرار بالأثر المتوقّع لإجراء مقترَح.
    # Runtime Cohesion: المحاكاة تدخل graph القرار عند طلبها (لا عبر مسار
    # منفصل). تُشغَّل فقط إن كان القرار actionable (لا محاكاة عبثيّة).
    simulation: dict = {}
    if simulate_fn is not None and decision.get("actionable"):
        try:
            sim = simulate_fn(req, decision, state)
            if sim:
                simulation = sim
                # إن أظهرت المحاكاة أنّ الإجراء لا يُجدي، نُعلنه في القرار
                if sim.get("recommended_action_helps") is False:
                    decision.setdefault("simulation_caveat_ar", "")
                    decision["simulation_caveat_ar"] = (
                        "المحاكاة تشير إلى أثر محدود للإجراء المقترَح — راجِع الجدوى."
                    )
        except Exception as e:  # noqa: BLE001 — صدق: المحاكاة إثراء لا شرط
            simulation = {"error": f"تعذّرت المحاكاة: {e}"}

    # ⑧ التوقّع الجوّي الحيّ (Open-Meteo) — إثراء للقرار، fail-safe (لا يُسقطه).
    # يُجلَب فعليّاً عند توفّر forecast_fn (المحوّل الافتراضي keyless). صدق: None ⇒ {}.
    forecast: dict = {}
    if forecast_fn is not None:
        try:
            fc = forecast_fn(req)
            if fc:
                forecast = fc
        except Exception as e:  # noqa: BLE001 — صدق: التوقّع إثراء لا شرط
            forecast = {"error": f"تعذّر التوقّع: {e}"}

    # ⑨ بوّابة التنفيذ المحكومة (ENFORCEMENT) — قرار not_evaluated **لا يُنفَّذ**.
    # القرار قابل للتنفيذ فقط إذا كان زراعيّاً actionable **و** أقرّت الحَوكمة
    # بحالة موافِقة فعليّاً. غياب guardrails_fn ⇒ not_evaluated ⇒ استشاريّ فقط
    # (لا تُختلق موافقة). نُعلن سبب المنع صراحةً في القرار (للواجهة وطبقة التوزيع).
    governance_ok = governance_permits_dispatch(governance)
    guardrails_cleared = bool(decision.get("actionable")) and governance_ok
    # DECISION-CENTER-UNIFY-01 (fail-closed default): guardrails clearance alone does NOT
    # make a field-intelligence policy executable — a decision-center pass is required.
    # FIELD_INTELLIGENCE_DIRECT_EXECUTABLE_ENABLED restores the legacy guardrails-only gate.
    executable = guardrails_cleared and _direct_executable_enabled()
    if executable:
        dispatch_block_reason = None
    elif not decision.get("actionable"):
        dispatch_block_reason = "not_actionable"  # القرار نفسه لا يستدعي تدخّلاً
    elif str(governance.get("status", "")).strip().lower() == "error":
        dispatch_block_reason = "governance_error"
    elif not governance_ok:
        dispatch_block_reason = "governance_not_evaluated"
    else:
        # الحَوكمة أقرّت لكنّ مركز القرار لم يُصرّح بالتنفيذ — لا تجاوز للمركز.
        dispatch_block_reason = "requires_decision_center"
    # نعكس البوّابة في القرار نفسه لئلّا يُعامَل actionable كأنّه مُخلَّص للتنفيذ.
    decision["executable"] = executable
    decision["dispatch_block_reason"] = dispatch_block_reason

    return FieldIntelligenceResult(
        field_id=req.field_id,
        canonical_state=state,
        policy_decision=decision,
        governance=governance,
        generated_at=now,
        farm_memory_context=farm_memory_context,
        simulation=simulation,
        forecast=forecast,
        executable=executable,
        dispatch_block_reason=dispatch_block_reason,
    )


def _derive_policy(state: CanonicalFieldState, economics: dict | None = None) -> dict:
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
            "الملوحة حرجة (تتجاوز المؤشّر الطيفي الإيجابي): غسيل + صرف + تجنّب اعتماد NDVI وحده."
        )
        decision["structured"] = {"issue": "salinity", "severity": "critical"}
    elif effective == "vigor_led":
        vigor = truths.get("crop_vigor", 0)
        if vigor < 0.4:
            decision["actionable"] = True
            decision["action_type"] = "investigate_stress"
            decision["recommendations_ar"].append(
                f"الحيويّة منخفضة ({vigor}): افحص الريّ/التغذية ميدانيّاً."
            )

    # التحليل الزمني يضيف إنذاراً مبكراً (trend > snapshot)
    if truths.get("ndvi_trend") == "decreasing":
        decision["actionable"] = True
        decision["recommendations_ar"].append(
            "اتّجاه NDVI هابط (إنذار مبكر) — تابع عن قرب حتّى لو القيمة طبيعيّة."
        )

    # مرحلة النمو تُخصّص التوصية (القرار بلا مرحلة نموّ أعمى)
    stage = truths.get("growth_stage") or truths.get("fao56_stage")
    if stage:
        decision["growth_stage"] = stage
        kc = truths.get("kc")
        if kc:
            decision["recommendations_ar"].append(
                f"الطلب المائي للمرحلة الحاليّة: Kc={kc} (FAO-56) — اضبط الريّ وفقه."
            )
        # الإنبات حسّاس للملوحة (germination_ece أدنى)
        if stage in ("emergence", "initial", "INITIAL") and truths.get("salinity_class") in (
            "moderate",
            "critical",
        ):
            decision["actionable"] = True
            decision["recommendations_ar"].append(
                "⚠ مرحلة الإنبات حسّاسة للملوحة — الملوحة الحاليّة قد تضرّ الإنبات."
            )

    # التوقيت النجمي كقرينة (لا حاكم)
    if truths.get("timing_context_ar"):
        decision["recommendations_ar"].append(
            f"سياق توقيت تقليدي: {truths['timing_context_ar'][:60]}"
        )

    # الثقة المنخفضة تُرفق صراحةً بالقرار (لا قرار واثق ببيانات ضعيفة)
    decision["confidence"] = state.confidence
    decision["confidence_reason"] = state.confidence_reason
    if state.confidence in ("none", "low"):
        decision["recommendations_ar"].append(
            "⚠ ثقة منخفضة (بيانات ناقصة/قديمة) — تحقّق ميداني قبل التنفيذ."
        )
    # القيد الاقتصادي — قد يحوّل قراراً قابلاً للتنفيذ إلى "لا تدخّل" مُبرّر
    if economics:
        decision["economics"] = economics
        # إن كان الإجراء غير مُجدٍ اقتصاديّاً، نُبقي الإنذار لكن نوصي بالتريّث
        if decision.get("actionable") and economics.get("economically_justified") is False:
            decision["recommendations_ar"].append(
                "⚖ اقتصاديّاً: "
                + economics.get("economic_note_ar", "العائد لا يبرّر التكلفة — وازِن قبل التنفيذ.")
            )
            decision["economic_caution"] = True
        # تقلّب السعر العالي يُضاف كسياق
        if economics.get("price_risk") in ("high", "HIGH"):
            decision["recommendations_ar"].append(
                "⚠ تقلّب سعري عالٍ — راعِ المخاطر السوقيّة في التوقيت."
            )

    # نيّة المزارع تُعدّل وزن القرار (تحويله من علميّ إلى تشغيلي)
    objective = truths.get("farmer_objective")
    if objective:
        decision["farmer_objective"] = objective
        if objective == "minimize_cost":
            decision["recommendations_ar"].append(
                "🎯 هدفك تقليل التكلفة — فضّل التدخّلات منخفضة التكلفة وراجع الجدوى."
            )
        elif objective == "water_saving":
            decision["recommendations_ar"].append(
                "🎯 هدفك توفير الماء — اضبط الريّ على Kc بدقّة وتجنّب الإفراط."
            )
        elif objective == "risk_reduction":
            decision["recommendations_ar"].append(
                "🎯 هدفك تقليل المخاطر — تدخّل وقائيّ مبكر مفضّل حتّى بكلفة أعلى."
            )
        elif objective == "maximize_yield":
            decision["recommendations_ar"].append("🎯 هدفك أقصى إنتاج — لا تؤخّر معالجة الإجهاد.")

    return decision
