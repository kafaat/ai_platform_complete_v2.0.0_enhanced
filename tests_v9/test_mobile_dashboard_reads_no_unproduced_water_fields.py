"""
tests_v9/test_mobile_dashboard_reads_no_unproduced_water_fields.py

شاهد MOBILE-DASHBOARD-SAVINGS-PCT-HAS-NO-PRODUCER-01: المُنتِج الوحيد للوحة الموبايل،
GET /api/v1/indicators/dashboard، لا يُصدِر `water_usage` (لا `this_month_m3` ولا
`savings_pct`). كانت `dashboard_screen.dart` تقرأ `data['water_usage']['savings_pct']`
بلا حارس فتعرض «توفير X%» بلا قياس. هذا الاختبار يفحص مصدر Dart (بلا تعليقات) ويحمرّ
إن عاد أيّ ملفّ تحت lib/ يقرأ أحد هذه المفاتيح، أو إن فقدت اللوحةُ بطاقةَ «غير مقيس».

اختبار Dart المكافئ (`mobile/sahool_app/test/dashboard_water_not_measured_test.dart`)
يعمل في وظيفة Flutter Analyze & Test؛ هذا الشاهد يعمل في جناح الوحدة بلا Flutter.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "mobile" / "sahool_app" / "lib"
DASHBOARD = LIB / "screens" / "dashboard_screen.dart"
CARD = LIB / "widgets" / "water_usage_card.dart"

UNPRODUCED_KEYS = ("water_usage", "this_month_m3", "savings_pct")
_KEY_READ = re.compile(r"""\[\s*['"](""" + "|".join(UNPRODUCED_KEYS) + r""")['"]\s*\]""")
_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _code(path: Path) -> str:
    return _strip_comments(path.read_text(encoding="utf-8"))


def test_no_mobile_source_reads_an_unproduced_water_field():
    offenders = []
    for path in sorted(LIB.rglob("*.dart")):
        for match in _KEY_READ.finditer(_code(path)):
            offenders.append(f"{path.relative_to(ROOT)}: [{match.group(1)!r}]")
    assert not offenders, (
        "الموبايل يقرأ مفاتيح مياه لا يُصدِرها /api/v1/indicators/dashboard: " + "; ".join(offenders)
    )


def test_dashboard_renders_the_not_measured_water_card():
    assert "WaterUsageNotMeasuredCard()" in _code(DASHBOARD)
    card = CARD.read_text(encoding="utf-8")
    assert "kWaterNotMeasuredValue = 'غير مقيس'" in card


def test_the_key_pattern_catches_the_pre_fix_read():
    # الشكل الذي كان على main: يجب أن يلتقطه النمط، وإلّا صار الشاهد صامتاً.
    pre_fix = "value: '${data['water_usage']['savings_pct']}%',"
    assert [m.group(1) for m in _KEY_READ.finditer(pre_fix)] == ["water_usage", "savings_pct"]
    assert not _KEY_READ.findall(_strip_comments("// data['water_usage']"))
