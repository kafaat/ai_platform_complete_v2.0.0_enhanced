"""router_registry.py — تسجيل تلقائيّ لراوترات guardrails-engine (نمط تفكيك المنصّة).

كلّ وحدة في حزمة ``routers/`` تُصدّر ``router = APIRouter()`` تُضمَّن تلقائيّاً في
التطبيق **بلا prefix** (المسارات تبقى كما هي تماماً — تفكيك محفوظ السلوك). يُستدعى
``register_routers(app)`` في **نهاية** ``main.py`` بعد تعريف ``app`` وكلّ التبعيّات
المشتركة — فيُحلّ الاستيراد الدائريّ (وحدات ``routers`` تستورد رموزاً من ``main``).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

logger = logging.getLogger("guardrails-engine")


def register_routers(app) -> list[str]:
    """يضمّ كلّ ``router`` في حزمة ``routers/`` إلى ``app``. يُرجِع أسماء ما سُجِّل.

    آمن: غياب الحزمة أو تعذّر استيراد وحدة لا يُسقِط التطبيق (يُسجَّل ويُتخطّى).
    """
    registered: list[str] = []
    try:
        import routers as _routers_pkg
    except ImportError:
        return registered
    for mod_info in sorted(pkgutil.iter_modules(_routers_pkg.__path__)):
        try:
            mod = importlib.import_module(f"routers.{mod_info.name}")
        except Exception:  # noqa: BLE001 — وحدة معطّلة لا تُسقِط الخدمة كلّها
            logger.exception("تعذّر استيراد راوتر routers.%s — يُتخطّى", mod_info.name)
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            _include_flat(app, router)
            registered.append(mod_info.name)
            logger.info("راوتر مُسجَّل تلقائيّاً: routers.%s", mod_info.name)
    return registered


def _include_flat(app, router) -> None:
    """يضمّ ``router`` بحيث تظهر مساراته **مسطّحةً** في ``app.routes`` (بلا prefix).

    خلفيّة: ``app.include_router`` في Starlette الحديثة (≥1.3) يلفّ الراوتر في كائن
    ``_IncludedRouter`` كسول (lazy) فلا تُسطَّح مساراته في ``app.routes`` — فيختلّ
    عدّ المسارات وحارس التفكيك الذي يعدّ ``r.path`` على ``app.routes``. لتجنّب ذلك
    نُمدّد قائمة مسارات التطبيق بمسارات الراوتر مباشرةً (راوتراتنا بلا prefix وكلّها
    ``APIRoute`` مبنيّة عبر ``@router.<m>`` — فالتمديد مكافئ سلوكيّاً لـ
    ``include_router`` الكلاسيكيّ: نفس كائنات المسار، نفس المطابقة والمخطّط). نتفادى
    التكرار إن سُجِّل المسار مسبقاً (إعادة استيراد). يبقى ``include_router`` متاحاً
    للإصدارات التي تُسطّح أصلاً، لكنّ التمديد المباشر أمتن عبر الإصدارات.
    """
    # إصلاح P0 (dependency_overrides): إلحاق كائنات المسار خاماً يكسر ربطها بموفِّر
    # التطبيق فلا تُطبَّق app.dependency_overrides (اختبارات الحقن للـauth تفشل). Starlette
    # 1.3.1 يُسطّح include_router في app.routes أصلاً — فنعود للطريق القياسيّ (يربط بالسياق).
    existing = {
        (getattr(r, "path", None), frozenset(getattr(r, "methods", None) or ())) for r in app.routes
    }
    fresh = [
        rt
        for rt in router.routes
        if (getattr(rt, "path", None), frozenset(getattr(rt, "methods", None) or ()))
        not in existing
    ]
    if not fresh:
        return
    _tmp = router.__class__()
    _tmp.routes = fresh
    app.include_router(_tmp)
