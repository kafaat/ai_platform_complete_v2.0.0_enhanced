"""api/canonical_water.py — قارئ موحّد لقيم المياه الكنسيّة من الحالة القانونيّة (Bundle D / D3).

D1 (#466) جعل الحالة القانونيّة (`field_state.agronomic.operational_truths`) تحمل ET0/ETc الكنسيّين.
D3 يُغلق فئة التناقضات المستقبليّة: بدل أن يقرأ كلّ مستهلِك ET0/ETc من مصدر مختلف، يقرؤونها **من
مكان واحد** عبر هذا القارئ النقيّ — فتُسقَط كتلة `water` ثابتة على نموذج قراءة الحالة.

صدق: لا قيمة ⇒ ``None`` (لا اختلاق). **لا يحسب شيئاً** (لا يمسّ المحرّكات/القرار) — قراءة صرفة لما
أنتجته D1 في الحالة. ``source`` يُعلَن دائماً للتدقيق.
"""

from __future__ import annotations

_WATER_KEYS = ("et0_mm", "etc_mm", "etc_demand_class", "kc", "fao56_stage")


def canonical_water(truths: dict | None) -> dict | None:
    """يستخرج كتلة المياه الكنسيّة من ``operational_truths`` — أو ``None`` إن غابت.

    يُرجِع ``{et0_mm, etc_mm, etc_demand_class, kc, fao56_stage, source}`` ملتقطاً المفاتيح
    الموجودة فقط (المفقود لا يُلفَّق). يلزم وجود ``et0_mm`` **و** ``etc_mm`` (جوهر الكتلة) وإلّا
    ``None`` — فالمستهلكون يقرؤون كتلة مكتملة أو يعرفون أنّها غير متاحة بصدق.
    """
    if not isinstance(truths, dict):
        return None
    if truths.get("et0_mm") is None or truths.get("etc_mm") is None:
        return None
    block = {k: truths[k] for k in _WATER_KEYS if k in truths and truths[k] is not None}
    block["source"] = "field_state.canonical"  # مصدر واحد مُعلَن (يُغلق تعدّد المصادر)
    return block
