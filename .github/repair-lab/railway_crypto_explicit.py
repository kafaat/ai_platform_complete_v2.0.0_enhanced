"""Add the explicitly requested RSA backend and verify the actual service image."""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE = "6f2d4eaaf029a90626dabd58e734dc6e4acbb9a9"
MAIN = "52deac58088406be76b04a5216c2bddffb12cdcf"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "railway-crypto-explicit-evidence"
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
assert "PyJWT[crypto]>=2.13.0" in original
assert not any(line.strip().lower().startswith("cryptography") for line in original.splitlines())
test = ROOT / "tests_v9/test_guardrails_crypto_dependency.py"
test.write_text(test.read_text(encoding="utf-8") + '''\n\ndef test_guardrails_explicitly_declares_cryptography_for_rs256():
    path = ROOT / "services/guardrails-engine/requirements.txt"
    declared = {
        Requirement(line.split("#", 1)[0].strip()).name.lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }
    assert "cryptography" in declared, "The RSA runtime backend must be explicit"
''', encoding="utf-8")
run("explicit-witness-before", ["python", "-m", "pytest", "-q", str(test)], expected=1)
assert "test_guardrails_explicitly_declares_cryptography_for_rs256" in (OUT / "explicit-witness-before.log").read_text()
req.write_text(original + "cryptography>=44.0.0  # RSA backend for PyJWT RS256; matches the auth runtime minimum\n", encoding="utf-8")
run("format", ["ruff", "format", str(test)])
run("lint", ["ruff", "check", str(test)])
run("explicit-witness-after", ["python", "-m", "pytest", "-q", str(test)])
run("git-name", ["git", "config", "user.name", "github-actions[bot]"])
run("git-email", ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
run("stage-source", ["git", "add", "services/guardrails-engine/requirements.txt", "tests_v9/test_guardrails_crypto_dependency.py"])
run("commit-source", ["git", "commit", "-m", "fix(guardrails): explicitly install cryptography for RS256"])
source_sha = run("measured-source", ["git", "rev-parse", "HEAD"])

# Reuse the reviewed, literal isolated-image probe without executing its old controller.
old = Path(os.environ["RUNNER_TEMP"]) / "railway_rs256_probe_source.py"
probes = [ast.literal_eval(node.value) for node in ast.parse(old.read_text()).body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "probe" for target in node.targets)]
assert len(probes) == 1
probe = probes[0]
probe_path = OUT / "probe_guardrails_rs256.py"
probe_path.write_text(probe, encoding="utf-8")
image = "sahool-guardrails-rs256:explicit-cryptography"
run("build-image", ["docker", "build", "-f", "services/guardrails-engine/Dockerfile", "--build-arg", "SAHOOL_GIT_SHA=" + source_sha, "--build-arg", "SAHOOL_BUILD_ID=rs256-explicit-crypto-lab", "--build-arg", "SAHOOL_SOURCE_REPOSITORY=kafaat/ai_platform_complete_v2.0.0_enhanced", "--build-arg", "SAHOOL_SOURCE_REF=isolated-rs256-lab", "-t", image, "."])
image_id = run("image-id", ["docker", "image", "inspect", image, "--format", "{{.Id}}"])
run("runtime-rs256-contract", ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp", "-v", str(OUT) + ":/probe:ro", image, "python", "/probe/probe_guardrails_rs256.py"])
run("installed-crypto-version", ["docker", "run", "--rm", "--network", "none", "--read-only", image, "python", "-c", "import importlib.metadata,json;print(json.dumps({n:importlib.metadata.version(n) for n in ('PyJWT','cryptography')}))"])
run("generated-fix", ["python", "scripts/ci/verify_all_generated.py", "--fix"], timeout=1500)
run("stage-generated", ["git", "add", "-A"])
if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
    run("commit-generated", ["git", "commit", "-m", "chore(generated): bind explicit cryptography dependency"])
run("generated-check", ["python", "scripts/ci/verify_all_generated.py"], timeout=1500)
run("release-check", ["python", "scripts/release/validate_release_package.py", "--root", "."])
run("final-unit", ["python", "-m", "pytest", "-q", str(test)])
sha = run("candidate-sha", ["git", "rev-parse", "HEAD"])
tree = run("candidate-tree", ["git", "rev-parse", "HEAD^{tree}"])
run("diff-stat", ["git", "diff", "--stat", MAIN, "HEAD"])
impact = subprocess.run(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", MAIN, "--head", sha, "--output", str(OUT / "capability-impact.json")], cwd=ROOT, capture_output=True, text=True, timeout=120)
(OUT / "capability-impact.log").write_text(impact.stdout + impact.stderr)
assert impact.returncode in (0, 1)
payload = json.loads((OUT / "capability-impact.json").read_text())
assert isinstance(payload["direct"], list)
body = "Capability-Impact: " + ", ".join(payload["direct"]) + "\n"
(OUT / "proposed-pr-declaration.txt").write_text(body)
assert not run("clean-final", ["git", "status", "--porcelain"])
summary = {"main_sha": MAIN, "previous_candidate_sha": SOURCE, "source_sha": source_sha, "candidate_sha": sha, "tree_sha": tree, "image_id": image_id, "probe_sha256": hashlib.sha256(probe.encode()).hexdigest(), "explicit_requirement": "cryptography>=44.0.0", "rs256_valid": "accepted", "hs256_under_rs256": "rejected_401", "foreign_rs256": "rejected_401", "scope": "isolated_image_no_live_credentials_no_Railway_mutation"}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
run("candidate-bundle", ["git", "bundle", "create", str(OUT / "candidate.bundle"), MAIN + "..HEAD"])
print(json.dumps(summary), flush=True)
