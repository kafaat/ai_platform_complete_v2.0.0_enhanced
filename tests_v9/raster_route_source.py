"""مساعد اختبارات: مصدر مسارات raster-service بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/raster-service/main.py`` نقل مُزخرِفات المسارات من ``@app.<method>``
في ``main.py`` إلى ``@router.<method>`` في وحدات ``routers/``. الحُرّاس الساكنة التي
تمسح المصدر يجب أن تمسح ``main.py`` **و** ``routers/*.py`` معاً كي تبقى صحيحة.
"""

from __future__ import annotations

import os


def raster_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن للمسارات)."""
    rs = os.path.join(root, "services", "raster-service")
    src = open(os.path.join(rs, "main.py"), encoding="utf-8").read()
    rdir = os.path.join(rs, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
