"""تجميدُ سطح الحجب — BLOCKING-SURFACE-GROWS-FASTER-THAN-IT-IS-PROVEN-01.

**العطلُ مقيسٌ لا مظنون** (على `main @ 912ad691`): **٢٩٦ ثلاثيّةَ حجبٍ** من **٢٦٧
حارساً**، و**٤٨** منها فقط له مواصفةُ طفرةٍ مسجَّلة. أي أنّ **٢١٩ حارساً يحجب الدمج
ولم يُقَس قطّ أنّه يفشل حين يوجد العطل**. والحارسُ يُضاف لأنّه يبدو صواباً، لا لأنّ
عطلاً وقع — فينمو السطحُ أسرعَ ممّا يُثبَت، ويصير الأخضرُ ثمناً يُدفَع لا معلومةً تُقرأ.

**والاتّجاه المقابل وقع ثلاثَ مرّاتٍ في يومٍ واحد** قبل هذا التجميد: حارسٌ يمنع
العلاجَ الذي يطلبه حارسٌ آخر · اختبارٌ يُثبِّت صلاحيّةً زائدةً **شرطاً** · واختبارٌ
يفرض بقاءَ لقطةٍ عدديّةٍ بائتة. ولذلك **الشاهدُ الموجب** خاصّيّةٌ أولى هنا لا زينة:
لا يكفي أن يُمنَع الخرق، بل يجب أن يمرّ **العلاجُ المشروع**.

**وهذه الحالاتُ تقيس دالّةً نقيّة** (`blocking_surface_findings`) بلا ملفّاتٍ ولا
workflows — فالقاعدةُ تُختبَر بمعزلٍ عن جرد الشجرة الذي يتغيّر كلَّ يوم.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "ci" / "guard_mutation_guard.py"
WORKFLOW = ROOT / ".github" / "workflows" / "capability-governance.yml"
ADDITIONS = ROOT / "docs" / "architecture" / "blocking_surface_additions.json"
BASELINE = ROOT / "docs" / "architecture" / "blocking_surface_baseline.json"


def _mod():
    spec = importlib.util.spec_from_file_location("_gmg_surface", GUARD)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gmg_surface"] = module
    spec.loader.exec_module(module)
    return module


MOD = _mod()

_NEW = ("scripts/ci/new_guard.py", "ci.yml", "structural-lint")
_OLD = ("scripts/ci/old_guard.py", "ci.yml", "structural-lint")
_BASELINE = {MOD.surface_key(_OLD): "legacy_blocking"}
_COMPLETE = {
    "counterexample": "وقع في #123 عند `abc1234` — ملفٌّ كذا حمل كذا.",
    "mutation": "guard_mutation_registry.json :: new_guard — يقتلها test_x",
    "positive_witness": "test_the_legitimate_remedy_passes",
    "impact": "merge",
}


def test_an_undeclared_addition_is_reported():
    """زيادةٌ بلا إقرار ⇒ ملاحظة تُسمّي الثلاثيّة.

    هذه هي الحالةُ التي تُكذِّب الآليّة: لو مرّت زيادةٌ صامتةً لكان التجميدُ اسماً بلا
    قياس — وهو بالضبط صنفُ «الحارس الذي لا يرى العطل أصلاً» الذي وُجِد
    `guard_mutation_guard` لأجله.
    """
    findings = MOD.blocking_surface_findings({_OLD, _NEW}, _BASELINE, {})
    assert len(findings) == 1
    assert MOD.surface_key(_NEW) in findings[0]
    assert "بلا إقرار" in findings[0]


def test_a_fully_declared_addition_passes():
    """**الشاهدُ الموجب:** زيادةٌ تحمل الخصائصَ الأربع تمرّ بلا ملاحظة.

    بدونه يمرّ فحصٌ يرفض **كلّ** زيادةٍ بما فيها المشروعة — وذاك ليس تجميداً بل
    منعاً، ويُلتَفّ عليه في أوّل ضغط.
    """
    assert (
        MOD.blocking_surface_findings({_OLD, _NEW}, _BASELINE, {MOD.surface_key(_NEW): _COMPLETE})
        == []
    )


def test_the_frozen_baseline_itself_raises_nothing():
    """`legacy_blocking` **مُتوارَثٌ لا مُثبَت** — ولا يُطالَب بأثرٍ رجعيّ.

    التجميدُ يمنع النموّ، ولا يُقلّم الموجود، ولا يُخفّفه آليّاً.
    """
    assert MOD.blocking_surface_findings({_OLD}, _BASELINE, {}) == []


@pytest.mark.parametrize("missing", ["counterexample", "mutation", "positive_witness", "impact"])
def test_a_declaration_missing_any_one_property_is_reported(missing):
    """الأربعُ مطلوبةٌ **كلٌّ على حدة** — لا «ثلاثٌ تكفي»."""
    partial = {k: v for k, v in _COMPLETE.items() if k != missing}
    findings = MOD.blocking_surface_findings(
        {_OLD, _NEW}, _BASELINE, {MOD.surface_key(_NEW): partial}
    )
    assert any(missing in f for f in findings), findings


def test_an_empty_property_is_not_a_property():
    """حقلٌ حاضرٌ بقيمةٍ فارغة **ليس إقراراً** — وإلّا صار الملءُ الشكليّ كافياً."""
    hollow = {**_COMPLETE, "counterexample": "   "}
    findings = MOD.blocking_surface_findings(
        {_OLD, _NEW}, _BASELINE, {MOD.surface_key(_NEW): hollow}
    )
    assert any("counterexample" in f for f in findings), findings


def test_an_unknown_impact_placement_is_reported():
    """`impact` يجب أن يقول **أين** يحجب — قيمةٌ غيرُ معروفةٍ تُخفي السؤال."""
    findings = MOD.blocking_surface_findings(
        {_OLD, _NEW}, _BASELINE, {MOD.surface_key(_NEW): {**_COMPLETE, "impact": "somewhere"}}
    )
    assert any("impact" in f for f in findings), findings


def test_a_declaration_for_a_vanished_addition_is_reported():
    """إقرارٌ لزيادةٍ زالت ⇒ ملاحظة.

    الاتّجاهُ الثالث مقصود: سجلٌّ يحمل ما لا وجودَ له يُدرِّب قارئَه على تجاهله، وهو
    كيف يصير السجلُّ زينةً.
    """
    findings = MOD.blocking_surface_findings({_OLD}, _BASELINE, {MOD.surface_key(_NEW): _COMPLETE})
    assert len(findings) == 1
    assert "لا وجودَ لها" in findings[0]


def test_the_advisory_report_returns_zero_even_with_findings(capsys, monkeypatch):
    """**إرشاديٌّ يعني إرشاديّ:** ملاحظاتٌ موجودة والخروجُ 0.

    ولو أُعيد 1 هنا لصار التجميدُ حاجباً قبل أن يُكذَّب هو نفسُه — وهو ما تمنعه
    السياسةُ التي يقيسها، فيكون أوّلَ مَن يخرقها.
    """
    monkeypatch.setattr(MOD, "discover_blocking_surface", lambda: {_OLD, _NEW})
    monkeypatch.setattr(
        MOD, "_load_surface_json", lambda path, key: _BASELINE if "baseline" in path.name else {}
    )
    assert MOD.report_blocking_surface() == 0
    assert "إرشاديّ" in capsys.readouterr().out


def test_enforce_is_available_but_not_wired_into_any_workflow():
    """`--enforce` يوجد ليُشغَّل يدويّاً — **ولا يمرّره أيُّ workflow**.

    فترقيةُ التجميد إلى الحجب تصير قراراً يُتَّخذ بقياسٍ لا بالنسيان.
    """
    assert "--enforce" in GUARD.read_text(encoding="utf-8")
    for path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        text = path.read_text(encoding="utf-8")
        assert "--blocking-surface --enforce" not in text, path.name
        assert "--enforce --blocking-surface" not in text, path.name


def test_the_advisory_job_does_not_lean_on_continue_on_error():
    """الإرشاديّةُ خاصّيّةُ **الأداة** لا خاصّيّةُ الـworkflow.

    لو اعتُمِد `continue-on-error` لصارت الترقيةُ تقع **بالصدفة** يومَ يُنزَع السطر،
    بلا قرارٍ ولا قياس. والأداةُ تُعيد 0 بنفسها، وذلك مُختبَرٌ أعلاه.
    """
    import yaml

    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["blocking-surface-advisory"]
    assert job.get("continue-on-error") is None
    steps = [s for s in job["steps"] if "--blocking-surface" in str(s.get("run", ""))]
    assert len(steps) == 1, "خطوةُ القياس مفقودةٌ أو مكرّرة"
    assert steps[0].get("continue-on-error") is None


def test_the_mechanism_declares_its_own_addition():
    """الآليّةُ تُقرّ نفسَها — وإلّا كانت سياسةً تُطالِب غيرَها بما لا تلتزمه.

    إدخالُ الوظيفة الإرشاديّة **زيادةٌ في سطح الاستدعاء** كغيرها، فيجب أن تحمل
    الخصائصَ الأربع وأن يكون تصنيفُها `advisory` صدقاً لا تحايلاً.
    """
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8"))["additions"]
    key = "scripts/ci/guard_mutation_guard.py::capability-governance.yml::blocking-surface-advisory"
    assert key in additions, "الآليّةُ لم تُقرّ إدخالَ نفسِها"
    assert MOD.addition_violations(key, additions[key]) == []
    assert additions[key]["impact"] == "advisory"


def test_the_live_tree_has_no_undeclared_addition():
    """الشجرةُ الحيّةُ نظيفةٌ الآن — وهذا ما يجعل أوّلَ زيادةٍ قادمةٍ مرئيّة."""
    findings = MOD.blocking_surface_findings(
        MOD.discover_blocking_surface(),
        MOD._load_surface_json(BASELINE, "legacy_blocking"),
        MOD._load_surface_json(ADDITIONS, "additions"),
    )
    assert findings == [], findings


def test_the_surface_is_derived_from_the_catalogue_not_a_second_model():
    """مصدرٌ واحدٌ للاشتقاق — `guard_catalogue.discover_invocations`.

    نموذجان لسطحٍ واحد ينحرفان، وهو الصنفُ الذي أُغلِق في هذه الشجرة مراراً (جدولا
    وجهةِ القاعدة · قائمتا الحواجز · أعدادُ الكتالوج المنقولة).
    """
    source = GUARD.read_text(encoding="utf-8")
    body = source[
        source.index("def discover_blocking_surface") : source.index("def _load_surface_json")
    ]
    assert "guard_catalogue.py" in body
    assert "discover_invocations" in body
    assert "python3?\\s+(scripts/ci/" not in source, (
        "نمطُ التقاط `python scripts/ci/…` يخصّ `guard_catalogue` وحدَه. نسخُه هنا يُنشِئ "
        "**نموذجاً ثانياً** لسطحٍ واحد: يتّفقان اليوم وينحرفان غداً، فيقيس التجميدُ سطحاً "
        "غيرَ الذي يولّده الكتالوج — وهو الصنفُ الذي أُغلِق في هذه الشجرة مراراً."
    )
