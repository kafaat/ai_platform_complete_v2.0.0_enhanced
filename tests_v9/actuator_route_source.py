"""مساعد اختبارات: مصدر مسارات actuator-service بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/actuator-service/main.py`` نقل مُعالِجات المسارات (مثل ``/command``)
من ``@app.<method>`` في ``main.py`` إلى ``@router.<method>`` في وحدات ``routers/``. الحُرّاس
الساكنة التي تمسح مصدر مُعالِج مسار (مثل استدعاء حارس التحكّم بالأجهزة، أو تبعيّة
``Depends(_verify_token)``، أو اشتقاق ``tenant_id`` من التوكن) يجب أن تمسح ``main.py``
**و** ``routers/*.py`` معاً كي تبقى صحيحة بعد النقل.

النِيّة: المساعِدات/النماذج/الحالة المشتركة (و``_verify_token`` و``_authorize_device_control``
و``_DEVICE_CONTROL_ROLES`` …) تبقى في main.py؛ مُعالِجات المسارات في routers/. هذا المساعِد
يُرجِع المصدر المُسلسَل فيغطّي الحالتين **بلا إضعاف أيّ تأكيد أمنيّ** (توسيع نطاق المسح فقط).
"""

from __future__ import annotations

import os


def actuator_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + ``*_runtime.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن)."""
    svc = os.path.join(root, "services", "actuator-service")
    src = open(os.path.join(svc, "main.py"), encoding="utf-8").read()
    # P1 decomposition: المنطق المشترك (الحُرّاس/الحالة) انتقل إلى actuator_runtime.py
    # الشقيقة — نوسّع المسح إليها (توسيع نطاق فقط، لا إضعاف للتأكيدات).
    for fn in sorted(os.listdir(svc)):
        if fn.endswith("_runtime.py"):
            src += "\n" + open(os.path.join(svc, fn), encoding="utf-8").read()
    rdir = os.path.join(svc, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
