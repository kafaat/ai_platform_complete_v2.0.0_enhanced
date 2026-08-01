"""EXPECTED-CONTROL-FLOW-EXCEPTION — موضعان يطابقان نمط «المعالِج الصامت» وليسا منه.

كاشف `SILENT-EXCEPTION-HANDLERS-11-01` قاعدته نحويّة صرفة: ``except …:`` يليه ``pass``.
موضعان من الأحد عشر يطابقانها بينما الاستثناء فيهما **هو إشارة التحكّم المقصودة**:

  • ``api/main.py`` — ``task.cancel()`` ثمّ ``await task`` يرفع ``CancelledError`` دائماً؛
    الاستثناء **تأكيد** التوقّف. تسجيله يُسجّل نجاحاً كأنّه عطل، وإعادة رفعه تُفشِل
    الإيقاف على نجاحه.
  • ``soil-service/projection_jobs.py`` — ``wait_for(stop.wait(), timeout)`` يرفع
    ``TimeoutError`` على المسار **العاديّ** مرّة كلّ فترة استطلاع إلى الأبد؛ تسجيله
    يُنتِج ضجيجاً يتناسب مع زمن التشغيل.

فإخراجهما من الدَّين قرار **صحيح**، لكنّه لا يجوز أن يكون حذفاً من أساس. الشرط الذي
وضعه المالك: لكلّ موضع دليل بنيويّ — نوع استثناء ضيّق · تعليق عقديّ · اختبار يُثبِت أنّ
الاستثناء هو إشارة التحكّم · ومنع ``except Exception``. هذا الملفّ يحمل الأربعة، فيصير
التصنيف **مفروضاً** لا مُدّعى: توسيع أيّ موضع إلى ``Exception`` يُسقِط CI.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

SITES = {
    "services/sahool-platform/api/main.py": ("_stop_outbox_worker", "CancelledError"),
    "services/soil-service/projection_jobs.py": ("worker_loop", "TimeoutError"),
}


def _function(path: str, name: str) -> ast.AST:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path}: الدالّة {name} غير موجودة")


def _suppressed_names(fn: ast.AST) -> set[str]:
    """أسماء الاستثناءات المُمرَّرة إلى ``contextlib.suppress`` داخل الدالّة."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        for item in node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if attr != "suppress":
                continue
            for arg in call.args:
                names.add(arg.attr if isinstance(arg, ast.Attribute) else getattr(arg, "id", ""))
    return names


# ───────────────── الدليل البنيويّ لكلّ موضع ─────────────────


@pytest.mark.parametrize(("path", "spec"), sorted(SITES.items()))
def test_site_uses_suppress_with_a_narrow_type(path: str, spec: tuple[str, str]):
    """``contextlib.suppress`` بنوع مُسمّى — القصد بنيويّ لا معتمِد على قراءة ``pass``."""
    func_name, exc_name = spec
    suppressed = _suppressed_names(_function(path, func_name))
    assert exc_name in suppressed, (
        f"{path}::{func_name} يجب أن يكتم {exc_name} صراحةً عبر contextlib.suppress"
    )


@pytest.mark.parametrize(("path", "spec"), sorted(SITES.items()))
def test_site_never_widens_to_bare_exception(path: str, spec: tuple[str, str]):
    """توسيع الكتم إلى ``Exception``/``BaseException`` يُسقِط الفحص — هذا هو الحارس.

    بلا هذا، «إعادة التصنيف» تصير رخصةً: يكفي أن يوسّع أحدهم النوع لاحقاً فيعود
    الابتلاع الصامت تحت اسم مُبرَّأ.
    """
    func_name, _ = spec
    suppressed = _suppressed_names(_function(path, func_name))
    forbidden = suppressed & {"Exception", "BaseException"}
    assert not forbidden, (
        f"{path}::{func_name} يكتم {sorted(forbidden)} — الكتم العريض يُعيد العيب الصامت"
    )


@pytest.mark.parametrize(("path", "spec"), sorted(SITES.items()))
def test_site_carries_the_classification_comment(path: str, spec: tuple[str, str]):
    """التصنيف مكتوب في مصدره: قارئ لاحق يجد السبب عند الكود لا في سجلّ بعيد."""
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "EXPECTED-CONTROL-FLOW-EXCEPTION" in src, f"{path}: تعليق التصنيف مفقود"


# ───────────── إثبات سلوكيّ: الاستثناء **هو** إشارة التحكّم ─────────────


def test_cancelled_error_is_the_stop_confirmation():
    """``cancel()`` ثمّ ``await`` يرفع ``CancelledError`` — فكتمه انتظارُ نجاح."""

    async def scenario() -> str:
        async def forever():
            await asyncio.sleep(3600)

        task = asyncio.ensure_future(forever())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "raised"
        return "not-raised"

    assert asyncio.run(scenario()) == "raised"


def test_timeout_error_is_the_normal_poll_tick():
    """انقضاء فترة الاستطلاع يرفع ``TimeoutError`` بينما العلم مُطفأ — مسار عاديّ."""

    async def scenario() -> str:
        stop = asyncio.Event()
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.01)
        except TimeoutError:
            return "raised"
        return "not-raised"

    assert asyncio.run(scenario()) == "raised"


def test_set_event_returns_early_without_raising():
    """والعلم المرفوع يعود مبكراً بلا استثناء — فالكتم لا يبتلع مسار التوقّف."""

    async def scenario() -> bool:
        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(stop.wait(), timeout=5)
        return True

    assert asyncio.run(scenario()) is True
