"""Declare railway-dockerfile-pr-build.yml::plan on the blocking surface + register its mutations. argv: root"""
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
GUARD = "railway_dockerfile_pr_build_plan.py"
KEY = "scripts/ci/railway_dockerfile_pr_build_plan.py::railway-dockerfile-pr-build.yml::plan"
src = (root / "scripts/ci" / GUARD).read_text(encoding="utf-8")

MUTATIONS = [
    {
        "expect": "test_a_broken_matcher_is_caught_instead_of_reading_green",
        "find": "        assert_plan_covers_touched_dockerfiles(changed, result)\n",
        "replace": "        pass  # mutated: لا فحصَ مستقلّ للخطّة\n",
        "why": "إسقاطُ الفحص المستقلّ ⇒ مُطابِقٌ معطوبٌ يُنتِج «لا شيءَ يُبنى» لـPR يمسّ Dockerfile فيُقرأ أخضر — الصنفُ نفسُه الذي وُجد المُخطِّطُ لإغلاقه (skipped يُقرأ نجاحاً).",
    },
    {
        "expect": "test_a_file_the_image_copies_selects_its_build_even_if_the_dockerfile_is_unchanged",
        "find": "    return changed == source or changed.startswith(source + \"/\")\n",
        "replace": "    return changed == source\n",
        "why": "مطابقةُ المسار الحرفيّ وحده ⇒ ملفٌّ داخل مجلّدٍ يُنسَخ في الصورة لا يختار بناءها، فيكسر PR البناءَ في الإنتاج وخطّتُه فارغة.",
    },
    {
        "expect": "test_changing_the_verifier_rebuilds_everything_it_verifies",
        "find": "        reasons += [f\"verifier_changed:{v}\" for v in VERIFIER_PATHS if v in changed_files]\n",
        "replace": "        reasons += []\n",
        "why": "الـPR الذي يُضيف المُتحقِّقَ أو يكسره لا يبني شيئاً ⇒ «لا شيءَ يُبنى» يُقرأ نجاحاً على التغيير الذي يمسّ المُتحقِّقَ نفسَه.",
    },
]
for m in MUTATIONS:
    assert src.count(m["find"]) == 1, m["find"]

reg_p = root / "docs/architecture/guard_mutation_registry.json"
reg = json.loads(reg_p.read_text(encoding="utf-8"))
assert GUARD not in reg["mutated"]
reg["mutated"][GUARD] = {"test": "tests_v9/test_railway_dockerfile_pr_build_plan.py", "mutations": MUTATIONS}
reg_p.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

add_p = root / "docs/architecture/blocking_surface_additions.json"
add = json.loads(add_p.read_text(encoding="utf-8"))
assert KEY not in add["additions"]
add["additions"][KEY] = {
    "counterexample": "Measured on main 166bdebf (#1112) and b0c14b6d (#1114): docker-build-matrix-verifier.yml:58 `docker-build` runs only on workflow_dispatch, so it reports `skipped` on every PR and reads as passing; Railway production deploys from main with checkSuites:false, so no Dockerfile Railway builds is built before Railway builds it in production. The planner selects Railway Dockerfiles whose file or COPY context the PR touches.",
    "mutation": "test_a_broken_matcher_is_caught_instead_of_reading_green",
    "$mutation_ar": "ثلاثُ طفرات مسجَّلة: إسقاطُ الفحص المستقلّ · تضييقُ المُطابِق إلى المسار الحرفيّ · إسقاطُ قاعدة المُتحقِّق — يقتل كلّاً منها اختبارُه المسمّى.",
    "positive_witness": "test_a_change_outside_every_build_context_builds_nothing and test_a_file_in_the_service_directory_that_is_not_copied_builds_nothing: a PR touching only brain/compose/tests plans zero builds and the verdict job passes with a named 'no Dockerfile or COPY context touched' result.",
    "impact": "merge",
    "$scope_limit_ar": "يبني ما يبنيه Railway (13 Dockerfile) حين يمسّ الـPR الملفَّ أو سياقَ COPY؛ لا يُشغّل الصورة ولا يختبر سلوكها، ولا يُغني عن «Wait for CI» على Railway.",
}
add_p.write_text(json.dumps(add, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("declared", KEY)
