"""api/routers/coffee.py — دليل البنّ اليمني (Coffee Advisor)
============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ النطاق (``coffee_advisor``) كانت مُستورَدة على مستوى وحدة ``main`` وتُستخدَم
حصريّاً من هذه الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً) لتفادي استيراد
يتيم في ``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.coffee_advisor import (
    coffee_pests,
)
from api.coffee_advisor import (
    cultivation_guide as coffee_guide,
)
from api.coffee_advisor import (
    site_suitability as coffee_site,
)
from api.coffee_advisor import (
    varieties as coffee_varieties,
)

router = APIRouter()


@router.get("/api/v1/coffee/site-suitability")
def coffee_site_endpoint(altitude_m: float):
    """ملاءمة موقع لزراعة البنّ بناءً على الارتفاع (المثالي 1500-2400م)."""
    return coffee_site(altitude_m)


@router.get("/api/v1/coffee/guide")
def coffee_guide_endpoint():
    """دليل زراعة البنّ اليمني: المدرّجات، التظليل، الريّ، التجفيف الطبيعي."""
    return coffee_guide()


@router.get("/api/v1/coffee/varieties")
def coffee_varieties_endpoint(region: str | None = None):
    """أصناف البنّ اليمنيّة (كلّها أو حسب منطقة)."""
    return coffee_varieties(region)


@router.get("/api/v1/coffee/pests")
def coffee_pests_endpoint():
    """آفات البنّ الرئيسيّة (صدأ الأوراق، ثاقبة الثمار) مرتبطة بـIPM."""
    return coffee_pests()
