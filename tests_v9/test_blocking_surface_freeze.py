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
    """`--enforce` يوجد ليُشغَّل يدويّاً — **ولا يمرّره أيُّ workflow لهذه الأداة**.

    فترقيةُ التجميد إلى الحجب تصير قراراً يُتَّخذ بقياسٍ لا بالنسيان.

    **والقياسُ بالتحليل لا بمطابقة سلسلة.** الصياغةُ الأولى بحثت عن
    `"--blocking-surface --enforce"` حرفيّاً بمسافةٍ واحدة، فكان يكفي شَرطةٌ مائلةٌ
    وسطرٌ جديدٌ بين العلمين لتمرّ:

        run: |
          python scripts/ci/guard_mutation_guard.py --blocking-surface \\
            --enforce

    أي **حارسٌ يبدو أنّه يحرس ولا يحرس** — وهو الصنفُ عينُه الذي وُجِدت هذه الشريحة
    لأجله، فوقع في اختبارها. (أصابت مراجعةٌ آليّة على #982.)

    ولا يُحظَر `--enforce` في الشجرة جملةً: `ci.yml` يمرّر `--enforce-expiry` لأداةٍ
    أخرى مشروعةٍ تماماً. فالمقيسُ **العلمُ في نداء هذه الأداة بعينها**.
    """
    import re

    import yaml

    assert "--enforce" in GUARD.read_text(encoding="utf-8")
    for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                body = str(step.get("run") or "")
                if not body:
                    continue
                # تُطوى وصلاتُ الأسطر ثمّ تُقسَّم الأوامر: العلمُ يُنسَب إلى نداءٍ لا إلى ملفّ.
                folded = re.sub(r"\\\s*\n\s*", " ", body)
                for command in re.split(r"[\n;&|]+", folded):
                    if "guard_mutation_guard.py" not in command:
                        continue
                    assert "--enforce" not in command.split(), (
                        f"{path.name} :: {job_name} يمرّر `--enforce` إلى تجميد سطح الحجب — "
                        "الترقيةُ إلى الحجب قرارٌ يُتَّخذ بقياسٍ لا بتعديل workflow"
                    )


def test_a_non_adjacent_enforce_flag_is_still_caught(tmp_path):
    """`--enforce` **غيرُ ملاصقٍ** لـ`--blocking-surface` يُمسَك أيضاً.

    اقترحت المراجعةُ الآليّة نمطاً يسمح بالفراغات والأسطر **بين العلمين**، وهو يُصلِح
    صياغةَ السطرين. لكنّه يشترط **التلاصق**، فيفلت منه:

        python scripts/ci/guard_mutation_guard.py --blocking-surface --shard 1/2 --enforce

    ولا شيءَ في الأداة يمنع علماً ثالثاً بينهما. فالمقيسُ ليس المسافةَ بين العلمين بل
    **أن يحمل نداءُ هذه الأداة العلمَ أصلاً** — ولذلك يُحلَّل الـYAML ويُقسَّم الأمر،
    ولا يُطابَق نصٌّ خام. وهذه الحالةُ هي ما يمنع الارتدادَ إلى النمط.
    """
    import re

    import yaml

    workflow = tmp_path / "escaped.yml"
    workflow.write_text(
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: python scripts/ci/guard_mutation_guard.py "
        "--blocking-surface --shard 1/2 --enforce\n",
        encoding="utf-8",
    )
    text = workflow.read_text(encoding="utf-8")

    adjacent_only = (
        r"(?s)--blocking-surface(?:[ \t\\\n]+)--enforce|--enforce(?:[ \t\\\n]+)--blocking-surface"
    )
    assert not re.search(adjacent_only, text), "النمطُ الملاصق لا يرى هذه الصياغة — وهو سببُ التحليل"

    caught = False
    document = yaml.safe_load(text) or {}
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            folded = re.sub(r"\\\s*\n\s*", " ", str(step.get("run") or ""))
            for command in re.split(r"[\n;&|]+", folded):
                if "guard_mutation_guard.py" in command and "--enforce" in command.split():
                    caught = True
    assert caught, "التحليلُ يجب أن يمسك ما يفلت من النمط"


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


