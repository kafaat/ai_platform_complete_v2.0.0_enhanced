"""api/field_aggregate_ports.py — منافذ الحقل الحيّة (الجسر بين الـAggregate والقاعدة).

`FieldAggregate` (api/field_aggregate.py) نواةٌ نقيّة لا I/O؛ تحتاج منافذ مُحقَنة
لتعمل على قاعدة حقيقيّة:

  • `load_state(conn, field_id)` — يقرأ لقطة حالة الحقل من القاعدة (وجوده، موسمه
    النشط، مرحلته في دورة الحياة) ويبنيها كـ`FieldState` — مدخل النواة.
  • منفذ التطبيق الذرّيّ (`ApplyPort`) — يكتب الحالة ويُصدِر الأحداث في **معاملة
    واحدة**؛ يبقى مسؤوليّة كلّ endpoint (جسمه المُثبَت هو المنفذ) ويُوصَل تدريجيّاً
    عند توجيهه عبر الـaggregate (POST_DEPLOYMENT_ROADMAP — المرحلة ٣، خطوة ٣).

هذا الملفّ يُنفّذ **النصف القرائيّ** (`load_state`) — منفذ حتميّ يأخذ اتّصالاً
مُهيّأً (داخل `tenant_connection`/RLS) ولا يفتح اتّصاله بنفسه، فيكون قابلاً للاختبار
باتّصال وهميّ offline وبقاعدة حقيقيّة في CI. لا يغيّر أيّ سلوك endpoint قائم (لا
يستعمله مسار حيّ بعد) — تمهيدٌ أمين للتوجيه دون تراجع.

صدق: القراءة **مطابِقة لما تفحصه endpoints الإنتاج فعليّاً** (مصدر الحقيقة
`api/routers/fields.py`):
  • الوجود: `SELECT 1 FROM fields WHERE field_id=$1` — يطابق `_assert_field_in_tenant`.
  • الموسم النشط: `…FROM seasons WHERE field_id=$1 AND status='active'` — يطابق فحص
    create_season/delete_field. أوّل صفّ (LIMIT 1) — العقد القاعديّ يضمن واحداً نشطاً.
RLS مُطبَّق عبر الاتّصال المُمرَّر (لا فلترة tenant_id صريحة هنا — العقد نفسه الذي
تعتمده الـendpoints؛ صفّ خارج المستأجِر لا يُرى أصلاً).

ملاحظة `lifecycle_state` (صدق): **لا يُقرأ هنا**. جدول `field_lifecycle` مفتاحه
`field_id` من نوع **UUID** (v10)، بينما `fields.field_id` نصّ (`fld_…`، VARCHAR) —
فاستعلامه بمعرّف نصّيّ يرفع خطأ صبّ UUID **يُفسِد المعاملة المشتركة** في مسار التوجيه
(الذرّيّة مع متجر الأوامر). والأهمّ: النواة `FieldAggregate` **لا تستعمل**
`lifecycle_state` في أيّ invariant (تعتمد `exists` + `has_active_season` فقط) — فقراءته
خطرٌ بلا فائدة. يبقى الحقل في `FieldState` (اختياريّ، None) لمصدر لاحق إن لزم.
"""

from __future__ import annotations

from typing import Any

from api.field_aggregate import FieldState


async def load_state(conn: Any, field_id: str) -> FieldState:
    """يقرأ لقطة حالة الحقل من القاعدة عبر اتّصال مُهيّأ (RLS) — منفذ `StateLoader`.

    لا يفتح اتّصالاً (يأخذه من المُنادي ضمن `tenant_connection`) فيكون ذرّيّاً مع بقيّة
    عمليّة الأمر وقابلاً للاختبار باتّصال وهميّ. حقلٌ غير مرئيّ للمستأجِر (RLS) ⇒
    `exists=False` (نفس دلالة 404 في الـendpoints). لا يرفع استثناءً للغياب — النواة
    (FieldAggregate) هي مَن يقرّر الـinvariant بناءً على اللقطة.
    """
    exists = bool(await conn.fetchval("SELECT 1 FROM fields WHERE field_id = $1", field_id))
    if not exists:
        # حقل غير موجود/خارج المستأجِر — لقطة "غير موجود" (النواة تترجمها 404 عند اللزوم).
        return FieldState(field_id=field_id, exists=False)

    active = await conn.fetchrow(
        "SELECT season_id FROM seasons WHERE field_id = $1 AND status = 'active' LIMIT 1",
        field_id,
    )
    # lifecycle_state لا يُقرأ عمداً (field_lifecycle.field_id من نوع UUID ≠ field_id
    # النصّيّ؛ والنواة لا تستعمله) — انظر docstring الوحدة. يبقى None.
    return FieldState(
        field_id=field_id,
        exists=True,
        has_active_season=active is not None,
        active_season_id=(active["season_id"] if active is not None else None),
    )
