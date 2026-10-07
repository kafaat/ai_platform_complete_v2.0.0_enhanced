from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def mod():
    path = ROOT / "scripts/ci/gap_registry_measure.py"
    spec = importlib.util.spec_from_file_location("gap_registry_measure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_measure_does_not_guess_noncanonical_states():
    report = mod().measure(
        "| ID | Detail | Status |\n| --- | --- | --- |\n"
        "| GAP-A-01 | x | **open — detail** |\n| GAP-B-01 | x | **BLOCKED_BY_ENVIRONMENT** |"
    )
    assert report["row_state_counts"] == {"open": 1, "unclassified": 1}
    assert report["unclassified_rows"][0]["id"] == "GAP-B-01"


def test_measure_reports_nonadjacent_duplicate_headings():
    report = mod().measure(
        "## GAP-A-01 — first\n\n"
        "- **الحالة:** fixed\n"
        "text\n"
        "## GAP-A-01 — second\n\n"
        "- **الحالة:** open\n"
    )
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [1, 5]}


def test_measure_keeps_gap_rows_with_label_suffixes():
    report = mod().measure(
        "| ID | Detail | Status |\n| --- | --- | --- |\n"
        "| HYBRID-FUSION-SCORE-NORMALIZATION-01 (B1a) | x | **open** |\n"
        "| DIRECT-VS-CANONICAL-DENSE-SEMANTICS-01 (B1b) | x | **fixed** |"
    )
    assert report["row_count"] == 2
    assert [row["id"] for row in report["unclassified_rows"]] == []
    assert report["row_state_counts"] == {"fixed": 1, "open": 1}


def test_measure_reports_contradictory_section_states_by_gap_id():
    report = mod().measure(
        "## GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01 — first\n\n"
        "- **الحالة:** fixed\n"
        "historical detail\n"
        "## GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01 — second\n\n"
        "- **الحالة:** open\n"
    )
    conflicts = report["contradictory_sections"]["GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"]
    assert [item["state"] for item in conflicts] == ["fixed", "open"]
    assert [item["id"] for item in conflicts] == [
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
    ]


def test_status_column_and_quoted_history_do_not_manufacture_a_closure():
    report = mod().measure(
        "| ID | Status | Evidence |\n| --- | --- | --- |\n"
        "| H4 | **open** — HTTP_PENDING | `float | None` |\n"
        "| APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01 | "
        "implemented / pending final CI; original row: GAP-X \\| **fixed** | #987 |\n"
    )
    assert report["row_state_counts"] == {"open": 1, "unclassified": 1}
    assert report["table_structure_errors"] == []
    pending = report["unclassified_rows"][0]
    assert pending["id"] == "APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01"
    assert pending["raw_state"].startswith("implemented / pending final CI")


def test_cells_preserve_escaped_pipes_and_exact_matching_code_spans():
    assert mod().table_cells(r"| GAP-X | a\|b | ``a`|b`` and `x|y` | open |") == [
        "GAP-X",
        r"a\|b",
        "``a`|b`` and `x|y`",
        "open",
    ]
    assert mod().table_cells("| GAP-X | unmatched ` | fixed |") == ["GAP-X", "unmatched `", "fixed"]


def test_complete_ids_and_qualifiers_keep_their_original_case():
    report = mod().measure(
        "| ID | Status |\n| --- | --- |\n"
        "| CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01 | pending |\n"
        "| SAM2 | pending |\n| H5.1-BINDING-INTEGRITY | pending |\n"
        "## CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01\n"
        "- **status:** unknown\n"
    )
    assert [row["id"] for row in report["unclassified_rows"]] == [
        "CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01",
        "SAM2",
        "H5.1-BINDING-INTEGRITY",
    ]
    assert report["unclassified_section_states"][0]["id"].endswith("generated-DIRS-01")
    assert mod().classify("**OPEN** — PG_PENDING / #ABC") == ("open", "PG_PENDING / #ABC")


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fenced_examples_and_unrelated_sections_do_not_change_gap_states(fence):
    report = mod().measure(
        "## GAP-A-01\n- **status:** fixed\n"
        f"{fence}markdown\n"
        "## GAP-A-01\n- **status:** open\n"
        "| GAP-X | missing header |\n"
        f"{fence}\n"
        "## Notes\n- **status:** pending\n"
    )
    assert report["heading_count"] == 1
    assert report["row_count"] == 0
    assert report["section_state_count"] == 1
    assert report["contradictory_sections"] == {}
    assert report["unscoped_section_states"][0]["id"] is None