def test_a_mutation_naming_an_unregistered_test_is_reported():
    """**المثالُ المضادّ:** إقرارٌ يسمّي تكذيباً لا وجودَ له يُبلَّغ عنه.

    كان `mutation` نثراً حرّاً لا يُقرأ إلّا بالعين: أوّلُ إقرارٍ كُتِب في هذا
    المستودع حمل جملةً تذكر اسمَ الاختبار **داخلها**، وكان الحقلُ سيقبل «طفرةٌ ما»
    بالقدر نفسِه. أي شرطٌ يُستوفى بالكتابة لا بالتسجيل — و«بوّابةٌ تُغلَق بالنثر»
    صنفٌ من «حارسٍ يبدو أنّه يحرس ولا يحرس».
    """
    declaration = dict(_COMPLETE, mutation="test_a_name_nobody_registered")
    problems = MOD.addition_violations(
        MOD.surface_key(_NEW),
        declaration,
        {"new_guard.py": {"test_the_registered_one"}},
    )
    assert len(problems) == 1
    assert "test_a_name_nobody_registered" in problems[0]
    assert "تكذيباً لا وجودَ له" in problems[0]


def test_a_mutation_naming_a_registered_test_passes():
    """**الشاهدُ الموجب:** الاسمُ المسجَّل يمرّ — وإلّا صار الحقلُ يرفض كلَّ إقرار."""
    declaration = dict(_COMPLETE, mutation="test_the_registered_one")
    assert (
        MOD.addition_violations(
            MOD.surface_key(_NEW),
            declaration,
            {"new_guard.py": {"test_the_registered_one"}},
        )
        == []
    )


def test_a_registered_test_of_another_guard_is_not_this_guard_s_proof():
    """التسجيلُ **لهذا الحارس بعينه** — لا «موجودٌ في السجلّ في مكانٍ ما».

    وإلّا كفى أن يُستعار اسمُ اختبارٍ يُكذِّب حارساً آخر، فيصير الإقرارُ صحيحَ
    الشكل ولا يُكذِّب شيئاً ممّا يُقرّه.
    """
    declaration = dict(_COMPLETE, mutation="test_belongs_to_someone_else")
    problems = MOD.addition_violations(
        MOD.surface_key(_NEW),
        declaration,
        {"other_guard.py": {"test_belongs_to_someone_else"}},
    )
    assert len(problems) == 1
    assert "new_guard.py" in problems[0]


def test_the_registry_reader_reads_the_expected_test_not_the_suite_file():
    """`expect` اسمُ الحالة · `test` ملفُّ الجناح — وخلطُهما يقلب الفحصَ كاذباً.

    قرأتُ `mutation_test` أوّلَ مرّة (وهو يُعيد **ملفَّ** الجناح) فأبلغ الفحصُ عن
    طفرةٍ **مسجَّلةٍ** بأنّها غيرُ مسجَّلة. كشفه تشغيلٌ لا قراءة، فيُثبَّت هنا.
    """
    registry = {
        "mutated": {
            "some_guard.py": {
                "test": "tests_v9/test_some_guard.py",
                "mutations": [{"expect": "test_the_case_name", "find": "x", "replace": "y"}],
            }
        }
    }
    assert MOD.registered_mutation_tests(registry) == {"some_guard.py": {"test_the_case_name"}}


def test_the_live_declaration_names_a_registered_mutation_test():
    """الإقرارُ الحيُّ الوحيد يجتاز الفحصَ الجديد بسجلّ الطفرات الحقيقيّ."""
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8"))["additions"]
    key = "scripts/ci/guard_mutation_guard.py::capability-governance.yml::blocking-surface-advisory"
    known = MOD.registered_mutation_tests(MOD.load_registry())
    assert MOD.addition_violations(key, additions[key], known) == []


