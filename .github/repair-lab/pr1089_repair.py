"""One-shot repair lab. Never checked out into the candidate tree."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

SOURCE = "617a3e5687769d85ee8998d4d753ce0d0acc234f"
MAIN = "c6d4ac3bb02a0df5069ce774bfad8f35606f9c62"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "pr1089-evidence"
OUT.mkdir(parents=True, exist_ok=True)


def run(label, args, *, expected=(0,), timeout=900, env=None):
    print(f"=== {label}: {' '.join(args)} ===", flush=True)
    proc = subprocess.run(args, text=True, encoding="utf-8", stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, env=env)
    (OUT / f"{label}.log").write_text(proc.stdout, encoding="utf-8")
    print(proc.stdout[-16000:], flush=True)
    if proc.returncode not in expected:
        raise RuntimeError(f"{label}: exit {proc.returncode}")
    return proc


def git(*args):
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def failures(path):
    root = ET.parse(path).getroot()
    return root.findall(".//testcase[failure]"), root.findall(".//testcase[error]")


if git("rev-parse", "HEAD") != SOURCE:
    raise RuntimeError("candidate checkout is not the pinned PR head")
run("fetch-main", ["git", "fetch", "--no-tags", "origin", "main"])
if git("rev-parse", "origin/main") != MAIN:
    raise RuntimeError("main moved; do not synthesize a repair on a stale base")
run("git-user", ["git", "config", "user.name", "github-actions[bot]"])
run("git-email", ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
run("merge", ["git", "merge", "--no-commit", "--no-ff", MAIN], expected=(0, 1))
conflicts = git("diff", "--name-only", "--diff-filter=U").splitlines()
allowed_conflicts = {
    "release/FILE_CHECKSUMS.sha256",
    "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
    "release/SBOM_MINIMAL.json",
}
if set(conflicts) - allowed_conflicts:
    raise RuntimeError(f"unexpected conflicts need source review: {conflicts}")
for path in conflicts:
    run("resolve-" + Path(path).name, ["git", "checkout", MAIN, "--", path])
(OUT / "conflicts.json").write_text(json.dumps(conflicts, indent=2) + "\n", encoding="utf-8")

# Verify the original attempt-aware contract before extending its boundary tests.
run("original-contract", [sys.executable, "-m", "pytest", "-q", "tests_v9/test_certify_artifact_contract.py"])
test_path = ROOT / "tests_v9/test_certify_artifact_contract.py"
extra = '''

@pytest.mark.parametrize("attempt", [True, False, 0, -1, 1.5, "2", None])
def test_run_attempt_requires_a_positive_non_boolean_integer(attempt) -> None:
    with pytest.raises(SystemExit, match="run_attempt"):
        probe.judge(_inventory(*_pair()), HEAD, attempt)


@pytest.mark.parametrize("ev_attempt,at_attempt", [(2, 1), (1, 2), (2, 3), (3, 2)])
def test_evidence_and_attestation_from_different_attempts_are_not_paired(
    ev_attempt, at_attempt
) -> None:
    inventory = _inventory(
        _artifact(f"live-pg-evidence-{HEAD}-attempt-{ev_attempt}"),
        _artifact(f"live-pg-evidence-attestation-{HEAD}-attempt-{at_attempt}", id=40374290),
    )
    reason = "EVIDENCE_WITHOUT_ATTESTATION" if ev_attempt == ATTEMPT else "ATTESTATION_WITHOUT_EVIDENCE"
    with pytest.raises(SystemExit, match=reason):
        probe.judge(inventory, HEAD, ATTEMPT)


def test_a_future_attempt_pair_is_not_reused() -> None:
    future = ATTEMPT + 1
    verdict = probe.judge(
        _inventory(
            _artifact(f"live-pg-evidence-{HEAD}-attempt-{future}"),
            _artifact(f"live-pg-evidence-attestation-{HEAD}-attempt-{future}", id=40374290),
        ), HEAD, ATTEMPT,
    )
    assert verdict["status"] == "absent"
    assert verdict["artifacts"] is None
    assert verdict["run_attempt"] == ATTEMPT


def test_duplicate_attestations_for_the_current_attempt_are_rejected() -> None:
    evidence, attestation = _pair()
    with pytest.raises(SystemExit, match="AMBIGUOUS_ARTIFACT:attestation:2"):
        probe.judge(_inventory(evidence, attestation, dict(attestation)), HEAD, ATTEMPT)


def test_producer_and_consumer_both_use_the_run_attempt() -> None:
    import yaml

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    names = {
        step.get("with", {}).get("name")
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    }
    for prefix in ("live-pg-evidence", "live-pg-evidence-attestation", "live-pg-verified-evidence"):
        assert prefix + "-${{ github.sha }}-attempt-${{ github.run_attempt }}" in names
    certify = yaml.safe_load((ROOT / ".github/workflows/certify-run.yml").read_text(encoding="utf-8"))
    steps = [step for job in certify["jobs"].values() for step in job.get("steps", [])]
    contract = next(step for step in steps if step.get("id") == "artifact_contract")
    assert contract["env"]["RUN_ATTEMPT"] == "${{ github.event.workflow_run.run_attempt }}"
    assert '--run-attempt "${RUN_ATTEMPT}"' in contract["run"]
'''
if "test_run_attempt_requires_a_positive_non_boolean_integer" in test_path.read_text(encoding="utf-8"):
    raise RuntimeError("repair already present")
test_path.write_text(test_path.read_text(encoding="utf-8") + extra, encoding="utf-8")
pre_xml = OUT / "before-fix.xml"
run("before-fix", [sys.executable, "-m", "pytest", "-q", str(test_path), f"--junitxml={pre_xml}"], expected=(1,))
failed, errors = failures(pre_xml)
if errors or len(failed) != 1 or "positive_non_boolean_integer[True]" not in failed[0].get("name", ""):
    raise RuntimeError("the pre-fix failure was not the isolated boolean attempt regression")

contract_path = ROOT / "scripts/ci/certify_artifact_contract.py"
old = contract_path.read_text(encoding="utf-8")
needle = "if not isinstance(run_attempt, int) or run_attempt < 1:"
if old.count(needle) != 1:
    raise RuntimeError("attempt validator anchor changed")
fixed = old.replace(needle, "if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt < 1:")
contract_path.write_text(fixed, encoding="utf-8")
run("focused-tests", [sys.executable, "-m", "pytest", "-q", str(test_path), f"--junitxml={OUT / 'focused.xml'}"])

# Negative witnesses: valid syntax, expected assertion failures, then exact byte restoration.
mutations = [
    ("accept-boolean", "isinstance(run_attempt, bool) or ", ""),
    ("reuse-prior-attempt", "attempt=run_attempt)", "attempt=run_attempt - 1)"),
]
mutant_summary = []
for name, before, after in mutations:
    if before not in fixed:
        raise RuntimeError(f"mutation anchor missing: {name}")
    try:
        contract_path.write_text(fixed.replace(before, after, 1), encoding="utf-8")
        xml = OUT / f"mutation-{name}.xml"
        run("mutation-" + name, [sys.executable, "-m", "pytest", "-q", str(test_path), f"--junitxml={xml}"], expected=(1,))
        failed, errors = failures(xml)
        if not failed or errors:
            raise RuntimeError(f"mutation {name} was not killed by assertion failures")
        mutant_summary.append({"mutation": name, "killed": True, "failing_tests": [x.get("name") for x in failed]})
    finally:
        contract_path.write_text(fixed, encoding="utf-8")
assert contract_path.read_text(encoding="utf-8") == fixed
(OUT / "mutations.json").write_text(json.dumps(mutant_summary, indent=2) + "\n", encoding="utf-8")

# Append a separate causal gap; do not change the existing v25 runtime acceptance state.
registry = ROOT / "sahool-brain/gaps/registry.md"
text = registry.read_text(encoding="utf-8")
gap = "CERTIFY-ARTIFACT-IDENTITY-OMITS-RUN-ATTEMPT-01"
if f"## {gap}" in text:
    raise RuntimeError("gap already exists; reconcile rather than duplicate")
entry = f'''

## {gap}

- **الحالة:** fixed — source-fixed / post-run-runtime-unverified (2026-09-28). إصلاح اختيار المصنوعات لا يساوي اعتماد تشغيل إنتاجي.
- **المصدر:** #1089؛ `scripts/ci/certify_artifact_contract.py`؛ `.github/workflows/ci.yml`؛ `.github/workflows/certify-run.yml`؛ `tests_v9/test_certify_artifact_contract.py`.
- **السبب:** اختيار أدلة Live-PG بواسطة head_sha وحده كان يسمح بإعادة استخدام أدلة محاولة سابقة بعد failed-only rerun لم يُعد تشغيل منتج الأدلة. يرفض مدقق المنشأ الصحيح عدم تطابق run_attempt؛ لا يُخفف شرط run_identity_clean ولا release binding.
- **إصلاح المصدر:** أسماء الأدلة والتوقيع والأرشيف الموثق تتضمن SHA ورقم المحاولة؛ المستهلك يشتق الزوج من head_sha وrun_attempt ويختار exactly-one لكل دور. لا تُخلط أدوار من محاولات مختلفة، ولا تُقبل قيمة boolean كرقم محاولة موجب.
- **الشواهد:** الاختبارات في الملف المذكور تقيس المحاولة الحالية والسابقة واللاحقة، الزوج المختلط، التكرار، انتهاء الصلاحية، الهوية الأجنبية والمدخلات غير الصالحة، وربط المنتج بالمستهلك. زرع قبول boolean وإعادة استخدام محاولة سابقة يجب أن يُسقط الشاهد ثم يُستعاد المصدر بلا تغيير في بايتاته.
- **حد القبول:** وجود أدلة لمحاولة أقدم فقط ينتج absent للمحاولة المطلوبة، لا شهادة نجاح ولا إسقاطاً لفحص المنشأ. يلزم تشغيل post-run جديد بدليل موقّع مطابق لمحاولته قبل ادعاء اعتماد حي. runtime_verified وproduction_certified لا يُرقّيان بهذه الشريحة؛ إعدادات الخدمات والبيانات وRailway وNATS لا تتغير.
'''
registry.write_text(text + entry, encoding="utf-8")
assert registry.read_bytes().startswith(text.encode("utf-8"))
for name in ("hot.md", "log.md"):
    path = ROOT / "sahool-brain" / name
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n\n### متابعة إصلاح #1089 — 2026-09-28\n\nمزامنة الشريحة مع main@{MAIN[:8]} بعد #1090 مع إعادة توليد المصنوعات. السبب وحد القبول موثقان في `gaps/registry.md` تحت `{gap}`؛ لا اعتماد حي ولا تفعيل تشغيلي بهذه الشريحة. نتائج القياس تحفظ في مصنوعات مختبر الإصلاح.\n")

run("format", ["ruff", "format", str(contract_path), str(test_path)])
run("lint", ["ruff", "check", str(contract_path), str(test_path)])
run("tests-after-format", [sys.executable, "-m", "pytest", "-q", str(test_path), f"--junitxml={OUT / 'final-focused.xml'}"])
run("stage", ["git", "add", "-A"])
run("regenerate", [sys.executable, "scripts/ci/verify_all_generated.py", "--fix"], timeout=1500)
run("stage-generated", ["git", "add", "-A"])
run("release-build", [sys.executable, "scripts/release/build_release_bundle.py", "--root", "."])
run("release-validate", [sys.executable, "scripts/release/validate_release_package.py", "--root", "."])
run("stage-release", ["git", "add", "-A"])
run("diff-check", ["git", "diff", "--cached", "--check"])
run("commit", ["git", "commit", "-m", "fix(ci): synchronize attempt-aware certification and harden identity tests"])
# Recheck after the candidate commit, so measurements include its actual committed tree.
run("generated-check", [sys.executable, "scripts/ci/verify_all_generated.py", "--check"], timeout=1500)
run("preflight", ["bash", "scripts/ci/preflight.sh", "--fast", "--no-fetch"], env={**os.environ, "BASE": MAIN}, timeout=1200)
run("release-final", [sys.executable, "scripts/release/validate_release_package.py", "--root", "."])
if git("status", "--porcelain"):
    raise RuntimeError("checks left a dirty candidate tree")
# The application/runtime surface must exactly match the newly merged main.
run("runtime-unchanged", ["git", "diff", "--exit-code", MAIN, "HEAD", "--", "services/", "migrations/", "frontend/", "nginx/", "docker-compose*.yml"])
if git("ls-tree", "-r", "--name-only", "HEAD", ".github/repair-lab", ".github/workflows/pr1089-repair-lab.yml"):
    raise RuntimeError("repair laboratory leaked into the candidate")
run("impact-measure", [sys.executable, "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN, "--head", "HEAD", "--output", str(OUT / "impact.json")], expected=(0, 1))
impact = json.loads((OUT / "impact.json").read_text(encoding="utf-8"))
declaration = ", ".join(impact["direct"])
run("impact-validate", [sys.executable, "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN, "--head", "HEAD", "--declared", declaration, "--output", str(OUT / "impact-validated.json")])
summary = {
    "source_head": SOURCE, "main_sha": MAIN, "candidate_sha": git("rev-parse", "HEAD"),
    "candidate_tree": git("rev-parse", "HEAD^{tree}"), "parents": git("show", "-s", "--format=%P", "HEAD").split(),
    "resolved_conflicts": conflicts, "capability_declaration": "Capability-Impact: " + declaration,
    "changed_paths": git("diff", "--name-only", MAIN, "HEAD").splitlines(),
    "runtime_source_unchanged": True, "production_certified": False,
    "mutations": mutant_summary,
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
run("patch", ["git", "diff", MAIN, "HEAD"])
print("REPAIR_SUMMARY=" + json.dumps(summary, ensure_ascii=False), flush=True)
