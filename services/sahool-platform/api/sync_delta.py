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

# قيمة cursor المقبولة: نصّ ISO-8601 (طابع created_at للعميل). نُبقي المقارنة
# نصّيّة معجميّة لأنّ طوابع ISO-8601 بنفس المنطقة الزمنيّة قابلة للترتيب معجميّاً،
# وهي بالضبط ما يُخزّنه PendingOperation.created_at (datetime.utcnow().isoformat()).


def _op_cursor(op: Any) -> str | None:
    """يستخرج طابع الـcursor من عمليّة (``created_at``). None إن غاب/فسد."""
    value = getattr(op, "created_at", None)
    if value is None and isinstance(op, dict):
        value = op.get("created_at")
    if isinstance(value, str) and value:
        return value
    return None


def _is_valid_cursor(cursor: Any) -> bool:
    """هل الـcursor صالح للمقارنة؟ (نصّ غير فارغ). أيّ شيء آخر ⇒ ارتداد full."""
    return isinstance(cursor, str) and bool(cursor)


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
    if not _is_valid_cursor(cursor):
        # None/فارغ/نوع غير نصّيّ ⇒ السلوك الحاليّ (full). لا نرمي على الفاسد.
        return list(operations)

    out: list[Any] = []
    for op in operations:
        op_cur = _op_cursor(op)
        if op_cur is None:
            # عمليّة بلا طابع ⇒ نُبقيها (لا نُسقط ما لا نؤرّخه — fail-safe).
            out.append(op)
            continue
        try:
            if op_cur > cursor:  # type: ignore[operator]
                out.append(op)
        except TypeError:
            # مقارنة فاسدة لعمليّة بعينها ⇒ نُبقيها (لا فقدان).
            out.append(op)
    return out


def newest_cursor(operations: list[Any]) -> str | None:
    """أحدث طابع ``created_at`` بين العمليّات (الـcursor الجديد للعميل).

    None إن لم توجد طوابع صالحة (لا عمليّات/كلّها بلا تأريخ) ⇒ العميل يُبقي
    cursorه الحاليّ. يُحسَب عبر ``max`` على الطوابع النصّيّة (ISO قابل للترتيب).
    """
    cursors = [c for c in (_op_cursor(op) for op in operations) if c is not None]
    if not cursors:
        return None
    return max(cursors)
