"""
api/trial_engine.py — محرّك تحليل التجارب المقترنة (t-test / LSD)

خارطة الطريق: المرحلة ٢، البند ١١. الميزة الرئيسيّة لـ"الصدق الإحصائي".

يأخذ نتائج حصاد كتل مقترنة (معالجة مقابل مقارنة) ويُجري اختبار t مزدوج +
LSD ليُجيب بصدق: "هل الفرق مؤكّد إحصائيّاً أم مجرّد تباين طبيعي؟"

المعايير العلميّة (SARE / Penn State / Purdue / Iowa State / FAO):
  • مقارنة مقترنة (معالجة مقابل مقارنة)، لا تقسيم الحقل لنصفَين
  • ≥4 كتل مستقلة (حدّ هذا المحرّك؛ العدد وحده لا يثبت صلاحية التصميم)
  • اختبار t مزدوج: t = mean(d) / (sd(d)/√n)
  • LSD = t_critical × SE_diff؛ الفرق مؤكّد لو |mean(d)| > LSD
  • "لا فرق" نتيجة صحيحة وقيّمة — لا نُجمّل

يستخدم scipy.stats لتوزيع t (دقيق). يدمج اختياريّاً معايرة trueup.py للرطوبة.

⚠ لا EONR/Quadratic-Plateau هنا (يحتاج yield-response متعدّد السنوات لا نملكه
— حذّرنا من ثوابت الذرة الأمريكيّة). هذا المحرّك يُنتج البيانات التي قد يحتاجها
EONR لاحقاً، بالترتيب الصحيح.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Literal

import numpy as np
from scipy import stats


@dataclass
class BlockResult:
    """نتيجة حصاد كتلة واحدة: إنتاج المعالجة مقابل المقارنة."""

    block_number: int
    treatment_yield: float  # kg/ha (أو أيّ وحدة متّسقة)
    control_yield: float


@dataclass
class TrialVerdict:
    """نتيجة التحليل الإحصائي الكاملة."""

    n_blocks: int
    treatment_mean: float
    control_mean: float
    mean_difference: float  # معالجة − مقارنة
    std_diff: float
    se_diff: float
    t_statistic: float | None
    df: int
    p_value: float
    confidence_level: float
    lsd: float
    is_significant: bool
    ci_lower: float
    ci_upper: float
    percent_change: float | None
    verdict_ar: str
    recommendation_ar: str
    statistic_status: Literal["ok", "zero_variance_equal", "zero_variance_difference"] = "ok"
    percent_change_status: Literal["ok", "zero_control"] = "ok"
    inferential_valid: bool = True
    requires_review: bool = False

    def to_dict(self) -> dict:
        return {
            "n_blocks": int(self.n_blocks),
            "treatment_mean": round(float(self.treatment_mean), 3),
            "control_mean": round(float(self.control_mean), 3),
            "mean_difference": round(float(self.mean_difference), 3),
            "std_diff": round(float(self.std_diff), 4),
            "se_diff": round(float(self.se_diff), 4),
            "t_statistic": (
                round(float(self.t_statistic), 4) if self.t_statistic is not None else None
            ),
            "statistic_status": self.statistic_status,
            "df": int(self.df),
            "p_value": round(float(self.p_value), 5),
            "confidence_level": float(self.confidence_level),
            "lsd": round(float(self.lsd), 4),
            "is_significant": bool(self.is_significant),
            "ci_lower": round(float(self.ci_lower), 3),
            "ci_upper": round(float(self.ci_upper), 3),
            "percent_change": (
                round(float(self.percent_change), 2) if self.percent_change is not None else None
            ),
            "percent_change_status": self.percent_change_status,
            "inferential_valid": self.inferential_valid,
            "requires_review": self.requires_review,
            "verdict_ar": self.verdict_ar,
            "recommendation_ar": self.recommendation_ar,
        }


@dataclass(frozen=True)
class METObservation:
    genotype: str
    environment_id: str
    yield_value: float
    replicate: int | None = None


@dataclass(frozen=True)
class METAnalysis:
    n_observations: int
    genotypes: list[str]
    environments: list[str]
    grand_mean: float
    genotype_means: dict[str, float]
    environment_means: dict[str, float]
    interaction_rms: dict[str, float]
    stability_rank: list[str]

    def to_dict(self) -> dict:
        return {
            "n_observations": self.n_observations,
            "genotypes": self.genotypes,
            "environments": self.environments,
            "grand_mean": round(self.grand_mean, 4),
            "genotype_means": {k: round(v, 4) for k, v in self.genotype_means.items()},
            "environment_means": {k: round(v, 4) for k, v in self.environment_means.items()},
            "interaction_rms": {k: round(v, 4) for k, v in self.interaction_rms.items()},
            "stability_rank": self.stability_rank,
            "method": "two_way_additive_residual_rms",
            "claim_scope": "descriptive_gxe_stability_only",
            "decision_eligible": False,
            "automatic_model_promotion_eligible": False,
        }


def analyze_met(observations: list[METObservation]) -> METAnalysis:
    """Summarize a complete genotype/environment matrix without inferential claims.

    A supplied replicate identifies one observation within its genotype and
    environment and must be a unique positive integer there.  Missing replicate
    IDs remain permitted for descriptive data: these rows are neither silently
    deduplicated nor claimed to be independent field replications.  In particular,
    ``n_observations`` counts rows, not verified experimental units.
    """
    if not observations:
        raise ValueError("met_observations فارغة")

    rows: dict[tuple[str, str], list[float]] = {}
    identified_replicates: set[tuple[str, str, int]] = set()
    for obs in observations:
        genotype = str(obs.genotype).strip()
        environment_id = str(obs.environment_id).strip()
        value = _finite_number(obs.yield_value, "MET yield_value")
        if not genotype or not environment_id:
            raise ValueError("MET inputs invalid")
        if obs.replicate is not None:
            replicate = _positive_integer(obs.replicate, "MET replicate")
            identity = (genotype, environment_id, replicate)
            if identity in identified_replicates:
                raise ValueError(
                    "Duplicate MET replicate identity: "
                    f"genotype={genotype}, environment_id={environment_id}, replicate={replicate}"
                )
            identified_replicates.add(identity)
        rows.setdefault((genotype, environment_id), []).append(value)

    genotypes = sorted({genotype for genotype, _environment_id in rows})
    environments = sorted({environment_id for _genotype, environment_id in rows})
    if len(genotypes) < 2 or len(environments) < 2:
        raise ValueError("MET/G×E يتطلب genotypeين وبيئتين")
    if any((g, e) not in rows for g in genotypes for e in environments):
        raise ValueError("MET/G×E matrix incomplete")

    try:
        with np.errstate(over="raise", invalid="raise"):
            cells = {(g, e): float(np.mean(values)) for (g, e), values in rows.items()}
            grand_mean = float(np.mean(list(cells.values())))
            genotype_means = {
                g: float(np.mean([cells[(g, e)] for e in environments])) for g in genotypes
            }
            environment_means = {
                e: float(np.mean([cells[(g, e)] for g in genotypes])) for e in environments
            }
            interaction_rms = {
                g: float(
                    np.sqrt(
                        np.mean(
                            np.square(
                                [
                                    cells[(g, e)]
                                    - genotype_means[g]
                                    - environment_means[e]
                                    + grand_mean
                                    for e in environments
                                ]
                            )
                        )
                    )
                )
                for g in genotypes
            }
    except FloatingPointError as exc:
        raise ValueError("MET yield magnitudes exceed the finite analysis range") from exc
    if not all(
        math.isfinite(value)
        for value in [
            grand_mean,
            *genotype_means.values(),
            *environment_means.values(),
            *interaction_rms.values(),
        ]
    ):
        raise ValueError("MET yield magnitudes exceed the finite analysis range")
    return METAnalysis(
        n_observations=len(observations),
        genotypes=genotypes,
        environments=environments,
        grand_mean=grand_mean,
        genotype_means=genotype_means,
        environment_means=environment_means,
        interaction_rms=interaction_rms,
        stability_rank=sorted(genotypes, key=lambda g: (interaction_rms[g], g)),
    )


def build_digital_trial_envelope(
    *,
    season_id: str | None,
    study_id: str | None,
    trial_id: str | None,
    met: METAnalysis,
) -> dict:
    """Build a truthful C5 envelope without inventing season authority.

    The current endpoint has no canonical season lookup in its dependency graph.
    Therefore a caller-provided ``season_id`` is a reference, not proof that the
    season exists or is authoritative.  Decision/model-promotion eligibility stays
    false until a later governed consumer supplies that proof.
    """
    if not season_id:
        raise ValueError("season_id مطلوب لتحليل Digital Trials/MET")
    return {
        "season_id": season_id,
        "study_id": study_id,
        "trial_id": trial_id,
        "lifecycle_authority": "caller_provided_season_reference",
        "season_binding_verified": False,
        "parallel_trial_season_created": False,
        "met_analysis": met.to_dict(),
        "decision_eligible": False,
        "automatic_model_promotion_eligible": False,
    }


MIN_BLOCKS = 4  # سياسة هذا المحرّك؛ لا تغني عن التحقّق من استقلال الكتل وبنية التصميم


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a finite number, not a boolean")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def analyze_paired_trial(
    blocks: list[BlockResult],
    *,
    confidence_level: float = 0.95,
    treatment_label_ar: str = "المعالجة الجديدة",
) -> TrialVerdict:
    """يُحلّل تجربة مقترنة باختبار t مزدوج + LSD.

    Each row must represent a different field block, with one treatment/control
    pair. Repeated observations of the same block must be resolved upstream;
    they are not additional independent replications. IDs cannot by themselves
    establish biological independence, but duplicate IDs must never inflate n.

    Zero-variance nonzero differences have no finite t statistic. In that case
    p=0 and the point interval are limiting conventions, explicitly marked by
    statistic_status; they are not an ordinary estimate of uncertainty.
    """
    confidence_level = _finite_number(confidence_level, "confidence_level")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be strictly between 0 and 1")

    block_ids: set[int] = set()
    for block in blocks:
        block_id = _positive_integer(block.block_number, "block_number")
        if block_id in block_ids:
            raise ValueError(f"Duplicate block_number: {block_id}; blocks must be unique")
        block_ids.add(block_id)

    n = len(blocks)
    if n < MIN_BLOCKS:
        raise ValueError(
            f"يتطلب هذا المحرّك {MIN_BLOCKS} كتل مستقلة على الأقل (وُجد {n}). "
            "القياسات المتكرّرة للكتلة نفسها لا تُحسب كتلًا إضافية."
        )

    treatment = np.array(
        [_finite_number(b.treatment_yield, "treatment_yield") for b in blocks], dtype=float
    )
    control = np.array(
        [_finite_number(b.control_yield, "control_yield") for b in blocks], dtype=float
    )
    try:
        with np.errstate(over="raise", invalid="raise"):
            diffs = treatment - control
            mean_diff = float(np.mean(diffs))
            std_diff = float(np.std(diffs, ddof=1))  # عيّنة (n-1)
            control_mean = float(np.mean(control))
            treatment_mean = float(np.mean(treatment))
    except FloatingPointError as exc:
        raise ValueError("Yield magnitudes exceed the finite analysis range") from exc
    se_diff = std_diff / math.sqrt(n)
    df = n - 1

    statistic_status = "ok"
    # اختبار t مزدوج (مكافئ لـttest_1samp على الفروق)
    if se_diff == 0:
        if not np.all(diffs == diffs[0]):
            raise ValueError("Yield magnitudes exceed the finite analysis range")
        # لا نختلق t محدوداً ولا نرسل Infinity غير صالح في JSON.
        t_stat = None if mean_diff != 0 else 0.0
        p_value = 0.0 if mean_diff != 0 else 1.0
        statistic_status = "zero_variance_difference" if mean_diff != 0 else "zero_variance_equal"
    else:
        t_stat = mean_diff / se_diff
        p_value = float(2 * stats.t.sf(abs(t_stat), df))

    alpha = 1 - confidence_level
    t_crit = float(stats.t.isf(alpha / 2, df))
    lsd = t_crit * se_diff
    inferential_valid = statistic_status == "ok"
    is_sig = bool(inferential_valid and abs(mean_diff) > lsd)

    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    pct = (mean_diff / control_mean * 100) if control_mean != 0 else None
    finite_results = [mean_diff, std_diff, se_diff, p_value, lsd, ci_lower, ci_upper]
    if pct is not None:
        finite_results.append(pct)
    if t_stat is not None:
        finite_results.append(t_stat)
    if not all(math.isfinite(value) for value in finite_results):
        raise ValueError("Yield magnitudes exceed the finite analysis range")

    # حُكم صادق بالعربيّة
    if statistic_status == "zero_variance_difference":
        verdict = (
            f"الفروق بين الكتل متطابقة وغير صفرية (متوسط الفرق = {mean_diff:+.3f}). "
            "لا توجد قيمة t محدودة؛ p=0 وفترة الثقة النقطية اصطلاح حدّي، "
            "ولا يمثّلان تقديراً عادياً لعدم اليقين."
        )
        rec = "تحقّق من استقلال الكتل ودقّة القياسات وتكرار التسجيل قبل تغيير الممارسة."
    elif statistic_status == "zero_variance_equal":
        verdict = "فروق الكتل متطابقة وصفرية؛ لا تقدير عادي لعدم اليقين."
        rec = "تحقق من القياسات واستقلال الكتل قبل استخلاص حكم."
    elif is_sig:
        if mean_diff > 0:
            comparison = (
                f"{treatment_label_ar} أفضل بـ{abs(pct):.1f}%."
                if pct is not None
                else f"متوسط الزيادة المطلقة {mean_diff:.3f}؛ النسبة غير معرّفة لأن متوسط الشاهد صفر."
            )
            verdict = f"الفرق مؤكّد إحصائيّاً (p = {p_value:.3f}). {comparison}"
            rec = f"الدليل يدعم اعتماد {treatment_label_ar}."
        else:
            verdict = f"الفرق مؤكّد إحصائيّاً (p = {p_value:.3f}). المقارنة (الممارسة الحاليّة) أفضل."
            rec = "الممارسة الحاليّة أفضل — لا تغيير موصى به."
    else:
        verdict = f"لا يوجد فرق مؤكّد إحصائيّاً (p = {p_value:.3f}، LSD = {lsd:.2f})."
        rec = "الفرق قد يكون تبايناً طبيعيّاً. لا دليل كافٍ لتغيير الممارسة."

    return TrialVerdict(
        n_blocks=n,
        treatment_mean=treatment_mean,
        control_mean=control_mean,
        mean_difference=mean_diff,
        std_diff=std_diff,
        se_diff=se_diff,
        t_statistic=t_stat,
        df=df,
        p_value=p_value,
        confidence_level=confidence_level,
        lsd=lsd,
        is_significant=is_sig,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        percent_change=pct,
        verdict_ar=verdict,
        recommendation_ar=rec,
        statistic_status=statistic_status,
        percent_change_status="ok" if pct is not None else "zero_control",
        inferential_valid=inferential_valid,
        requires_review=not inferential_valid,
    )
