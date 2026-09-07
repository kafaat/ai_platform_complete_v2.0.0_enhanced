"""شاهدُ `GUARDS` — الفارقُ بين ما يُعلَن حاجباً وما أُثبِت تشغيلُه.

`PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`.

الحاجبُ `GUARDS` غيرُ قابلٍ للإعفاء، ويشترط `guard_results_summary.json` بحالة
`verified` — و**لا شيءَ في المستودع كان يكتبه**. فالحكمُ `production_certified=false`
لم يكن قياساً فشل بل قياساً لا وجودَ له.

وما يُقاس هنا ليس «هل يمرّ الجامعُ على شجرةٍ سليمة» — تلك خاصّيّةٌ يُحقّقها جامعٌ لا
يفعل شيئاً — بل **أنّه يرفض** كلَّ متّجهٍ يحوّل «لم يُقَس» إلى «مرّ»: خطوةٌ مُتخطّاة،
وظيفةٌ غائبة، خطوةٌ أُعيدت تسميتُها، رِجلُ مصفوفةٍ لم تُنفَّذ، خطوةٌ لا تحجب أصلاً،
وجردٌ انهار إلى الصفر.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WITNESS = _load(ROOT / "scripts/ci/collect_guard_surface_evidence.py", "_guard_surface")
CATALOGUE = _load(ROOT / "scripts/ci/guard_catalogue.py", "_guard_catalogue_for_witness")

GUARD = "scripts/ci/example_guard.py"


def _site(**over) -> dict:
    site = {
        "workflow": "ci.yml",
        "job": "lint",
        "job_names": ["Lint & Format"],
        "step_index": 3,
        "step_name": "claim-base guard",
        "step_if": None,
        "continue_on_error": False,
        "guards": [GUARD],
    }
    site.update(over)
    return site


def _run(*jobs: dict, run_id: str = "42") -> dict:
    return {"run_id": run_id, "conclusion": "success", "jobs": list(jobs)}


def _job(name: str, conclusion: str = "success", steps: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "conclusion": conclusion,
        "steps": steps
        if steps is not None
        else [{"name": "claim-base guard", "conclusion": "success"}],
    }


def _status_of(result: dict, guard: str = GUARD) -> str:
    return next(g["status"] for g in result["guards"] if g["guard"] == guard)


# ── الشاهدُ الموجب: بلا هذا لا معنى لأيّ رفضٍ أدناه ──────────────────────────


def test_a_successful_step_proves_its_guard_ran():
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(_job("Lint & Format"))})
    assert _status_of(result) == "ran"
    assert result["guards_unproven"] == []
    assert result["guards_proven_run"] == 1


# ── وكلُّ ما تحته متّجهُ «لم يُقَس ⇒ مرّ» ────────────────────────────────────


def test_a_skipped_step_is_not_a_run():
    """`skipped` تعني أنّ الحارسَ **لم يُشغَّل**؛ وقبولُها هو العطل بعينه.

    وهو ليس افتراضاً: خمسُ خطواتٍ حاجبةٍ في هذه الشجرة تحمل `if:`، ومنها ما يُتخطّى
    على الدفع ويعمل على PR — فالتخطّي حالةٌ يوميّةٌ لا نادرة.
    """
    job = _job("Lint & Format", steps=[{"name": "claim-base guard", "conclusion": "skipped"}])
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(job)})
    assert _status_of(result) == "not_proven"
    assert result["guards_unproven"][0]["reasons"] == ["step_skipped"]


def test_a_step_that_failed_is_not_a_run():
    job = _job("Lint & Format", steps=[{"name": "claim-base guard", "conclusion": "failure"}])
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(job)})
    assert result["guards_unproven"][0]["reasons"] == ["step_failure"]


def test_a_renamed_step_does_not_inherit_the_jobs_green():
    """إعادةُ تسميةٍ تُسقِط الشاهدَ ولا تُمرّره.

    المتّجهُ الخفيّ: الوظيفةُ خضراء، فيَسهُل الاستدلالُ بخضرتها على خطوةٍ لم تُرَ —
    وهو استدلالٌ يبقى صحيحاً حتّى اليوم الذي تُحذَف فيه الخطوة.
    """
    job = _job(
        "Lint & Format", steps=[{"name": "claim-base guard (renamed)", "conclusion": "success"}]
    )
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(job)})
    assert result["guards_unproven"][0]["reasons"] == ["step_missing"]


def test_a_missing_job_is_not_a_run():
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(_job("Some Other Job"))})
    assert result["guards_unproven"][0]["reasons"] == ["job_missing"]


def test_a_job_that_did_not_succeed_is_not_a_run():
    job = _job("Lint & Format", conclusion="skipped")
    result = WITNESS.evaluate([_site()], {"ci.yml": _run(job)})
    assert result["guards_unproven"][0]["reasons"] == ["job_skipped"]


def test_a_workflow_with_no_run_on_this_commit_names_that_reason():
    """أحدَ عشرَ حارساً في هذه الشجرة لا يُستدعى إلّا في workflows لا تعمل على الدفع.

    وهذه حقيقةٌ يجب أن **تظهر** في الفارق: العددُ وحدَه («٢٦٠ من ٢٧١») يخفي أنّ
    الأحدَ عشرَ الغائبة هي بالضبط أدلّةُ الاعتماد وإثباتُ المنشأ.
    """
    result = WITNESS.evaluate([_site()], {"ci.yml": {"error": "لا عدّاءَ على abc12345…"}})
    assert result["guards_unproven"][0]["reasons"] == ["workflow_not_run_on_this_commit"]


def test_a_matrix_job_must_prove_every_leg():
    """رِجلٌ واحدةٌ ناجحةٌ من خمسٍ ليست تشغيلاً للحارس على الشجرة كلِّها."""
    site = _site(
        job="mutation-sweep",
        job_names=[f"Mutation Sweep {i}/5" for i in range(1, 6)],
        step_name="Plant this shard's defects",
    )
    steps = [{"name": "Plant this shard's defects", "conclusion": "success"}]
    jobs = [_job(f"Mutation Sweep {i}/5", steps=steps) for i in range(1, 5)]
    result = WITNESS.evaluate([site], {"ci.yml": _run(*jobs)})
    assert result["guards_unproven"][0]["reasons"] == ["job_missing"]
    assert result["guards_unproven"][0]["sites"][0]["detail"] == "Mutation Sweep 5/5"

    complete = [*jobs, _job("Mutation Sweep 5/5", steps=steps)]
    assert _status_of(WITNESS.evaluate([site], {"ci.yml": _run(*complete)})) == "ran"


def test_continue_on_error_is_not_a_blocking_run():
    """حارسٌ لا يُسقِط وظيفتَه حين يفشل ليس حاجباً — وعدُّه حاجباً يضخّم السطحَ كذباً."""
    result = WITNESS.evaluate(
        [_site(continue_on_error=True)], {"ci.yml": _run(_job("Lint & Format"))}
    )
    assert result["guards_unproven"][0]["reasons"] == ["non_blocking_by_declaration"]


def test_a_job_name_that_cannot_be_derived_is_a_gap_not_a_match():
    result = WITNESS.evaluate([_site(job_names=[])], {"ci.yml": _run(_job("Lint & Format"))})
    assert result["guards_unproven"][0]["reasons"] == ["job_name_not_derivable"]


# ── الوجهُ الآخر: لا تشدّدَ كاذب ─────────────────────────────────────────────


def test_a_guard_invoked_twice_is_proven_by_either_site():
    """التشغيلُ واقعةٌ لا إجماع: موضعٌ مُتخطٍّ لا يُبطِل موضعاً نُفِّذ."""
    sites = [
        _site(workflow="other.yml", step_name="ghost"),
        _site(),
    ]
    runs = {
        "other.yml": {"error": "لا عدّاء"},
        "ci.yml": _run(_job("Lint & Format")),
    }
    assert _status_of(WITNESS.evaluate(sites, runs)) == "ran"


def test_an_unnamed_step_is_matched_by_the_command_github_names_it_with():
    """خمسٌ وعشرون خطوةً حاجبةً بلا اسم — تصل الواجهةَ باسمٍ مولَّدٍ من أمرها."""
    job = _job(
        "Lint & Format",
        steps=[{"name": f"Run python {GUARD} --check", "conclusion": "success"}],
    )
    result = WITNESS.evaluate([_site(step_name=None)], {"ci.yml": _run(job)})
    assert _status_of(result) == "ran"


# ── الدور: شاهدٌ لا يشهد على العدّاء الذي هو فيه ─────────────────────────────


def test_the_witness_does_not_demand_proof_of_the_run_it_lives_in():
    """وإلّا اشترط الشرطُ نفسَه فلم يتقارب أبداً — بوّابةٌ لا تُغلَق بعملٍ صحيح."""
    site = _site(workflow=WITNESS.SELF_WITNESSING_WORKFLOW, job="certification-verdict")
    result = WITNESS.evaluate([site], {})
    assert _status_of(result) == "self_witnessing_excluded"
    assert result["guards_unproven"] == []
    assert result["self_witnessing_excluded"] == [GUARD]
    assert result["guards_proven_run"] == 0, "المُستثنى لا يُعَدّ مُثبَتاً"


def test_the_exclusion_does_not_leak_to_a_guard_that_also_runs_elsewhere():
    sites = [
        _site(workflow=WITNESS.SELF_WITNESSING_WORKFLOW, job="certification-verdict"),
        _site(),
    ]
    job = _job("Lint & Format", steps=[{"name": "claim-base guard", "conclusion": "skipped"}])
    result = WITNESS.evaluate(sites, {"ci.yml": _run(job)})
    assert _status_of(result) == "not_proven"


def test_the_self_witnessing_membership_is_pinned_not_open_ended():
    """الاستثناءُ بابٌ يُراجَع لا يُنزلَق إليه: مَن أراد إعفاءَ حارسٍ ينقله إلى هذا
    الـworkflow — فتُثبَّت العضويّةُ هنا كي يصير النقلُ فعلاً مقصوداً مرئيّاً.
    """
    invocations = CATALOGUE.discover_invocations()
    excluded = sorted(
        guard
        for guard, sites in invocations.items()
        if {workflow for workflow, _ in sites} == {WITNESS.SELF_WITNESSING_WORKFLOW}
    )
    assert excluded == [
        "scripts/ci/collect_full_branch_ci_evidence.py",
        "scripts/ci/collect_guard_surface_evidence.py",
        "scripts/ci/emit_certification_evidence.py",
        "scripts/ci/production_certification_blockers_status.py",
        "scripts/ci/verify_certification_evidence_digests.py",
    ], "تغيّرت عضويّةُ الاستثناء — راجِعها بدل تحديث الرقم"


# ── الجردُ نفسُه: شاهدٌ عن لا شيء ليس شاهداً على التمام ──────────────────────


def test_the_inventory_actually_reads_the_tree():
    sites = CATALOGUE.discover_invocation_sites()
    guards = {g for site in sites for g in site["guards"]}
    assert len(guards) > WITNESS.MINIMUM_DISCOVERED_GUARDS
    assert len(sites) >= len(guards)
    # والعرضُ المُشتقّ لا ينحرف عن العرض الذي يُبنى عليه الكتالوج: تحليلٌ واحد، رؤيتان.
    projected: dict[str, set[tuple[str, str]]] = {}
    for site in sites:
        for guard in site["guards"]:
            projected.setdefault(guard, set()).add((site["workflow"], site["job"]))
    assert projected == CATALOGUE.discover_invocations()


def test_an_inventory_that_collapsed_to_nothing_fails_closed(monkeypatch):
    """صفرُ حرّاس ⇒ صفرُ فارق ⇒ `verified` عن لا شيء — أخطرُ فشلٍ ممكنٍ هنا."""

    class _Stub:
        @staticmethod
        def discover_invocation_sites():
            return [_site()]

    monkeypatch.setattr(WITNESS, "_load", lambda *_a, **_k: _Stub)
    # تُنزَع متغيّراتُ الأصل كي يكون السقوطُ **بالأرضيّة** لا بغيابها: بلا ذلك يمرّ
    # الاختبار في عدّاء Actions لسببٍ آخر، فيصير أخضرَ عن شرطٍ لم يُقَس.
    for var in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit) as excinfo:
        WITNESS.collect()
    assert "الأرضيّة" in str(excinfo.value)


# ── الحقولُ كما يشترطها الباعثُ والحارس ──────────────────────────────────────


def test_a_nonempty_difference_exits_nonzero(monkeypatch, tmp_path):
    """الفارقُ يمنع بلوغَ خطوة الانبعاث — وهي الآليّة الوحيدة التي تحدّد `status`."""
    monkeypatch.setattr(
        WITNESS,
        "collect",
        lambda: {
            "guards": [{"guard": GUARD, "status": "not_proven", "reasons": ["step_skipped"]}],
            "guards_declared": 1,
            "guards_proven_run": 0,
            "guards_unproven": [{"guard": GUARD, "reasons": ["step_skipped"], "sites": []}],
        },
    )
    out = tmp_path / "fields.json"
    assert WITNESS.main(["--out", str(out)]) == 1
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["guards_unproven"], "الفارقُ يُكتَب حتّى حين يسقط — وإلّا ضاع التشخيص"


def test_the_measured_fields_never_collide_with_provenance():
    """`repository`/`workflow`/`commit`/`status` تُقرأ من البيئة، وتمريرُها يُرفَض.

    فحقلٌ بهذا الاسم في مخرَج الجامع يُسقِط الانبعاثَ في العدّاء لا هنا — والسقوطُ
    هناك يُقرأ «القياسُ فشل» وهو في الحقيقة تصادمُ أسماء.
    """
    emitter = _load(ROOT / "scripts/ci/emit_certification_evidence.py", "_emit_for_witness")
    produced = set(WITNESS.evaluate([_site()], {"ci.yml": _run(_job("Lint & Format"))}))
    produced |= {"guard_catalogue", "workflow_runs", "honesty_limit"}
    assert not produced & set(emitter._RESERVED_FIELDS)


def test_the_blocker_minimum_fields_are_satisfied_by_what_this_witness_produces():
    emitter = _load(ROOT / "scripts/ci/emit_certification_evidence.py", "_emit_for_minimums")
    guards_blocker = next(b for b in emitter._blockers() if b["id"] == "GUARDS")
    fields = WITNESS.evaluate([_site()], {"ci.yml": _run(_job("Lint & Format"))})
    # `status` و`timestamp_utc` يكتبهما الباعثُ من بلوغ الخطوة وساعةِ العدّاء.
    assert set(guards_blocker["minimum_fields"]) - {"status", "timestamp_utc"} == {"guards"}
    assert fields["guards"], "الحقلُ الذي يشترطه الحارسُ لا يُملأ بقيمةٍ شكليّة"
