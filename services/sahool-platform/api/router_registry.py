"""api/router_registry.py — تسجيل مركزيّ لكلّ موجِّهات HTTP في التطبيق.

استُخرِج من نهاية ``api/main.py`` (تقليص الوحدة الأحاديّة) إلى وحدة مخصّصة.
يُستدعى ``register_routers(app)`` في *نهاية* ``main.py`` — بعد تعريف ``app`` وكلّ
الرموز المشتركة — كي يُحلّ الاستيراد الدائريّ: وحدات الراوتر تستورد من ``api.main``،
وحين تُنفَّذ الدالّة تكون تلك الرموز مُعرَّفة بالكامل. السلوك والترتيب محفوظان تماماً.

ثلاث طبقات (نفس ترتيب ``main.py`` السابق):
  ١) مراحل 9-12 (autonomy/learning/federation/ecosystem) — استيراد+تضمين صريح.
  ٢) تسجيل تلقائيّ: كلّ وحدة في ``api/routers/`` تُصدّر ``router`` (ترتيب أبجديّ
     مستقرّ)، عدا ما في ``ROUTER_AUTOREG_EXCLUDE``.
  ٣) ``service_proxy`` — يُستورَد متأخّراً صراحةً (يستورد من ``api.main`` ⇒ تفادي دورة).
"""

from __future__ import annotations

import importlib
import pkgutil

# الراوترات المُستثناة من التسجيل التلقائيّ (تُسجَّل صراحةً لتفادي دورة الاستيراد).
ROUTER_AUTOREG_EXCLUDE = {"service_proxy"}


def register_routers(app) -> None:
    """يضمّ كلّ موجِّهات HTTP في ``app`` — يُستدعى من نهاية ``api.main`` فقط."""
    # ١) مراحل 9-12 — تفعيل وقت التشغيل لواجهات public (Runtime Activation Patch).
    from api.phase9_autonomous_farm_os import router as phase9_autonomous_router
    from api.phase10_continuous_learning import router as phase10_learning_router
    from api.phase11_federated_agents import router as phase11_federation_router
    from api.phase12_marketplace_ecosystem import router as phase12_ecosystem_router

    app.include_router(phase9_autonomous_router)
    app.include_router(phase10_learning_router)
    app.include_router(phase11_federation_router)
    app.include_router(phase12_ecosystem_router)

    # ٢) تسجيل تلقائيّ لكلّ وحدة في api/routers/ (ترتيب أبجديّ مستقرّ).
    #    الحارس test_router_decomposition_guard يتحقّق عبر app.routes (وقت التشغيل).
    from api import routers as _routers_pkg

    for mod_info in sorted(pkgutil.iter_modules(_routers_pkg.__path__), key=lambda m: m.name):
        if mod_info.name in ROUTER_AUTOREG_EXCLUDE:
            continue
        router_mod = importlib.import_module(f"api.routers.{mod_info.name}")
        router_obj = getattr(router_mod, "router", None)
        if router_obj is not None:
            app.include_router(router_obj)

    # ٣) بوّابات الخدمات الداخلية (edge/soil): تُستورَد متأخّراً (api.main مكتمل)
    #    لتفادي دورة الاستيراد — المنصّة تتحقّق ثمّ تحقن X-Agent-Token خادميّاً.
    from api.routers.service_proxy import router as service_proxy_router

    app.include_router(service_proxy_router)
