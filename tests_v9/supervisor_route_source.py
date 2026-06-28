"""مساعد اختبارات: مصدر مسارات supervisor-agent بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/supervisor-agent/main.py`` نقل مُعالِجات مسارات ``/agent/*`` من
``@app.<method>`` في ``main.py`` إلى ``@router.<method>`` في وحدات ``routers/``. الحُرّاس
الساكنة التي تمسح مصدر مُعالِج مسار (مثل تمرير الإجراءات للبوّابة أو كشف الإجراءات القابلة
للتنفيذ) يجب أن تمسح ``main.py`` **و** ``routers/*.py`` معاً كي تبقى صحيحة بعد النقل.

النِيّة: المساعِدات/النماذج/الحالة المشتركة تبقى في main.py؛ مُعالِجات المسارات في
routers/. هذا المساعِد يُرجِع المصدر المُسلسَل فيغطّي الحالتين بلا إضعاف أيّ تأكيد أمنيّ.
"""

from __future__ import annotations

import os


def supervisor_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن للمسارات)."""
    svc = os.path.join(root, "services", "supervisor-agent")
    src = open(os.path.join(svc, "main.py"), encoding="utf-8").read()
    rdir = os.path.join(svc, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
