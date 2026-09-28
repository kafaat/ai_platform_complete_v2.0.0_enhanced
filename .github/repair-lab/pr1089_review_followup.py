"""Pinned review repair; controller never enters the candidate tree."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

SOURCE = "f995dd66a560951b866b7f59132e48b286b6939e"
MAIN = "c6d4ac3bb02a0df5069ce774bfad8f35606f9c62"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "pr1089-review-evidence"
OUT.mkdir(parents=True, exist_ok=True)
GAP = "CERTIFY-ARTIFACT-IDENTITY-OMITS-RUN-ATTEMPT-01"
MEASUREMENTS = [
    "docs/architecture/tenant_guc_scope_baseline.json",
    "docs/architecture/db_writer_ownership_baseline.json",
    "docs/architecture/db_writer_ownership_triage.json",
    "docs/architecture/fake_connection_debt.json",
    "docs/architecture/generated_write_targets.json",
    "docs/architecture/source_text_assertion_inventory.json",
]
GENERATORS = [
    "tenant_guc_scope_guard.py",
    "db_writer_ownership_guard.py",
    "fake_connection_debt_guard.py",
    "generated_write_targets.py",
    "prohibition_reason_guard.py",
]
SOURCE_PATHS = [
    "scripts/ci/certify_artifact_contract.py",
    "tests_v9/test_certify_artifact_contract.py",
    "sahool-brain/decisions/ledger.md",
    "sahool-brain/log.md",
    "sahool-brain/hot.md",
    "sahool-brain/gaps/registry.md",
]


def run(label, args, *, expected=(0,), timeout=900, env=None):
    print(f"=== {label}: {' '.join(args)} ===", flush=True)
    proc = subprocess.run(args, text=True, encoding="utf-8", stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, env=env)
    (OUT / f"{label}.log").write_text(proc.stdout, encoding="utf-8")
    print(proc.stdout[-12000:], flush=True)
    if proc.returncode not in expected:
        raise RuntimeError(f"{label}: exit {proc.returncode}")
    return proc


def git(*args):
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def check_failure(xml):
    tree = ET.parse(xml).getroot()
    failures = tree.findall(".//testcase[failure]")
    errors = tree.findall(".//testcase[error]")
    if errors or len(failures) != 1:
        raise RuntimeError("negative witness must be one assertion failure, not an error")
    return failures[0].get("name")


def replace_exact(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"reviewed source anchor changed: {old!r}")
    return text.replace(old, new, 1)


def append(path, text):
    before = path.read_bytes()
    path.write_bytes(before + text.encode("utf-8"))
    if not path.read_bytes().startswith(before):
        raise RuntimeError(f"append-only violated: {path}")


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if git("rev-parse", "HEAD") != SOURCE or git("status", "--porcelain"):
    raise RuntimeError("candidate is not the exact clean reviewed head")
run("fetch-main", ["git", "fetch", "--no-tags", "origin", "main"])
if git("rev-parse", "origin/main") != MAIN:
    raise RuntimeError("main moved; re-review rather than publishing a stale candidate")
run("ancestor", ["git", "merge-base", "--is-ancestor", MAIN, SOURCE])
run("git-user", ["git", "config", "user.name", "github-actions[bot]"])
run("git-email", ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
old_measurements = {p: json.loads((ROOT / p).read_text(encoding="utf-8")) for p in MEASUREMENTS}
write_json("measurements-before.json", old_measurements)

# Add a response-contract witness first and prove the old verdict under-documents its identity.
test_path = ROOT / SOURCE_PATHS[1]
test_name = "test_present_verdict_honesty_limit_names_both_identity_dimensions"
if test_name in test_path.read_text(encoding="utf-8"):
    raise RuntimeError("follow-up already exists; do not duplicate it")
append(test_path, '''

def test_present_verdict_honesty_limit_names_both_identity_dimensions() -> None:
    verdict = probe.judge(_inventory(*_pair()), HEAD, ATTEMPT)
    assert verdict["run_attempt"] == ATTEMPT
    explanation = verdict["$honesty_limit_ar"]
    assert "head_sha" in explanation
    assert "run_attempt" in explanation
''')
xml = OUT / "honesty-before.xml"
run("honesty-before", [sys.executable, "-m", "pytest", "-q", str(test_path), "-k", test_name,
                      f"--junitxml={xml}"], expected=(1,))
check_failure(xml)

contract = ROOT / SOURCE_PATHS[0]
text = contract.read_text(encoding="utf-8")
text = replace_exact(text, "اسمٌ مشتقٌّ من ``head_sha``،", "اسمٌ مشتقٌّ من ``head_sha`` و``run_attempt``،")
text = replace_exact(text, "يُبنى من ``head_sha`` المشهود له حرفاً حرفاً، بلا", "يُبنى من الزوج ``head_sha`` و``run_attempt`` المشهود له، بلا")
text = replace_exact(text, "والاسم دالّةٌ في الـSHA لا نصٌّ ثابت.", "والاسم دالّةٌ في SHA ورقم المحاولة لا نصٌّ ثابت.")
text = replace_exact(text, "الاسم مشتقٌّ من head_sha ", "الاسم مشتقٌّ من head_sha وrun_attempt ")
text = replace_exact(text, "description=\"عقد مصنوعة الاعتماد المشتقّ من head_sha\"", "description=\"عقد مصنوعة الاعتماد المشتقّ من head_sha وrun_attempt\"")
contract.write_text(text, encoding="utf-8")
run("format", ["ruff", "format", str(contract), str(test_path)])
run("lint", ["ruff", "check", str(contract), str(test_path)])
run("focused", [sys.executable, "-m", "pytest", "-q", str(test_path),
               f"--junitxml={OUT / 'focused.xml'}"])
fixed = contract.read_bytes()
try:
    mutated = replace_exact(fixed.decode("utf-8"), "الاسم مشتقٌّ من head_sha وrun_attempt ", "الاسم مشتقٌّ من head_sha ")
    contract.write_text(mutated, encoding="utf-8")
    xml = OUT / "mutation-honesty.xml"
    run("mutation-honesty", [sys.executable, "-m", "pytest", "-q", str(test_path), "-k", test_name,
                             f"--junitxml={xml}"], expected=(1,))
    check_failure(xml)
finally:
    contract.write_bytes(fixed)
if contract.read_bytes() != fixed:
    raise RuntimeError("source not restored after mutation")

# Record the decision without rewriting any historical brain text.
marker = "PR1089-REVIEW-FOLLOWUP-20260928"
ledger = ROOT / SOURCE_PATHS[2]
if marker in ledger.read_text(encoding="utf-8"):
    raise RuntimeError("decision already recorded")
append(ledger, f'''

## 2026-09-28 — {marker}

- **القرار:** تثبيت هوية مصنوعتي الاعتماد بالزوج `(head_sha, run_attempt)` وعدم إعادة استخدام زوج من محاولة أقدم. توثيق الرقم في `$honesty_limit_ar` ونص المساعدة، مع شاهد انحدار على الحكم الصادر.
- **السبب:** إعادة تشغيل الوظائف الفاشلة وحدها لا تعيد بالضرورة منتج أدلة Live-PG؛ مطابقة SHA فقط تخلط هوية التنفيذ. رقم المحاولة جزء من الهوية لا معلومة عرض.
- **المصدر:** #1089؛ الرأس المراجع `{SOURCE}`؛ `scripts/ci/certify_artifact_contract.py`؛ `tests_v9/test_certify_artifact_contract.py`؛ `gaps/registry.md` تحت `{GAP}`. ملاحظات المراجعة: 4125271896، 4125271963، 4125272012.
- **إسناد القياس:** تُحفظ تعديلات المصدر والقرار في إيداع مستقل أولاً، ثم تُشغّل المولدات الرسمية على ذلك الإيداع النظيف وتُحفظ المصنوعات والبصمات في إيداع لاحق. `measured_on` يحدد إيداع المصدر المقيس، لا إيداع المخرجات الذي لم يوجد بعد القياس. تبقى سلطة الصلاحية بصمات أساس القياس وإعادة الاشتقاق؛ لا يُفرض ختم ذاتي مستحيل ولا تُعدّل البصمات يدوياً.
- **حد القبول:** source-fixed / post-run-runtime-unverified؛ غياب أدلة المحاولة المطلوبة ينتج absent لا اعتماداً. لا ترقية runtime_verified أو production_certified قبل قبول post-run جديد موقّع ومطابق، ولا تغيير خدمات أو بيانات أو Railway أو NATS.
''')
for name in ("hot.md", "log.md"):
    append(ROOT / "sahool-brain" / name, f'''

### متابعة مراجعة #1089 — 2026-09-28 — {marker}

الرأس المراجع `{SOURCE}`. أُلحق قرار السبب وحد القبول في `decisions/ledger.md`؛ يُوثق `run_attempt` في حكم المصنوعات ويقاس شاهد حذف ذكره. يعاد توليد القياسات بعد تثبيت المصدر ثم تبنى حزمة الإصدار أخيراً. تبقى `{GAP}` source-fixed / post-run-runtime-unverified، بلا ادعاء قبول حي.
''')
registry = ROOT / "sahool-brain/gaps/registry.md"
reg = registry.read_text(encoding="utf-8")
section = reg.rfind(f"## {GAP}")
if section < 0 or "\n## " in reg[section + 4:]:
    raise RuntimeError("gap is no longer the final section; review append location")
append(registry, f'''\n- **تتمة مراجعة (2026-09-28):** القرار وسببه مرجعهما `decisions/ledger.md` تحت `{marker}` (#1089، الرأس المراجع `{SOURCE}`). يُذكر `run_attempt` صراحة في حد صدق الحكم. إعادة إسناد المصنوعات تقاس على إيداع المصدر المثبت قبل توليدها، مع بقاء قيود أساس القياس وعدم ترقية القبول الحي.\n''')

# Commit sources before measuring them. The later output commit cannot truthfully name itself.
run("stage-source", ["git", "add", "--", *SOURCE_PATHS])
run("source-diff-check", ["git", "diff", "--cached", "--check"])
run("commit-source", ["git", "commit", "-m", "fix(ci): document attempt identity and record certification decision (#1089)"])
measured_source = git("rev-parse", "HEAD")
measured_tree = git("rev-parse", "HEAD^{tree}")
if git("status", "--porcelain"):
    raise RuntimeError("measurement must start from a clean committed source tree")

# First enforce the ratchets; regeneration must not silently accept new debt.
for generator in GENERATORS:
    path = "scripts/ci/" + generator
    run("before-" + generator, [sys.executable, path, "--check"])
for generator in GENERATORS:
    run("generate-" + generator, [sys.executable, "scripts/ci/" + generator, "--generate"])
run("stage-measurements", ["git", "add", "-A"])
run("generated-fix", [sys.executable, "scripts/ci/verify_all_generated.py", "--fix"], timeout=1500)
run("stage-generated", ["git", "add", "-A"])
run("release-build", [sys.executable, "scripts/release/build_release_bundle.py", "--root", "."])
run("release-validate", [sys.executable, "scripts/release/validate_release_package.py", "--root", "."])
measurements = {p: json.loads((ROOT / p).read_text(encoding="utf-8")) for p in MEASUREMENTS}
for path, data in measurements.items():
    if data.get("measured_on") != measured_source:
        raise RuntimeError(f"{path}: generator did not bind the committed source candidate")
if old_measurements[MEASUREMENTS[0]].get("offenders") != measurements[MEASUREMENTS[0]].get("offenders"):
    raise RuntimeError("tenant debt changed unexpectedly")
if old_measurements[MEASUREMENTS[2]].get("counts") != measurements[MEASUREMENTS[2]].get("counts"):
    raise RuntimeError("ownership debt changed unexpectedly")
write_json("measurements-after.json", measurements)
run("stage-final", ["git", "add", "-A"])
run("final-diff-check", ["git", "diff", "--cached", "--check"])
run("commit-generated", ["git", "commit", "-m", f"chore(generated): bind review measurements to source {measured_source[:12]}"])
run("generated-check", [sys.executable, "scripts/ci/verify_all_generated.py", "--check"], timeout=1500)
run("preflight", ["bash", "scripts/ci/preflight.sh", "--fast", "--no-fetch"],
    env={**os.environ, "BASE": MAIN}, timeout=1200)
run("release-final", [sys.executable, "scripts/release/validate_release_package.py", "--root", "."])
run("focused-final", [sys.executable, "-m", "pytest", "-q", str(test_path),
                     f"--junitxml={OUT / 'focused-final.xml'}"])
run("source-unchanged-after-measurement", ["git", "diff", "--exit-code", measured_source, "HEAD", "--", *SOURCE_PATHS])
run("runtime-unchanged", ["git", "diff", "--exit-code", MAIN, "HEAD", "--", "services/", "migrations/", "frontend/", "nginx/", "docker-compose*.yml"])
if git("ls-tree", "-r", "--name-only", "HEAD", ".github/repair-lab", ".github/workflows/pr1089-repair-lab.yml"):
    raise RuntimeError("repair controller entered the candidate")
if git("status", "--porcelain"):
    raise RuntimeError("final candidate is dirty")
run("impact-measure", [sys.executable, "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN,
                       "--head", "HEAD", "--output", str(OUT / "impact.json")], expected=(0, 1))
impact = json.loads((OUT / "impact.json").read_text(encoding="utf-8"))
body = "Capability-Impact: " + ", ".join(impact["direct"]) + "\n"
(OUT / "pr-body.txt").write_text(body, encoding="utf-8")
run("impact-declared", [sys.executable, "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN,
                        "--head", "HEAD", "--pr-number", "1089", "--pr-body-file", str(OUT / "pr-body.txt"),
                        "--output", str(OUT / "impact-declared.json")])
summary = {
    "reviewed_head": SOURCE, "main_sha": MAIN, "measured_source_sha": measured_source,
    "measured_source_tree": measured_tree, "candidate_sha": git("rev-parse", "HEAD"),
    "candidate_tree": git("rev-parse", "HEAD^{tree}"),
    "measurement_pins": {p: d["measured_on"] for p, d in measurements.items()},
    "changed_paths": git("diff", "--name-only", SOURCE, "HEAD").splitlines(),
    "declaration": body.strip(), "honesty_mutation_killed": True,
    "runtime_changed": False, "post_run_acceptance": "unverified",
    "candidate_published_to_pr": False,
}
write_json("summary.json", summary)
(OUT / "change.patch").write_text(subprocess.check_output(["git", "diff", SOURCE, "HEAD"], text=True, encoding="utf-8"), encoding="utf-8")
lines = [hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in sorted(OUT.iterdir()) if p.is_file()]
(OUT / "EVIDENCE_SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
