"""api/sync_delta.py — مزامنة تفاضليّة (Delta-Sync) للموبايل — منطق نقيّ.

السياق (تدقيق #399): نقطة ``/api/v1/sync`` تستهلك الطابور بالكامل (full replay)
بلا cursor، فالعميل يُعيد إرسال كلّ المعلّق دائماً ⇒ هدر نطاق على شبكة يمنيّة
متقطّعة. هذه الوحدة تضيف ترشيحاً تفاضليّاً **نقيّاً عديم الحالة** (stateless):

  • لا جدول، لا migration، لا حالة على الخادم — **العميل** يحمل آخر cursor
    (طابع ``created_at`` ISO لأحدث عمليّة استلمها) ويُرسله في الطلب التالي.
  • ``filter_since(operations, cursor)`` يُرجِع فقط ما هو **أحدث** من cursor.
  • ``cursor=None`` ⇒ كلّ العمليّات (السلوك الحاليّ تماماً — صفر كسر).
  • cursor فاسد (غير قابل للمقارنة/تنسيق مجهول) ⇒ ارتداد آمن لـ**full**
    (لا فقدان عمليّات أبداً — fail-safe).
  • ``newest_cursor(operations)`` يحسب الـcursor الجديد ليُرفَق في الاستجابة.

النواة كلّها pure-Python بلا I/O؛ تُختبَر in-memory. مُحاطة في ``sync.py`` بعلم
``FEATURE_DELTA_SYNC`` (إغلاق مرن: مُطفأ ⇒ يُتجاهَل ``since`` ويبقى السلوك الحاليّ).

التمثيل: الـ"عمليّة" هنا أيّ كائن له سمة ``created_at`` (طابع ISO أُنشئ به offline)
— يطابق ``core.offline_first.PendingOperation``. الترتيب الأصليّ (FIFO) محفوظ.
"""

from __future__ import annotations

from typing import Any

from core.offline_first import parse_operation_timestamp

# Legacy offset-free stamps were produced in UTC. Compare instants, preserving
# the original stored string on output so existing cursors remain valid.


def _op_cursor(op: Any) -> str | None:
    """يستخرج طابع الـcursor من عمليّة (``created_at``). None إن غاب/فسد."""
    value = getattr(op, "created_at", None)
    if value is None and isinstance(op, dict):
        value = op.get("created_at")
    if isinstance(value, str) and value:
        return value
    return None


def filter_since(operations: list[Any], cursor: str | None) -> list[Any]:
    """يُرجِع العمليّات الأحدث من ``cursor`` فقط (مزامنة تفاضليّة).

    عقد نقيّ عديم الحالة:
      • ``cursor`` None/فارغ ⇒ كلّ العمليّات (السلوك الحاليّ — full replay).
      • ``cursor`` صالح ⇒ فقط العمليّات التي ``created_at`` لها **أكبر تماماً**
        من ``cursor`` (إقصاء ما استلمه العميل سابقاً؛ ``>`` لا ``>=`` لتفادي
        إعادة آخر عمليّة معروفة).
      • cursor فاسد (نوع غير نصّيّ، أو أيّ خطأ مقارنة) ⇒ **ارتداد لـfull**
        (تُرجَع الكلّ — لا فقدان عمليّات، fail-safe).
      • الترتيب الأصليّ (FIFO) محفوظ؛ العمليّات بلا ``created_at`` تُبقى دائماً
        (لا نُسقط ما لا نستطيع تأريخه — جانب الأمان).

    لا يُعدّل المُدخل؛ يُرجِع قائمة جديدة.
    """
    since = parse_operation_timestamp(cursor)
    if since is None:
        # Invalid or absent cursors replay all operations; no silent loss.
        return list(operations)

    out: list[Any] = []
    for op in operations:
        op_cur = parse_operation_timestamp(_op_cursor(op))
        if op_cur is None:
            # عمليّة بلا طابع ⇒ نُبقيها (لا نُسقط ما لا نؤرّخه — fail-safe).
            out.append(op)
            continue
        if op_cur > since:
            out.append(op)
    return out


def newest_cursor(operations: list[Any]) -> str | None:
    """أحدث طابع ``created_at`` بين العمليّات (الـcursor الجديد للعميل).

    None إن لم توجد طوابع صالحة (لا عمليّات/كلّها بلا تأريخ) ⇒ العميل يُبقي
    cursorه الحاليّ. المقارنة باللحظة UTC؛ النص الأصلي يبقى متوافقًا مع العميل.
    """
    cursors = [
        (stamp, value)
        for op in operations
        if (value := _op_cursor(op)) is not None
        and (stamp := parse_operation_timestamp(value)) is not None
    ]
    if not cursors:
        return None
    return max(cursors, key=lambda item: item[0])[1]
