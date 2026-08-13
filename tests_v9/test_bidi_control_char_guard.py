"""محارف الاتّجاه الخفيّة — BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01.

الحالتان الفارقتان هنا **متقابلتان**، وأيّهما سقطت أفسدت الحارس:

* **قلبُ الاتّجاه يُحجَب مطلقاً** — لا أساس ولا استثناء. هذه تُعيد ترتيب الرموز بصريّاً
  فيقرأ المراجع سطراً ويُنفَّذ غيرُه (trojan source، CVE-2021-42574).
* **العلامةُ المشروعة لا تُحجَب** — ٣٥٠ منها في الشجرة، أكثرها لضبط اتّجاه قوسٍ في شرحٍ
  عربيّ. حظرُها الشامل يُكذَّب أوّل مرّة، وأساسٌ يُكذَّب فوراً يُدرَّب قارئه على تعطيله.

وثالثةٌ تخصّ الحادثة نفسها: `bandit` يحجب `RLM` ولا يحجب `LRM`، فاستبدالُ أحدهما بالآخر
كان **يُمرِّر البوّابة ويُبقي المحرف الخفيّ**. فالحارس يعدّهما معاً.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "bidi_control_char_guard", ROOT / "scripts/ci/bidi_control_char_guard.py"
)
bidi = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(bidi)

# تُبنى من نقاط الترميز لا حرفيّاً: ملفٌّ يحمل المحرف نفسه يُسقِط الحارس على نفسه
# — وهو ما وقع في أوّل صياغة، وأمسكه الحارس فور تتبّع الملفّ. والاختبارُ الذي
# يُدخِل ما يمنعه ليس اختباراً بل حالةً أولى للعطل.
RLO = chr(0x202E)
RLM = chr(0x200F)
LRM = chr(0x200E)


def test_a_direction_override_is_blocked_with_no_baseline() -> None:
    """السطر الذي يقرؤه المراجع ليس السطر الذي يُنفَّذ — ولا استعمال مشروع له هنا."""
    overrides, marks = bidi.scan_text(f"if (admin){RLO} # trusted")

    assert overrides == {"RLO": 1}
    failures = bidi.violations({"x.py": dict(overrides)}, {}, {})

    assert any("قلبِ اتّجاه" in f for f in failures)


def test_an_override_is_not_excusable_by_the_baseline() -> None:
    """الأساس يحكم العلامات وحدها؛ ولو غطّى القالبات لصار رخصةً للهجوم نفسه."""
    failures = bidi.violations({"x.py": {"RLO": 1}}, {}, {"x.py": 99})

    assert failures, "أساسٌ يُرخّص قلبَ الاتّجاه يُبطِل الحارس كلّه"


def test_a_legitimate_mark_within_the_baseline_passes() -> None:
    """٣٥٠ علامةً مشروعة في الشجرة — حظرُها الشامل يُكذَّب أوّل مرّة."""
    _, marks = bidi.scan_text(f"# شرحٌ عربيّ {RLM}(قوس)")

    assert marks == {"RLM": 1}
    assert bidi.violations({}, {"doc.py": 1}, {"doc.py": 1}) == []


def test_one_more_mark_than_declared_is_blocked() -> None:
    assert bidi.violations({}, {"doc.py": 2}, {"doc.py": 1}) != []


def test_a_file_with_no_entry_may_not_introduce_marks() -> None:
    """ملفٌّ خارج الأساس سقفُه صفر — وإلّا نما الأساس بملفّاتٍ جديدة بلا حساب."""
    assert bidi.violations({}, {"new.py": 1}, {}) != []


def test_swapping_rlm_for_lrm_does_not_launder_the_character() -> None:
    """`bandit` يحجب RLM ولا يحجب LRM — فالاستبدال كان يُمرِّر البوّابة ويُبقي الخفيّ.

    وهذا هو سبب حذف المحرف يوم الحادثة بدل استبداله: الغرض سلامة المصدر لا خضرة البوّابة.
    """
    _, before = bidi.scan_text(f"x = 1 {RLM}")
    _, after = bidi.scan_text(f"x = 1 {LRM}")

    assert sum(before.values()) == sum(after.values()) == 1
    assert bidi.violations({}, {"f.py": 1}, {}) != []


def test_the_committed_baseline_holds_no_overrides() -> None:
    """الأساس المُلتزَم لا يحمل قالباً واحداً — والمقيس اليوم صفر، فليبقَ صفراً."""
    import json

    data = json.loads(
        (ROOT / "docs/architecture/bidi_control_char_baseline.json").read_text(encoding="utf-8")
    )

    assert data["overrides_present"] == {}


def test_the_real_tree_is_clean_of_overrides() -> None:
    overrides, _ = bidi.scan()

    assert overrides == {}, f"قلبُ اتّجاه في الشجرة: {sorted(overrides)}"
