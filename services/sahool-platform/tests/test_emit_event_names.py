"""حارس انحدار: أسماء الأحداث المُمرَّرة لـ_emit_domain_event صالحة (main + الراوترات).

بعد نقل بحث EventType[name] خارج الـtry (لم يعد يُبتلَع)، اسم حدث مُخطئ يرفع KeyError
وقت التشغيل. هذا الحارس يكشف أيّ اسم غير موجود في EventType **قبل** النشر (لا أحداث
مفقودة صامتة ولا 500 مفاجئ). يستخرج وسائط _emit_domain_event الحرفيّة من main.py
وكلّ ملفّات api/routers/ (تفكيك B1/P0 نقل معظم نقاط الإصدار إلى الراوترات — مثل نقل
_persist_field FIELD_CREATED/FIELD_STATE_CHANGED إلى routers/fields).

ملاحظة (سبب التشديد): الإصدار السابق التقط فقط `[A-Z_]+`، فكان يتخطّى بصمت السلاسل
الحرفيّة منخفضة الحالة المنقّطة (مثل "irrigation.valve.registered") — وهي بالضبط
الخلل الذي تسرّب وأسقط نقاط الصمّامات بـ500. الآن نلتقط **كلّ** سلسلة حرفيّة تُمرَّر
كوسيط ثالث ونتحقّق أنّها اسم عضو EventType صالح؛ فلا اسم منقّط يفلت بعد اليوم.
"""

import re
from pathlib import Path

from api.event_bus import EventType

_API_DIR = Path(__file__).resolve().parent.parent / "api"
# مصادر الإصدار: الوحدة المركزيّة + كلّ الراوترات (نقاط الإصدار انتقلت إليها).
_EMIT_SOURCES = [_API_DIR / "main.py", *sorted((_API_DIR / "routers").glob("*.py"))]


def _emitted_event_names() -> set[str]:
    """يلتقط الوسيط الثالث (اسم الحدث) من نداءات _emit_domain_event(conn, user, "NAME", ...).

    يمسح main.py وكلّ ملفّات api/routers/. يلتقط **أيّ** سلسلة حرفيّة (لا أسماء كبيرة
    فقط) حتى تُكشَف السلاسل المنقّطة منخفضة الحالة التي كانت تُسقِط الكتابة بـKeyError.
    """
    # _emit_domain_event(\n conn,\n user,\n "<أيّ سلسلة>", ...
    pattern = re.compile(
        r"_emit_domain_event\(\s*conn\s*,\s*user\s*,\s*\"([^\"]+)\"",
        re.MULTILINE,
    )
    names: set[str] = set()
    for src_path in _EMIT_SOURCES:
        names.update(pattern.findall(src_path.read_text(encoding="utf-8")))
    return names


def test_all_emitted_event_names_are_valid_eventtype_members():
    emitted = _emitted_event_names()
    assert emitted, "لم تُلتقَط أيّ أسماء أحداث — تحقّق من الـregex/نمط النداء"
    unknown = sorted(n for n in emitted if n not in EventType.__members__)
    assert not unknown, f"أسماء أحداث غير موجودة في EventType (ستُسقِط الكتابة بـ500): {unknown}"


def test_no_lowercase_dotted_event_literal_remains():
    """حارس صريح: لا تبقى سلسلة حرفيّة منقّطة (قيمة subject) كاسم حدث في نداءات الإصدار."""
    emitted = _emitted_event_names()
    dotted = sorted(n for n in emitted if "." in n)
    assert not dotted, f"سلاسل منقّطة (قيم NATS) مُمرَّرة كأسماء أحداث — استخدم اسم العضو: {dotted}"


def test_valve_event_members_exist_and_map_to_subjects():
    """يثبت الإصلاح: عضوا الصمّامات موجودان وقيمتهما هي subject NATS الصحيح."""
    assert EventType["IRRIGATION_VALVE_REGISTERED"].value == "irrigation.valve.registered"
    assert EventType["IRRIGATION_VALVE_STATE_CHANGED"].value == "irrigation.valve.state_changed"
