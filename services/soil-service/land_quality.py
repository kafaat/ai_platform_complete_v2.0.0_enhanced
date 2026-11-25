"""land_quality.py — تقييم جودة الأرض: الصوديّة والجبس وصنف القدرة (Farmland Phase 2 · 0002).

نوى حسابيّة نقيّة (بلا I/O) تستهلك سجلّ المعايير (`standards_registry`) ومحرّك المطابقة
(`compliance_engine`) بدل تكرار عتباتهما:

- **ESP من الصوديوم المتبادل و CEC**: ESP = 100 · Na_ex / CEC (USDA HB60).
- **ESP مُقدَّرة من SAR** (مستخلص التشبّع): ESR = −0.0126 + 0.01475·SAR؛
  ESP = 100·ESR/(1+ESR) (USDA HB60، المعادلة التجريبيّة للمختبر الأمريكيّ للملوحة).
  تقدير لا قياس — يُعلَّم `basis="estimated_from_sar"`.
- **احتياج الجبس**: الصوديوم الواجب إحلاله (cmolc/kg) = CEC·(ESPi − ESPt)/100؛
  الجبس (كغ/هـ) = ذلك × 0.8609 غ/cmolc (الوزن المكافئ لـ CaSO4·2H2O = 86.09)
  × كتلة التربة (10⁷ · العمق م · الكثافة الظاهريّة t/m³ كغ/هـ) ÷ 1000،
  مقسوماً على النقاوة ومضروباً في معامل كفاءة الإحلال المُعلَن.
  فحص المعقوليّة الكلاسيكيّ: 1 cmolc/kg في 15 سم بكثافة 1.33 ⇒ ≈ 1.72 t/ha.
- **صنف الملوحة/الصوديّة** (HB60): normal / saline / sodic / saline_sodic عبر المحرّك.
- **صنف القدرة (AH-210)** بمبدأ العامل المُحدِّد: أسوأ عامل يحدّد الصنف، والصنف الفرعيّ
  يسمّي العامل (e انحدار/تعرية · s تربة · w ابتلال). عاملٌ ناقص ⇒ الصنف **مؤقّت**
  («في أحسن الأحوال») لا نهائيّ — لا تصنيف كامل على بيانات ناقصة.

لا قيم مُختلَقة: العتبات من السجلّ وكلّها `calibrated_for_region=False`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date

from compliance_engine import Observation, classify_band, evaluate_standards
from standards_registry import (
    AH210_LAND_CAPABILITY,
    AH210_SOURCE,
    DRAINAGE_CLASS_TO_CAPABILITY,
    EFFECTIVE_DEPTH_CLASS_LIMITS_CM,
    HB60_SALINE_SODIC,
)

LAND_QUALITY_VERSION = "land-quality.v1"
GYPSUM_EQ_WEIGHT_G_PER_MOLC = 86.09  # CaSO4·2H2O: 172.17 g/mol ÷ 2
_CLASS_ORDER = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")


class LandQualityInputError(ValueError):
    """مدخل غير صالح — يُرفَع بدل إرجاع رقم مُضلِّل."""


def _req_finite(
    name: str,
    value: float,
    *,
    lo: float | None = None,
    hi: float | None = None,
    lo_open: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LandQualityInputError(f"{name}_must_be_finite")
    v = float(value)
    if lo is not None and (v < lo or (lo_open and v == lo)):
        raise LandQualityInputError(f"{name}_out_of_range")
    if hi is not None and v > hi:
        raise LandQualityInputError(f"{name}_out_of_range")
    return v


# ── ESP ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EspResult:
    esp_pct: float
    basis: str  # "measured_exchangeable_na" | "estimated_from_sar"
    source: str

    def to_dict(self) -> dict:
        return {"esp_pct": self.esp_pct, "basis": self.basis, "source": self.source}


def esp_from_exchangeable_na(na_cmolc_kg: float, cec_cmolc_kg: float) -> EspResult:
    """ESP = 100 · Na_ex / CEC. صوديوم يفوق CEC مستحيل فيزيائيّاً ⇒ خطأ لا قصّ."""
    cec = _req_finite("cec_cmolc_kg", cec_cmolc_kg, lo=0.0, lo_open=True)
    na = _req_finite("na_cmolc_kg", na_cmolc_kg, lo=0.0)
    if na > cec:
        raise LandQualityInputError("exchangeable_na_exceeds_cec")
    return EspResult(
        esp_pct=round(100.0 * na / cec, 4),
        basis="measured_exchangeable_na",
        source="USDA HB60 (1954): ESP = exchangeable Na / CEC × 100",
    )


def esp_from_sar(sar: float) -> EspResult:
    """تقدير ESP من SAR مستخلص التشبّع (HB60). ESR السالب عند SAR صغير جدّاً ⇒ ESP = 0."""
    s = _req_finite("sar", sar, lo=0.0)
    esr = -0.0126 + 0.01475 * s
    esp = 0.0 if esr <= 0 else 100.0 * esr / (1.0 + esr)
    return EspResult(
        esp_pct=round(esp, 4),
        basis="estimated_from_sar",
        source="USDA HB60 (1954): ESR = -0.0126 + 0.01475·SAR; ESP = 100·ESR/(1+ESR)",
    )


# ── احتياج الجبس ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GypsumRequirement:
    gypsum_t_per_ha: float
    na_to_replace_cmolc_kg: float
    soil_mass_t_per_ha: float
    inputs: dict
    assumptions: dict
    source: str

    def to_dict(self) -> dict:
        return {
            "gypsum_t_per_ha": self.gypsum_t_per_ha,
            "na_to_replace_cmolc_kg": self.na_to_replace_cmolc_kg,
            "soil_mass_t_per_ha": self.soil_mass_t_per_ha,
            "inputs": dict(self.inputs),
            "assumptions": dict(self.assumptions),
            "source": self.source,
        }


def gypsum_requirement_from_exchangeable_na(
    *,
    cec_cmolc_kg: float,
    na_exchangeable_cmolc_kg: float,
    esp_target_pct: float,
    depth_m: float,
    bulk_density_t_m3: float,
    purity: float = 1.0,
    exchange_efficiency_factor: float = 1.0,
) -> GypsumRequirement:
    """احتياج الجبس من القياس المخبريّ المباشر (Na المتبادل + CEC) — المسار المُفضَّل.

    لا تقدير لـ ESP من SAR هنا: الجرعة تُبنى على ما قِيس، والأساس يُسجَّل في الناتج.
    """
    esp = esp_from_exchangeable_na(na_exchangeable_cmolc_kg, cec_cmolc_kg)
    r = gypsum_requirement(
        cec_cmolc_kg=cec_cmolc_kg,
        esp_initial_pct=esp.esp_pct,
        esp_target_pct=esp_target_pct,
        depth_m=depth_m,
        bulk_density_t_m3=bulk_density_t_m3,
        purity=purity,
        exchange_efficiency_factor=exchange_efficiency_factor,
        esp_basis=esp.basis,
    )
    return replace(
        r, inputs={**r.inputs, "na_exchangeable_cmolc_kg": float(na_exchangeable_cmolc_kg)}
    )


def gypsum_requirement(
    *,
    cec_cmolc_kg: float,
    esp_initial_pct: float,
    esp_target_pct: float,
    depth_m: float,
    bulk_density_t_m3: float,
    purity: float = 1.0,
    exchange_efficiency_factor: float = 1.0,
    esp_basis: str = "caller_supplied",
) -> GypsumRequirement:
    """احتياج الجبس (t/ha) لخفض ESP من القيمة الحاليّة إلى الهدف في عمق مُعلَن.

    `exchange_efficiency_factor` = 1.0 يعني الاحتياج **النظريّ (الاستوكيومتريّ)**؛ المراجع
    تستعمل عادةً 1.1–1.3 لتعويض الإحلال غير الكامل — قرارٌ للمستدعي يُسجَّل في الناتج لا
    يُفرَض صامتاً. هدفٌ ≥ الحاليّ ⇒ صفر (لا حاجة)، لا قيمة سالبة.
    """
    cec = _req_finite("cec_cmolc_kg", cec_cmolc_kg, lo=0.0, lo_open=True)
    esp_i = _req_finite("esp_initial_pct", esp_initial_pct, lo=0.0, hi=100.0)
    esp_t = _req_finite("esp_target_pct", esp_target_pct, lo=0.0, hi=100.0)
    depth = _req_finite("depth_m", depth_m, lo=0.0, hi=3.0, lo_open=True)
    bd = _req_finite("bulk_density_t_m3", bulk_density_t_m3, lo=0.5, hi=2.65)
    pur = _req_finite("purity", purity, lo=0.0, hi=1.0, lo_open=True)
    eff = _req_finite("exchange_efficiency_factor", exchange_efficiency_factor, lo=1.0, hi=2.0)

    na_replace = max(0.0, cec * (esp_i - esp_t) / 100.0)
    soil_mass_t = 1.0e4 * depth * bd  # m² × m × t/m³
    # cmolc/kg × 0.8609 g/cmolc = g/kg soil  ⇒ × soil kg ÷ 1e6 = t
    gypsum_t = na_replace * (GYPSUM_EQ_WEIGHT_G_PER_MOLC / 100.0) * soil_mass_t * 1000.0 / 1.0e6
    gypsum_t = gypsum_t * eff / pur
    return GypsumRequirement(
        gypsum_t_per_ha=round(gypsum_t, 3),
        na_to_replace_cmolc_kg=round(na_replace, 4),
        soil_mass_t_per_ha=round(soil_mass_t, 1),
        inputs={
            "cec_cmolc_kg": cec,
            "esp_initial_pct": esp_i,
            "esp_target_pct": esp_t,
            "depth_m": depth,
            "bulk_density_t_m3": bd,
        },
        assumptions={
            "purity": pur,
            "exchange_efficiency_factor": eff,
            "requirement_basis": "theoretical" if eff == 1.0 else "efficiency_adjusted",
            "esp_basis": esp_basis,
            "amendment": "CaSO4·2H2O",
            "equivalent_weight_g_per_molc": GYPSUM_EQ_WEIGHT_G_PER_MOLC,
        },
        source=(
            "USDA HB60 (1954) gypsum requirement: Na to replace = CEC·(ESPi−ESPt)/100; "
            "gypsum = Na × 86.09 g/molc × soil mass"
        ),
    )


# ── صنف الملوحة/الصوديّة (HB60) ─────────────────────────────────────────


SATURATION_EXTRACT_25C = "saturation_extract_25c"


@dataclass(frozen=True)
class SalinitySodicityClass:
    """صنف HB60 بنصفَين مستقلّين: الملوحة (ECe) والصوديّة (ESP).

    `saline`/`sodic`: True/False حين يُحسَم النصف من قياسٍ صالح، None حين لا يُحسَم (غائب، قديم،
    أو EC بطريقةٍ لا تقارَن بمستخلص العجينة المشبعة). كلّ نصفٍ محسوم يكفي لما يخصّه (ESP ≥ 15
    صوديّة أيّاً كان EC)؛ أمّا **التسمية الكاملة** (`soil_class`) فلا تُعطى إلّا بحسم النصفين.
    """

    soil_class: str | None  # normal | saline | sodic | saline_sodic | None (نصفٌ غير محسوم)
    complete: bool
    saline: bool | None
    sodic: bool | None
    compliance: dict
    reason: str
    freshness: str  # "enforced" | "not_verifiable_no_sample_date"
    withheld: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "soil_class": self.soil_class,
            "complete": self.complete,
            "saline": self.saline,
            "sodic": self.sodic,
            "reason": self.reason,
            "withheld": list(self.withheld),
            "freshness": self.freshness,
            "compliance": self.compliance,
            "standard": HB60_SALINE_SODIC.ref,
        }


def classify_salinity_sodicity(
    *,
    ece_ds_m: float | None,
    ec_method: str | None,
    esp_pct: float | None,
    observed_on: date | None,
    source: str,
    on: date | None = None,
) -> SalinitySodicityClass:
    """صنف HB60 من ECe و ESP عبر محرّك المطابقة (العتبات من السجلّ لا من هنا).

    - **EC يُفسَّر فقط إن قِيس بمستخلص العجينة المشبعة عند 25°م** (`ec_method`، نمط P2):
      حدّ HB60 (ECe ≥ 4) لا يُحوَّل إلى نِسَب تربة:ماء أخرى، فـEC بطريقةٍ أخرى أو مجهولة يُحجَب
      نصفُه بسببٍ مكتوب — لا «طبيعيّ» كاذب من مستخلص 1:5.
    - بتاريخ عيّنة ⇒ يُفرَض حدّ العمر؛ بلا تاريخ ⇒ العتبات وحدها مع
      `freshness="not_verifiable_no_sample_date"` صراحةً.
    """
    standard = HB60_SALINE_SODIC
    freshness = "enforced"
    if observed_on is None:
        standard = replace(
            standard, clauses=tuple(replace(c, max_age_days=None) for c in standard.clauses)
        )
        freshness = "not_verifiable_no_sample_date"
    withheld: list[str] = []
    obs = []
    if ece_ds_m is not None:
        if ec_method == SATURATION_EXTRACT_25C:
            obs.append(
                Observation(
                    "ece_ds_m",
                    ece_ds_m,
                    "dS/m",
                    source=source,
                    observed_on=observed_on,
                    method=ec_method,
                )
            )
        else:
            withheld.append(
                f"saline.ECe:ec_method_not_saturation_extract_25c:{ec_method or 'unknown'}"
            )
    if esp_pct is not None:
        obs.append(Observation("esp_pct", esp_pct, "%", source=source, observed_on=observed_on))
    report = evaluate_standards([standard], obs, on=on)
    status = {r.clause_id: r.status for r in report.results}

    def half(clause_id: str) -> bool | None:
        st = status.get(clause_id)
        return True if st == "fail" else False if st == "pass" else None

    saline, sodic = half("saline.ECe"), half("sodic.ESP")
    if saline is None or sodic is None:
        reasons = sorted(
            f"{r.clause_id}:{r.reason}"
            for r in report.results
            if r.status == "not_evaluated"
            and not any(w.startswith(f"{r.clause_id}:") for w in withheld)
        )
        return SalinitySodicityClass(
            None,
            False,
            saline,
            sodic,
            report.to_dict(),
            "partial:" + ",".join(withheld + reasons),
            freshness,
            tuple(withheld),
        )
    soil_class = (
        "saline_sodic"
        if saline and sodic
        else "saline"
        if saline
        else "sodic"
        if sodic
        else "normal"
    )
    return SalinitySodicityClass(
        soil_class, True, saline, sodic, report.to_dict(), f"hb60:{soil_class}", freshness
    )


# ── صنف القدرة (AH-210، عامل مُحدِّد) ───────────────────────────────────


@dataclass(frozen=True)
class FactorClass:
    factor: str
    value: float | str | None
    capability_class: str | None
    subclass: str
    status: str  # evaluated | missing | invalid
    source: str = AH210_SOURCE  # مصدر حدود الصنف لهذا العامل

    def to_dict(self) -> dict:
        return {
            "factor": self.factor,
            "value": self.value,
            "class": self.capability_class,
            "subclass": self.subclass,
            "status": self.status,
            "source": self.source,
        }


@dataclass
class LandCapability:
    capability_class: str | None  # نهائيّ فقط عند اكتمال كلّ العوامل
    best_possible_class: str | None  # أسوأ صنف بين العوامل المُقيَّمة: الصنف الحقيقيّ لا يتجاوزه
    limiting_subclasses: list[str]
    complete: bool
    factors: list[FactorClass] = field(default_factory=list)
    arable: bool | None = None  # الأصناف I–IV صالحة للزراعة (AH-210)

    def to_dict(self) -> dict:
        return {
            "capability_class": self.capability_class,
            "best_possible_class": self.best_possible_class,
            "limiting_subclasses": list(self.limiting_subclasses),
            "complete": self.complete,
            "arable": self.arable,
            "factors": [f.to_dict() for f in self.factors],
            "standard": AH210_LAND_CAPABILITY.ref,
            "calibrated_for_region": False,
            "version": LAND_QUALITY_VERSION,
        }


def _depth_class(depth_cm: float) -> str:
    for label, minimum in EFFECTIVE_DEPTH_CLASS_LIMITS_CM:
        if depth_cm >= minimum:
            return label
    return "VII"


def land_capability(
    *,
    slope_pct: float | None,
    effective_depth_cm: float | None,
    ece_ds_m: float | None,
    esp_pct: float | None,
    drainage_class: str | None,
) -> LandCapability:
    """صنف القدرة بالعامل المُحدِّد. قيمة غير صالحة لعامل ⇒ `invalid` (لا يُحسَب، يُبقي الصنف مؤقّتاً)."""
    factors: list[FactorClass] = []

    def banded(name: str, clause_id: str, value: float | None, subclass: str) -> None:
        clause = AH210_LAND_CAPABILITY.clause(clause_id)
        src = f"{AH210_LAND_CAPABILITY.ref}#{clause_id}: {clause.source}"
        if value is None:
            factors.append(FactorClass(name, None, None, subclass, "missing", src))
            return
        label = classify_band(clause, value)
        factors.append(
            FactorClass(name, value, label, subclass, "evaluated" if label else "invalid", src)
        )

    banded("slope_pct", "slope", slope_pct, "e")
    if effective_depth_cm is None:
        factors.append(FactorClass("effective_depth_cm", None, None, "s", "missing"))
    elif (
        isinstance(effective_depth_cm, bool)
        or not isinstance(effective_depth_cm, (int, float))
        or not math.isfinite(effective_depth_cm)
        or effective_depth_cm < 0
    ):
        factors.append(FactorClass("effective_depth_cm", effective_depth_cm, None, "s", "invalid"))
    else:
        factors.append(
            FactorClass(
                "effective_depth_cm",
                effective_depth_cm,
                _depth_class(effective_depth_cm),
                "s",
                "evaluated",
            )
        )
    banded("ece_ds_m", "ece", ece_ds_m, "s")
    banded("esp_pct", "esp", esp_pct, "s")
    if drainage_class is None:
        factors.append(FactorClass("drainage_class", None, None, "w", "missing"))
    else:
        label = DRAINAGE_CLASS_TO_CAPABILITY.get(str(drainage_class).strip().lower())
        factors.append(
            FactorClass(
                "drainage_class", drainage_class, label, "w", "evaluated" if label else "invalid"
            )
        )

    evaluated = [f for f in factors if f.status == "evaluated"]
    complete = len(evaluated) == len(factors)
    if not evaluated:
        return LandCapability(None, None, [], False, factors, None)
    worst = max(evaluated, key=lambda f: _CLASS_ORDER.index(f.capability_class))
    worst_class = worst.capability_class
    subclasses = sorted(
        {f.subclass for f in evaluated if f.capability_class == worst_class and worst_class != "I"}
    )
    final = worst_class if complete else None
    arable = (
        (_CLASS_ORDER.index(final) <= _CLASS_ORDER.index("IV"))
        if final
        else (False if _CLASS_ORDER.index(worst_class) > _CLASS_ORDER.index("IV") else None)
    )
    return LandCapability(final, worst_class, subclasses, complete, factors, arable)
