"""Pinned repair for PR1091; no Railway access, secrets, or application data."""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE = "f6cd3f5532a816d29192461e65d3f0f2bd41b0ae"
MAIN = "52deac58088406be76b04a5216c2bddffb12cdcf"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "railway-crypto-pin-evidence"
OUT.mkdir(parents=True, exist_ok=True)


def run(label, args, expected=0, timeout=900):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    (OUT / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(json.dumps({"check": label, "exit_code": result.returncode, "expected": expected}), flush=True)
    if result.returncode != expected:
        raise RuntimeError(f"{label}: unexpected exit {result.returncode}; see retained log")
    return result.stdout.strip()


assert run("source-head", ["git", "rev-parse", "HEAD"]) == SOURCE
assert not run("source-clean", ["git", "status", "--porcelain"])
req = ROOT / "services/guardrails-engine/requirements.txt"
original = req.read_text(encoding="utf-8")
assert original.count("cryptography>=44.0.0") == 1
assert "PyJWT[crypto]>=2.13.0" in original
ratchet = ROOT / "tests_v9/test_requirements_pinning_guard.py"
ratchet_sha256 = hashlib.sha256(ratchet.read_bytes()).hexdigest()
run("reported-failure-before", ["python", "-m", "pytest", "-q", str(ratchet) + "::test_unpinned_count_does_not_grow"], expected=1)
assert "9" in (OUT / "reported-failure-before.log").read_text()
test = ROOT / "tests_v9/test_guardrails_crypto_dependency.py"
test.write_text(test.read_text(encoding="utf-8") + '''\n\ndef test_guardrails_cryptography_keeps_an_exact_version_pin():
    path = ROOT / "services/guardrails-engine/requirements.txt"
    requirements = [
        Requirement(line.split("#", 1)[0].strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    crypto = [item for item in requirements if item.name.lower() == "cryptography"]
    assert len(crypto) == 1, "Exactly one explicit RSA backend requirement is required"
    pin = list(crypto[0].specifier)
    assert len(pin) == 1 and pin[0].operator == "==" and "*" not in pin[0].version, (
        "The new RSA backend must remain exactly pinned without increasing unpinned debt"
    )
''', encoding="utf-8")
run("new-pin-witness-before", ["python", "-m", "pytest", "-q", str(test) + "::test_guardrails_cryptography_keeps_an_exact_version_pin"], expected=1)
req.write_text(original.replace("cryptography>=44.0.0  # RSA backend for PyJWT RS256; matches the auth runtime minimum", "cryptography==50.0.1  # RSA backend pinned to the version measured in the repair image"), encoding="utf-8")
assert "cryptography==50.0.1" in req.read_text()
run("format", ["ruff", "format", str(test)])
run("lint", ["ruff", "check", str(test)])
run("pin-and-ratchet-after", ["python", "-m", "pytest", "-q", str(test), str(ratchet)])
fixed = req.read_bytes()
try:
    req.write_text(req.read_text().replace("cryptography==50.0.1", "cryptography>=50.0.1"))
    run("unpinned-mutation", ["python", "-m", "pytest", "-q", str(test) + "::test_guardrails_cryptography_keeps_an_exact_version_pin", str(ratchet) + "::test_unpinned_count_does_not_grow"], expected=1)
    assert "2 failed" in (OUT / "unpinned-mutation.log").read_text()
finally:
    req.write_bytes(fixed)
assert hashlib.sha256(ratchet.read_bytes()).hexdigest() == ratchet_sha256
run("git-name", ["git", "config", "user.name", "github-actions[bot]"])
run("git-email", ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
run("stage-source", ["git", "add", "services/guardrails-engine/requirements.txt", "tests_v9/test_guardrails_crypto_dependency.py"])
run("commit-source", ["git", "commit", "-m", "fix(guardrails): pin cryptography without increasing dependency debt"])
source_sha = run("measured-source", ["git", "rev-parse", "HEAD"])
old = Path(os.environ["RUNNER_TEMP"]) / "railway_rs256_probe_source.py"
probes = [ast.literal_eval(node.value) for node in ast.parse(old.read_text()).body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "probe" for target in node.targets)]
assert len(probes) == 1
probe = probes[0]
(OUT / "probe_guardrails_rs256.py").write_text(probe)
image = "sahool-guardrails-rs256:pinned-cryptography"
run("build-image", ["docker", "build", "-f", "services/guardrails-engine/Dockerfile", "--build-arg", "SAHOOL_GIT_SHA=" + source_sha, "--build-arg", "SAHOOL_BUILD_ID=rs256-crypto-pin-lab", "--build-arg", "SAHOOL_SOURCE_REPOSITORY=kafaat/ai_platform_complete_v2.0.0_enhanced", "--build-arg", "SAHOOL_SOURCE_REF=isolated-rs256-pin-lab", "-t", image, "."])
image_id = run("image-id", ["docker", "image", "inspect", image, "--format", "{{.Id}}"])
run("runtime-rs256-contract", ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp", "-v", str(OUT) + ":/probe:ro", image, "python", "/probe/probe_guardrails_rs256.py"])
versions = json.loads(run("installed-versions", ["docker", "run", "--rm", "--network", "none", "--read-only", image, "python", "-c", "import importlib.metadata,json;print(json.dumps({n:importlib.metadata.version(n) for n in ('PyJWT','cryptography')}))"]))
assert versions["cryptography"] == "50.0.1"
run("image-pip-check", ["docker", "run", "--rm", "--network", "none", "--read-only", image, "python", "-m", "pip", "check"])
run("generated-fix", ["python", "scripts/ci/verify_all_generated.py", "--fix"], timeout=1500)
run("stage-generated", ["git", "add", "-A"])
if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
    run("commit-generated", ["git", "commit", "-m", "chore(generated): bind pinned crypto dependency and release checksums"])
run("generated-check", ["python", "scripts/ci/verify_all_generated.py"], timeout=1500)
run("release-check", ["python", "scripts/release/validate_release_package.py", "--root", "."])
run("final-targeted-suite", ["python", "-m", "pytest", "-q", str(test), str(ratchet), "tests/ci/test_phase16_ci_cd_gates.py", "tests/deploy/test_phase15_deployment_readiness_contracts.py", "tests/release/test_phase14_release_packaging_contracts.py", "tests/observability/test_phase13_observability_assets.py", "tests/security/test_phase12_final_production_gates.py"])
assert hashlib.sha256(ratchet.read_bytes()).hexdigest() == ratchet_sha256
assert not run("clean-final", ["git", "status", "--porcelain"])
sha = run("candidate-sha", ["git", "rev-parse", "HEAD"])
tree = run("candidate-tree", ["git", "rev-parse", "HEAD^{tree}"])
run("diff-stat", ["git", "diff", "--stat", SOURCE, "HEAD"])
impact = subprocess.run(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN, "--head", sha, "--output", str(OUT / "capability-impact.json")], cwd=ROOT, capture_output=True, text=True, timeout=120)
(OUT / "capability-impact.log").write_text(impact.stdout + impact.stderr)
assert impact.returncode in (0,1)
payload = json.loads((OUT / "capability-impact.json").read_text())
assert payload["direct"]
(OUT / "pr-body.txt").write_text("Capability-Impact: " + ", ".join(payload["direct"]) + "\n")
run("impact-declaration-check", ["python", "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN, "--head", sha, "--pr-number", "1091", "--pr-body-file", str(OUT / "pr-body.txt"), "--output", str(OUT / "capability-impact-verified.json")])
summary = {"base_sha":MAIN,"previous_pr_head":SOURCE,"source_sha":source_sha,"candidate_sha":sha,"tree_sha":tree,"image_id":image_id,"versions":versions,"ratchet_file_unchanged":True,"reported_failure_reproduced":True,"pin_witness_failed_before":True,"unpinned_mutation_killed_by_two_tests":True,"probe_sha256":hashlib.sha256(probe.encode()).hexdigest(),"scope":"isolated_image_source_and_generated_artifacts_not_Railway_acceptance"}
(OUT / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
run("candidate-bundle", ["git", "bundle", "create", str(OUT / "candidate.bundle"), SOURCE + "..HEAD"])
print(json.dumps(summary), flush=True)
