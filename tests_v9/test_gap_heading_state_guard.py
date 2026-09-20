"""تكذيب راتشِت العناوين اليتيمة — `GAP-HEADING-WITHOUT-A-STATE-RECORD-IS-INVISIBLE-01`.

الخاصّيّةُ المقيسة ليست «يمرّ على شجرةٍ سليمة» — تلك يُحقّقها حارسٌ لا يفعل شيئاً. بل:
**عنوانٌ جديدٌ يحمل حالتَه حيث لا يقرؤها أحد يُحمِّر**، و**لا يُحمِّر على ما كان**.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "gap_heading_state_guard.py"
_BASELINE = _ROOT / "docs" / "architecture" / "gap_heading_state_baseline.json"
_REGISTRY = _ROOT / "sahool-brain" / "gaps" / "registry.md"

_spec = importlib.util.spec_from_file_location("ghsg", _GUARD)
guard = importlib.util.module_from_spec(_spec)
sys.modules["ghsg"] = guard
_spec.loader.exec_module(guard)


_ORPHANS = [{"id": "GAP-A-01", "line": 3}, {"id": "GAP-B-01", "line": 9}]


def test_growth_beyond_the_baseline_blocks():
    errors = guard.evaluate(measured=212, baseline=211, orphans=_ORPHANS)
    assert errors and "212 > الأساس 211" in errors[0]


def test_a_shrinking_ratchet_passes():
    """**ينزل ولا يصعد.** خفضُ الدَّين لا يحتاج إذناً — رفعُه هو الذي يحتاجه."""
    assert guard.evaluate(measured=200, baseline=211, orphans=[]) == []


def test_equality_is_not_growth():
    """الحدُّ شاملٌ لا حصريّ: أساسٌ لم يتغيّر ليس نموّاً."""
    assert guard.evaluate(measured=211, baseline=211, orphans=_ORPHANS) == []


def test_the_message_names_the_remedy_and_the_rejected_spelling():
    """رسالةٌ تقول «ارتفع العدد» بلا علاجٍ تُرسِل قارئَها ليخمّن الصيغة المقبولة."""
    message = guard.evaluate(measured=212, baseline=211, orphans=_ORPHANS)[0]
    assert "- **الحالة:**" in message
    assert "«مفتوحة» في العنوان لا تُقرأ" in message
    assert "GAP-A-01" in message


def test_the_live_tree_matches_its_declared_baseline():
    """الأساسُ المُعلَن يطابق الشجرة — وإلّا كان راتشِتاً يحرس رقماً لا واقعاً."""
    assert guard.main([]) == 0
    declared = json.loads(_BASELINE.read_text(encoding="utf-8"))["baseline"]
    module = guard._measure_module()
    report = module.measure(_REGISTRY.read_text(encoding="utf-8"))
    assert report["orphan_gap_heading_count"] == declared


def test_a_missing_baseline_fails_closed(tmp_path):
    """أساسٌ مفقود ليس «صفرَ ديْن» — و«لم يُقرأ» ليست «لا شيء»."""
    with pytest.raises((OSError, ValueError, KeyError)):
        guard.main(["--baseline", str(tmp_path / "absent.json")])


# ── A-GAP-UNDER-A-DEEPER-HEADING-IS-INVISIBLE-TO-ITS-OWN-RATCHET-01 ─────────────
#
# الراتشِتُ أعلاه يُمسِك «عنوانٌ بلا سجلِّ حالة». وما لا يُقرأ **عنواناً أصلاً** يفلت
# منه: `gap_registry_measure.HEADING` كان `^##` وحدَه، فمدخلةٌ تحت `###` لا تدخل
# `heading_count`، فلا تصير يتيمةً، فلا يراها الحارسُ الذي وُجِد لهذا الصنف.
#
# مقيسٌ على `a0bba343` (دمج #1036): `V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01` مفتوحةٌ في
# الملفّ وغائبةٌ عن كلّ عدّ — heading وsection_state وrow وكلّ حقول الشذوذ —
# و«Gap registry measurement» خضراء. حارسٌ أعمى عن مدخل حارسه.

_DEEP = [{"id": "V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01", "line": 6332, "level": 3}]


def test_a_gap_id_under_a_deeper_heading_blocks():
    """**الأرضيّةُ صفر هنا لا راتشِت** — المقيسُ صفرٌ بعد إصلاح الحالة الوحيدة."""
    errors = guard.level_errors(_DEEP)
    assert errors, "مدخلةُ فجوةٍ تحت `###` مرّت صامتة"
    assert "V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01" in errors[0]
    assert "مستوى 3" in errors[0] and "سطر 6332" in errors[0]


def test_the_level_message_names_the_remedy():
    """رسالةٌ بلا علاجٍ تُدرِّب قارئَها على تجاوزها — فالعلاجُ منصوصٌ بحرفه."""
    message = guard.level_errors(_DEEP)[0]
    assert "## <معرِّف>" in message
    assert "- **الحالة:** open" in message


def test_a_canonical_registry_has_no_level_findings():
    """ولا يُحمِّر على عملٍ طبيعيّ: صفرٌ حين لا مدخلَ تحت مستوى غير قانونيّ."""
    assert guard.level_errors([]) == []


def test_the_live_registry_has_no_noncanonical_gap_heading():
    """**الزرعُ الحيّ على السجلّ الحقيقيّ، لا على نصٍّ اصطناعيّ.**

    الشجرةُ اليوم صفرٌ في هذا الحقل — وهذا ما يجعل أرضيّةَ الصفر قابلةً للفرض.
    """
    module = guard._measure_module()
    report = module.measure(_REGISTRY.read_text(encoding="utf-8"))
    assert report["noncanonical_heading_level_count"] == 0, report["noncanonical_heading_levels"]


def test_a_section_title_that_is_not_a_gap_entry_is_not_reported():
    """**الحقلُ أضيقُ من `ID` عمداً، وهذا شاهدُ الضيق.**

    `### HIL SQL follow-up` و`### MCP review follow-up` عنوانا قسمٍ فوق جدولٍ تُقرأ
    صفوفُه أصلاً، لا مدخلَي فجوة. وقبولُ الكلمة الكبيرة المفردة كان يجعل الحقلَ
    يُبلِّغ عمّا لا عطلَ فيه — وحقلٌ يُحمِّر على عملٍ طبيعيّ يُطفَأ.
    """
    module = guard._measure_module()
    report = module.measure(
        "### HIL SQL follow-up 2026-09-08\n\n| Gap | Status |\n|---|---|\n"
        "### MCP review follow-up 2026-09-08\n"
    )
    assert report["noncanonical_heading_levels"] == []


def test_a_deeper_gap_entry_is_caught_end_to_end():
    """من النصّ إلى رمز الخروج: `###` ⇒ حجب، و`##` بسطر حالةٍ قانونيّ ⇒ مرور."""
    module = guard._measure_module()
    broken = "### NEW-DEEP-GAP-01\n\n- **الحالة:** open — نصّ\n"
    assert guard.level_errors(module.measure(broken)["noncanonical_heading_levels"])
    fixed = "## NEW-DEEP-GAP-01\n\n- **الحالة:** open — نصّ\n"
    assert guard.level_errors(module.measure(fixed)["noncanonical_heading_levels"]) == []


def test_the_level_finding_is_blocking_not_advisory(tmp_path, capsys):
    """**من النصّ إلى رمز الخروج.** اكتشافٌ يُطبَع ولا يحجب خضرةٌ بثوبِ تقرير.

    هذا ما وقع فعلاً على `a0bba343`: «Gap registry measurement» تقريرٌ لا يحجب،
    فلو بقي الاكتشافُ فيه وحدَه لمرّ الصنفُ نفسُه مرّةً أخرى.
    """
    registry = tmp_path / "registry.md"
    registry.write_text("### DEEP-GAP-ENTRY-01\n\n- **الحالة:** open — نصّ\n", encoding="utf-8")
    code = guard.main(["--registry", str(registry), "--baseline", str(_BASELINE)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "gap_heading_state_guard_failed" in out
    assert "DEEP-GAP-ENTRY-01" in out
