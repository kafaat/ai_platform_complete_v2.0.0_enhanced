"""
sahool_core.knowledge_levels
=============================
تقنين "مصفوفة القرار الموحّدة" — تصنيف صريح لمستويات المعرفة.

المصفوفة تكشف بنية موجودة في النواة (لا تضيف منطقاً): كل مصدر معلومة
ينتمي لمستوى معرفي بدرجة يقين (FSI) وسقف ثقة. هذه الوحدة تجعل التصنيف
صريحاً بدل كونه ضمنياً، وتطبّق قاعدة الانصهار الموحّدة.

المستويات (من الأعلى يقيناً للأدنى):
  7 رياضيات    — ثابتة، لا تُعاير، لا سقف (1.00)
  6 فيزياء     — استنباطي، حياد مكاني + حاكم صارم (Penman-Monteith, PHI)
  5 مخبري      — تحليلي، يحكم (EC, pH, N)
  4 ميداني     — قياس ميداني، يحتاج معايرة
  3 استقرائي   — إحصائي، الثقة فئوية (zone_factor)
  2 توليدي     — LLM/نموذج، يُقترح لا يُقرّر، سقف LOW أبداً لا HIGH
  1 مجتمعي     — خبرة/أنواء، يُحترم لا يحكم
  0 استكشافي   — تخمين، الصمت قرار، BLOCKED دائماً

القواعد الموحّدة المطبّقة:
  • السقف الأدنى يحكم: confidence ≤ min(سقوف المستويات المساهمة)
  • الحاكم يُلغي الكل: أي مستوى BLOCKED → الناتج BLOCKED
  • المعايرة شرط لا كفاية: غياب المعايرة → سقف MEDIUM
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class KnowledgeLevel(IntEnum):
    GUESS = 0          # استكشافي
    SOCIAL = 1         # مجتمعي
    GENERATIVE = 2     # توليدي
    INDUCTIVE = 3      # استقرائي
    FIELD = 4          # ميداني
    ANALYTICAL = 5     # مخبري
    PHYSICAL = 6       # فيزيائي
    MATHEMATICAL = 7   # رياضي


# سقف الثقة لكل مستوى (تطبيق "لا HIGH للتوليدي/التخمين")
# none < low < medium < high — نمثّلها رتبةً للمقارنة
_CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
_RANK_CONF = {v: k for k, v in _CONF_RANK.items()}

_LEVEL_CEILING = {
    KnowledgeLevel.MATHEMATICAL: "high",   # ثابت كوني
    KnowledgeLevel.PHYSICAL: "high",       # فيزياء معايَرة → high ممكن
    KnowledgeLevel.ANALYTICAL: "high",     # المختبر يحكم
    KnowledgeLevel.FIELD: "medium",        # ميداني يحتاج معايرة
    KnowledgeLevel.INDUCTIVE: "medium",    # إحصائي مقيّد
    KnowledgeLevel.GENERATIVE: "low",      # توليدي: لا HIGH أبداً
    KnowledgeLevel.SOCIAL: "low",          # مجتمعي يُحترم لا يحكم
    KnowledgeLevel.GUESS: "none",          # تخمين: الصمت قرار
}

# درجة اليقين المرجعية (FSI) — للتوثيق والشفافية
_LEVEL_FSI = {
    KnowledgeLevel.MATHEMATICAL: 1.00, KnowledgeLevel.PHYSICAL: 0.95,
    KnowledgeLevel.ANALYTICAL: 0.90, KnowledgeLevel.FIELD: 0.75,
    KnowledgeLevel.INDUCTIVE: 0.60, KnowledgeLevel.GENERATIVE: 0.35,
    KnowledgeLevel.SOCIAL: 0.30, KnowledgeLevel.GUESS: 0.10,
}

# تصنيف المصادر الفعلية لمستوياتها (يربط الكود بالمصفوفة)
_SOURCE_LEVEL = {
    # فيزياء (6)
    "fao56": KnowledgeLevel.PHYSICAL, "penman_monteith": KnowledgeLevel.PHYSICAL,
    "phi": KnowledgeLevel.PHYSICAL, "maas_hoffman": KnowledgeLevel.PHYSICAL,
    # مخبري (5)
    "lab": KnowledgeLevel.ANALYTICAL, "ec": KnowledgeLevel.ANALYTICAL,
    "ph": KnowledgeLevel.ANALYTICAL, "soil_test": KnowledgeLevel.ANALYTICAL,
    # ميداني (4)
    "field_sensor": KnowledgeLevel.FIELD, "weather_station": KnowledgeLevel.FIELD,
    # استقرائي (3)
    "zone_factor": KnowledgeLevel.INDUCTIVE, "ml_model": KnowledgeLevel.INDUCTIVE,
    "district_baseline": KnowledgeLevel.INDUCTIVE,
    # توليدي (2)
    "llm": KnowledgeLevel.GENERATIVE, "chatbot": KnowledgeLevel.GENERATIVE,
    # استشعار طيفي → قرينة استقرائية بصرية (سقف منخفض)
    "satellite": KnowledgeLevel.INDUCTIVE, "ndvi": KnowledgeLevel.INDUCTIVE,
    "si": KnowledgeLevel.INDUCTIVE, "bsi": KnowledgeLevel.INDUCTIVE,
    # مجتمعي (1)
    "farmer": KnowledgeLevel.SOCIAL, "anwa": KnowledgeLevel.SOCIAL,
    # استكشافي (0)
    "day_zero": KnowledgeLevel.GUESS, "guess": KnowledgeLevel.GUESS,
}


@dataclass
class LevelInfo:
    level: KnowledgeLevel
    name_ar: str
    ceiling: str         # سقف الثقة
    fsi: float           # درجة اليقين المرجعية


_NAME_AR = {
    KnowledgeLevel.MATHEMATICAL: "رياضي", KnowledgeLevel.PHYSICAL: "فيزيائي",
    KnowledgeLevel.ANALYTICAL: "مخبري", KnowledgeLevel.FIELD: "ميداني",
    KnowledgeLevel.INDUCTIVE: "استقرائي", KnowledgeLevel.GENERATIVE: "توليدي",
    KnowledgeLevel.SOCIAL: "مجتمعي", KnowledgeLevel.GUESS: "استكشافي",
}


def level_of_source(source: str) -> KnowledgeLevel:
    """يُرجع المستوى المعرفي لمصدر. غير معروف → استكشافي (أحوط)."""
    return _SOURCE_LEVEL.get(source.lower().strip(), KnowledgeLevel.GUESS)


def level_info(level: KnowledgeLevel) -> LevelInfo:
    return LevelInfo(level, _NAME_AR[level], _LEVEL_CEILING[level], _LEVEL_FSI[level])


def ceiling_for_source(source: str) -> str:
    """سقف الثقة لمصدر (تطبيق 'التوليدي لا HIGH'، إلخ)."""
    return _LEVEL_CEILING[level_of_source(source)]


def fuse_confidence(sources: list[str], proposed: str = "high") -> tuple[str, str]:
    """قاعدة الانصهار الموحّدة: الثقة ≤ سقف أدنى مستوى مساهم.
    يُرجع (الثقة المسموحة, تعليل). تطبيق صريح لـ confidence ≤ min(ceiling_i)."""
    if not sources:
        return "none", "لا مصادر — لا ثقة"
    # السقف = أدنى سقوف المصادر
    ceilings = [(_CONF_RANK[ceiling_for_source(s)], s) for s in sources]
    min_rank, limiting = min(ceilings, key=lambda x: x[0])
    allowed_rank = min(_CONF_RANK.get(proposed, 3), min_rank)
    allowed = _RANK_CONF[allowed_rank]
    lvl = level_info(level_of_source(limiting))
    return allowed, (f"الثقة محدودة بـ«{allowed}» — أدنى سقف من مصدر "
                     f"{limiting} (مستوى {lvl.name_ar}، سقفه {lvl.ceiling})")


def explain_matrix_ar() -> str:
    """شرح المصفوفة للمهندس (شفافية)."""
    lines = ["مصفوفة المستويات المعرفية (الأعلى يقيناً أولاً):"]
    for lv in sorted(KnowledgeLevel, reverse=True):
        i = level_info(lv)
        lines.append(f"  {int(lv)} {i.name_ar}: سقف={i.ceiling}, يقين مرجعي={i.fsi}")
    return "\n".join(lines)
