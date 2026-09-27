"""Apply the already-approved PR1087 appendix in a pinned, isolated checkout.

Never updates refs. Publication creates Git objects only; the connector separately
performs the final non-force PR ref update after checking the returned evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO = "kafaat/ai_platform_complete_v2.0.0_enhanced"
SOURCE = "1111d2bc44a6b3fb46c2b4937ae6c6684a5ea5c2"
BASE = "637279076eff14a30fbbc75b2cb104cac805cdfd"
TARGET = "codex/consumer-evidence-20260927"
ORIGINAL = "e35aeabb22acfab775fefd0d5031d1aa653e2662"
UPDATED = "d2e3ecbfc2c33fd254fea021312b0bac8163c17f"
REGISTRY = "sahool-brain/gaps/registry.md"
GAP = "FRONTEND-CONSUMER-EVIDENCE-BINDING-UNSOUND-01"
PATCH_HASH = "9b79e6cd8c9594b692da359a994bd9a79bc3ae55051afb864a6aef897d53fa89"
ROOT = Path.cwd()
OUT = Path(os.environ["RUNNER_TEMP"]) / "pr1087-registry-evidence"
OUT.mkdir(exist_ok=True)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(label, argv, timeout=1800):
    print(f"BEGIN {label}", flush=True)
    with (OUT / f"{label}.log").open("w", encoding="utf-8") as output:
        result = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    print((OUT / f"{label}.log").read_text(encoding="utf-8", errors="replace")[-9000:], flush=True)
    require(result.returncode == 0, f"{label} failed: {result.returncode}")
    print(f"PASS {label}", flush=True)


def api(endpoint, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{endpoint}",
        data=data,
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def prepare(patch):
    require(git("rev-parse", "HEAD") == SOURCE, "source_head_changed")
    require(git("rev-parse", "HEAD^{tree}") == "e029f639f6aff154213596b8e2c5e0dee97b5614", "source_tree_changed")
    require(not git("status", "--porcelain"), "source_checkout_not_clean")
    require(hashlib.sha256(patch.read_bytes()).hexdigest() == PATCH_HASH, "append_patch_mismatch")
    require(git("hash-object", REGISTRY) == ORIGINAL, "registry_identity_mismatch")
    before_bytes = (ROOT / REGISTRY).read_bytes()
    require(before_bytes.count(GAP.encode()) == 0, "duplicate_gap_id")
    require(git("hash-object", "scripts/ci/gap_registry_measure.py") == "22832339b7665676e8f8484e3886816510a5ae31", "measurement_tool_changed")
    git("checkout", "-B", TARGET, SOURCE)
    run("stability-before", ["python", "scripts/ops/pre_push_stability_guard.py", "--allow-dirty"])
    measure = load_module("registry_measure_for_apply", "scripts/ci/gap_registry_measure.py")
    before = measure.measure(before_bytes.decode("utf-8"))
    run("append-check", ["git", "apply", "--check", str(patch)])
    run("append-apply", ["git", "apply", str(patch)])
    after_bytes = (ROOT / REGISTRY).read_bytes()
    require(after_bytes.startswith(before_bytes), "append_changed_history")
    require(git("hash-object", REGISTRY) == UPDATED, "append_output_mismatch")
    require(after_bytes.count(GAP.encode()) == 1, "nonunique_gap_id")
    after = measure.measure(after_bytes.decode("utf-8"))
    require(after["heading_count"] == before["heading_count"] + 1, "heading_delta")
    require(after["section_state_count"] == before["section_state_count"] + 1, "state_delta")
    for key in before:
        if key not in {"heading_count", "section_state_count"}:
            require(before[key] == after[key], f"unexpected_measurement_delta:{key}")
    write("registry-before.json", before)
    write("registry-after.json", after)
    write("append-receipt.json", {"source_head": SOURCE, "registry_before": ORIGINAL, "registry_after": UPDATED, "gap": GAP, "state": "fixed", "history_preserved": True, "new_bytes": len(after_bytes) - len(before_bytes)})
    git("add", "--", REGISTRY)
    run("generated-fixed-point", ["bash", "scripts/ci/regenerate_all_generated.sh"])
    require(git("hash-object", REGISTRY) == UPDATED, "generator_changed_registry")
    classifier = load_module("conflict_classifier_for_apply", "scripts/ci/resolve_merge_conflicts.py")
    paths = git("diff", "--name-only", SOURCE).splitlines()
    require(REGISTRY in paths, "append_not_in_diff")
    classes = {p: classifier.classify(p) for p in paths}
    require(all(p == REGISTRY or classes[p] == "generated" for p in paths), f"unexpected_nongenerated_change:{classes}")
    require(not any(p.startswith(("services/", "migrations/", "scripts/", ".github/")) for p in paths), "source_or_runtime_changed")
    for path in ("docs/architecture/db_writer_ownership_baseline.json", "docs/architecture/db_writer_ownership_triage.json"):
        if path in paths:
            old = json.loads(git("show", f"{SOURCE}:{path}"))
            new = json.loads((ROOT / path).read_text(encoding="utf-8"))
            old.pop("measured_on", None)
            new.pop("measured_on", None)
            require(old == new, f"ownership_semantics_changed:{path}")
    write("changed-paths.json", classes)
    git("add", "--", *paths)
    run("diff-check", ["git", "diff", "--cached", "--check"])
    sys.path.insert(0, str(ROOT / "scripts/ci"))
    from capability_impact import compute
    impact = compute(git("diff", "--name-only", BASE).splitlines())
    write("capability-impact.json", impact)
    declaration = "ALL" if impact["governance_wide"] else ", ".join(impact["direct"]) or "NONE"
    (OUT / "pr-body.txt").write_text(f"Capability-Impact: {declaration}\n", encoding="utf-8")
    git("config", "user.name", "PR1087 Registry Automation")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("commit", "-m", "docs(gaps): register bounded consumer evidence fix and refresh generated artifacts")
    local = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    run("targeted-tests", ["python", "-m", "pytest", "-q", "tests_v9/test_resolve_inventory_edges.py", "tests_v9/test_main_inventory_generator.py", "tests_v9/test_gap_registry_claim_guard.py", "tests_v9/test_text_encoding_locale.py", "tests/architecture/test_gap_registry_measure.py", "tests_v9/test_gap_heading_state_guard.py", "tests_v9/test_brain_append_only_guard.py", f"--junitxml={OUT / 'targeted-tests.xml'}"])
    run("preflight", ["bash", "scripts/ci/preflight.sh", "--no-fetch", "--pr-body-file", str(OUT / "pr-body.txt")], timeout=2400)
    run("generated-final", ["python", "scripts/ci/verify_all_generated.py", "--check"])
    run("release-final", ["python", "scripts/release/validate_release_package.py"])
    run("stability-final", ["python", "scripts/ops/pre_push_stability_guard.py"])
    require(not git("status", "--porcelain"), "posttests_tree_changed")
    require(git("rev-parse", "HEAD^{tree}") == tree, "final_tree_changed")
    patch_bytes = subprocess.check_output(["git", "diff", "--binary", SOURCE, "HEAD"], cwd=ROOT)
    (OUT / "applied-complete.patch").write_bytes(patch_bytes)
    for path in paths:
        dest = OUT / "changed-files" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / path).read_bytes())
    author = git("show", "-s", "--format=%an%n%ae%n%aI", local).splitlines()
    write("candidate.json", {"repository": REPO, "target_branch": TARGET, "source_head": SOURCE, "base": BASE, "local_commit": local, "tree": tree, "paths": paths, "author": {"name": author[0], "email": author[1], "date": author[2]}, "message": git("show", "-s", "--format=%B", local), "capability_impact": declaration, "no_ref_update": True})


def publish_objects():
    candidate = json.loads((OUT / "candidate.json").read_text(encoding="utf-8"))
    require(git("rev-parse", "HEAD^{tree}") == candidate["tree"], "publication_tree_mismatch")
    require(not git("status", "--porcelain"), "publication_checkout_not_clean")
    require(api(f"git/ref/heads/{TARGET}")["object"]["sha"] == SOURCE, "remote_pr_head_changed")
    require(api("git/ref/heads/main")["object"]["sha"] == BASE, "remote_main_changed")
    pr = api("pulls/1087")
    require(pr["state"] == "open" and pr["head"]["sha"] == SOURCE and pr["draft"], "pr_state_changed")
    entries = []
    for path in candidate["paths"]:
        data = (ROOT / path).read_bytes()
        created = api("git/blobs", {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        require(created["sha"] == git("hash-object", path), f"remote_blob_mismatch:{path}")
        mode = git("ls-files", "-s", "--", path).split()[0]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": created["sha"]})
    created_tree = api("git/trees", {"base_tree": git("rev-parse", f"{SOURCE}^{{tree}}"), "tree": entries})
    require(created_tree["sha"] == candidate["tree"], "remote_tree_mismatch")
    commit = api("git/commits", {"message": candidate["message"], "tree": created_tree["sha"], "parents": [SOURCE], "author": candidate["author"], "committer": candidate["author"]})
    require(commit["tree"]["sha"] == candidate["tree"], "remote_commit_tree_mismatch")
    require([p["sha"] for p in commit["parents"]] == [SOURCE], "remote_commit_parent_mismatch")
    write("publication.json", {**candidate, "created_commit": commit["sha"], "created_at": datetime.now(timezone.utc).isoformat(), "remote_tree_match": True, "pr_branch_updated": False, "main_updated": False})
    print(f"VERIFIED_CANDIDATE_COMMIT={commit['sha']}", flush=True)
    print(f"VERIFIED_CANDIDATE_TREE={candidate['tree']}", flush=True)
    print(f"Capability-Impact: {candidate['capability_impact']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--publish-objects", action="store_true")
    args = parser.parse_args()
    try:
        if args.prepare:
            prepare(args.prepare.resolve())
        elif args.publish_objects:
            publish_objects()
        else:
            raise RuntimeError("mode_required")
    except Exception as exc:
        write("failure.json", {"type": type(exc).__name__, "error": str(exc)[:1000], "pr_branch_updated": False})
        raise
