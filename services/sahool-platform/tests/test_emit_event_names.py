"""حارس انحدار: أسماء الأحداث المُمرَّرة لـ_emit_domain_event في main.py صالحة.

بعد نقل بحث EventType[name] خارج الـtry (لم يعد يُبتلَع)، اسم حدث مُخطئ يرفع KeyError
وقت التشغيل. هذا الحارس يكشف أيّ اسم غير موجود في EventType **قبل** النشر (لا أحداث
مفقودة صامتة ولا 500 مفاجئ). يستخرج وسائط _emit_domain_event الحرفيّة من main.py.
"""

import re
from pathlib import Path

from api.event_bus import EventType

_MAIN = Path(__file__).resolve().parent.parent / "api" / "main.py"


def _emitted_event_names() -> set[str]:
    """يلتقط الوسيط الثالث (اسم الحدث) من نداءات _emit_domain_event(conn, user, "NAME", ...)."""
    src = _MAIN.read_text(encoding="utf-8")
    # _emit_domain_event(\n conn,\n user,\n "EVENT_NAME", ...
    pattern = re.compile(
        r"_emit_domain_event\(\s*conn\s*,\s*user\s*,\s*\"([A-Z_]+)\"",
        re.MULTILINE,
    )
    return set(pattern.findall(src))


def test_all_emitted_event_names_are_valid_eventtype_members():
    emitted = _emitted_event_names()
    assert emitted, "لم تُلتقَط أيّ أسماء أحداث — تحقّق من الـregex/نمط النداء"
    unknown = sorted(n for n in emitted if n not in EventType.__members__)
    assert not unknown, f"أسماء أحداث غير موجودة في EventType (ستُسقِط الكتابة): {unknown}"