def test_broken_tables_remain_findings_instead_of_guessing_the_last_cell():
    report = mod().measure(
        "| GAP-X | evidence | fixed |\n\n"
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-Y | pending | fixed |\n\n"
        "| ID | Status | Status |\n| --- | --- | --- |\n"
        "| GAP-Z | open | fixed |\n"
    )
    assert report["row_state_counts"] == {"unclassified": 3}
    assert [item["reason"] for item in report["table_structure_errors"]] == [
        "missing_table_header",
        "invalid_table_shape",
        "invalid_table_shape",
    ]


def test_alias_maps_are_visible_but_are_not_state_tables():
    report = mod().measure("| ID | Replacement |\n| --- | --- |\n| GAP-A-01 | GAP-B-01 |\n")
    assert report["row_count"] == 0
    assert report["non_state_table_rows"][0]["id"] == "GAP-A-01"


def test_explicit_non_state_records_keep_their_evidence_separate():
    report = mod().measure(
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-A-01 | <!-- gap-registry: alias --> see GAP-B-01 |\n"
        "| SAM2 | <!-- gap-registry: policy --> by-design |\n"
        "| GAP-C-01 | <!-- gap-registry: adjudicated --> not a defect (#997) |\n"
        "| GAP-D-01 | by-design |\n"
        "## GAP-A-01\n- **status:** <!-- gap-registry: alias --> see GAP-B-01\n"
    )
    assert report["row_count"] == 4
    assert report["gap_row_count"] == 1
    assert report["row_state_counts"] == {"unclassified": 1}
    assert report["non_state_row_counts"] == {"adjudicated": 1, "alias": 1, "policy": 1}
    assert "#997" in report["non_state_rows"][2]["raw_state"]
    assert report["non_state_section_states"][0]["kind"] == "alias"


def test_reviewed_history_remains_visible_without_becoming_a_current_conflict():
    report = mod().measure(
        "## GAP-A-01 — resolved\n<!-- gap-registry: current -->\n- **status:** fixed\n"
        "## GAP-A-01 — original finding\n<!-- gap-registry: historical -->\n- **status:** open\n"
    )
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [1, 4]}
    assert report["unreviewed_duplicate_heading_ids"] == {}
    assert report["contradictory_sections"] == {}
    assert [s["state"] for s in report["historical_state_variations"]["GAP-A-01"]] == [
        "fixed",
        "open",
    ]


@pytest.mark.parametrize(
    "first,second", [("current", "current"), ("historical", "historical"), ("current", None)]
)
def test_incomplete_or_ambiguous_history_review_cannot_hide_a_conflict(first, second):
    annotation = f"<!-- gap-registry: {second} -->\n" if second else ""
    report = mod().measure(
        f"## GAP-A-01\n<!-- gap-registry: {first} -->\n- **status:** fixed\n"
        f"## GAP-A-01\n{annotation}- **status:** open\n"
    )
    assert report["reviewed_heading_sequences"] == {}
    assert "GAP-A-01" in report["unreviewed_duplicate_heading_ids"]
    assert report["contradictory_section_id_count"] == 1


def test_misplaced_or_unknown_annotations_are_reported():
    report = mod().measure(
        "## GAP-A-01\n- **status:** fixed\n<!-- gap-registry: current -->\n"
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-X | <!-- gap-registry: exempt --> pending |\n"
        "| GAP-Y | <!-- gap-registry: alias --><!-- gap-registry: policy --> pending |\n"
    )
    assert [item["line"] for item in report["annotation_errors"]] == [3, 6, 7]
    assert report["gap_row_count"] == 2
    assert report["row_state_counts"] == {"unclassified": 2}


def report_job():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["gap-registry-report"]


