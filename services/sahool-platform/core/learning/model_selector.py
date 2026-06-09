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

شرط حاسم: "نقطة متنوّعة" = من حقول/مواسم مستقلة فعلاً.
نقاط من حقل واحد (pseudoreplication) لا تُحتسب كاملة — نطبّق
معامل خصم للاستقلالية.

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
    expected_r2_range: str
    confidence: str
    rationale_ar: str


def effective_sample_size(
    n_records: int,
    n_farms: int,
    n_seasons: int,
) -> int:
    """Honest effective N, accounting for pseudoreplication.

    Records from the same farm are correlated. The real independent unit
    is closer to (farms x seasons) than raw record count. We take the
    MINIMUM of raw points and the independent-unit estimate.
    """
    independent_units = max(1, n_farms) * max(1, n_seasons)
    # effective N cannot exceed independent units (the binding constraint)
    return min(n_records, independent_units)


def select_model(
    n_records: int,
    n_farms: int,
    n_seasons: int,
) -> ModelDecision:
    """Return the most complex model the data HONESTLY supports."""
    eff = effective_sample_size(n_records, n_farms, n_seasons)
    indep = max(1, n_farms) * max(1, n_seasons)

    if eff < 15:
        tier, r2, conf = ModelTier.RULES_ONLY, "—", "physics-based"
        why = (
            f"عينة فعّالة {eff} < 15 → قواعد + WOFOST فقط. "
            f"بيانات أقل من أن تدرّب أي نموذج. نقاط مستقلة: {indep}"
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
