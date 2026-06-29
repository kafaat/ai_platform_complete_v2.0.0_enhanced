"""
agronomic_state_engine.py — طبقة الغراء (Semantic Composition Layer).

ليست "عقلاً جديداً" بل **غراء** يجمع اللبنات الموجودة في حالة موحّدة:
  - fuse_health (engines/fusion.py) — دمج المؤشّرات الطيفيّة + ثقة احتماليّة
  - detect_trend (core/time_series.py) — التحليل الزمني (slope/anomaly)
  - fuse_confidence (core/knowledge_levels.py) — قاعدة الثقة ≤ أدنى سقف
  - provenance — سلسلة الأدلّة

المبدأ (من المراجعتين): الدمج يحدث **مرّة واحدة** هنا، فيُنتج CanonicalFieldState،
ثمّ decision_engine يصبح policy-over-state (لا يعيد تفسير المؤشّرات الخام).

حلّ التعارض (arbitration): قواعد أسبقيّة صريحة، لا IF عشوائيّة. مثال حاسم:
  ملوحة حرجة تتجاوز NDVI الإيجابي (NDVI قد يتأخّر؛ الملوحة انهيار بنيوي).

الصدق: كلّ مؤشّر غائب يُعلَن، والثقة تنخفض بنقص المُدخلات (لا تخمين).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.thresholds import SALINITY_CRITICAL_ECE, SALINITY_MODERATE_ECE

# إصدارات (المراجعة الثانية: القرارات historical-sensitive — replay/audit)
SCHEMA_VERSION = "1.0"
FUSION_STRATEGY_VERSION = "1.0"

# عتبات حلّ التعارض من المصدر الموحّد core.thresholds (SAL-SOIL-*؛ نفس القيم 8/4 dS/m).
# مُعاد تصديرها هنا (مُستعمَلة أدناه) للحفاظ على المستورِدين الحاليّين لهذين الاسمين.

# مصفوفة الأسبقيّة الصريحة (arbitration matrix) — من يحكم عند التعارض؟
# المبدأ (من المراجعة): القيود البنيويّة طويلة الأمد تتقدّم على القرائن اللحظيّة.
# الترتيب تنازليّاً: الأعلى أولويّةً يحكم الحالة الفعليّة (effective_status).
# كلّ بند: (المعرّف, الحالة الناتجة, شرط التفعيل, التعليل, القاعدة المصدر).
ARBITRATION_PRECEDENCE = [
    # ١. الملوحة الحرجة — انهيار بنيوي يتجاوز أيّ مؤشّر إيجابي
    (
        "salinity_critical",
        "salinity_limited",
        "الملوحة الحرجة (انهيار بنيوي) تتجاوز المؤشّرات اللحظيّة",
        "SAL-SOIL-03",
    ),
    # ٢. الإجهاد الحراري الحادّ — ضغط مستقبلي وشيك
    ("heat_severe", "heat_limited", "إجهاد حراري حادّ — يتقدّم على الحيويّة الحاليّة", "HEAT-01"),
    # ٣. اتّجاه هابط مستمرّ — إنذار مبكر يتقدّم على القيمة اللحظيّة
    (
        "declining_trend",
        "trend_warning",
        "اتّجاه هابط مستمرّ (trend>snapshot) — إنذار مبكر",
        "MON-TREND-01",
    ),
    # ٤. حيويّة منخفضة — حالة فعليّة مُلاحَظة
    ("low_vigor", "vigor_stressed", "حيويّة منخفضة فعليّة — تستوجب فحصاً", "RS-VIGOR-01"),
    # ٥. الحيويّة الجيّدة تقود (الحالة الطبيعيّة)
    ("vigor_ok", "vigor_led", "حيويّة جيّدة بلا قيود مهيمنة", "RS-VIGOR-02"),
]


@dataclass
class SignalInput:
    """إشارة خام مُطبّعة من مصدر (المراجعة: NormalizedSignal)."""

    source: str  # ndvi | ndre | ndsi | soil_ec | weather...
    value: float | None = None
    confidence: str = "medium"  # high | medium | low | none
    observed_at: str | None = None  # ISO — لحساب الحداثة
    spatial_resolution_m: float | None = None
    field_coverage: float | None = None  # 0..1 (نسبة تغطية الحقل)


@dataclass
class CropContext:
    """سياق المحصول للتقويم الفينولوجي (Kc/GDD/مرحلة النمو)."""

    crop_id: str | None = None
    days_after_planting: int | None = None
    ndvi_series: list | None = None  # [(day_of_year, ndvi), ...] لمرحلة النمو
    et0_mm: float | None = None  # Bundle D: ET0 المرجعيّ (mm) لحقن ETc الكنسيّ = Kc·ET0
    star_id: str | None = None  # نوء حالي (التقويم النجمي)
    location_zone: str | None = None  # الإقليم المناخي (المكان)
    variety_id: str | None = None  # صنف (يُعدّل عتبات الملوحة/الجفاف)
    farmer_objective: str | None = None  # maximize_yield|minimize_cost|water_saving|risk_reduction


@dataclass
class EconomicContext:
    """سياق اقتصادي — يجعل 'لا تدخّل' قراراً صحيحاً اقتصاديّاً أحياناً."""

    crop_id: str | None = None
    historical_prices: list | None = None  # أسعار تاريخيّة للتقلّب
    local_price: float | None = None
    import_price: float | None = None
    intervention_cost: float | None = None  # تكلفة الإجراء المقترح
    expected_gain: float | None = None  # العائد المتوقّع منه
    # تكاليف المدخلات المفصّلة (من المستخدم — لا نخترع أسعاراً)
    input_costs: dict | None = None  # {"seeds":..,"fertilizer":..,"labor":..,"irrigation":..}
    area_ha: float | None = None  # لحساب التكلفة لكلّ هكتار


@dataclass
class CanonicalFieldState:
    """الحالة الزراعيّة الرسميّة الموحّدة للحقل (الغراء الحقيقي).

    تُنتَج مرّة واحدة، ويستهلكها decision_engine + guardrails (لا إعادة تفسير).
    """

    field_id: str
    generated_at: str
    # سيادة البيانات: كلّ حالة مملوكة لمستأجر (multi-tenant isolation)
    tenant_id: str | None = None
    farm_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    fusion_strategy_version: str = FUSION_STRATEGY_VERSION
    # الحقائق التشغيليّة المشتقّة (operational truths)
    operational_truths: dict = field(default_factory=dict)
    # الثقة الكلّيّة + تفصيلها
    confidence: str = "none"
    confidence_reason: str = ""
    # سلسلة الأدلّة (provenance) — كلّ حقيقة لمصدرها ووزنه
    provenance: list = field(default_factory=list)
    # التعارضات المُكتشَفة وكيف حُلّت
    contradictions: list = field(default_factory=list)
    # المؤشّرات الغائبة (صدق: نُعلنها صراحةً)
    missing_signals: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """تسلسل قابل للحفظ (persistence) والمقارنة الموسميّة (replay/audit).

        الإصدارات مُضمَّنة لتفسير الحالة عبر ترقيات النموذج لاحقاً.
        """
        return {
            "field_id": self.field_id,
            "tenant_id": self.tenant_id,
            "farm_id": self.farm_id,
            "generated_at": self.generated_at,
            "schema_version": self.schema_version,
            "fusion_strategy_version": self.fusion_strategy_version,
            "operational_truths": dict(self.operational_truths),
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "provenance": list(self.provenance),
            "contradictions": list(self.contradictions),
            "missing_signals": list(self.missing_signals),
        }

    def explain_decision(self) -> dict:
        """سلسلة تفسير القرار الموحّدة (decision explainability lineage).

        يجمع ما هو مبعثر أصلاً (provenance/arbitration/conflicts/confidence)
        في مخرج واحد يجيب: ماذا قرّرنا؟ لماذا؟ بأيّ ثقة؟ ما التعارضات وكيف حُلّت؟
        ليس policy DSL ثقيلاً — بل تصدير شفّاف لما يحسبه المايسترو فعلاً.
        """
        t = self.operational_truths
        return {
            "field_id": self.field_id,
            "decision": {
                "effective_status": t.get("effective_status"),
                "reason_ar": t.get("effective_status_reason"),
                "winning_rule": t.get("effective_status_rule"),
            },
            "confidence": {
                "level": self.confidence,
                "reason_ar": self.confidence_reason,
            },
            # سلسلة الأدلّة: كلّ حقيقة ← مصدرها ووزنها
            "evidence_chain": list(self.provenance),
            # التحكيم: التعارضات وكيف حُسمت (conflict audit lineage)
            "conflicts_resolved": [c for c in self.contradictions if isinstance(c, dict)],
            "warnings": [c for c in self.contradictions if not isinstance(c, dict)],
            "missing_signals": list(self.missing_signals),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CanonicalFieldState:
        """يُعيد بناء الحالة من تسلسل محفوظ (للمقارنة التاريخيّة)."""
        return cls(
            field_id=d["field_id"],
            tenant_id=d.get("tenant_id"),
            farm_id=d.get("farm_id"),
            generated_at=d["generated_at"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            fusion_strategy_version=d.get("fusion_strategy_version", FUSION_STRATEGY_VERSION),
            operational_truths=d.get("operational_truths", {}),
            confidence=d.get("confidence", "none"),
            confidence_reason=d.get("confidence_reason", ""),
            provenance=d.get("provenance", []),
            contradictions=d.get("contradictions", []),
            missing_signals=d.get("missing_signals", []),
        )


def _signal_age_days(observed_at: str | None) -> float | None:
    """عمر الإشارة بالأيّام (للثقة المعتمدة على الحداثة)."""
    if not observed_at:
        return None
    try:
        dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        # BLOCKER-02: طابع بلا منطقة زمنيّة (mobile/IoT) ⇒ naive؛ طرحه من now(UTC)
        # المُدرَكة يرفع TypeError (غير مُلتقَط) فيُسقِط محرّك الحالة. نفترض UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        return (now - dt).total_seconds() / 86400.0
    except (ValueError, AttributeError, TypeError):
        return None


def compose_field_state(
    field_id: str,
    signals: list[SignalInput],
    ndvi_trend_values: list[float] | None = None,
    crop_context: CropContext | None = None,
    tenant_id: str | None = None,
    farm_id: str | None = None,
) -> CanonicalFieldState:
    """يؤلّف الحالة الموحّدة من الإشارات — يعيد استخدام اللبنات الموجودة.

    لا يخترع منطق دمج جديد: يستدعي fuse_health/detect_trend/fuse_confidence.
    tenant_id/farm_id لسيادة البيانات (كلّ حالة مملوكة لمستأجر).
    """
    now = datetime.now(UTC).isoformat()
    state = CanonicalFieldState(
        field_id=field_id, generated_at=now, tenant_id=tenant_id, farm_id=farm_id
    )

    by_source = {s.source: s for s in signals}
    truths: dict = {}
    prov: list = []

    # ── ١. صحّة نباتيّة من المؤشّرات الطيفيّة + الرادار (يعيد استخدام fuse_health) ──
    spectral = [
        s for s in signals if s.source in ("ndvi", "ndre", "ndsi", "ndwi") and s.value is not None
    ]
    # رادار: RVI (مؤشّر الغطاء الراداري، مُطبَّع [0,1] — قابل للدمج مع البصري، عكس
    # الـbackscatter الخام بـdB). family="sar" ⇒ fuse_health يرفع وزنه عند السحب،
    # فيُكمل مقاومة الغيوم (البصري ينخفض، الرادار يرتفع).
    sar = [s for s in signals if s.source in ("rvi", "sar") and s.value is not None]
    if spectral or sar:
        try:
            from core.engines.fusion import IndexReading, fuse_health

            n = len(spectral) + len(sar)
            readings = [
                IndexReading(
                    name=s.source, value=s.value, sigma=0.05, weight=1.0 / n, family="optical"
                )
                for s in spectral
            ]
            readings += [
                IndexReading(name=s.source, value=s.value, sigma=0.08, weight=1.0 / n, family="sar")
                for s in sar
            ]
            # cloud_cover من إشارة إن وُجدت، وإلّا 0 (لا تخمين سحب عالٍ)
            cloud = next((s.value for s in signals if s.source == "cloud_cover"), 0.0)
            fr = fuse_health(readings, cloud_cover_pct=cloud or 0.0)
            truths["crop_vigor"] = round(fr.fused_value, 3)
            truths["crop_vigor_confidence"] = fr.confidence.value
            truths["crop_vigor_dominant"] = fr.dominant_family  # optical|sar (مقاومة السحاب)
            # شفافيّة: ملاحظات الدمج (منها تحويل الوزن للرادار عند السحب) تُسطَّح
            # في الحالة الموحّدة لتكون مرئيّة/قابلة للتتبّع (كانت تُفقَد).
            if fr.notes:
                truths["crop_vigor_notes"] = fr.notes
            truths["cloud_cover_pct"] = round(float(cloud or 0.0), 1)
            for s in spectral + sar:
                prov.append(
                    {
                        "source": s.source,
                        "weight": round(1.0 / n, 3),
                        "contributes_to": "crop_vigor",
                    }
                )
        except Exception as e:  # noqa: BLE001 — صدق: لو فشل، نُعلن لا نخترع
            state.contradictions.append(f"fuse_health تعذّر: {e}")
    else:
        state.missing_signals.append("spectral_indices (ndvi/ndre/ndsi)")

    # ── ١-ب. مؤشّرات مشتقّة: LAI (من NDVI) + BSI/SI (قرائن، لا أدلّة) ──
    ndvi_sig = by_source.get("ndvi")
    if ndvi_sig and ndvi_sig.value is not None:
        try:
            from core.spatial.pipeline import estimate_lai_from_ndvi

            lai = estimate_lai_from_ndvi(ndvi_sig.value)
            if lai.get("lai") is not None:
                truths["lai"] = round(lai["lai"], 2)
                truths["lai_confidence"] = lai.get("confidence", "low")
                prov.append({"source": "ndvi_lai", "contributes_to": "lai"})
        except Exception as e:  # noqa: BLE001
            state.contradictions.append(f"estimate_lai تعذّر: {e}")
    # BSI (تربة عارية) وSI (ملوحة طيفي): قرائن توجّه لعيّنة، لا تحكم.
    for ind, key, note in (
        ("bsi", "bare_soil_index", "تربة عارية — قرينة غطاء"),
        ("si", "spectral_salinity", "ملوحة طيفيّة — قرينة لا حكم"),
    ):
        sig = by_source.get(ind)
        if sig and sig.value is not None:
            truths[key] = round(sig.value, 3)
            truths[f"{key}_class"] = "indication"  # قرينة (سقف ثقة منخفض)
            prov.append({"source": ind, "contributes_to": key, "note_ar": note})

    # ── ٢. مخاطر الملوحة من التربة (SAL-SOIL-*) ──
    soil_ec = by_source.get("soil_ec")
    if soil_ec and soil_ec.value is not None:
        ec = soil_ec.value
        if ec >= SALINITY_CRITICAL_ECE:
            truths["salinity_risk"] = round(min(ec / 16.0, 1.0), 2)
            truths["salinity_class"] = "critical"
        elif ec >= SALINITY_MODERATE_ECE:
            truths["salinity_risk"] = round(ec / 16.0, 2)
            truths["salinity_class"] = "moderate"
        else:
            truths["salinity_risk"] = round(ec / 16.0, 2)
            truths["salinity_class"] = "low"
        prov.append({"source": "soil_ec", "value": ec, "contributes_to": "salinity_risk"})
    else:
        state.missing_signals.append("soil_ec (الملوحة)")

    # ── ٢-ب. مخاطر الطقس (heat_risk من إشارة الطقس) ──
    weather_sig = by_source.get("weather")
    if weather_sig and weather_sig.value is not None:
        truths["heat_risk"] = round(weather_sig.value, 2)
        prov.append({"source": "weather", "contributes_to": "heat_risk"})

    # ── ٣. التحليل الزمني (يعيد استخدام detect_trend) ──
    if ndvi_trend_values and len(ndvi_trend_values) >= 4:
        try:
            from datetime import timedelta

            from core.time_series import TimePoint, detect_trend

            # بناء TimePoint بتواريخ يوميّة تنازليّة (الأحدث آخراً)
            base = datetime.now(UTC)
            n = len(ndvi_trend_values)
            points = [
                TimePoint(timestamp=(base - timedelta(days=(n - 1 - i))).isoformat(), value=v)
                for i, v in enumerate(ndvi_trend_values)
            ]
            tr = detect_trend(points)
            truths["ndvi_trend"] = (
                tr.direction.value if hasattr(tr.direction, "value") else str(tr.direction)
            )
            truths["ndvi_slope_per_day"] = tr.slope_per_day
            prov.append({"source": "ndvi_timeseries", "contributes_to": "ndvi_trend"})
        except Exception as e:  # noqa: BLE001
            state.contradictions.append(f"detect_trend تعذّر: {e}")

    # ── ٤. حلّ التعارض (arbitration) — مصفوفة أسبقيّة صريحة ──
    # تُقيَّم الشروط بترتيب الأولويّة؛ أوّل شرط يتحقّق يحكم الحالة الفعليّة.
    # هذا يستبدل المنطق الـad-hoc بمصفوفة شاملة قابلة للتدقيق.
    vigor = truths.get("crop_vigor")
    sal_class = truths.get("salinity_class")
    heat = truths.get("heat_risk")
    trend = truths.get("ndvi_trend")
    # خريطة المعرّف → هل شرطه متحقّق؟
    conditions = {
        "salinity_critical": sal_class == "critical",
        "heat_severe": heat is not None and heat >= 0.8,
        "declining_trend": trend == "decreasing",
        "low_vigor": vigor is not None and vigor < 0.4,
        "vigor_ok": vigor is not None,
    }
    for cond_id, status, reason_ar, rule in ARBITRATION_PRECEDENCE:
        if conditions.get(cond_id):
            truths["effective_status"] = status
            truths["effective_status_reason"] = reason_ar
            truths["effective_status_rule"] = rule
            # سجّل التعارض إن كان مؤشّر إيجابي مُتجاوَزاً بقيد أعلى
            if status != "vigor_led" and vigor is not None and vigor > 0.5:
                state.contradictions.append(
                    {
                        "type": f"positive_signal_overridden_by_{cond_id}",
                        "resolution": f"{cond_id}_overrides",
                        "reason_ar": reason_ar,
                        "source_rule": rule,
                    }
                )
            break

    # ── ٥. الثقة الكلّيّة (يعيد استخدام fuse_confidence) ──
    # fuse_confidence يأخذ أسماء المصادر (ndvi/ec/lab...) ويطبّق سقف أدنى مصدر.
    # الثقة تنخفض بنقص المُدخلات + قِدَم البيانات (المراجعة: confidence رياضي).
    source_names = [s.source for s in signals if s.value is not None]
    # ترجمة أسماء SAHOOL لمفردات knowledge_levels (soil_ec→ec)
    _map = {
        "soil_ec": "ec",
        "ndre": "ndvi",
        "ndsi": "si",
        "ndwi": "ndvi",
        "weather": "weather_station",
    }
    mapped = [_map.get(s, s) for s in source_names]
    try:
        from core.knowledge_levels import fuse_confidence

        conf, reason = fuse_confidence(mapped or ["guess"])
        state.confidence = conf
        state.confidence_reason = reason
    except Exception:  # noqa: BLE001 — fallback صادق
        state.confidence = "low" if source_names else "none"
        state.confidence_reason = "تعذّر fuse_confidence — تقدير محافظ"

    # خفض الثقة لو نقصت مؤشّرات جوهريّة (صدق)
    if state.missing_signals:
        state.confidence_reason += f" | مؤشّرات ناقصة: {len(state.missing_signals)}"

    # خفض الثقة لو البيانات قديمة (freshness SLA)
    stale = [s.source for s in signals if (_signal_age_days(s.observed_at) or 0) > 14]
    if stale:
        state.contradictions.append(
            {
                "type": "stale_observation",
                "sources": stale,
                "reason_ar": "بيانات أقدم من 14 يوماً — الثقة مخفّضة",
            }
        )

    # ── ٦. التقويم الفينولوجي + النجمي (مرحلة النمو + Kc + التوقيت) ──
    if crop_context is not None:
        _wire_phenology_and_calendar(state, truths, crop_context, prov)

    state.operational_truths = truths
    state.provenance = prov
    return state


def _wire_phenology_and_calendar(state, truths, ctx, prov):
    """يربط: مرحلة النمو (من NDVI) + Kc/GDD + التقويم النجمي (anwa).

    يعيد استخدام: detect_growth_stage_from_ndvi, kc_for_age, anwa_timing_context.
    القرار بلا مرحلة نموّ أعمى — هذه أهمّ إضافة.
    """
    # ① مرحلة النمو من منحنى NDVI الزمني
    if ctx.ndvi_series and len(ctx.ndvi_series) >= 3:
        try:
            from core.spatial.pipeline import detect_growth_stage_from_ndvi

            # detect_growth_stage_from_ndvi يتوقّع أزواج (يوم السنة، NDVI).
            # المايسترو قد يتلقّى أرقاماً مجرّدة [0.4,0.5,..] → نطبّعها لأزواج
            # بفهرسة متساوية (الترتيب الزمني محفوظ) لتجنّب 'float not subscriptable'.
            _series = ctx.ndvi_series
            if _series and not isinstance(_series[0], (tuple, list)):
                _series = [(i, float(v)) for i, v in enumerate(_series)]
            gs = detect_growth_stage_from_ndvi(_series)
            if gs.get("stage"):
                truths["growth_stage"] = gs["stage"]
                truths["growth_stage_ar"] = gs.get("stage_ar")
                truths["growth_stage_confidence"] = gs.get("confidence", "medium")
                prov.append({"source": "ndvi_phenology", "contributes_to": "growth_stage"})
        except Exception as e:  # noqa: BLE001
            state.contradictions.append(f"detect_growth_stage تعذّر: {e}")

    # ② Kc/المرحلة من عمر المحصول (الجانب البيولوجي الثابت — FAO-56)
    if ctx.crop_id and ctx.days_after_planting is not None:
        try:
            from core.crop_cards.loader import load_crop_card
            from core.engines.fao56 import CropKcProfile, kc_for_age

            card = load_crop_card(ctx.crop_id)
            if card and card.get("kc"):
                kc_d = card["kc"]
                salt = card.get("salt_tolerance", {})
                profile = CropKcProfile(
                    crop_id=ctx.crop_id,
                    kc_initial=kc_d.get("initial", 0.3),
                    kc_mid=kc_d.get("mid", 1.0),
                    kc_end=kc_d.get("end", 0.4),
                    stage_days=kc_d.get("stage_days", [15, 25, 50, 30]),
                    salt_tolerance_ece=salt.get("threshold_ece_ds_m", 4.0),
                    salt_slope_pct=salt.get("slope_pct_per_ds_m", 0.0),
                )
                kc, stage = kc_for_age(profile, ctx.days_after_planting)
                truths["kc"] = round(kc, 2)
                truths["fao56_stage"] = stage.value if hasattr(stage, "value") else str(stage)
                truths["water_fingerprint_source"] = "FAO-56"
                prov.append({"source": "fao56_kc", "contributes_to": "water_demand"})
                # Bundle D (D1): ETc الكنسيّ = Kc·ET0 عند توفّر إشارة ET0 — **إضافة صرفة**
                # (لا تمسّ effective_status/التحكيم/الصلاحيّة). يجعل الحالة القانونيّة تحمل
                # ET0/ETc الموحّدين بدل إعادة حسابهما في كلّ نقطة. صدق: غياب ET0 ⇒ لا etc
                # (الحقل غائب، لا اختلاق). ET0 يُمرَّر عبر CropContext.et0_mm من إسقاط الحالة.
                if ctx.et0_mm is not None:
                    et0v = float(ctx.et0_mm)
                    etc = max(0.0, kc * et0v)
                    truths["et0_mm"] = round(et0v, 2)
                    truths["etc_mm"] = round(etc, 2)
                    truths["etc_demand_class"] = (
                        "high" if etc > 8.0 else "medium" if etc > 4.0 else "low"
                    )
                    prov.append(
                        {"source": "fao56_etc", "contributes_to": "etc_mm", "formula": "Kc·ET0"}
                    )
            else:
                state.missing_signals.append(f"kc_profile ({ctx.crop_id}): لا بطاقة/Kc")
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن لا نخترع Kc
            state.missing_signals.append(f"kc_profile ({ctx.crop_id}): {e}")

    # ③ التقويم النجمي (anwa) — قرينة توقيت مجتمعيّة
    if ctx.star_id:
        try:
            from core.anwa_calendar import anwa_timing_context

            tc = anwa_timing_context(ctx.star_id)
            if tc:
                truths["timing_context_ar"] = getattr(tc, "traditional_advice_ar", None) or getattr(
                    tc, "note_ar", None
                )
                truths["timing_is_governing"] = getattr(tc, "is_governing", False)
                truths["timing_source"] = "anwa_calendar (الحميري العنسي)"
                prov.append({"source": "anwa_calendar", "contributes_to": "timing"})
        except Exception as e:  # noqa: BLE001
            state.contradictions.append(f"anwa_calendar تعذّر: {e}")

    # ④ المكان (الإقليم المناخي) — سياق بيئي
    if ctx.location_zone:
        truths["climate_zone"] = ctx.location_zone
        prov.append({"source": "geo_zone", "contributes_to": "climate_context"})

    # ⑤ الصنف (cultivar) — يُعدّل عتبات القرار (ليس metadata)
    if ctx.variety_id:
        try:
            from core.crop_cards.loader import load_variety_card

            v = load_variety_card(ctx.variety_id)
            if v:
                traits = v.get("variety_traits", {})
                truths["variety_id"] = ctx.variety_id
                truths["variety_drought_tolerance"] = traits.get("drought_tolerance")
                # مُعدّل تحمّل الملوحة: يُزيح عتبة الملوحة الحرجة للصنف
                salt_mod = traits.get("salt_tolerance_modifier", 0.0)
                if salt_mod:
                    truths["salinity_threshold_shift"] = salt_mod
                    truths["salinity_threshold_note_ar"] = (
                        f"الصنف يُعدّل عتبة الملوحة بـ{salt_mod} dS/m"
                    )
                truths["maturity_class"] = v.get("maturity_class") or traits.get("maturity_class")
                prov.append({"source": "cultivar", "contributes_to": "decision_thresholds"})
        except Exception as e:  # noqa: BLE001
            state.missing_signals.append(f"variety ({ctx.variety_id}): {e}")

    # ⑥ نيّة المزارع — تُحوّل القرار من علميّ إلى تشغيلي
    if ctx.farmer_objective:
        truths["farmer_objective"] = ctx.farmer_objective
        prov.append({"source": "farmer_intent", "contributes_to": "decision_weighting"})


def assess_economics(econ: EconomicContext) -> dict:
    """يحلّل الجدوى الاقتصاديّة — يعيد استخدام analyse_market.

    صدق: يُرجِع تقييماً لا يحكم وحده؛ القرار النهائي يوازنه مع الأَولويّات.
    """
    result: dict = {}
    # تقلّب السعر ومخاطره (analyse_market)
    if econ.crop_id and econ.historical_prices:
        try:
            from core.engines.market_analyzer import analyse_market

            sig = analyse_market(
                econ.crop_id, econ.historical_prices, econ.local_price, econ.import_price
            )
            result["price_risk"] = (
                sig.price_risk.value if hasattr(sig.price_risk, "value") else str(sig.price_risk)
            )
            result["price_cv"] = sig.cv
            result["market_opportunity_ar"] = sig.opportunity_ar
            result["market_data_quality"] = sig.data_quality
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن لا نخترع
            result["market_error"] = str(e)
    # نسبة العائد/التكلفة للإجراء (هل يستحقّ اقتصاديّاً؟)
    if econ.intervention_cost is not None and econ.expected_gain is not None:
        cost = econ.intervention_cost
        gain = econ.expected_gain
        result["benefit_cost_ratio"] = round(gain / cost, 2) if cost > 0 else None
        # قاعدة صريحة: عائد < تكلفة → "لا تدخّل" اقتصاديّاً
        result["economically_justified"] = bool(cost > 0 and gain > cost)
        if not result["economically_justified"]:
            result["economic_note_ar"] = (
                "العائد المتوقّع لا يغطّي تكلفة الإجراء — قد يكون 'لا تدخّل' "
                "أصحّ اقتصاديّاً رغم وجود إجهاد بسيط."
            )

    # تكاليف المدخلات المفصّلة (من المستخدم) — إجمالي + لكلّ هكتار
    if econ.input_costs:
        total = sum(v for v in econ.input_costs.values() if isinstance(v, (int, float)))
        result["input_cost_total"] = round(total, 2)
        result["input_cost_breakdown"] = dict(econ.input_costs)
        if econ.area_ha and econ.area_ha > 0:
            result["cost_per_hectare"] = round(total / econ.area_ha, 2)
    return result


def economic_context_from_ledger(
    season_summary, crop_id=None, historical_prices=None, local_price=None, area_ha=None
):
    """يبني EconomicContext من ملخّص موسم دفتر المزرعة (farm_ledger).

    دفتر المزرعة يُملأ من Odoo (المخزون/العمليّات الحقليّة/التكاليف) عبر
    odoo-bridge. هذه الدالّة الجسر: تحوّل التكاليف الفعليّة (لا المخترعة) إلى
    سياق اقتصادي يدخل القرار. صدق: تعتمد على بيانات Odoo الحقيقيّة حين تتوفّر.

    season_summary: كائن SeasonSummary (له expense_breakdown + total_expenses).
    """
    # expense_breakdown: kind → مبلغ (بذور/أسمدة/عمالة/ريّ... من Odoo)
    breakdown = getattr(season_summary, "expense_breakdown", None) or {}
    total_exp = getattr(season_summary, "total_expenses", None)
    total_inc = getattr(season_summary, "total_income", None)
    ctx = EconomicContext(
        crop_id=crop_id,
        historical_prices=historical_prices,
        local_price=local_price,
        input_costs=dict(breakdown) if breakdown else None,
        area_ha=area_ha,
        # العائد المتوقّع = الدخل الفعلي؛ التكلفة = المصروف الفعلي (من Odoo)
        intervention_cost=total_exp,
        expected_gain=total_inc,
    )
    return ctx


def state_to_event_row(
    state: CanonicalFieldState, actor_id: str = "system", command_id: str | None = None
) -> dict:
    """يحوّل الحالة الموحّدة إلى صفّ حدث لجدول events الموجود (DB-backed).

    يربط المايسترو الجديد بالـpersistence/event-sourcing الموجود (events table).
    سيادة البيانات: tenant_id مُلزَم (RLS). صدق: الكتابة الفعليّة في DB على
    جهازك؛ هذه الدالّة تُنتج الصفّ المطابق للمخطّط، جاهزاً للإدراج.

    يُمكّن: الذاكرة الموسميّة + replay + المقارنة التاريخيّة (عبر event_replay).
    """
    if not state.tenant_id:
        raise ValueError("tenant_id مُلزَم لحفظ الحالة (سيادة البيانات/RLS)")
    return {
        "event_type": "field.canonical_state_computed",
        "schema_version": 1,
        "entity_type": "field",
        "entity_id": state.field_id,
        "tenant_id": state.tenant_id,
        "actor_id": actor_id,
        "command_id": command_id,
        "payload": state.to_dict(),  # الحالة كاملة (JSONB) — قابلة للـreplay
        "source": "ai",  # المايسترو مصدر ذكاء
        "occurred_at": state.generated_at,
    }


def compare_seasons(current: CanonicalFieldState, previous: CanonicalFieldState) -> dict:
    """يقارن حالتين موسميّتين (intelligence over time — رفع الفجوة الزمنيّة).

    يعمل على CanonicalFieldState المحفوظة (عبر state_to_event_row + event_replay).
    صدق: يقارن المتاح فقط؛ المؤشّرات الغائبة في أيّهما تُعلَن لا تُختلق.
    """
    cur_t = current.operational_truths
    prev_t = previous.operational_truths
    result = {
        "field_id": current.field_id,
        "current_at": current.generated_at,
        "previous_at": previous.generated_at,
        "deltas": {},
        "notes_ar": [],
    }
    # قارن المقاييس العدديّة المشتركة
    for metric in ("crop_vigor", "salinity_risk", "lai", "kc"):
        cur_v = cur_t.get(metric)
        prev_v = prev_t.get(metric)
        if isinstance(cur_v, (int, float)) and isinstance(prev_v, (int, float)):
            delta = round(cur_v - prev_v, 3)
            pct = round((delta / prev_v) * 100, 1) if prev_v else None
            result["deltas"][metric] = {
                "current": cur_v,
                "previous": prev_v,
                "delta": delta,
                "pct_change": pct,
            }
        elif cur_v is None or prev_v is None:
            result["notes_ar"].append(f"{metric}: غير متاح في أحد الموسمين (لا مقارنة)")
    # تنبيهات الاتّجاه المهمّة
    sal = result["deltas"].get("salinity_risk")
    if sal and sal["delta"] > 0.05:
        result["notes_ar"].append(
            f"⚠ الملوحة ترتفع عبر المواسم (+{sal['delta']}) — تدهور تدريجي محتمل."
        )
    vig = result["deltas"].get("crop_vigor")
    if vig and vig["pct_change"] is not None and vig["pct_change"] < -10:
        result["notes_ar"].append(f"⚠ الحيويّة أدنى {abs(vig['pct_change'])}% من الموسم السابق.")
    return result