def test_workflow_report_is_independent_nonblocking_and_bound_to_head():
    job = report_job()
    assert "needs" not in job
    assert job["continue-on-error"] is True
    measure = next(step for step in job["steps"] if step.get("id") == "measure")
    assert measure["env"]["EVIDENCE_DIR"] == "${{ runner.temp }}/gap-registry-measurement"
    checkout = next(step for step in job["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    upload = next(
        step for step in job["steps"] if "actions/upload-artifact@" in step.get("uses", "")
    )
    assert "${{ github.event.pull_request.head.sha || github.sha }}" in upload["with"]["name"]
    assert upload["with"]["path"] == measure["env"]["EVIDENCE_DIR"] + "/"
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize("registry_exists", [True, False])
def test_workflow_command_emits_real_read_only_evidence(tmp_path, registry_exists):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    script = checkout / "scripts/ci/gap_registry_measure.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/ci/gap_registry_measure.py", script)
    registry = checkout / "sahool-brain/gaps/registry.md"
    if registry_exists:
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "| ID | Detail | Status |\n| --- | --- | --- |\n"
            "| GAP-A-01 | x | BLOCKED_BY_ENVIRONMENT |\n"
            "## GAP-A-01\n- **الحالة:** fixed\n"
            "## GAP-A-01\n- **الحالة:** open\n",
            encoding="utf-8",
        )

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=checkout, check=True, capture_output=True, encoding="utf-8"
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    evidence = tmp_path / "evidence"
    command = next(step["run"] for step in report_job()["steps"] if step.get("id") == "measure")
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", command],
        cwd=checkout,
        env={**os.environ, "EVIDENCE_DIR": str(evidence)},
        capture_output=True,
        encoding="utf-8",
    )
    assert git("status", "--porcelain") == ""
    if not registry_exists:
        assert result.returncode != 0
        assert "sahool-brain/gaps/registry.md" in result.stderr
        assert not (evidence / "gap-registry.json").exists()
        return

    assert result.returncode == 0, result.stderr
    report = json.loads((evidence / "gap-registry.json").read_text(encoding="utf-8"))
    assert report["row_state_counts"] == {"unclassified": 1}
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [4, 6]}
    assert report["contradictory_section_id_count"] == 1
    assert (evidence / "source-sha.txt").read_text(encoding="utf-8").strip() == git(
        "rev-parse", "HEAD"
    )
    checksums = (evidence / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 2
    for path, line in zip((registry, script), checksums, strict=True):
        assert (
            line == f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(checkout)}"
        )


# ── GAP-HEADING-WITHOUT-A-STATE-RECORD-IS-INVISIBLE-01 ─────────────────────────
# **مقيسٌ على مصنوعَتَي تشغيلٍ حقيقيَّتين:** عنوانُ فجوةٍ بصيغة
# `## <معرِّف> — مفتوحة (…)` رفع `heading_count` (٢٦٣ ⇒ ٢٦٤) وترك
# `section_state_count` عند ٤٢ و`unclassified_section_states` فارغاً — فاختفت الفجوةُ
# من كلّ عدٍّ يُقرأ ووظيفةُ القياس خضراء.
#
# **والسببُ بنيويّ:** حقولُ `unclassified_*` تصف ما **رآه** القارئُ ولم يفهمه، وما لم
# يُرَ أصلاً لا يقع في أيٍّ منها. فهذه الشواهدُ تقيس الفرقَ بين «لم يُفهَم» و«لم يُرَ».

_ORPHAN = "## GAP-ORPHAN-01 — مفتوحة (P2 حوكمة، 2026-09-19)\n\n- وصفٌ نثريٌّ بلا سطر حالة.\n"


def test_an_arabic_state_in_the_heading_is_not_read_as_a_state():
    """**الصنفُ بعينه كما وقع.** «مفتوحة» في العنوان ليست `open`."""
    report = mod().measure(_ORPHAN)
    assert report["heading_count"] == 1
    assert report["section_state_count"] == 0
    assert report["unclassified_section_states"] == []
    assert [item["id"] for item in report["orphan_gap_headings"]] == ["GAP-ORPHAN-01"]
    assert report["orphan_gap_heading_count"] == 1


def test_a_heading_with_a_canonical_state_line_is_not_an_orphan():
    """العلاجُ المُلزِم: سطرُ حالةٍ قانونيٌّ تحت العنوان."""
    report = mod().measure("## GAP-OK-01\n\n- **الحالة:** **open** — سببٌ ما.\n")
    assert report["section_state_count"] == 1
    assert report["orphan_gap_headings"] == []


