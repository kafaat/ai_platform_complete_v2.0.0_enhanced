"""`A-RATCHET-CLEARED-BY-DELETING-WHAT-IT-MEASURES-01` — شواهدُ الحارس.

الحارسُ يمنع طريقاً واحداً: إنزالَ عدّاد مخالفات ملكيّة الكتابة بإضافة الخدمة
المخالِفة إلى `writers` بدل نقلِ الكتابة — وهو ما يمحو هدفَ الاستخراج الذي كان
العدّادُ يقيس المسافةَ إليه.

وهذه الشواهدُ لا تُعيد فحصَ ما يفحصه، بل تحرس **دلالتَه**: أنّ النطاقَ مشتقٌّ من
خريطةٍ حيّة لا من قائمةٍ مكتوبة، وأنّ الاستثناءَ الموثَّقَ يبقى مسموحاً، وأنّ بابَ
التقاعد المشروع يبقى مفتوحاً.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "ownership_extraction_alignment_guard.py"

_SPEC = importlib.util.spec_from_file_location("ownership_extraction_alignment_guard", SCRIPT)
guard = importlib.util.module_from_spec(_SPEC)
sys.modules["ownership_extraction_alignment_guard"] = guard
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)


def _contract(**tables) -> dict:
    """عقدٌ مُختلَق — الحشوُ يُرضي شرطَ القراءة (≥١٠٠) ولا يُدخِل حافّةً في المقيس."""
    out = dict(tables)
    for index in range(150):
        out[f"filler_{index}"] = {"owner": "nobody", "writers": ["nobody"]}
    return out


def test_the_tree_holds_the_floor_today():
    """أرضيّةُ صفرٍ حقيقيّة لا راتشِتٌ بدَين — وإلّا دُرِّب قارئُها على تجاوزها."""
    assert guard.main() == 0


def test_an_extra_declared_writer_on_a_live_target_is_refused():
    """**الطريقُ الذي يدعو إليه نصُّ الأساس نفسُه.**

    «يُخفَّض … أو بتصحيح العقد» — فمن أراد إنزالَ العدّاد بلا نقلِ سطرٍ أضاف المخالِفَ
    إلى `writers`. المقيسُ أنّ ٧٤/٧٤ من المخالفات مالكُها هدفُ استخراجٍ حيّ، فهذا
    «التصحيح» يمحو الهدفَ ويُبقي الشيفرةَ كما هي.
    """
    contract = _contract(
        farm_energy_records={
            "owner": "field-management-service",
            "writers": ["field-management-service"],
        }
    )
    targets = {"field-management-service"}
    assert guard.findings(contract, targets) == []

    contract["farm_energy_records"]["writers"].append("sahool-platform")
    problems = guard.findings(contract, targets)
    assert len(problems) == 1
    assert "farm_energy_records" in problems[0]
    assert "sahool-platform" in problems[0]


def test_retiring_the_target_reopens_the_correction():
    """**القرارُ يبقى ممكناً، والصمتُ يصير مستحيلاً.**

    الحارسُ لا يُجمِّد العقد: إن سقط المالكُ من أهداف الخريطة — أي تقاعد الهدفُ فعلاً
    في التغيير نفسِه — خرج الجدولُ من النطاق وصار التصحيحُ مشروعاً. بلا هذا يصير
    الحارسُ «بوّابةً لا تُغلَق بعملٍ صحيح».
    """
    contract = _contract(
        farm_energy_records={
            "owner": "field-management-service",
            "writers": ["field-management-service", "sahool-platform"],
        }
    )
    assert guard.findings(contract, {"field-management-service"})
    assert guard.findings(contract, {"weather-service"}) == []


def test_the_documented_interim_bridge_stays_allowed():
    """خلطُ الاستثناء الموثَّق بالانحراف يُنذِر كذباً، فيموت الحارسُ وهو أخضر.

    `mirror` جسرٌ انتقاليٌّ يحترمه `db_writer_ownership_guard` بالفعل؛ وحارسان
    يختلفان في الاستثناء نفسِه يُنتِجان حكمين عن سؤالٍ واحد.
    """
    contract = _contract(
        bridged={
            "owner": "field-management-service",
            "writers": ["field-management-service", "sahool-platform"],
            "mirror": "sahool-platform",
        }
    )
    assert guard.findings(contract, {"field-management-service"}) == []


def test_a_table_outside_the_extraction_scope_is_not_judged():
    """النطاقُ مشتقٌّ من الخريطة لا مفروضٌ على كلّ جدول — ٩ جداولَ اليوم خارجَه."""
    contract = _contract(shared_ref={"owner": "nobody-special", "writers": ["nobody-special", "x"]})
    assert guard.findings(contract, {"field-management-service"}) == []


def test_an_unreadable_contract_fails_loudly_instead_of_passing_empty(tmp_path):
    """حارسٌ يمرّ صفراً كاذباً أسوأُ من غيابه — يُقرَأ ضماناً ويُسجَّل تغطية."""
    bad = tmp_path / "db_ownership.yml"
    bad.write_text("tables:\n  only_one:\n    owner: x\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        guard.load_contract(bad)
    assert "OWNERSHIP_CONTRACT_UNREADABLE" in str(excinfo.value)


def test_an_empty_extraction_map_fails_closed_not_open(tmp_path):
    """خريطةٌ بلا أهدافٍ تجعل النطاقَ خالياً فيمرّ الحارسُ على كلّ شيء.

    وذاك أخطرُ من غيابه: يُبلِغ خُضرةً عن سؤالٍ لم يُطرَح. فيفشل مُغلَقاً.
    """
    empty = tmp_path / "platform_extraction_map.json"
    empty.write_text(json.dumps({"routes": []}), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        guard.live_targets(empty)
    assert "EXTRACTION_MAP_UNREADABLE" in str(excinfo.value)


def test_the_scope_is_derived_from_the_shipped_map_not_a_written_list():
    """قائمةٌ مكتوبةٌ في الحارس تبيت يومَ يتغيّر هدف — المصدرُ هو الخريطةُ المُسلَّمة."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "platform_extraction_map.json" in source
    targets = guard.live_targets()
    assert "field-management-service" in targets, "الخريطةُ المُسلَّمة فقدت هدفاً يفترضه العقد"
    for name in sorted(targets):
        assert f'"{name}"' not in source, f"هدفٌ مكتوبٌ بيدٍ في الحارس: {name}"


def test_the_guard_does_not_claim_to_reduce_the_violations():
    """حدُّ الحارس مُعلَنٌ في نصّه: لا يُنقِص الـ٧٤ — إنقاصُها يحتاج نقلَ الكتابة.

    وحارسٌ يُقرأ أوسعَ ممّا يفعل يُسجَّل تغطيةً لا يملكها.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ما لا يدّعيه هذا الحارس" in source
    assert "نقلَ الكتابة" in source