def test_the_baseline_is_frozen_at_the_current_merge_base():
    """خطُّ التجميد قاعدةُ الطلب — لا لقطةٌ أُخِذت قبل عملٍ آخر ثمّ بقيت.

    قِيس الأساسُ أوّلاً على `912ad691`، ثمّ دُمِج #979 فزاد السطحُ ستَّ ثلاثيّات.
    ولقطةٌ بائتةٌ كانت ستُبلِّغ عنها بوصفها «زيادةً بعد التجميد» وهي سابقةٌ له —
    وهو بعينه صنفُ «تعريفان لحاجةٍ واحدة، أحدُهما ساقط».
    """
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["measured_on"] == baseline["frozen_at_sha"]
    assert len(baseline["frozen_at_sha"]) == 40
    live = {MOD.surface_key(t) for t in MOD.discover_blocking_surface()}
    declared = set(MOD._load_surface_json(ADDITIONS, "additions"))
    frozen = set(MOD._load_surface_json(BASELINE, "legacy_blocking"))
    assert live - frozen - declared == set(), "الأساسُ لا يغطّي السطحَ الحيّ — أعِد التجميد"


_RETIRED_OK = {"reason": "نُقِل الحارس إلى وظيفةٍ أنسب في #123", "retired_on": "2026-09-05"}


def test_a_blocker_that_vanished_is_reported():
    """**المثالُ المضادّ — مقيسٌ لا مُتوقَّع.**

    على `main @ a3124ccf` نُزِع سطرٌ واحد (استدعاءُ
    `vegetation_runtime_truth_guard.py` من `ci.yml`) فهبط السطحُ ٣٠١ ⇒ ٣٠٠. ولم
    يشتكِ إلّا فحصُ انحراف الكتالوج — **وعلاجُه المنصوصُ عليه إعادةُ التوليد**،
    فإذا فُعِل قال الاثنان `guard_catalogue_ok` و`blocking_surface_ok`. أي أنّ
    **العلاجَ الذي يأمر به النظامُ هو ما يمحو الدليل**، ويبقى ملفُّ الحارس في مكانه
    يبدو حمايةً ولا يُشغّله شيء.
    """
    findings = MOD.blocking_surface_findings(set(), _BASELINE, {})
    assert len(findings) == 1
    assert MOD.surface_key(_OLD) in findings[0]
    assert "تقاعد" in findings[0]


def test_a_declared_retirement_passes():
    """**الشاهدُ الموجب:** التقاعدُ المنطوق يمرّ — فالحذفُ لا يُمنَع، يُقال.

    بدونه يصير التجميدُ يفرض بقاءَ كلّ حاجبٍ إلى الأبد، فيُعاقِب التضييقَ المشروع
    ويُدرِّب الناسَ على الالتفاف عليه.
    """
    retired = {MOD.surface_key(_OLD): _RETIRED_OK}
    assert MOD.blocking_surface_findings(set(), _BASELINE, {}, None, retired) == []


@pytest.mark.parametrize("missing", ["reason", "retired_on"])
def test_a_retirement_without_reason_or_date_is_not_a_declaration(missing):
    """سببٌ وتاريخ — وإلّا فهو حذفٌ ارتدى اسمَ الإقرار."""
    incomplete = {k: v for k, v in _RETIRED_OK.items() if k != missing}
    retired = {MOD.surface_key(_OLD): incomplete}
    findings = MOD.blocking_surface_findings(set(), _BASELINE, {}, None, retired)
    assert len(findings) == 1
    assert missing in findings[0]


def test_a_retirement_declared_for_a_blocker_still_running_is_reported():
    """سجلٌّ يقول «تقاعد» عن حاجبٍ يعمل يكذب في الاتّجاه المعاكس.

    ولو أُهمِل لصار بابَ إسكاتٍ دائم: يُعلَن التقاعدُ اليومَ ويُعاد الاستدعاءُ غداً،
    فلا يُبلَّغ عن شيء.
    """
    retired = {MOD.surface_key(_OLD): _RETIRED_OK}
    findings = MOD.blocking_surface_findings({_OLD}, _BASELINE, {}, None, retired)
    assert len(findings) == 1
    assert "ما زال يعمل" in findings[0]


