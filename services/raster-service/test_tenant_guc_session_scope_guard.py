"""حارس ساكن: كلّ ضبط لـ``app.current_tenant`` في db_persist.py جلسيّ (is_local=false).

الخلفيّة (علّة قصّ مضلّع مؤكَّدة على main، أُصلِحت هنا): asyncpg بلا معاملة صريحة يعمل
في وضع autocommit — فكلّ ``execute``/``fetchrow`` معاملةٌ مستقلّة. مع ذلك، كان
``fetch_field_geometry`` وحده يضبط السياق بـ``set_config(..., true)`` (نطاق المعاملة)،
فيضيع السياق فور تنفيذه قبل ``fetchrow`` التالي ⇒ RLS يعيد صفراً ⇒ ``geometry=None`` ⇒
بلاطة bbox مستطيلة بلا قصّ على المضلّع. بقيّة الدوالّ العشر في الملفّ كانت تستخدم
``false`` (نطاق الجلسة) الصحيح؛ فحصٌ سابق رأى العشرة السليمة وصنّف الدلتا «تكرار»،
مُغفِلاً هذا الموضع الحادي عشر الشاذّ.

آمن جلسيّاً هنا لأنّ ``_connect()`` يفتح اتّصالاً جديداً قصير العمر لكلّ عمليّة (لا pool،
يُغلق في finally) ⇒ لا تسرّب سياق عبر العملاء. هذا الحارس يمنع أيّ موضع مستقبليّ من
إعادة إدخال ``true`` صامتاً.

مسح مصدر ساكن (لا تشغيل/شبكة).
"""

import os
import re

import pytest

pytestmark = pytest.mark.unit

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PERSIST = os.path.join(_HERE, "db_persist.py")

# يلتقط الوسيط الثالث (is_local) لأيّ set_config على app.current_tenant.
_SET_CONFIG_RE = re.compile(
    r"set_config\(\s*'app\.current_tenant'\s*,\s*\$1\s*,\s*(true|false)\s*\)"
)


def _matches() -> list[str]:
    with open(_DB_PERSIST, encoding="utf-8") as fh:
        return _SET_CONFIG_RE.findall(fh.read())


def test_every_tenant_guc_is_session_scoped_not_transaction_scoped():
    flags = _matches()
    assert flags, "لم يُعثر على أيّ set_config('app.current_tenant', $1, ...) — تغيّر النمط؟"
    offenders = [f for f in flags if f != "false"]
    assert not offenders, (
        "set_config('app.current_tenant', $1, true) ممنوع: نطاق المعاملة يضيع تحت "
        "asyncpg autocommit قبل الاستعلام التالي ⇒ فقدان سياق المستأجِر ⇒ RLS يعيد صفراً "
        "⇒ قصّ مضلّع مكسور. استخدم false (نطاق الجلسة؛ آمن لأنّ الاتّصال قصير العمر بلا pool). "
        f"مواضع مخالفة: {offenders}"
    )
