"""Isolated source repair; no Railway credentials or runtime access."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess

BASE = "52deac58088406be76b04a5216c2bddffb12cdcf"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "railway-rs256-evidence"
OUT.mkdir(parents=True, exist_ok=True)


def run(label, argv, expected=0, timeout=900):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    (OUT / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(json.dumps({"check": label, "exit_code": result.returncode, "expected": expected}), flush=True)
    if result.returncode != expected:
        raise RuntimeError(f"{label}: unexpected exit {result.returncode}; see retained log")
    return result.stdout.strip()


assert run("base", ["git", "rev-parse", "HEAD"]) == BASE
assert not run("clean-base", ["git", "status", "--porcelain"])
req = ROOT / "services/guardrails-engine/requirements.txt"
original = req.read_text(encoding="utf-8")
assert original.count("PyJWT>=2.13.0") == 1
unit = '''"""Guard the dependency needed by Guardrails' production RS256 verifier."""
from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_guardrails_declares_the_pyjwt_crypto_runtime_extra():
    path = ROOT / "services/guardrails-engine/requirements.txt"
    requirements = [
        Requirement(line.split("#", 1)[0].strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    pyjwt = [item for item in requirements if item.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1
    assert "crypto" in pyjwt[0].extras, "RS256 must be installed in the service image, not just the CI environment"
'''
unit_path = ROOT / "tests_v9/test_guardrails_crypto_dependency.py"
assert not unit_path.exists()
unit_path.write_text(unit, encoding="utf-8")
run("dependency-witness-before", ["python", "-m", "pytest", "-q", str(unit_path)], expected=1)
probe = '''import json, os, sys, time
sys.path.insert(0, "/app")
import jwt
assert "RS256" in jwt.algorithms.get_default_algorithms(), "RS256 backend unavailable in this runtime image"
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
os.environ["JWT_PUBLIC_KEY"] = public
os.environ["SAHOOL_ENV"] = "production"
os.environ["SAHOOL_AGENT_TOKEN"] = "isolated-rsa-image-test-token-not-for-deployment"
import main
claims = {"sub":"1", "tenant_id":"00000000-0000-4000-8000-000000000001", "role":"admin", "aud":"sahool", "iss":"sahool-auth", "exp":int(time.time())+120}
valid = jwt.encode(claims, key, algorithm="RS256")
assert main._gr_authn("Bearer " + valid)["tenant_id"] == claims["tenant_id"]
assert main._gr_verify("Bearer " + valid)["role"] == "admin"
invalid = [jwt.encode(claims, "isolated-hs256-test-key-not-for-deployment", algorithm="HS256"), jwt.encode(claims, rsa.generate_private_key(public_exponent=65537,key_size=2048), algorithm="RS256")]
for token in invalid:
    try:
        main._gr_authn("Bearer " + token)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("foreign or wrong-algorithm token was accepted")
print(json.dumps({"rs256_valid":"accepted", "hs256_under_rs256":"rejected_401", "foreign_rs256":"rejected_401", "scope":"isolated_image_no_network_no_live_credentials"}))
'''
probe_path = OUT / "probe_guardrails_rs256.py"
probe_path.write_text(probe, encoding="utf-8")


def build_and_probe(phase, sha, expected):
    image = "sahool-guardrails-rs256:" + phase
    run("build-"+phase, ["docker", "build", "-f", "services/guardrails-engine/Dockerfile", "--build-arg", "SAHOOL_GIT_SHA="+sha, "--build-arg", "SAHOOL_BUILD_ID=rs256-lab-"+phase, "--build-arg", "SAHOOL_SOURCE_REPOSITORY=kafaat/ai_platform_complete_v2.0.0_enhanced", "--build-arg", "SAHOOL_SOURCE_REF=isolated-rs256-lab", "-t", image, "."])
    run("image-id-"+phase, ["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    run("runtime-"+phase, ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp", "-v", str(OUT)+":/probe:ro", image, "python", "/probe/probe_guardrails_rs256.py"], expected=expected)
    if phase == "before":
        assert "RS256 backend unavailable in this runtime image" in (OUT / "runtime-before.log").read_text(), "before-failure must be the missing RSA backend, not a harness error"


build_and_probe("before", BASE, 1)
req.write_text(original.replace("PyJWT>=2.13.0", "PyJWT[crypto]>=2.13.0"), encoding="utf-8")
run("format", ["ruff", "format", str(unit_path)])
run("lint", ["ruff", "check", str(unit_path)])
run("dependency-witness-after", ["python", "-m", "pytest", "-q", str(unit_path)])
registry = ROOT / "sahool-brain/gaps/registry.md"
text = registry.read_text(encoding="utf-8")
heading = "## V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01"
start = text.index(heading)
end = text.find("\n## ", start + len(heading))
assert end > start
note = "\n- **2026-09-28 — Guardrails RS256 runtime dependency:** Railway staging review found that the image installs `PyJWT` without its `crypto` extra while the approval verifier selects RS256. Declare `PyJWT[crypto]>=2.13.0` and guard the runtime dependency. Scope: **source-fixed / Railway-runtime-unverified**; this does not provision JWT keys, authorize operations, or close the v25 umbrella. Isolated image checks use synthetic keys only; live auth-issued token acceptance remains required. Reference: `codex/railway-rs256-reviewed-20260928`, source base `" + BASE + "`.\n"
registry.write_text(text[:end] + note + text[end:], encoding="utf-8")
ledger = ROOT / "sahool-brain/decisions/ledger.md"
with ledger.open("a", encoding="utf-8") as f:
    f.write("\n\n## 2026-09-28 — RAILWAY-GUARDRAILS-RS256-DEPENDENCY-20260928\n\n- Decision: install PyJWT's crypto extra in Guardrails; never enable HS256 to mask a missing RSA backend.\n- Rationale: staging recovery exposed missing verifier material and the image's declared dependencies lacked the RSA backend. Environment configuration and image dependencies are separate acceptance gates.\n- Reference: `codex/railway-rs256-reviewed-20260928`, base `"+BASE+"`; isolated image evidence will be attached to the repair PR.\n- Boundary: synthetic RSA/HS256 proofs are not live Railway acceptance; no database, NATS, private-key, or production changes. The v25 umbrella remains open.\n")
for filename in ("hot.md", "log.md"):
    with (ROOT / "sahool-brain" / filename).open("a", encoding="utf-8") as f:
        f.write("\n\n### 2026-09-28 — Railway Guardrails RSA dependency repair\nSource-base `"+BASE+"`; see decision `RAILWAY-GUARDRAILS-RS256-DEPENDENCY-20260928` and V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01. Declare the service-image crypto dependency; keep Railway acceptance unverified.\n")
run("git-identity-name", ["git", "config", "user.name", "github-actions[bot]"])
run("git-identity-email", ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
run("stage-source", ["git", "add", "services/guardrails-engine/requirements.txt", "tests_v9/test_guardrails_crypto_dependency.py", "sahool-brain/gaps/registry.md", "sahool-brain/decisions/ledger.md", "sahool-brain/hot.md", "sahool-brain/log.md"])
run("commit-source", ["git", "commit", "-m", "fix(guardrails): declare RSA verifier runtime dependency"])
source_sha = run("source-sha", ["git", "rev-parse", "HEAD"])
build_and_probe("after", source_sha, 0)
run("generated-fix", ["python", "scripts/ci/verify_all_generated.py", "--fix"], timeout=1500)
run("stage-generated", ["git", "add", "-A"])
if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
    run("commit-generated", ["git", "commit", "-m", "chore(generated): bind Guardrails crypto dependency repair"])
run("generated-check", ["python", "scripts/ci/verify_all_generated.py"], timeout=1500)
run("release-check", ["python", "scripts/release/validate_release_package.py", "--root", "."])
run("final-unit", ["python", "-m", "pytest", "-q", str(unit_path)])
assert not run("clean-final", ["git", "status", "--porcelain"])
sha = run("candidate-sha", ["git", "rev-parse", "HEAD"])
tree = run("candidate-tree", ["git", "rev-parse", "HEAD^{tree}"])
run("diff-stat", ["git", "diff", "--stat", BASE, "HEAD"])
summary = {"base_sha":BASE,"source_sha":source_sha,"candidate_sha":sha,"tree_sha":tree,"before_image_probe_exit":1,"after_image_probe_exit":0,"scope":"isolated_image_and_generated_contracts_not_live_auth_acceptance"}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps(summary),flush=True)