def test_a_heading_documented_only_by_a_table_row_is_not_an_orphan():
    """**اليُتمُ غيابُ سجلٍّ لا غيابُ قسم.**

    كثيرٌ من مدخلات هذا السجلّ حالتُها في صفِّ جدولٍ لا في قسم. فحقلٌ يعدّ «عنواناً بلا
    `- **الحالة:**`» كان سيُحمِّر على مدخلاتٍ **مرئيّةٍ تماماً** — أي يُنتِج ٢٦٤ عطلاً
    كاذباً ويُطفَأ في أوّل أسبوع.
    """
    report = mod().measure(
        "## GAP-ROWED-01\n\n| ID | Detail | Status |\n| --- | --- | --- |\n"
        "| GAP-ROWED-01 | x | **open** |\n"
    )
    assert report["orphan_gap_headings"] == []


@pytest.mark.parametrize(
    "heading",
    [
        "## GAP-X-01 — مفتوحة",
        "## GAP-X-01 — ✅ FIXED (2026-09-19)",
        "## GAP-X-01 — OPEN (blocked on blessed environment)",
        "## GAP-X-01 — مُصلَحة في مرشّح الدمج",
    ],
)
def test_no_heading_shape_can_smuggle_a_state_past_the_state_count(heading):
    """**لا صيغةَ عنوانٍ تُغني عن سجلّ الحالة** — ولا واحدةٌ منها تُقرأ حالةً.

    وشمولُ `✅ FIXED` و`OPEN` الإنجليزيّتين مقصود: العطلُ ليس «عربيّة» بل **العنوانُ
    موضعاً**. ولو قُصِر الشاهدُ على العربيّة لصار قارئاً أضيقَ من دعواه، فمرّت
    `— ✅ FIXED` صامتةً وهي الصيغةُ الأكثرُ وروداً في هذا السجلّ.
    """
    report = mod().measure(heading + "\n\n- وصفٌ بلا سجلّ حالة.\n")
    assert report["section_state_count"] == 0
    assert report["orphan_gap_heading_count"] == 1


