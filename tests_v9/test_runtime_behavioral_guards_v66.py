"""اختبارات سلوكيّة (behavioral) لقيم EventType — تكمّل الحُرّاس البنيويّة (فجوة A2).

الفرق عن الحارس البنيويّ: بدل فحص أسماء الأعضاء نصّيّاً، نكرّر على EventType الفعليّ
ونفحص القيم/السلوك وقت التشغيل (EventType[name] كما يفعله _emit_domain_event حرفيّاً).

ملاحظة: اختبارات «تسجيل المسارات وقت التشغيل» (التي تُحمّل التطبيق الكامل) تتطلّب
fastapi فنُقلت إلى مجموعة المنصّة (services/sahool-platform/tests/test_runtime_routes_v66.py)
حيث تتوفّر التبعيّات — لأنّ وظيفة Unit Tests تعمل ببيئة دنيا بلا fastapi. هذا الملفّ
يبقى نقيّاً (api.event_bus لا يتطلّب fastapi) فيعمل في تلك البوّابة.
"""

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

_NATS_SUBJECT_RE = re.compile(r"^[a-z0-9]+([._-][a-z0-9]+)*$")


def test_eventtype_values_are_valid_nats_subjects():
    """كلّ عضو EventType قيمته subject نقطيّ صالح لـNATS (حروف صغيرة/نقاط/شرطات).

    بنيويّاً: حارس يفحص أسماء الأعضاء نصّيّاً. سلوكيّاً نكرّر على EventType الفعليّ
    ونتحقّق من القيمة الحقيقيّة — قيمة بحرف كبير/مسافة/شكل غير صالح تُنتج subject
    لا يقبله NATS وقت النشر، وهذا ما يمسكه هذا الاختبار.
    """
    from api.event_bus import EventType

    members = list(EventType)
    assert members, "EventType فارغ — لا أحداث معرّفة"
    for member in members:
        value = member.value
        assert isinstance(value, str) and value, f"{member.name} قيمته ليست نصّاً غير فارغ"
        assert _NATS_SUBJECT_RE.match(value), (
            f"{member.name}={value!r} ليس NATS subject صالح (حروف صغيرة/نقاط/شرطات فقط)"
        )


def test_eventtype_name_lookup_works_like_emit_domain_event():
    """EventType[name] ينجح لكلّ اسم ويعيد العضو الصحيح — كما يفعل _emit_domain_event.

    _emit_domain_event يستعمل EventType[event_type_name] (بحث بالاسم) لتحويل اسم
    الحدث إلى العضو قبل الإصدار. سلوكيّاً نتحقّق أنّ البحث ينجح فعلاً ويعيد القيمة
    الصحيحة — لا مجرّد فحص عضويّة نصّاً.
    """
    from api.event_bus import EventType

    for member in EventType:
        looked_up = EventType[member.name]
        assert looked_up is member
        assert looked_up.value == member.value


def test_eventtype_values_are_unique():
    """لا قيمتان متطابقتان في EventType (سلوكيّ: تصادم subjects يكسر التوجيه).

    عضوان بنفس القيمة يعنيان أنّ النشر/الاشتراك لا يميّز بينهما وقت التشغيل.
    """
    from api.event_bus import EventType

    values = [m.value for m in EventType]
    assert len(values) == len(set(values)), "توجد قيم EventType مكرّرة (تصادم NATS subject)"


def test_eventtype_is_str_enum_for_serialization():
    """EventType عضو str فعليّاً — يُسلسَل مباشرة في JSON/payload الحدث (سلوكيّ)."""
    from api.event_bus import EventType

    sample = next(iter(EventType))
    assert isinstance(sample, str), "EventType ليس str-mixin — تسلسل القيمة سيكسر"
    assert str(sample.value) == sample.value
