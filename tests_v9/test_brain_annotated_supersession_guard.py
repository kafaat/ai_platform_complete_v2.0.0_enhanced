"""وسمُ `current`/`historical` يجب أن يكلّف شيئاً — وأن يبقى الصادقُ ممكناً.

`ANNOTATED-SUPERSESSION-CLOSES-A-GAP-WITHOUT-A-WITNESS-01`

نصفُ هذا الملفّ يمنع الخرق، ونصفُه يُثبِت أنّ **العلاجَ المشروع يمرّ**. والنصفُ
الثاني ليس زينةً: صنفُ «حارسٍ لا يقبل حالةً صادقة» أُغلِق في #1026 على شاهد المؤشّر،
حيث رفض الربطُ المنفرد `open` و`fixed` معاً عند إصلاحٍ جزئيّ — فلم يكن إيجابيّاً
كاذباً ولا سلبيّاً كاذباً بل **استحالة**. وهنا أخطرُ وجهٍ له: حارسٌ يطالب مدخلاً
أُعيد فتحُه بشاهدِ إغلاق، فيجعل **إعادةَ الفتح** مستحيلةً بعد أوّل وسم — أي يحرس
الاتّجاهَ المعاكسَ تماماً لما وُجِد له.

والبنيةُ عمداً على `findings()` النقيّة بنصٍّ في الذاكرة: فحصُ الشجرة الحيّة وحده
كان سيقيس **حالةً واحدة** (مجموعةٌ موسومةٌ واحدةٌ فيها خلافةٌ مُغلِقة على
`c3ebd6a7`)، ويبقى بقيّةُ جدول الصدق غيرَ مقيسٍ إلى أن يقع.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "scripts/ci/brain_annotated_supersession_guard.py"
MEASURE_PATH = ROOT / "scripts/ci/gap_registry_measure.py"


def _load(path: Path, name: str):
    """`spec_from_file_location` لا `sys.path.insert`.

    الإدراجُ في `sys.path` يُسرِّب `scripts/ci` إلى بقيّة الجناح فيلتقط استيرادٌ
    لاحقٌ وحدةً لم يقصدها — درسٌ مقيسٌ على شاهد بصمة نماذج الحافّة (#1022).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            del sys.modules[name]
        else:
            sys.modules[name] = previous
    return module


GUARD = _load(GUARD_PATH, "brain_annotated_supersession_guard")
MEASURE = _load(MEASURE_PATH, "gap_registry_measure_for_supersession_test").measure


def registry(current_state: str, historical_state: str, current_body: str = "") -> str:
    body = f"\n{current_body}\n" if current_body else "\n"
    return (
        "# سجلُّ الفجوات\n\n"
        "## GAP-A-01 — عنوانٌ واحد\n"
        "<!-- gap-registry: current -->\n\n"
        f"- **الحالة:** {current_state} — نصُّ المدخل الحاليّ.\n"
        f"{body}"
        "## GAP-A-01 — عنوانٌ واحد\n"
        "<!-- gap-registry: historical -->\n\n"
        f"- **الحالة:** {historical_state} — نصُّ الاكتشاف الأصليّ.\n"
    )


def run(text: str, *, tree: Path | None = None, wired: set[str] | None = None) -> list[str]:
    return GUARD.findings(text, tree or ROOT, wired if wired is not None else set(), MEASURE)


# ── ① الخرقُ يُمنَع ───────────────────────────────────────────────────────────


def test_an_annotated_closure_without_a_cited_witness_is_reported():
    """العطلُ بعينه: `open` يُوسَم تاريخيّاً و`fixed` يُوسَم حاليّاً، فتختفي الفجوة."""
    problems = run(registry("fixed", "open"))
    assert len(problems) == 1
    assert "GAP-A-01" in problems[0]
    assert "بلا شاهدٍ" in problems[0]


def test_citing_the_source_of_the_defect_is_not_citing_a_witness():
    """الاستشهادُ بالمصدر المُصلَح ليس شاهداً — وإلّا صار الثمنُ ذكرَ الملفّ المعطوب.

    مقيسٌ على الشجرة الحيّة: نزعُ ذكرِ ملفّ الشاهد من مدخل
    `GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01` يُحمِّر رغم بقاء ذكرِ
    `shared/ai/recommendation_runtime/flags.py` و`config/guardrail_feature_flags.py`.
    """
    problems = run(registry("fixed", "open", "- **المصدر:** `scripts/ci/preflight.sh`\n"))
    assert len(problems) == 1


def test_a_cited_path_that_does_not_exist_is_not_a_witness(tmp_path):
    problems = run(
        registry("fixed", "open", "- **الشاهد:** `tests_v9/test_never_written.py`\n"),
        tree=tmp_path,
    )
    assert len(problems) == 1


def test_a_wired_guard_that_is_gone_from_the_tree_is_not_a_witness(tmp_path):
    """طفرةٌ نجت فكشفت ثغرةً حقيقيّة، ولم تُستبدَل بطفرةٍ ألطف.

    نزعُ `is_file()` لم يُحمِّر شيئاً أوّلَ قياس: مسارُ الاختبار غيرُ الموجود كان
    يسقط في `read_text` فيُمسَك بـ`except OSError`. أي أنّ فحصَ الوجود كان
    **مُغطًّى صدفةً** على ذراع الاختبارات و**غيرَ مُغطًّى بتاتاً** على ذراع
    الحرّاس: اسمٌ ما زال مذكوراً في workflow لحارسٍ حُذِف ملفُّه كان سيُقبَل ثمناً
    لإغلاق — وهو بالضبط صنفُ «حارسٍ يبدو أنّه يحرس ولا يحرس» المسجَّل في
    `blocking_surface_baseline`.
    """
    text = registry("fixed", "open", "- **الشاهد:** `scripts/ci/deleted_guard.py`\n")
    assert len(run(text, tree=tmp_path, wired={"scripts/ci/deleted_guard.py"})) == 1


def test_an_empty_test_file_is_not_a_witness(tmp_path):
    """ثمنٌ يُدفَع بـ`touch` ثمنٌ صفريّ بخطوةٍ إضافيّة."""
    (tmp_path / "tests_v9").mkdir()
    (tmp_path / "tests_v9/test_hollow.py").write_text("# لا شيء\n", encoding="utf-8")
    problems = run(
        registry("fixed", "open", "- **الشاهد:** `tests_v9/test_hollow.py`\n"), tree=tmp_path
    )
    assert len(problems) == 1


def test_an_unwired_guard_script_is_not_a_witness(tmp_path):
    """حارسٌ لا تستدعيه workflow لا يحرس شيئاً، فلا يصلح ثمناً لإغلاق."""
    (tmp_path / "scripts/ci").mkdir(parents=True)
    (tmp_path / "scripts/ci/lonely_guard.py").write_text("print('ok')\n", encoding="utf-8")
    text = registry("fixed", "open", "- **الشاهد:** `scripts/ci/lonely_guard.py`\n")
    assert len(run(text, tree=tmp_path, wired=set())) == 1
    assert run(text, tree=tmp_path, wired={"scripts/ci/lonely_guard.py"}) == []


def test_an_unannotated_contradiction_is_reported():
    """البندُ ①: معرِّفٌ بحالتين بلا وسمِ تاريخ يحجب — أرضيّتُه الصفر على الشجرة."""
    text = (
        "# سجلُّ الفجوات\n\n"
        "## GAP-B-01\n\n- **الحالة:** fixed — أُغلِقت.\n\n"
        "## GAP-B-01\n\n- **الحالة:** open — مفتوحة.\n"
    )
    problems = run(text)
    assert len(problems) == 1
    assert "بلا وسمِ تاريخ" in problems[0]


# ── ② العلاجُ المشروع يمرّ — الشاهدُ الموجب ──────────────────────────────────


def test_a_closure_citing_a_real_witness_passes(tmp_path):
    """الشاهدُ الموجب: من أغلق بحقٍّ واستشهد بشاهده يمرّ."""
    (tmp_path / "tests_v9").mkdir()
    (tmp_path / "tests_v9/test_real.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert (
        run(
            registry("fixed", "open", "- **الشاهد:** `tests_v9/test_real.py`\n"),
            tree=tmp_path,
        )
        == []
    )


def test_a_markdown_link_target_counts_as_a_citation(tmp_path):
    """السجلّ يستشهد بالروابط النسبيّة `[..](../../path)` كما يستشهد بـ`code span`."""
    (tmp_path / "tests_v9").mkdir()
    (tmp_path / "tests_v9/test_real.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    body = "- **الشاهد:** [شاهدٌ](../../tests_v9/test_real.py)\n"
    assert run(registry("fixed", "open", body), tree=tmp_path) == []


@pytest.mark.parametrize(
    "current_state,historical_state",
    [
        ("open", "fixed"),  # إعادةُ فتح — لا يُطلَب لها شاهدُ إغلاق
        ("open", "open"),
        ("open", "verified"),
    ],
)
def test_a_reopening_is_never_asked_for_a_closure_witness(current_state, historical_state):
    """**الحالةُ التي تجعل الحارسَ مستحيلاً لو أُغفِلت.**

    مطالبةُ مدخلٍ `open` بشاهدِ إغلاقٍ تعني أنّ فجوةً وُسِمت مرّةً لا يمكن إعادةُ
    فتحها أبداً — وهو نقيضُ ما وُجِد له هذا الحارس.
    """
    assert run(registry(current_state, historical_state)) == []


def test_a_reviewed_group_with_no_state_lines_passes():
    """١٣ من ١٤ مجموعةٍ موسومةٍ على `c3ebd6a7` بلا سطرِ حالة — لا حالةَ تُخفى."""
    text = (
        "# سجلُّ الفجوات\n\n"
        "## GAP-C-01\n<!-- gap-registry: current -->\n\nنصٌّ بلا حالة.\n\n"
        "## GAP-C-01\n<!-- gap-registry: historical -->\n\nنصٌّ آخر.\n"
    )
    assert run(text) == []


def test_unannotated_duplicate_headings_stay_out_of_scope():
    """العناوينُ المكرّرةُ غيرُ الموسومة يبلّغها القياس؛ هذا الحارسُ لا يُضاعِف بلاغَها."""
    text = "# سجلُّ الفجوات\n\n## GAP-D-01\n\nنصّ.\n\n## GAP-D-01\n\nنصّ آخر.\n"
    assert run(text) == []


# ── ③ الوظيفةُ التي يعمل فيها لا تُثبِّت تبعيّةً واحدة ────────────────────────


def test_the_guard_runs_where_its_job_runs_without_any_dependency(tmp_path):
    """`GUARD-IMPORTS-A-DEPENDENCY-ITS-JOB-NEVER-INSTALLS-01` — مُعادُ إنتاجُه.

    أوّلُ نسخةٍ من هذا الحارس استوردت `guard_catalogue` لأنّه «القارئُ القائم»، وهو
    مبدأٌ صحيحٌ وكان **خاطئاً بالقياس**: ذلك الملفّ يستورد `PyYAML`، ووظيفةُ
    `no-report-only-change` لا تُثبِّت تبعيّةً واحدة. فسقط بـ`ModuleNotFoundError`
    في أوّل تشغيلٍ على CI بينما مرّ `preflight --fast` أخضرَ — لأنّ `PyYAML`
    مُثبَّتةٌ في بيئتي. **أخضرُ قِيس في كونٍ غيرِ المنشور.**

    والقياسُ هنا لا يقرأ الاستيرادات نصّاً: يُشغّل الحارسَ في عمليّةٍ فرعيّةٍ
    و`yaml` فيها **يرمي عند الاستيراد** — فلو عاد أيُّ مسارٍ يستورده، حُمِّر.
    """
    (tmp_path / "yaml.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8"
    )
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(GUARD_PATH)], capture_output=True, text=True, env=env, cwd=ROOT
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "brain_annotated_supersession_guard_ok" in result.stdout


def test_the_dependency_free_reader_never_narrows_the_yaml_one(tmp_path):
    """الحدُّ ضاق بصدق («مذكور» لا «مُستدعًى») — ولا يجوز أن يضيق عن القديم.

    قارئٌ أضيقُ من سابقه يرفض حارساً موصولاً بحقّ ⇒ **رفضٌ كاذبٌ لإغلاقٍ صحيح**.
    مقيسٌ على الشجرة: النصّيُّ ٢٨٦ واليمائيُّ ٢٧٤، والفرقُ في اتّجاهٍ واحد.
    """
    catalogue = _load(ROOT / "scripts/ci/guard_catalogue.py", "guard_catalogue_for_comparison")
    parsed = {g for site in catalogue.discover_invocation_sites() for g in site["guards"]}
    assert parsed - GUARD._wired_guards() == set()


# ── ④ الشجرةُ الحيّة ─────────────────────────────────────────────────────────


def test_the_live_registry_satisfies_both_clauses():
    """البندان يُدخَلان عند أرضيّتهما: الشجرةُ القائمة تمرّ بلا عملٍ مؤجَّل."""
    text = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    assert GUARD.findings(text, ROOT, GUARD._wired_guards(), MEASURE) == []


def test_the_live_tree_has_exactly_one_closing_supersession_to_pay_for():
    """رقمٌ مقيسٌ لا مظنون — ولو نما، نما معه ما يُدفَع ثمنُه."""
    text = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    report = MEASURE(text)
    closing = [
        gap_id
        for gap_id, entries in report["historical_state_variations"].items()
        if any(e["entry_role"] == "historical" and e["state"] == "open" for e in entries)
        and next((e for e in entries if e["entry_role"] == "current"), {}).get("state")
        in GUARD.CLOSING
    ]
    assert closing == ["GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"]
    assert report["contradictory_sections"] == {}
