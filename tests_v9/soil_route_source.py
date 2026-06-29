"""مساعد اختبارات: مصدر مسارات soil-service بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/soil-service/main.py`` نقل مُعالِجات المسارات (``ingest_reading`` /
``get_readings``) من ``@app.<method>`` في ``main.py`` إلى ``@router.<method>`` في
وحدات ``routers/``. الحُرّاس الساكنة التي تمسح مصدر مُعالِج مسار (مثل عدم الثقة بـ
``tenant_id`` من الجسم) يجب أن تمسح ``main.py`` **و** ``routers/*.py`` معاً كي تبقى
صحيحة بعد النقل — لا إضعاف لأيّ تأكيد أمنيّ، فقط توسيع نطاق المسح.
"""

from __future__ import annotations

import os


def soil_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن للمسارات)."""
    svc = os.path.join(root, "services", "soil-service")
    src = open(os.path.join(svc, "main.py"), encoding="utf-8").read()
    rdir = os.path.join(svc, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