def test_the_real_registry_has_no_broken_rows_and_no_unclassified_states():
    """GAP-REGISTRY-MEASURE-REPORT-ONLY-HIDES-A-BROKEN-TABLE-01: الوظيفةُ ``gap-registry-report``
    تقريرٌ لا يحجب عمداً (الاختبارُ أعلاه)، فسجلٌّ مكسورٌ كان يظهر أخضر: صفٌّ واحد كُتِب فيه
    ``"\\n"`` سطراً جديداً حقيقيّاً (#1119) فأفقد المُحلِّلَ جدولَه وصار ٩ صفوفٍ بلا حالة.
    الحجبُ هنا لا في التقرير: هذا الملفّ يعمل تحت «Repository Tests (tests/)» المطلوب.
    راتشِت عند الصفر — main كان عند الصفر في الحقلين لحظةَ الإضافة."""
    report = mod().measure((ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8"))
    broken = [(row["id"], row["line"]) for row in report["table_structure_errors"]]
    unclassified = [(row["id"], row["line"]) for row in report["unclassified_rows"]]
    assert not broken, f"صفوفٌ كسرت جدولَ السجلّ (سطرٌ جديد داخل خليّة؟): {broken}"
    assert not unclassified, f"صفوفُ فجوةٍ بلا حالةٍ قانونيّة: {unclassified}"


# ── BRAIN-FIXED-PROVENANCE-NOT-RECONCILED-WITH-MERGE-01 ────────────────────────
# الدمجُ squash، فـSHA الإصلاح في صفّ fixed ليس سلفاً لـ`main` بعد الدمج. مقيسٌ على `ab07ceb8`:
# صفُّ #1149 يذكر `0726a887` في حالته و`main@c56db557` في وصفه — والقياسُ كان أخضر.

_HEAD = "| ID | Detail | Status |\n| --- | --- | --- |\n"
_MAIN = {"c56db557aaaa", "ab07ceb8cccc"}


def _reach(sha):
    return any(full.startswith(sha) for full in _MAIN)


def _flagged(text, merges=None):
    m = mod()
    report = m.measure(text)
    return m.fixed_provenance(text, report["fixed_records"], merges or {}, _reach)


def test_a_squashed_repair_sha_without_a_canonical_link_is_reported():
    row = "| GAP-A-01 | قيس على `main@c56db557` | **fixed** (`0726a887`، #1149) |\n"
    found = _flagged(_HEAD + row, {1149: "ab07ceb8cccc"})
    assert [f["id"] for f in found] == ["GAP-A-01"]
    assert found[0]["repair_shas"] == ["0726a887"]
    assert found[0]["cited_pr_merges"] == {"1149": "ab07ceb8cccc"}


def test_a_reachable_sha_outside_the_status_does_not_count_as_a_link():
    # الشاهدُ على الحالة التي وُجِد القياسُ لأجلها: قاعدةُ القياس في الوصف تُبلَغ، والربطُ غائب.
    row = "| GAP-A-01 | قيس على `main@c56db557` | **fixed** (`0726a887`) |\n"
    assert _flagged(_HEAD + row)


@pytest.mark.parametrize(
    "status",
    [
        "**fixed** (`0726a887`، #1149) · **canonical على `main`:** squash `ab07ceb8`",
        "**fixed** (`c56db557`)",
        "**fixed** (2026-10-06، `20260626` · `feedback` · run `2412021383`)",
    ],
    ids=["appended-merge", "repair-on-main", "dates-words-run-ids-are-not-shas"],
)
def test_a_linked_or_reachable_or_non_sha_status_is_not_reported(status):
    assert _flagged(_HEAD + f"| GAP-A-01 | x | {status} |\n") == []


def test_a_section_is_linked_by_its_canonical_line_not_by_any_sha_in_its_body():
    section = (
        "## GAP-B-01 — x\n<!-- gap-registry: current -->\n"
        "- **الحالة:** **fixed** (عند `0726a887`)\n- **النسخة المفحوصة:** `main@c56db557`.\n"
    )
    assert [f["id"] for f in _flagged(section)] == ["GAP-B-01"]
    linked = section + "- **canonical على `main` (2026-10-06):** squash `ab07ceb8`\n"
    assert _flagged(linked) == []


def test_an_open_row_and_a_historical_entry_are_not_provenance_findings():
    text = (
        _HEAD
        + "| GAP-A-01 | x | **open** (`0726a887`) |\n"
        + (
            "## GAP-C-01\n<!-- gap-registry: historical -->\n- **الحالة:** fixed (`0726a887`)\n"
            "## GAP-C-01\n<!-- gap-registry: current -->\n- **الحالة:** fixed (`c56db557`)\n"
        )
    )
    assert _flagged(text) == []


def _repo(tmp_path):
    def git(*args, cwd=tmp_path):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout.strip()

    return git


def test_the_cli_maps_a_squash_merge_from_real_history_and_declares_a_shallow_clone(tmp_path):
    git = _repo(tmp_path)
    reg = tmp_path / "sahool-brain/gaps/registry.md"
    reg.parent.mkdir(parents=True)
    reg.write_text("seed\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-qm", "seed")
    git("checkout", "-qb", "fix")
    (tmp_path / "fix.txt").write_text("fix\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "repair")
    repair = git("rev-parse", "--short=8", "HEAD")
    git("checkout", "-q", "main")
    git("merge", "-q", "--squash", "fix")
    git("commit", "-qm", "repair (#77)")
    merge = git("rev-parse", "HEAD")
    git("branch", "-qD", "fix")
    git("reflog", "expire", "--expire=now", "--all")
    git("gc", "-q", "--prune=now")
    reg.write_text(_HEAD + f"| GAP-A-01 | x | **fixed** (`{repair}`، #77) |\n", encoding="utf-8")

    def run(cwd):
        out = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/ci/gap_registry_measure.py"),
                "--json",
                str(cwd / "sahool-brain/gaps/registry.md"),
            ],
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout
        return json.loads(out)

    report = run(tmp_path)
    assert report["provenance_measured"] is True
    assert [f["id"] for f in report["unreconciled_fixed_provenance"]] == ["GAP-A-01"]
    assert report["unreconciled_fixed_provenance"][0]["cited_pr_merges"] == {"77": merge}

    git("add", "-A")
    git("commit", "-qm", "registry")
    shallow = tmp_path.parent / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{tmp_path}", str(shallow)],
        check=True,
        capture_output=True,
    )
    report = run(shallow)
    assert report["provenance_measured"] is False
    assert report["provenance_unmeasured_reason"] == "shallow_clone"
    assert report["unreconciled_fixed_provenance"] is None


def test_the_report_job_fetches_full_history_for_the_provenance_measure():
    checkout = next(
        step for step in report_job()["steps"] if "actions/checkout@" in step.get("uses", "")
    )
    assert checkout["with"]["fetch-depth"] == 0
