"""api/canonical_water_stress.py — قارئ الإجهاد المائيّ الكنسيّ (Bundle D / D2a+D2b) — اشتقاق صرف.

الغرض:
   يطبّع استنزاف منطقة الجذور المخزَّن (`water_ledger.depletion_mm` + الثقة) مع TAW
   (من `soil_water.soil_water_params`) إلى **كتلة `water_stress` كنسيّة واحدة** على
   نموذج الحالة القانونيّة، بمستويات FAO-56 صريحة — فتقرؤها الحالة والمستهلكون من
   **مصدر واحد**. القرار المُقَرّ (المستخدم 2026-06-23،
   [`decisions/water-stress-d2.md`](../../../sahool-brain/decisions/water-stress-d2.md)):

       NORMAL  : AWF > 1−p              (Dr < RAW)            تشغيل طبيعيّ
       WATCH   : 0.2 < AWF ≤ 1−p        (Dr ≥ RAW)            تنبيه/أولويّة ريّ
       CRITICAL: AWF ≤ 0.2              (Dr ≥ 0.8·TAW)        توصية عاجلة

   حيث AWF = 1 − Dr/TAW (جزء الماء المتاح المتبقّي؛ 1=سعة حقليّة، 0=ذبول).

صدق صريح — ما هذا وما ليس هو:
   - **اشتقاق + أهليّة، لا تصعيد هنا:** القارئ يحسب الكتلة المعلوماتيّة + الأهليّة
     (`escalation_eligible` بالمسند المُقَرّ) لكنّه **لا يطبّق العلم ولا يغيّر
     `execution_mode`** — ذلك للإسقاط (`field_state_projection`) خلف
     `FEATURE_WATER_STRESS_ESCALATION` (default off). D2b: الأهليّة = إجهاد ضارّ
     (critical) + ثقة استنزاف ≥ 0.8 + تأكيد طيفيّ (NDMI+MSI) — «فيزياء + رصد».
   - **غير معايَر يمنيّاً:** TAW من FAO-56 Table 19 وp افتراضيّ 0.5 — الكتلة موسومة
     `calibrated=False` صدقاً (تحتاج معايرة ميدانيّة قبل الاعتماد الكمّيّ).
   - **fail-safe:** غياب Dr أو TAW غير صالح / مدخل غير قاموس ⇒ `None` (لا كتلة
     مُلفّقة، لا قرار على غياب). لا يَرمي أبداً.
"""

from __future__ import annotations

from core.engines.spectral_stress_bridge import fuse_water_stress

from api.soil_water import available_water_fraction

# عتبة الإجهاد الضارّ (المُقَرّة): استنزاف ≥ 80% من TAW ⇒ AWF ≤ 0.2.
WATER_STRESS_CRITICAL_AWF = 0.2

# أدنى ثقة استنزاف لأهليّة التصعيد (قرار المستخدم 2026-06-23): فيزياء موثوقة.
ESCALATION_CONFIDENCE_MIN = 0.8

# إشارات الجسر الطيفيّ التي تُعدّ «إجهاداً مؤكَّداً» (moderate/severe).
_SPECTRAL_STRESS_SIGNALS = frozenset({"moderate", "severe"})


def _coerce_float(value) -> float | None:
    """تحويل آمن إلى float — None عند الفشل بدل الرمي."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_water_stress(row: dict | None) -> dict | None:
    """يطبّع استنزاف/TAW إلى كتلة إجهاد مائيّ كنسيّة، أو ``None`` عند غياب الأساس.

    المُدخل ``row`` — dict (أو None):
        ``depletion_mm`` (Dr، إلزاميّ) · ``taw_mm`` (إلزاميّ > 0) · ``raw_fraction``
        (p، افتراضيّ 0.5) · ``depletion_confidence`` (اختياريّ) · ``soil_moisture_pct``
        (اختياريّ، معلوماتيّ).

    المُدخل (D2b، اختياريّ): ``ndmi`` · ``msi`` (للتأكيد الطيفيّ).

    المُخرَج — dict أو None:
        ``water_stress_awf`` · ``water_stress_class`` (normal|watch|critical) ·
        ``depletion_mm`` · ``taw_mm`` · ``raw_fraction`` · ``depletion_confidence`` ·
        ``soil_moisture_pct`` · ``calibrated`` (=False) · ``source`` · **(D2b)** ``ndmi`` ·
        ``msi`` · ``spectral_confirmation_available`` · ``spectral_stress_detected``
        (bool|None) · ``spectral_confidence`` (high|moderate|None) · ``escalation_eligible``.

    صدق: غياب Dr أو TAW≤0 أو مدخل غير صالح ⇒ ``None``.
    """
    if not isinstance(row, dict):
        return None
    dr = _coerce_float(row.get("depletion_mm"))
    taw = _coerce_float(row.get("taw_mm"))
    if dr is None or taw is None or taw <= 0:
        return None

    p = _coerce_float(row.get("raw_fraction"))
    if p is None:
        p = 0.5
    p = max(0.0, min(1.0, p))

    awf = available_water_fraction(dr, taw)
    if awf <= WATER_STRESS_CRITICAL_AWF:
        cls = "critical"
    elif awf <= (1.0 - p):  # Dr ≥ RAW — بدء الإجهاد الفسيولوجيّ (تنبيه لا تصعيد)
        cls = "watch"
    else:
        cls = "normal"

    dep_conf = _coerce_float(row.get("depletion_confidence"))

    # D2b: تأكيد طيفيّ (NDMI + MSI) — قرار المستخدم: كلا المؤشّرين مطلوبان للتأكيد؛
    # غياب أيّهما ⇒ confirmation_available=False و detected=None ⇒ لا تصعيد (صدق:
    # «فيزياء + رصد»، لا تصعيد بلا رصد). الجسر fuse_water_stress جاهز (None ⇒ unknown).
    ndmi = _coerce_float(row.get("ndmi"))
    msi = _coerce_float(row.get("msi"))
    spectral_available = ndmi is not None and msi is not None
    spectral_detected: bool | None = None
    spectral_confidence: str | None = None
    if spectral_available:
        fused = fuse_water_stress(ndmi, msi)
        spectral_detected = fused["fused_signal"] in _SPECTRAL_STRESS_SIGNALS
        spectral_confidence = fused["confidence"]

    # الأهليّة (المسند المُقَرّ، بلا العلم — العلم يطبّقه الإسقاط): إجهاد ضارّ مؤكَّد
    # بفيزياء موثوقة + رصد طيفيّ.
    escalation_eligible = bool(
        cls == "critical"
        and dep_conf is not None
        and dep_conf >= ESCALATION_CONFIDENCE_MIN
        and spectral_available
        and spectral_detected
    )

    return {
        "water_stress_awf": round(awf, 3),
        "water_stress_class": cls,
        "depletion_mm": round(dr, 2),
        "taw_mm": round(taw, 2),
        "raw_fraction": round(p, 3),
        "depletion_confidence": dep_conf,
        "soil_moisture_pct": _coerce_float(row.get("soil_moisture_pct")),
        "ndmi": ndmi,
        "msi": msi,
        "spectral_confirmation_available": spectral_available,
        "spectral_stress_detected": spectral_detected,
        "spectral_confidence": spectral_confidence,
        "escalation_eligible": escalation_eligible,
        "calibrated": False,  # TAW/p غير معايَرين يمنيّاً (صدق)
        "source": "field_state.canonical",
    }
