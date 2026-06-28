"""مساعد اختبارات: مصدر مسارات auth-service بعد التفكيك المحفوظ-السلوك.

تفكيك ``services/auth/main.py`` نقل مُعالِجات المسارات الـ٢٧ من ``@app.<method>`` في
``main.py`` إلى ``@router.<method>`` في وحدات ``routers/``. الحُرّاس الساكنة التي تمسح
مصدر مُعالِج مسار (مثل register / accept_invitation / provision_tenant / change_role)
يجب أن تمسح ``main.py`` **و** ``routers/*.py`` معاً كي تبقى صحيحة بعد النقل.

النِيّة: المساعِدات/النماذج/الحالة المشتركة تبقى في main.py؛ مُعالِجات المسارات في
routers/. هذا المساعِد يُرجِع المصدر المُسلسَل فيغطّي الحالتين بلا إضعاف أيّ تأكيد أمنيّ.
"""

from __future__ import annotations

import os


def auth_combined_source(root: str) -> str:
    """يُرجِع نصّ ``main.py`` + كلّ ``routers/*.py`` مُسلسَلاً (لمسح ساكن للمسارات)."""
    auth = os.path.join(root, "services", "auth")
    src = open(os.path.join(auth, "main.py"), encoding="utf-8").read()
    rdir = os.path.join(auth, "routers")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".py") and fn != "__init__.py":
                src += "\n" + open(os.path.join(rdir, fn), encoding="utf-8").read()
    return src