def test_a_vanished_addition_is_reported_once_not_twice():
    """حقيقةٌ واحدة ⇒ ملاحظةٌ واحدة.

    أوّلُ صياغةٍ للاتّجاه الرابع شملت الإقراراتِ مع الأساس، فصار الإقرارُ الزائل
    يُبلَّغ **مرّتين**: «إقرارٌ لزيادةٍ لا وجودَ لها» و«حاجبٌ زال بلا إقرار تقاعد».
    وسجلٌّ يقول الشيءَ مرّتين يُدرِّب قارئَه على تخطّيه — وهو الصنفُ الذي تُغلقه هذه
    الآليّة نفسُها. وعلاجُ الإقرار الزائل حذفُه، لا كتابةُ تقاعدٍ له.
    """
    key = MOD.surface_key(_NEW)
    findings = MOD.blocking_surface_findings({_OLD}, _BASELINE, {key: _COMPLETE})
    assert len(findings) == 1, findings
    assert "لا وجودَ لها" in findings[0]


def test_the_live_tree_has_no_unspoken_retirement():
    """الشجرةُ الحيّةُ لا تقاعدَ فيها اليوم — وهذا ما يجعل أوّلَ نزعٍ قادمٍ مرئيّاً."""
    findings = MOD.blocking_surface_findings(
        MOD.discover_blocking_surface(),
        MOD._load_surface_json(BASELINE, "legacy_blocking"),
        MOD._load_surface_json(ADDITIONS, "additions"),
        MOD.registered_mutation_tests(MOD.load_registry()),
        MOD._load_surface_json(BASELINE, "retired"),
    )
    assert findings == [], findings


def test_a_retirement_for_a_triple_never_in_the_baseline_is_reported():
    """**أصابت مراجعةٌ آليّة على #983:** `retired` كان يقبل أيّ مفتاح.

    فتتراكم فيه أسماءٌ يتيمةٌ لا تخصّ ثلاثيّةً كانت في الأساس قطّ — سجلٌّ يبدو
    نظيفاً وهو يحمل ما لا وجودَ له. **وهو الصنفُ نفسُه** الذي أُغلِق للإقرارات في
    الاتّجاه الثالث، ولم يكن مُغلَقاً للتقاعد.
    """
    orphan = "scripts/ci/never_existed_guard.py::ci.yml::structural-lint"
    findings = MOD.blocking_surface_findings({_OLD}, _BASELINE, {}, None, {orphan: _RETIRED_OK})
    assert len(findings) == 1, findings
    assert orphan in findings[0]
    assert "لم تكن في الأساس" in findings[0]


def test_a_retirement_for_a_live_orphan_is_reported_once_not_twice():
    """حقيقةٌ واحدة ⇒ ملاحظةٌ واحدة — و«ما زال يعمل» أدقُّ من «لم تكن في الأساس».

    مفتاحٌ يتيمٌ **وحيٌّ** يستوفي الشرطين معاً؛ ولو لم يُستثنَ الحيُّ من فحص اليُتم
    لقيلت الحقيقةُ مرّتين، وهو ما تُغلقه هذه الآليّةُ نفسُها في موضعين قبله.
    """
    key = MOD.surface_key(_NEW)
    findings = MOD.blocking_surface_findings({_OLD, _NEW}, _BASELINE, {}, None, {key: _RETIRED_OK})
    # يبقى `_NEW` زيادةً بلا إقرار — حقيقةٌ **أخرى** صحيحة، لا تكرارٌ لهذه. والمقيسُ
    # هنا أنّ اليُتمَ لا يُقال عن مفتاحٍ حيّ، لأنّ «ما زال يعمل» أدقُّ منه ويصفه.
    about_key = [f for f in findings if key in f]
    assert sum("ما زال يعمل" in f for f in about_key) == 1, findings
    assert not any("لم تكن في الأساس" in f for f in about_key), findings
