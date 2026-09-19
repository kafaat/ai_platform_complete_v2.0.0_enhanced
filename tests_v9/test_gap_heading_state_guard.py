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
