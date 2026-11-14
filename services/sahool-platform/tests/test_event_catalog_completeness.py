"""حارس اكتمال سجلّ الأحداث (C-15/C-07): كلّ عضو EventType مسجَّل أو محجوز بسبب صريح.

كان `api/event_catalog.py` يعترف بأنّه لا حارس يربطه بـ`EventType` (api/event_bus.py)، فانحرف:
59 عضواً مقابل 40 مدخلاً. هذا الاختبار النقيّ (بلا قاعدة ولا شبكة) يفرض:

  1. كلّ عضو في `EventType` إمّا في `_CATALOG` وإمّا في `_RESERVED_NO_PRODUCER` أدناه.
  2. كلّ نوع في `_RESERVED_NO_PRODUCER` لا مُصدِر له فعلاً في شجرة المنصّة (فحص AST)،
     فلا تصير القائمة مخبأً لأنواع تُصدَر بلا توثيق.
  2ب. وبالعكس: كلّ نوع في `_CATALOG` له مُصدِر فعليّ، فلا يُعلَن حدث حيّ لا يُنشَر.
  3. لا مدخل في السجلّ أو القائمة لاسمٍ ليس عضواً في `EventType` (لا أسماء ميّتة).

«المُصدِر» = أيّ موضع خارج الاختبارات وخارج تعريف التعداد نفسه يكتب الحدث: نداء
`_emit_domain_event(conn, user, "NAME", ...)`، أو مرجع `EventType.NAME`/`EventType["NAME"]`،
أو وسيط `event_type="NAME"`/`event_type="<القيمة المنقّطة>"` في أيّ نداء.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest
from api.event_bus import EventType
from api.event_catalog import _CATALOG

pytestmark = pytest.mark.unit

_PLATFORM_ROOT = Path(__file__).resolve().parent.parent
_EVENT_BUS = _PLATFORM_ROOT / "api" / "event_bus.py"

# أعضاء EventType المعرَّفة بلا أيّ مُصدِر في الشجرة. مفردات الحجز تتبع
# event_publish_contracts.yaml («محجوز بلا ناشر، لا نختلق منتِجاً»). عند إضافة مُصدِر
# لأحدها: انقله إلى _CATALOG بحقول حمولته من نداء الإصدار، فيفشل البند 2 هنا حتّى يُنقَل.
_RESERVED_NO_PRODUCER: dict[str, str] = {
    "LIFECYCLE_TRANSITIONED": (
        "reserved, no producer: مقروء فقط في event_replay/field_timeline/event_upcasting"
    ),
    "NDVI_OBSERVATION": (
        "reserved, no producer: مقروء فقط في event_replay (remote_sensing.ndvi.observed)"
    ),
    "WEATHER_RAIN": "reserved, no producer: مقروء فقط في event_replay/yield_heuristics",
    "MOISTURE_LOW": "reserved, no producer: مقروء فقط في event_replay (weather.moisture.low)",
    "AI_ANOMALY_DETECTED": "reserved, no producer: مقروء فقط في event_replay",
    # قرار المالك 2026-11-14: «بدء» نشاط لا يُنفَّذ في أيّ مسار. المُخطَّط صار
    # ACTIVITY_RECORDED والمُنفَّذ *_COMPLETED (field_aggregate.activity_event_for)؛
    # event_replay يطوي ما بقي منها في المخزن تاريخيّاً، ولا مشترِك حيّ.
    "PLANTING_STARTED": (
        "reserved, no producer: مقروء فقط في event_replay (operation.planting.started)"
    ),
    "IRRIGATION_STARTED": (
        "reserved, no producer: مقروء فقط في event_replay (operation.irrigation.started)"
    ),
    "HARVEST_STARTED": (
        "reserved, no producer: مقروء فقط في event_replay (operation.harvest.started)"
    ),
}


def _iter_source_files():
    for path in sorted(_PLATFORM_ROOT.rglob("*.py")):
        rel = path.relative_to(_PLATFORM_ROOT)
        if rel.parts[0] == "tests" or path == _EVENT_BUS:
            continue
        yield path


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_event_type_ref(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "EventType") or (
        isinstance(node, ast.Attribute) and node.attr == "EventType"
    )


@lru_cache(maxsize=1)
def _emitted_members() -> dict[str, list[str]]:
    """اسم العضو → مواضع إصداره (path:line) في شجرة المنصّة خارج الاختبارات."""
    by_value = {m.value: name for name, m in EventType.__members__.items()}
    members = set(EventType.__members__)
    found: dict[str, list[str]] = {}

    def _hit(name: str | None, path: Path, node: ast.AST) -> None:
        if name in members:
            rel = path.relative_to(_PLATFORM_ROOT).as_posix()
            found.setdefault(name, []).append(f"{rel}:{node.lineno}")

    def _literal(node: ast.expr | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return by_value.get(node.value, node.value)
        return None

    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _is_event_type_ref(node.value):
                _hit(node.attr, path, node)
            elif isinstance(node, ast.Subscript) and _is_event_type_ref(node.value):
                _hit(_literal(node.slice), path, node)
            elif isinstance(node, ast.Call):
                if _callee_name(node.func) == "_emit_domain_event":
                    if len(node.args) >= 3:
                        _hit(_literal(node.args[2]), path, node)
                    for kw in node.keywords:
                        if kw.arg == "event_type_name":
                            _hit(_literal(kw.value), path, node)
                for kw in node.keywords:
                    if kw.arg == "event_type":
                        _hit(_literal(kw.value), path, node)
    return found


def test_scanner_sees_known_emitters_of_every_shape():
    """ضابط ضدّ الفحص الأجوف: الماسح يلتقط كلّ شكل إصدار قائم في الشجرة."""
    emitted = _emitted_members()
    # _emit_domain_event(conn, user, "NAME") في راوتر، وmain._emit_domain_event(conn, actor, ...)
    assert "FIELD_GEOMETRY_CHANGED" in emitted
    assert "AI_SUGGESTION" in emitted
    # EventBus.emit(event_type=EventType.NAME) و_emit(event_type=EventType.NAME.value)
    assert "TRUEUP_APPLIED" in emitted
    assert "IRRIGATION_RESERVATION_DISPATCH_REQUESTED" in emitted


def test_every_event_type_member_is_catalogued_or_reserved():
    missing = sorted(
        name
        for name in EventType.__members__
        if name not in _CATALOG and name not in _RESERVED_NO_PRODUCER
    )
    assert not missing, (
        "أعضاء EventType بلا مدخل في api/event_catalog.py _CATALOG ولا في "
        f"_RESERVED_NO_PRODUCER: {missing}"
    )


def test_reserved_types_really_have_no_producer():
    emitted = _emitted_members()
    produced = {name: emitted[name] for name in _RESERVED_NO_PRODUCER if name in emitted}
    assert not produced, (
        "أنواع في _RESERVED_NO_PRODUCER لها مُصدِر فعليّ — انقلها إلى _CATALOG بحقول "
        f"حمولتها: {produced}"
    )


def test_catalogued_types_really_have_a_producer():
    """العكس: مدخل في _CATALOG بلا مُصدِر يُعلن حدثاً حيّاً لا يُصدَر — مكانه الحجز."""
    emitted = _emitted_members()
    unproduced = sorted(name for name in _CATALOG if name not in emitted)
    assert not unproduced, (
        "أنواع في _CATALOG بلا أيّ مُصدِر في الشجرة — انقلها إلى _RESERVED_NO_PRODUCER "
        f"بسبب صريح حتّى يوجد منتِج حقيقيّ: {unproduced}"
    )


def test_reserved_entries_have_reasons_and_are_not_catalogued():
    for name, reason in _RESERVED_NO_PRODUCER.items():
        assert reason.startswith("reserved, no producer"), f"سبب الحجز ناقص لـ{name}"
        assert name not in _CATALOG, f"{name} مسجَّل ومحجوز معاً"


def test_no_catalog_or_reserved_name_outside_event_type():
    members = set(EventType.__members__)
    stale = sorted((set(_CATALOG) | set(_RESERVED_NO_PRODUCER)) - members)
    assert not stale, f"أسماء ليست أعضاء في EventType: {stale}"


def test_catalog_keys_match_entry_names():
    for key, ev in _CATALOG.items():
        assert ev.name == key, f"مفتاح {key} لا يطابق name={ev.name}"
