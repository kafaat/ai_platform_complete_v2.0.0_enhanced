"""
api/trial_engine.py — محرّك تحليل التجارب المقترنة (t-test / LSD)

خارطة الطريق: المرحلة ٢، البند ١١. الميزة الرئيسيّة لـ"الصدق الإحصائي".

يأخذ نتائج حصاد كتل مقترنة (معالجة مقابل مقارنة) ويُجري اختبار t مزدوج +
LSD ليُجيب بصدق: "هل الفرق مؤكّد إحصائيّاً أم مجرّد تباين طبيعي؟"

المعايير العلميّة (SARE / Penn State / Purdue / Iowa State / FAO):
  • مقارنة مقترنة (معالجة مقابل مقارنة)، لا تقسيم الحقل لنصفَين
  • ≥4 كتل مكرّرة (الحدّ الأدنى للصحّة الإحصائيّة)
  • اختبار t مزدوج: t = mean(d) / (sd(d)/√n)
  • LSD = t_critical × SE_diff؛ الفرق مؤكّد لو |mean(d)| > LSD
  • "لا فرق" نتيجة صحيحة وقيّمة — لا نُجمّل

يستخدم scipy.stats لتوزيع t (دقيق). يدمج اختياريّاً معايرة trueup.py للرطوبة.

⚠ لا EONR/Quadratic-Plateau هنا (يحتاج yield-response متعدّد السنوات لا نملكه
— حذّرنا من ثوابت الذرة الأمريكيّة). هذا المحرّك يُنتج البيانات التي قد يحتاجها
EONR لاحقاً، بالترتيب الصحيح.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    t_statistic: float
    df: int
    p_value: float
    confidence_level: float
    lsd: float
    is_significant: bool
    ci_lower: float
    ci_upper: float
    percent_change: float
    verdict_ar: str
    recommendation_ar: str

    def to_dict(self) -> dict:
        return {
            "n_blocks": self.n_blocks,
            "treatment_mean": round(self.treatment_mean, 3),
            "control_mean": round(self.control_mean, 3),
            "mean_difference": round(self.mean_difference, 3),
            "std_diff": round(self.std_diff, 4),
            "se_diff": round(self.se_diff, 4),
            "t_statistic": round(self.t_statistic, 4),
            "df": self.df,
            "p_value": round(self.p_value, 5),
            "confidence_level": self.confidence_level,
            "lsd": round(self.lsd, 4),
            "is_significant": self.is_significant,
            "ci_lower": round(self.ci_lower, 3),
            "ci_upper": round(self.ci_upper, 3),
            "percent_change": round(self.percent_change, 2),
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
    if not observations:
        raise ValueError("met_observations فارغة")

    rows: dict[tuple[str, str], list[float]] = {}
    for obs in observations:
        genotype = str(obs.genotype).strip()
        environment_id = str(obs.environment_id).strip()
        value = float(obs.yield_value)
        if not genotype or not environment_id or not np.isfinite(value):
            raise ValueError("MET inputs invalid")
        rows.setdefault((genotype, environment_id), []).append(value)

    genotypes = sorted({genotype for genotype, _environment_id in rows})
    environments = sorted({environment_id for _genotype, environment_id in rows})
    if len(genotypes) < 2 or len(environments) < 2:
        raise ValueError("MET/G×E يتطلب genotypeين وبيئتين")
    if any((g, e) not in rows for g in genotypes for e in environments):
        raise ValueError("MET/G×E matrix incomplete")

    cells = {(g, e): float(np.mean(values)) for (g, e), values in rows.items()}
    grand_mean = float(np.mean(list(cells.values())))
    genotype_means = {g: float(np.mean([cells[(g, e)] for e in environments])) for g in genotypes}
    environment_means = {
        e: float(np.mean([cells[(g, e)] for g in genotypes])) for e in environments
    }
    interaction_rms = {
        g: float(
            np.sqrt(
                np.mean(
                    np.square(
                        [
                            cells[(g, e)] - genotype_means[g] - environment_means[e] + grand_mean
                            for e in environments
                        ]
                    )
                )
            )
        )
        for g in genotypes
    }
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


MIN_BLOCKS = 4  # معيار SARE: أقلّ من ٤ = لا صحّة إحصائيّة


def analyze_paired_trial(
    blocks: list[BlockResult],
    *,
    confidence_level: float = 0.95,
    treatment_label_ar: str = "المعالجة الجديدة",
) -> TrialVerdict:
    """يُحلّل تجربة مقترنة باختبار t مزدوج + LSD.

    يرفع ValueError لو الكتل < 4 (تقسيم الحقل لنصفَين غير صالح).
    """
    n = len(blocks)
    if n < MIN_BLOCKS:
        raise ValueError(
            f"الحدّ الأدنى {MIN_BLOCKS} كتل للصحّة الإحصائيّة (وُجد {n}). "
            "تقسيم الحقل لنصفَين أو كتلتَين لا يُنتج استنتاجاً صالحاً."
        )

    treatment = np.array([b.treatment_yield for b in blocks], dtype=float)
    control = np.array([b.control_yield for b in blocks], dtype=float)
    diffs = treatment - control

    mean_diff = float(np.mean(diffs))
    std_diff = float(np.std(diffs, ddof=1))  # عيّنة (n-1)
    se_diff = std_diff / np.sqrt(n)
    df = n - 1

    # اختبار t مزدوج (مكافئ لـttest_1samp على الفروق)
    if se_diff == 0:
        # كل الفروق متطابقة — حالة حدّيّة
        t_stat = float("inf") if mean_diff != 0 else 0.0
        p_value = 0.0 if mean_diff != 0 else 1.0
    else:
        t_stat = mean_diff / se_diff
        p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df)))

    alpha = 1 - confidence_level
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    lsd = t_crit * se_diff
    is_sig = abs(mean_diff) > lsd

    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    control_mean = float(np.mean(control))
    treatment_mean = float(np.mean(treatment))
    pct = (mean_diff / control_mean * 100) if control_mean != 0 else 0.0

    # حُكم صادق بالعربيّة
    if is_sig:
        if mean_diff > 0:
            verdict = f"الفرق مؤكّد إحصائيّاً (p = {p_value:.3f}). {treatment_label_ar} أفضل بـ{abs(pct):.1f}%."
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
    )
