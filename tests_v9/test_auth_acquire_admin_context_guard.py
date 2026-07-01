"""حارس انحدار (V29.6.1): مسبح auth يضبط ``app.current_role='admin'`` على **كلّ**
اكتساب اتّصال، وعلى تهيئة المسبح.

لماذا هذا حرج: جدول ``users`` عليه FORCE RLS بسياسة ``user_self`` التي تسمح بالوصول عبر
``app.current_role='admin'`` (خدمة الهويّة تقرأ users بالبريد قبل معرفة المستأجِر). asyncpg
ينفّذ ``RESET ALL`` عند تحرير الاتّصال للمسبح فيمحو السياق session-level الذي ضبطه
``_init_auth_conn`` ⇒ الاكتساب التالي بلا سياق ⇒ RLS يرفض ⇒ login=401، register=RLS
violation (المنصّة كلّها معطّلة). العلاج (main.py ``_acquire``) يُعيد الضبط على كلّ اكتساب.

هذا الحارس ساكن (يمسح المصدر بـAST) فيلتقط أيّ انحدار يُسقِط إعادة الضبط قبل أن يصل إلى
runtime/الإنتاج — لا يحتاج DB. مكمّل لاختبار التكامل الذي يثبت السلوك على Postgres حيّ.
"""

from __future__ import annotations

import ast
import os

import pytest

pytestmark = pytest.mark.unit

_MAIN = os.path.join(os.path.dirname(__file__), "..", "services", "auth", "main.py")
# النمط اللازم: set_config لـapp.current_role إلى admin (نتحقّق من المفتاح والقيمة معاً).
_ROLE_KEY = "app.current_role"
_ROLE_VAL = "admin"


def _func_sources() -> dict[str, str]:
    """يُرجِع {اسم الدالّة: مصدرها} لكلّ FunctionDef/AsyncFunctionDef (متضمّناً المتداخلة)."""
    src = open(_MAIN, encoding="utf-8").read()
    tree = ast.parse(src)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(src, node)
            if seg is not None:
                out[node.name] = seg
    return out


def _sets_admin_context(source: str) -> bool:
    return _ROLE_KEY in source and _ROLE_VAL in source and "set_config" in source


def test_acquire_resets_admin_context_on_every_acquire():
    """``_acquire`` يجب أن يُعيد ضبط سياق admin (يصمد أمام RESET ALL بين الاكتسابات)."""
    funcs = _func_sources()
    assert "_acquire" in funcs, "لم يُعثَر على _acquire في services/auth/main.py"
    acquire_src = funcs["_acquire"]
    assert _sets_admin_context(acquire_src), (
        "_acquire لا يضبط app.current_role='admin' — انحدار خطير: بعد RESET ALL يفقد الاتّصال "
        "سياق الخدمة ⇒ RLS يرفض users ⇒ login=401/register=RLS violation. أعِد الضبط على كلّ "
        "اكتساب: await execute(\"SELECT set_config('app.current_role', 'admin', false)\")."
    )


def test_pool_init_sets_admin_context():
    """تهيئة المسبح (``_init_auth_conn``) تضبط سياق admin — حزام أمان للاستخدام الأوّل."""
    funcs = _func_sources()
    assert "_init_auth_conn" in funcs, "لم يُعثَر على _init_auth_conn (init المسبح)"
    assert _sets_admin_context(funcs["_init_auth_conn"]), (
        "_init_auth_conn لا يضبط app.current_role='admin' على تهيئة اتّصالات المسبح."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
