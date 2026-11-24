"""
core.learning.model_selector
=============================
المكوّن الثاني للتعلّم: سُلّم النماذج المتدرّج (Tiered Model Ladder).

يفرض القاعدة التي اتفقنا عليها عبر النقاش: لا تنتقل لنموذج أعقد قبل
تجاوز حدّ بياناته. هذا يمنع overfitting ووهم الدقة.

السُلّم (موثّق):
    < 15 نقطة    → قواعد + WOFOST فقط (أقل من أن يُدرّب نموذج)
    15-49        → TabPFN (بيانات صغيرة جداً، مُدرَّب مسبقاً، يكمّل القواعد)
    50-99        → LASSO / Linear (R² ~0.4-0.5)
    100-199      → XGBoost / Gradient Boosting (R² ~0.6-0.7)
    200-499      → Random Forest (مع tuning) (R² ~0.7-0.8)
    500+ متنوّع  → BiLSTM / Transformer (R² ~0.85-0.93)

نطاقات R² ومستويات الثقة أعلاه **افتراضات تخطيط للسياسة، لا نتائج قياس**:
الدالة لا تستقبل تنبّؤات ولا أهدافاً ولا نتيجة تحقّق، فلا يجوز عرضها كجودة
متوقّعة مثبتة. يُعلَن ذلك في كلّ قرار عبر `r2_basis` و`confidence_basis`،
و`measured_r2` يبقى `None` حتى وصول إيصال تقييم مستقلّ.

شرط حاسم: "نقطة متنوّعة" = من حقول/مواسم مستقلة فعلاً.
نقاط من حقل واحد (pseudoreplication) لا تُحتسب كاملة — نطبّق
سقفاً اسمياً من العدّادات (مزارع × مواسم). هذا السقف لا يعرف أزواج
المزرعة–الموسم المرصودة فعلاً: 600 سجلّ في 30 زوجاً مرصوداً و600 سجلّ
في 600 زوج يعطيان العدد نفسه، وحتى عدّ الأزواج لا يثبت استقلالها
(MODEL-SELECTOR-NOMINAL-SAMPLE-UNVALIDATED-01).

النماذج لا تُدرّب هنا — هذا المُحدِّد فقط يقول: "أي نموذج مسموح الآن؟"
ويتبع الأساليب المعتمدة (scikit-learn standard) عند التدريب الفعلي.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTier(str, Enum):
    RULES_ONLY = "rules_wofost_only"
    TABPFN = "tabpfn_small_data"  # للبيانات الصغيرة جداً (15-49) — يسدّ فجوة "لا ML"
    LINEAR = "lasso_linear"
    GBOOST = "xgboost"
    RF = "random_forest"
    DEEP = "bilstm_transformer"


@dataclass
class ModelDecision:
    allowed_model: ModelTier
    raw_points: int
    effective_points: int  # after independence discount
    n_independent_units: int  # farms x seasons (the real sample size)
    expected_r2_range: str  # policy planning assumption, not a measurement
    confidence: str  # policy label, not a calibrated confidence
    rationale_ar: str
    r2_basis: str = "policy_assumption_unvalidated"
    confidence_basis: str = "policy_label_not_calibrated"
    measured_r2: float | None = None  # stays None until an independent evaluation receipt


def effective_sample_size(
    n_records: int,
    n_farms: int,
    n_seasons: int,
) -> int:
    """Nominal upper bound on the sample size, from three counters only.

    Records from the same farm are correlated, so the count is capped at
    max(1, farms) x max(1, seasons). This is a ceiling derived from the
    counters, not an estimate of independence: the function cannot see which
    farm-season pairs were actually observed (600 records in 30 observed pairs
    and 600 records in 600 pairs both return 600), and even a count of
    observed pairs would not prove they are independent.
    """
    independent_units = max(1, n_farms) * max(1, n_seasons)
    # effective N cannot exceed independent units (the binding constraint)
    return min(n_records, independent_units)


def select_model(
    n_records: int,
    n_farms: int,
    n_seasons: int,
) -> ModelDecision:
    """Return the most complex model family the policy allows for these counts.

    This is a policy gate on the nominal sample size, not a quality claim: the
    returned R² range and confidence are planning assumptions
    (``r2_basis``/``confidence_basis``) and ``measured_r2`` is always None.
    """
    eff = effective_sample_size(n_records, n_farms, n_seasons)
    indep = max(1, n_farms) * max(1, n_seasons)

    if eff < 15:
        tier, r2, conf = ModelTier.RULES_ONLY, "—", "physics-based"
        why = (
            f"عينة فعّالة {eff} < 15 → قواعد + WOFOST فقط. "
            f"أقلّ من حدّ السياسة لتدريب نموذج متعلّم. سقف اسميّ (مزارع×مواسم): {indep}"
        )
    elif eff < 50:
        # مراجعة v16 (مقبولة): TabPFN يسدّ فجوة البيانات الصغيرة جداً
        # (مُدرَّب مسبقاً، لا يحتاج معايرة، يعطي عدم يقين يوافق conformal).
        tier, r2, conf = ModelTier.TABPFN, "0.3-0.5", "low"
        why = (
            f"عينة فعّالة {eff} (15-49) → TabPFN مسموح (للبيانات الصغيرة). "
            f"يكمّل القواعد، لا يستبدلها. نقاط مستقلة: {indep}"
        )
    elif eff < 100:
        tier, r2, conf = ModelTier.LINEAR, "0.4-0.5", "low"
        why = f"عينة فعّالة {eff} → LASSO/Linear مسموح"
    elif eff < 200:
        tier, r2, conf = ModelTier.GBOOST, "0.6-0.7", "medium"
        why = f"عينة فعّالة {eff} → XGBoost مسموح"
    elif eff < 500:
        tier, r2, conf = ModelTier.RF, "0.7-0.8", "medium"
        why = f"عينة فعّالة {eff} → Random Forest مسموح"
    else:
        tier, r2, conf = ModelTier.DEEP, "0.85-0.93", "high"
        why = f"عينة فعّالة {eff} متنوّعة → BiLSTM/Transformer مسموح"

    return ModelDecision(
        allowed_model=tier,
        raw_points=n_records,
        effective_points=eff,
        n_independent_units=indep,
        expected_r2_range=r2,
        confidence=conf,
        rationale_ar=why,
    )
