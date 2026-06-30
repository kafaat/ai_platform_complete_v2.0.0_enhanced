"""api/routers/ai_models.py — كتالوج نماذج الذكاء القابلة للاختيار (AI Models)
=============================================================================
يكشف للواجهة المزوّد الحاليّ وقائمة النماذج المتاحة (المضبوطة في `.env`) كي يبني
المستخدم منها منتقي نموذج لتحليل الحقول — دون أيّ أسرار (مفاتيح/ترويسات).

المصدر الوحيد للحقيقة: ``api.ai_provider_config`` (نفس مُحلِّل مسار الدردشة)، فلا
يتباعد ما تعرضه الواجهة عمّا يُنفَّذ خادميّاً.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.ai_provider_config import available_models, resolve_ai_provider
from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/ai/models")
def list_ai_models(user: UserSchema = Depends(get_current_user)):
    """المزوّد الحاليّ + كتالوج النماذج المتاحة للاختيار (بلا أسرار).

    تستهلكها شاشة المستشار لبناء منتقي النموذج (DeepSeek/Claude Sonnet/Gemini…).
    `default_model` هو ما يُستعمَل إن لم تختر الواجهة. `available` يعكس جاهزيّة
    المزوّد السحابيّ (مفتاح/نموذج)؛ غير الجاهز ⇒ سبب صريح بالعربيّة.
    """
    cfg = resolve_ai_provider()
    return {
        "provider": cfg.provider,
        "default_model": cfg.model or None,
        "available": cfg.available,
        "reason_ar": cfg.reason_ar or None,
        "models": available_models(),
    }
