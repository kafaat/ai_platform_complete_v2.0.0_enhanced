"""
services/sahool-platform/api/cost_governance.py — Cost Governance (حوكمة التكلفة)

سجلّ واحد لبيانات وصفيّة عن تكلفة/زمن استجابة خدمات المنصّة ونماذج الذكاء
ومصادر الصور، كي تقرأ القراراتُ الواعية بالتكلفة (الميزانيات، توجيه النماذج
model routing، تحديد مصدر الصور) من البيانات لا من ثوابت مبثوثة في الشيفرة.

لماذا؟
   اليوم تُتّخذ خيارات «أيّ نموذج؟» (core/learning/model_selector.py) و«أيّ
   مصدر صور؟» (api/imagery_automation.py عبر raster-service) بمنطق هندسيّ، لكن
   البُعد التكلفة/الزمن غير مُمثَّل صراحةً في مكان واحد قابل للقراءة. هذا الملفّ
   يجمع ذلك البُعد في سجلّ نقيّ (لا قاعدة، لا شبكة) يمكن لمنطق التوجيه والميزانية
   أن يستعلم منه.

مبدأ الأمانة (مهمّ):
   لا توجد أسعار $ حقيقيّة في المستودع، ولا توجد تكامل فوترة (billing) فعليّ.
   لذلك نستخدم *رُتباً نسبيّة ترتيبيّة* (low/medium/high) فقط، لا مبالغ ماليّة
   مُختلَقة. هذه الرُّتب نسبيّة بين الكيانات وتُمثّل تقديراً محافظاً، ويجب
   استبدالها لاحقاً ببيانات فوترة حقيقيّة (متابعة: ربط مصدر التكلفة الفعليّ).

ما يفعله:
   ✓ سجلّ بيانات وصفيّة (CostProfile) مُغذّى بكيانات حقيقيّة موجودة فعلاً
   ✓ استعلامات نقيّة: قائمة/جلب/تصفية حسب النوع/الأرخص

ما لا يفعله:
   ✗ لا يخترع أسعاراً ماليّة
   ✗ لا يتّصل بقاعدة بيانات أو خدمة فوترة
   ✗ لا يتّخذ قرار التوجيه نفسه — يوفّر البيانات فقط ليقرأها غيره
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# الرُّتب المسموحة (ترتيبيّة): الترتيب يعكس «الأرخص/الأسرع أوّلاً».
# نُبقيها ثابتة هنا كي تتّسق دوالّ الفرز مع فحوص الاختبار.
_COST_TIERS: tuple[str, ...] = ("low", "medium", "high")
_LATENCY_TIERS: tuple[str, ...] = ("low", "medium", "high")
_KINDS: tuple[str, ...] = ("service", "ai_model", "imagery")

# خريطة ترتيب الرُّتبة → رقم، للفرز النقيّ (low=0 أرخص/أسرع).
_TIER_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class CostProfile:
    """ملمح تكلفة/زمن نسبيّ لكيان واحد (خدمة أو نموذج أو مصدر صور).

    الرُّتب (cost_tier/latency_tier) نسبيّة ترتيبيّة لا مبالغ ماليّة؛ راجع
    notes_ar لكلّ مدخلة. لا أسعار $ مُختلَقة.
    """

    id: str
    kind: str  # "service" | "ai_model" | "imagery"
    cost_tier: str  # "low" | "medium" | "high"
    latency_tier: str  # "low" | "medium" | "high"
    unit: str  # "per_request" | "per_1k_tokens" | "per_scene" ...
    notes_ar: str


# ─── السجلّ (Registry) ───────────────────────────────────────────────
# مُغذّى بكيانات حقيقيّة موجودة في المستودع فقط:
#   • خدمات منصّة من docker-compose.v9.yml (sahool-*)
#   • نماذج ذكاء من core/learning/model_selector.py (ModelTier) + ollama (LLM محليّ)
#   • مصدر صور Sentinel-2 المُستخدَم في api/imagery_automation.py عبر raster-service
# الرُّتب محافظة ومُبرَّرة نسبيّاً، ولا تتضمّن أيّ سعر ماليّ.
_REGISTRY: dict[str, CostProfile] = {
    # — خدمات المنصّة —
    "sahool-platform": CostProfile(
        id="sahool-platform",
        kind="service",
        cost_tier="low",
        latency_tier="low",
        unit="per_request",
        notes_ar=(
            "خدمة الـAPI الأساسيّة (api/main.py). معالجة محليّة خفيفة نسبيّاً، "
            "رُتبة نسبيّة بانتظار فوترة حقيقيّة."
        ),
    ),
    "sahool-raster-service": CostProfile(
        id="sahool-raster-service",
        kind="service",
        cost_tier="medium",
        latency_tier="high",
        unit="per_scene",
        notes_ar=(
            "خدمة المعالجة النقطيّة (raster-service): بحث الصور وحساب المؤشّرات "
            "(NDVI/EVI). كثيفة I/O وحوسبة، فزمنها أعلى نسبيّاً. رُتبة نسبيّة."
        ),
    ),
    "sahool-vegetation-analysis": CostProfile(
        id="sahool-vegetation-analysis",
        kind="service",
        cost_tier="medium",
        latency_tier="medium",
        unit="per_request",
        notes_ar=(
            "خدمة تحليل الغطاء النباتيّ (vegetation-analysis-service). تعتمد على "
            "مخرجات raster، تكلفة/زمن متوسّطان نسبيّاً. رُتبة نسبيّة."
        ),
    ),
    "sahool-weather-service": CostProfile(
        id="sahool-weather-service",
        kind="service",
        cost_tier="low",
        latency_tier="medium",
        unit="per_request",
        notes_ar=(
            "خدمة الطقس (weather-service). استعلامات خارجيّة/تخزين مؤقّت، تكلفة "
            "منخفضة وزمن متوسّط نسبيّاً. رُتبة نسبيّة."
        ),
    ),
    # — نماذج الذكاء — (مطابقة لـ ModelTier في core/learning/model_selector.py)
    "tabpfn_small_data": CostProfile(
        id="tabpfn_small_data",
        kind="ai_model",
        cost_tier="low",
        latency_tier="low",
        unit="per_request",
        notes_ar=(
            "TabPFN للبيانات الصغيرة جداً (مُدرَّب مسبقاً، استدلال خفيف). الأرخص "
            "والأسرع بين النماذج. رُتبة نسبيّة لا سعر."
        ),
    ),
    "xgboost": CostProfile(
        id="xgboost",
        kind="ai_model",
        cost_tier="medium",
        latency_tier="low",
        unit="per_request",
        notes_ar=(
            "XGBoost (تدريب/استدلال متوسّط الكلفة، استدلال سريع). رُتبة نسبيّة مقابل بقيّة سُلّم النماذج."
        ),
    ),
    "bilstm_transformer": CostProfile(
        id="bilstm_transformer",
        kind="ai_model",
        cost_tier="high",
        latency_tier="high",
        unit="per_request",
        notes_ar=(
            "BiLSTM/Transformer (نماذج عميقة): الأعلى كلفةً وزمناً في السُّلّم. رُتبة نسبيّة لا سعر."
        ),
    ),
    "ollama_local_llm": CostProfile(
        id="ollama_local_llm",
        kind="ai_model",
        cost_tier="medium",
        latency_tier="high",
        unit="per_1k_tokens",
        notes_ar=(
            "نموذج لغويّ محليّ عبر Ollama (sahool-ollama، يخدم local-ai-rag). بلا "
            "كلفة استدعاء خارجيّة لكن زمنه أعلى على عتاد محدود. وحدة per_1k_tokens. "
            "رُتبة نسبيّة."
        ),
    ),
    # — مصدر الصور —
    "sentinel2": CostProfile(
        id="sentinel2",
        kind="imagery",
        cost_tier="low",
        latency_tier="high",
        unit="per_scene",
        notes_ar=(
            "صور Sentinel-2 (مفتوحة، تُجلب عبر raster-service في "
            "api/imagery_automation.py). كلفة بيانات منخفضة لكن جلب/معالجة المشهد "
            "بطيئة نسبيّاً. رُتبة نسبيّة."
        ),
    ),
}


def list_profiles() -> list[dict]:
    """كلّ الملامح كقواميس (للعرض/التسلسل). الترتيب ثابت كما في السجلّ."""
    return [asdict(p) for p in _REGISTRY.values()]


def get_profile(id: str) -> dict | None:
    """ملمح كيان واحد بالمُعرِّف، أو None إن لم يوجد."""
    p = _REGISTRY.get(id)
    return asdict(p) if p is not None else None


def for_kind(kind: str) -> list[dict]:
    """تصفية الملامح حسب النوع ("service"|"ai_model"|"imagery")."""
    return [asdict(p) for p in _REGISTRY.values() if p.kind == kind]


def cheapest(kind: str) -> dict | None:
    """أرخص كيان ضمن نوع: أدنى cost_tier، وعند التعادل أدنى latency_tier.

    فرز نقيّ ترتيبيّ على رُتب التعداد (low<medium<high)، لا مبالغ ماليّة.
    يُعيد None إن لم يوجد كيان من هذا النوع.
    """
    candidates = [p for p in _REGISTRY.values() if p.kind == kind]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda p: (_TIER_ORDER[p.cost_tier], _TIER_ORDER[p.latency_tier]),
    )
    return asdict(best)
