"""مساعد اختبارات: مصدر مسارات guardrails-engine بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/guardrails-engine/main.py`` نقل المُعالِجات السبعة من ``@app.<method>``
في ``main.py`` إلى ``@router.<method>`` في وحدات ``routers/`` (المسارات/الطرائق/الأجسام/
المخرجات/المصادقة مطابقة تماماً — توكن خدمة /validate ومنطق fail-safe محفوظان). الحُرّاس
الساكنة التي تمسح مصدر مُعالِج مسار (مثل ``Depends(_require_service_token)`` على /validate)
يجب أن تمسح ``main.py`` **و** ``routers/*.py`` معاً كي تبقى صحيحة بعد النقل — لا إضعاف
لأيّ تأكيد أمنيّ، فقط توسيع النطاق إلى حيث صار الكود.

النِيّة: المساعِدات/النماذج/توكن الخدمة (``_require_service_token``/``_gr_verify``/
``_gr_authn``) تبقى في main.py؛ مُعالِجات المسارات في routers/. هذا المساعِد يُرجِع
المصدر المُسلسَل فيغطّي الحالتين.
"""

from __future__ import annotations

import os


def guardrails_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن للمسارات)."""
    svc = os.path.join(root, "services", "guardrails-engine")
    src = open(os.path.join(svc, "main.py"), encoding="utf-8").read()
    rdir = os.path.join(svc, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
