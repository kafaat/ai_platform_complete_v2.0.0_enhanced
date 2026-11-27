"""Rebuild the exact inspection input, qualify a new candidate, and retain it.

This runner may update only its configured temporary CI branch. It never updates
an application branch or claims that the historical browser measured this build.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

WORK = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).parent)).resolve()
TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
SOURCE = TEMP / "inspection-source"
OUT = TEMP / "inspection-build-evidence"
CONFIG = json.loads((WORK / "build-manifest.json").read_text(encoding="utf-8"))
CLASSIFIER = "scripts/ci/resolve_merge_conflicts.py"
BUDGET = "docs/architecture/brain_hot_budget.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_state() -> dict:
    return json.loads((OUT / "build-state.json").read_text(encoding="utf-8"))


def git(*args: str, cwd: Path = SOURCE, data: bytes | None = None) -> bytes:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, input=data)
    except subprocess.CalledProcessError as exc:
        # stderr is already inherited; diff --check writes its diagnosis to stdout.
        if exc.output:
            sys.stderr.write(exc.output.decode("utf-8", errors="replace"))
            sys.stderr.flush()
        raise


def gt(*args: str, cwd: Path = SOURCE) -> str:
    return git(*args, cwd=cwd).decode("utf-8").strip()


def git_paths(*args: str) -> list[str]:
    return [p.decode("utf-8") for p in git(*args, "-z").split(b"\0") if p]


def file_bytes(path: str) -> bytes:
    parts = PurePosixPath(path)
    require(not parts.is_absolute() and ".." not in parts.parts and str(parts) == path, f"Unsafe path: {path}")
    target = SOURCE / path
    require(target.is_file() and not target.is_symlink(), f"Expected regular source file: {path}")
    require(target.resolve().is_relative_to(SOURCE), f"Source path escapes checkout: {path}")
    return target.read_bytes()


def file_hashes(paths: list[str]) -> dict[str, str]:
    return {path: sha256(file_bytes(path)) for path in sorted(set(paths))}


def run_logged(args: list[str], name: str, cwd: Path = SOURCE) -> dict:
    require(not (OUT / (name + "-receipt.json")).exists(), f"Refusing to overwrite command evidence: {name}")
    record = {"argv": args, "cwd": str(cwd), "started_at_utc": now(), "status": "RUNNING"}
    write_json(name + "-receipt.json", record)
    log_path = OUT / (name + ".log")
    child_env = {**os.environ, "BASE": CONFIG["main"], "PYTHONDONTWRITEBYTECODE": "1"}
    with log_path.open("xb") as log:
        proc = subprocess.Popen(args, cwd=cwd, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(proc.stdout is not None, "Missing subprocess output")
        for line in iter(proc.stdout.readline, b""):
            log.write(line)
            log.flush()
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        code = proc.wait()
    record.update(returncode=code, finished_at_utc=now(), log_sha256=sha256(log_path.read_bytes()),
                  status="PASS" if code == 0 else "FAIL")
    write_json(name + "-receipt.json", record)
    return record


def verify_transport() -> None:
    branch = CONFIG["transport_branch"]
    require(branch.startswith("ci/field-inspection-build-"), "Unexpected retention namespace")
    require(os.environ.get("GITHUB_REF_NAME") == branch, "Unexpected transport branch")
    require(os.environ.get("GITHUB_REPOSITORY") == CONFIG["repository"], "Unexpected repository")
    require(gt("rev-parse", "HEAD", cwd=WORK) == os.environ["GITHUB_SHA"], "Transport checkout drift")
    require(gt("rev-parse", "--is-shallow-repository", cwd=WORK) == "false", "Transport requires complete Git history")
    require(CONFIG["production_accepted"] is False and CONFIG["source_ref_updated"] is False,
            "Builder cannot grant production acceptance or update source refs")


def correction_specs() -> dict:
    specs = CONFIG["source_corrections"]
    require(isinstance(specs, dict) and specs, "Missing reviewed source corrections")
    forbidden = set(CONFIG["protected_control_sha256"]) | set(CONFIG["upstream_source_files"])
    for path, spec in specs.items():
        require(isinstance(path, str), "Correction path must be text")
        parts = PurePosixPath(path)
        require(not parts.is_absolute() and ".." not in parts.parts and str(parts) == path,
                f"Unsafe correction path: {path}")
        require(all(part.casefold() != ".git" for part in parts.parts),
                f"Correction cannot address Git metadata: {path}")
        current = SOURCE
        for part in parts.parts:
            current = current / part
            require(not current.is_symlink(), f"Correction cannot traverse a symlink: {path}")
        require(path not in forbidden and not path.startswith("sahool-brain/"),
                f"Source correction cannot change a pinned control, upstream source or brain journal: {path}")
        require(isinstance(spec, dict) and set(spec) == {"before_sha256", "after_sha256"},
                f"Invalid correction hash contract: {path}")
        require(all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
                    for value in spec.values()), f"Invalid correction digest: {path}")
        require(spec["before_sha256"] != spec["after_sha256"], f"Empty source correction: {path}")
        file_bytes(path)
    return specs


def apply_source_corrections() -> dict:
    require(CONFIG["source_corrections_file"] == "source-corrections.json", "Unexpected correction payload name")
    target = WORK / CONFIG["source_corrections_file"]
    require(target.is_file() and not target.is_symlink(), "Correction payload must be a regular file")
    raw = target.read_bytes()
    require(sha256(raw) == CONFIG["source_corrections_sha256"], "Reviewed source correction payload changed")
    payload = json.loads(raw)
    require(set(payload) == {"schema", "failed_source", "files"}
            and payload["schema"] == "sahool.inspection-source-corrections/v1",
            "Unexpected correction payload envelope")
    require(payload["failed_source"] == CONFIG["correction_failure_source"], "Correction failure identity differs")
    require(payload["failed_source"]["status"] == "PREFLIGHT_FAIL", "Corrections must preserve the failed source verdict")
    specs = correction_specs()
    rows = payload["files"]
    require(isinstance(rows, list) and len(rows) == len(specs), "Correction file count differs")
    names = [row["path"] for row in rows]
    require(len(set(names)) == len(names) and set(names) == set(specs), "Correction path set differs")
    pending = {}
    for row in rows:
        require(set(row) == {"path", "encoding", "content"} and row["encoding"] == "utf-8"
                and isinstance(row["content"], str), "Unexpected correction file payload")
        path = row["path"]
        before = file_bytes(path)
        after = row["content"].encode("utf-8")
        require(sha256(before) == specs[path]["before_sha256"], f"Correction baseline drift: {path}")
        require(sha256(after) == specs[path]["after_sha256"], f"Correction content drift: {path}")
        pending[path] = after
    # Validate every path and both hashes before making the first owned-checkout write.
    for path, data in pending.items():
        (SOURCE / path).write_bytes(data)
    require(file_hashes(names) == {path: specs[path]["after_sha256"] for path in names},
            "Applied source correction bytes differ")
    shutil.copyfile(target, OUT / CONFIG["source_corrections_file"])
    receipt = {"status": "APPLIED_PENDING_GENERATION_AND_PREFLIGHT", "files": specs,
               "payload_sha256": sha256(raw), "failed_source": payload["failed_source"],
               "historical_source_verdict_unchanged": True, "production_accepted": False}
    write_json("source-corrections-receipt.json", receipt)
    return receipt


def review_inputs(*, corrected: bool = True) -> dict:
    checks = []
    for path, expected in CONFIG["guard_sha256"].items():
        original = expected
        if corrected and path in CONFIG["source_corrections"]:
            expected = CONFIG["source_corrections"][path]["after_sha256"]
        actual = sha256(file_bytes(path))
        require(actual == expected, f"Reviewed guard source differs: {path}")
        checks.append({"path": path, "sha256": actual, "original_sha256": original,
                       "original_reference_tree": CONFIG["reconstructed_tree"],
                       "reviewed_correction_applied": corrected and actual != original, "status": "PASS"})
    if corrected:
        for path, spec in correction_specs().items():
            require(sha256(file_bytes(path)) == spec["after_sha256"], f"Reviewed source correction drift: {path}")
    for path, expected in CONFIG["upstream_source_files"].items():
        actual = file_bytes(path)
        require(actual == git("show", f"{CONFIG['main']}:{path}"), f"Pinned salinity/upstream source changed: {path}")
        require(sha256(actual) == expected["working_sha256"], f"Pinned upstream SHA256 mismatch: {path}")
        checks.append({"path": path, "sha256": sha256(actual), "reference_commit": CONFIG["main"], "status": "PASS"})
    for path, expected in CONFIG["protected_control_sha256"].items():
        require(sha256(file_bytes(path)) == expected, f"Qualification control changed: {path}")
    return {"status": "PASS", "checks": checks, "control_sha256": CONFIG["protected_control_sha256"],
            "historical_browser_tree": CONFIG["historical_browser"]["tree"],
            "final_browser_measured": False, "production_accepted": False}


def generated_inventory() -> list[str]:
    """Use the pinned repository classifier plus three explicitly owned outputs."""
    spec = importlib.util.spec_from_file_location("inspection_pinned_classifier", SOURCE / CLASSIFIER)
    require(spec is not None and spec.loader is not None, "Cannot load repository classifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    paths = git_paths("ls-files")
    generated = {path for path in paths if module.classify(path) == "generated"}
    for path, owner in CONFIG["extra_generated_paths"].items():
        require(path in paths, f"Unknown explicitly owned output: {path}")
        require(owner in CONFIG["protected_control_sha256"], f"Unpinned generator owner: {owner}")
        generated.add(path)
    generated -= set(CONFIG["protected_control_paths"])
    require(set(CONFIG["expected_generated_conflicts"]) <= generated, "A reviewed generated conflict became source")
    require(not (set(CONFIG["guard_sha256"]) & generated), "Guard source misclassified as generated")
    return sorted(generated)


def apply_brain_updates() -> dict:
    raw = (WORK / CONFIG["brain_updates_file"]).read_bytes()
    require(sha256(raw) == CONFIG["brain_updates_sha256"], "Brain update draft changed")
    draft = json.loads(raw)
    require(draft["base"] == CONFIG["main"] and draft["gap_id"] == CONFIG["gap_id"], "Brain draft identity mismatch")
    registry = "sahool-brain/gaps/registry.md"
    require(CONFIG["gap_id"].encode() not in file_bytes(registry), "Gap already exists; review instead of duplicating it")
    receipt = {}
    for path, entry in draft["entries"].items():
        old = file_bytes(path)
        require(sha256(old) == draft["expected_original_sha256"][path], f"Brain source changed before append: {path}")
        addition = entry["text"].encode("utf-8")
        if entry["mode"] == "prepend":
            require(path == "sahool-brain/hot.md", "Only hot.md permits prepending")
            new = addition + old
            require(new.endswith(old), "Hot journal bytes were removed")
        else:
            require(entry["mode"] == "append", "Unexpected brain edit mode")
            new = old + addition
            require(new.startswith(old), "Append-only journal bytes were removed")
        (SOURCE / path).write_bytes(new)
        receipt[path] = {"mode": entry["mode"], "before_sha256": sha256(old),
                         "after_sha256": sha256(new), "added_bytes": len(addition)}
    budget = json.loads(file_bytes(BUDGET))["budgets"]["sahool-brain/hot.md"]["max_bytes"]
    require(len(file_bytes("sahool-brain/hot.md")) <= budget, "Hot journal exceeds the unchanged repository budget")
    section = file_bytes(registry).decode("utf-8").split("## " + CONFIG["gap_id"], 1)[1]
    require("open" in section.split("\n## ", 1)[0], "Final-source qualification gap must remain open")
    return receipt


def configure_csv_whitespace_policy() -> None:
    """Honor the pinned CSV byte policy in this fresh clone's private Git metadata."""
    policy = file_bytes(".gitattributes")
    require(policy == git("show", f"{CONFIG['main']}:.gitattributes"),
            "Repository attributes differ from pinned main")
    require(any(line.split() == [b"*.csv", b"-text"] for line in policy.splitlines()),
            "Pinned repository does not preserve generator-owned CSV line endings")
    attributes = SOURCE / ".git" / "info" / "attributes"
    require(attributes.parent.is_dir() and not attributes.is_symlink(),
            "Expected private attributes in the fresh owned clone")
    require(attributes.parent.resolve().is_relative_to((SOURCE / ".git").resolve()),
            "Private Git attributes escape the owned clone")
    existed = attributes.exists()
    original = attributes.read_bytes() if existed else b""
    require(not original.strip(), "Unexpected inherited private Git attributes; review required")
    rule = "blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol"
    content = f"*.csv whitespace={rule}\n".encode()
    attributes.write_bytes(content)
    csv = gt("check-attr", "whitespace", "--", "__inspection_policy_probe.csv")
    other = gt("check-attr", "whitespace", "--", "__inspection_policy_probe.py")
    require(csv.endswith(": " + rule) and other.endswith(": unspecified"),
            "Private whitespace policy must affect CSV only")
    write_json("whitespace-policy.json", {
        "status": "APPLIED",
        "repository_policy_commit": CONFIG["main"],
        "repository_policy_path": ".gitattributes",
        "repository_policy_sha256": sha256(policy),
        "repository_policy_reason": "CRLF-PHANTOM-ARTIFACT-DRIFT-01: CSV bytes retain their generator's LF or CRLF.",
        "scope": "Fresh owned SOURCE clone .git/info/attributes; *.csv only.",
        "attributes_relative_path": ".git/info/attributes",
        "original_attributes_existed": existed,
        "original_attributes_sha256": sha256(original),
        "applied_rule": content.decode().rstrip("\n"),
        "applied_attributes_sha256": sha256(content),
        "retained_checks": ["blank-at-eol", "blank-at-eof", "space-before-tab"],
        "csv_line_ending_recognition": "cr-at-eol",
        "non_csv_check_attr": other,
        "git_diff_check_command": ["git", "diff", "--cached", "--check"],
        "source_or_generated_bytes_modified": False,
        "production_accepted": False,
    })


def prepare() -> None:
    verify_transport()
    require(not SOURCE.exists() and not OUT.exists(), "Use a fresh attempt; previous source/evidence must be preserved")
    OUT.mkdir(parents=True)
    for name in ("build-manifest.json", "brain-updates.json", "build_candidate.py"):
        shutil.copyfile(WORK / name, OUT / name)
    compressed = (WORK / CONFIG["patch_file"]).read_bytes()
    require(len(compressed) == CONFIG["patch_gzip_bytes"] and sha256(compressed) == CONFIG["patch_gzip_sha256"],
            "Input gzip size or SHA256 mismatch")
    require(gt("hash-object", CONFIG["patch_file"], cwd=WORK) == CONFIG["patch_blob"], "Input gzip Git blob mismatch")
    patch = gzip.decompress(compressed)
    require(len(patch) == CONFIG["patch_bytes"] and sha256(patch) == CONFIG["patch_sha256"], "Input patch identity mismatch")
    patch_path = OUT / "verified-input.patch"
    patch_path.write_bytes(patch)
    for commit, tree in ((CONFIG["base_5037"], CONFIG["base_5037_tree"]), (CONFIG["main"], CONFIG["main_tree"])):
        require(gt("rev-parse", f"{commit}^{{tree}}", cwd=WORK) == tree, f"Pinned source tree mismatch: {commit}")
    require(gt("show", "-s", "--format=%P", CONFIG["main"], cwd=WORK) == CONFIG["base_5037"], "Unexpected main ancestry")
    git("clone", "--shared", "--no-checkout", str(WORK), str(SOURCE), cwd=WORK)
    git("config", "core.autocrlf", "false")
    git("config", "user.name", "Codex")
    git("config", "user.email", "codex@openai.com")
    git("checkout", "--detach", CONFIG["base_5037"])
    git("remote", "set-url", "origin", f"https://github.com/{CONFIG['repository']}.git")
    git("update-ref", "refs/remotes/origin/main", CONFIG["main"])
    require(gt("rev-parse", "--is-shallow-repository") == "false", "Complete candidate Git history required")
    configure_csv_whitespace_policy()
    applied = run_logged(["git", "apply", "--index", "--binary", str(patch_path)], "reconstruct-6a4")
    require(applied["returncode"] == 0, "Exact reconstruction failed")
    require(gt("write-tree") == CONFIG["reconstructed_tree"], "Reconstructed tree is not the reviewed 6a4 candidate")
    overlay_paths = git_paths("diff", "--cached", "--name-only", CONFIG["base_5037"])
    require(len(overlay_paths) == CONFIG["expected_overlay_path_count"] and set(overlay_paths) == set(CONFIG["overlay_files"]),
            "Reconstructed overlay path set differs")
    require(file_hashes(overlay_paths) == CONFIG["overlay_files"], "A reconstructed overlay byte hash differs")
    for path, expected in CONFIG["guard_sha256"].items():
        require(sha256(file_bytes(path)) == expected, f"Reconstructed guard hash differs: {path}")
    historical = CONFIG["historical_browser"]["files"]
    require(set(CONFIG["overlay_files"]) - set(historical) == set(CONFIG["guard_sha256"]), "Unexpected additions beyond a94")
    require(all(CONFIG["overlay_files"][path] == digest for path, digest in historical.items()), "A94 inherited bytes differ")
    write_json("exact-reconstruction.json", {"status": "PASS", "tree": gt("write-tree"), "file_count": len(overlay_paths),
               "files": file_hashes(overlay_paths), "input_patch_sha256": sha256(patch),
               "guard_sha256": CONFIG["guard_sha256"], "historical_focused_test_count": 47,
               "focused_tests_rerun_here": False, "missing_0cd4_recovered": False, "production_accepted": False})
    # SOURCE was created by this attempt and its exact staged tree was recorded above.
    git("reset", "--hard", CONFIG["main"])
    require(not gt("status", "--porcelain"), "Fresh main checkout is dirty")
    upstream_paths = git_paths("diff", "--name-only", CONFIG["base_5037"], CONFIG["main"])
    require(upstream_paths == CONFIG["expected_upstream_paths"], "Main path delta differs from the reviewed nineteen paths")
    merged = run_logged(["git", "apply", "--3way", "--index", "--binary", str(patch_path)], "merge-db79")
    conflicts = git_paths("diff", "--name-only", "--diff-filter=U")
    require(merged["returncode"] == 1 and conflicts == CONFIG["expected_generated_conflicts"],
            f"Unexpected merge outcome; review required: returncode={merged['returncode']}, conflicts={conflicts}")
    resolved = {}
    for path in conflicts:
        stages = {str(stage): gt("rev-parse", f":{stage}:{path}") for stage in (1, 2, 3)}
        for stage, ref in (("1", CONFIG["base_5037"]), ("2", CONFIG["main"]), ("3", CONFIG["reconstructed_tree"])):
            require(stages[stage] == gt("rev-parse", f"{ref}:{path}"), f"Unexpected stage {stage} for {path}")
        git("checkout", "--ours", "--", path)
        git("add", "--", path)
        require(file_bytes(path) == git("show", f"{CONFIG['main']}:{path}"), f"Generated main seed differs: {path}")
        resolved[path] = {"stages": stages, "selected": "exact db79 bytes; seed only", "sha256": sha256(file_bytes(path))}
    require(not git_paths("diff", "--name-only", "--diff-filter=U"), "Unresolved conflicts remain")
    nonoverlap = sorted(set(overlay_paths) - set(upstream_paths))
    require(len(nonoverlap) == 96, "Unexpected non-overlapping source scope")
    require(file_hashes(nonoverlap) == {path: CONFIG["overlay_files"][path] for path in nonoverlap}, "Non-overlapping overlay changed during merge")
    write_json("merge-review.json", {"status": "PASS", "main": CONFIG["main"], "upstream_paths": upstream_paths,
               "original_merge_returncode": merged["returncode"], "resolved_generated_seeds": resolved,
               "nonoverlap_unchanged_paths": nonoverlap, "generation_completed": False, "production_accepted": False})
    write_json("functional-review-original.json", review_inputs(corrected=False))
    corrections = apply_source_corrections()
    write_json("functional-review.json", review_inputs())
    generated = generated_inventory()
    brain = apply_brain_updates()
    write_json("brain-update-receipt.json", {"status": "APPLIED_PENDING_GATES", "gap_open": CONFIG["gap_id"], "files": brain})
    git("add", "-A")
    git("diff", "--cached", "--check")
    changed = git_paths("diff", "--cached", "--name-only", CONFIG["main"])
    reviewed_paths = set(overlay_paths) | set(CONFIG["source_corrections"])
    require(set(changed) <= reviewed_paths, "Unreviewed changed path before generation")
    protected = sorted((reviewed_paths - set(generated)) | set(CONFIG["source_corrections"])
                       | set(CONFIG["upstream_source_files"]) | set(CONFIG["protected_control_paths"]))
    functional_hashes = file_hashes(protected)
    write_json("generation-allowed-paths.json", {"classifier": CLASSIFIER, "classifier_sha256": CONFIG["protected_control_sha256"][CLASSIFIER],
               "generated_paths": generated, "explicit_generator_owners": CONFIG["extra_generated_paths"], "protected_paths": protected})
    write_json("build-state.json", {"status": "PREPARED", "prepared_at_utc": now(), "source_parent": CONFIG["main"],
               "main": CONFIG["main"], "reconstructed_tree": CONFIG["reconstructed_tree"],
               "index_tree_before_generation": gt("write-tree"), "functional_hashes": functional_hashes,
               "allowed_generated_paths": generated, "allowed_changed_paths": sorted(reviewed_paths | set(generated)),
               "source_corrections": corrections,
               "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
               "transport_sha": os.environ["GITHUB_SHA"], "final_browser_measured": False, "production_accepted": False})


def verify_inputs_unchanged(state: dict) -> None:
    require(file_hashes(list(state["functional_hashes"])) == state["functional_hashes"], "Prepared functional inputs changed")
    review_inputs()


def verify_frozen(state: dict) -> None:
    require(gt("rev-parse", "HEAD") == state["head"] and gt("rev-parse", "HEAD^{tree}") == state["tree"], "Candidate commit or tree changed")
    require(not gt("status", "--porcelain"), "Frozen candidate worktree changed")
    verify_inputs_unchanged(state)


def generate() -> None:
    state = read_state()
    require(state["status"] == "PREPARED", "Unexpected generation state")
    require(gt("rev-parse", "HEAD") == CONFIG["main"], "Candidate base drift")
    require(gt("write-tree") == state["index_tree_before_generation"] and not git("diff", "--name-only"), "Prepared index or worktree drift")
    verify_inputs_unchanged(state)
    state["status"] = "GENERATING"
    write_json("build-state.json", state)
    result = run_logged(["bash", "scripts/ci/regenerate_all_generated.sh"], "generation")
    require(result["returncode"] == 0, "Official fix/check/release validation failed")
    verify_inputs_unchanged(state)
    changed = git_paths("diff", "--name-only", CONFIG["main"])
    unexpected = sorted(set(changed) - set(state["allowed_changed_paths"]))
    require(not unexpected, f"Generation changed unreviewed source paths: {unexpected}")
    require(not git_paths("ls-files", "--others", "--exclude-standard"), "Unexpected untracked generated output")
    git("add", "-A")
    git("diff", "--cached", "--check")
    git("commit", "-m", CONFIG["commit_subject"])
    require(not gt("status", "--porcelain"), "Candidate worktree is not clean")
    require(gt("show", "-s", "--format=%P", "HEAD") == CONFIG["main"], "Candidate ancestry mismatch")
    state.update(status="BUILT_PENDING_PREFLIGHT", head=gt("rev-parse", "HEAD"), tree=gt("rev-parse", "HEAD^{tree}"),
                 changed_paths=changed, generation=result, built_at_utc=now())
    write_json("functional-review-final.json", review_inputs())
    pack = git("pack-objects", "--stdout", "--revs", "--thin", data=f"{state['head']}\n^{CONFIG['main']}\n".encode())
    (OUT / "candidate-recovery.pack").write_bytes(pack)
    state["candidate_pack_sha256"] = sha256(pack)
    # Persist the frozen identity even if subsequent capability declaration fails.
    write_json("build-state.json", state)
    impact_path = OUT / "capability-impact.json"
    derived = run_logged(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", CONFIG["main"],
                          "--head", state["head"], "--output", str(impact_path)], "capability-impact-derive")
    require(derived["returncode"] in (0, 1) and impact_path.is_file(), "Cannot derive capability impact")
    impact = json.loads(impact_path.read_text(encoding="utf-8"))
    require(impact["git"]["merge_base"] == CONFIG["main"] and not impact["declaration"]["errors"], "Invalid capability derivation")
    declaration = ", ".join(impact["direct"]) if impact["direct"] else "NONE"
    body = (
        "## Source inspection delivery candidate\n\n"
        "Restore the byte-verified a94 inspection delivery overlay and repair class-local HTTP path extraction. "
        "The guard preserves rejection of unknown URLs and undeclared operations. "
        "The new source keeps the salinity change from #1651 at db79 unchanged.\n\n"
        f"Candidate: `{state['head']}`; tree: `{state['tree']}`; base: `{CONFIG['main']}`.\n\n"
        "The 47 focused guard cases belong to the historical 6a4 input before rebasing. "
        "The historical browser run belongs only to a94. This candidate requires complete source preflight "
        "and a new final-tree browser replay; neither is asserted by this draft.\n\n"
        f"Open gap: {CONFIG['gap_id']}. The missing 0cd4 candidate was not recovered. "
        "Previous failed/interrupted attempts retain their results. Production acceptance remains false.\n\n"
        f"Capability-Impact: {declaration}\n"
    )
    body_path = OUT / "source-pr-body.md"
    body_path.write_text(body, encoding="utf-8")
    validated = run_logged(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", CONFIG["main"],
                            "--head", state["head"], "--pr-body-file", str(body_path),
                            "--output", str(OUT / "capability-impact-validated.json")], "capability-impact-validation")
    require(validated["returncode"] == 0, "Capability declaration failed validation")
    state.update(capability_impact=impact["direct"], pr_body_sha256=sha256(body_path.read_bytes()))
    write_json("build-state.json", state)
    print(json.dumps({"candidate_head": state["head"], "candidate_tree": state["tree"], "status": state["status"]}))


def preflight() -> None:
    state = read_state()
    require(state["status"] == "BUILT_PENDING_PREFLIGHT" and "pr_body_sha256" in state, "Candidate is not fully prepared and frozen")
    verify_frozen(state)
    body = OUT / "source-pr-body.md"
    require(sha256(body.read_bytes()) == state["pr_body_sha256"], "PR declaration drift")
    state["status"] = "PREFLIGHT_RUNNING"
    write_json("build-state.json", state)
    result = run_logged(["/usr/bin/time", "-v", "-o", str(OUT / "resource-usage.txt"),
                         "bash", "scripts/ci/preflight.sh", "--no-fetch", "--pr-body-file", str(body)], "preflight-command")
    text = (OUT / "preflight-command.log").read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"^═══ إخفاقات: (\d+) · متخطّاة: (\d+) ═══$", text, re.M)
    counts = tuple(map(int, matches[-1])) if matches else None
    status = gt("status", "--porcelain")
    unchanged = gt("rev-parse", "HEAD") == state["head"] and gt("rev-parse", "HEAD^{tree}") == state["tree"] and not status
    inputs_unchanged = file_hashes(list(state["functional_hashes"])) == state["functional_hashes"]
    passed = result["returncode"] == 0 and counts == (0, 0) and unchanged and inputs_unchanged
    receipt = {**result, "status": "PASS" if passed else "FAIL", "head": state["head"], "tree": state["tree"],
               "parent": CONFIG["main"], "base": CONFIG["main"], "worktree_status": status,
               "source_unchanged": bool(unchanged), "functional_inputs_unchanged": inputs_unchanged,
               "gate_failures": counts[0] if counts else None, "gate_skips": counts[1] if counts else None,
               "execution_scope": "Unchanged contiguous default complete preflight plus PR-body gates; not --full and not final-head source CI.",
               "skip_scope": "Zero skipped gates does not assert zero individual pytest skips.",
               "historical_browser_tree": CONFIG["historical_browser"]["tree"],
               "final_browser_measured": False, "production_accepted": False}
    write_json("preflight-receipt.json", receipt)
    state.update(status="PREFLIGHT_PASS_PENDING_RETENTION" if passed else "PREFLIGHT_FAIL", preflight=receipt)
    write_json("build-state.json", state)
    print(json.dumps(receipt, ensure_ascii=False))
    require(passed, "Complete default preflight or frozen-source verification failed")


def retain() -> None:
    verify_transport()
    state = read_state()
    receipt = json.loads((OUT / "preflight-receipt.json").read_text(encoding="utf-8"))
    require(state["status"] == "PREFLIGHT_PASS_PENDING_RETENTION", "Unverified source cannot be retained")
    require(receipt["status"] == "PASS" and receipt["returncode"] == 0 and receipt["gate_failures"] == 0 and receipt["gate_skips"] == 0,
            "Preflight receipt failed")
    verify_frozen(state)
    require(state["transport_sha"] == os.environ["GITHUB_SHA"], "Transport state mismatch")
    remote = gt("ls-remote", "--heads", "origin", f"refs/heads/{CONFIG['transport_branch']}", cwd=WORK).split()
    require(len(remote) == 2 and remote[0] == state["transport_sha"], "Transport branch moved; preserve evidence and coordinate")
    pack = (OUT / "candidate-recovery.pack").read_bytes()
    require(sha256(pack) == state["candidate_pack_sha256"], "Candidate recovery pack changed")
    git("index-pack", "--stdin", "--fix-thin", "--strict", cwd=WORK, data=pack)
    require(gt("rev-parse", f"{state['head']}^{{tree}}", cwd=WORK) == state["tree"], "Retained tree mismatch")
    patch = git("diff", "--binary", "--full-index", CONFIG["main"], state["head"], "--")
    compressed = gzip.compress(patch, mtime=0)
    paths = git_paths("diff", "--name-only", CONFIG["main"], state["head"])
    files = {path: sha256(git("show", f"{state['head']}:{path}")) for path in paths}
    overlay = {"schema": "sahool.task-delivery-source-overlay/v1", "source_sha": CONFIG["main"], "source_tree": CONFIG["main_tree"],
               "source_commit": state["head"], "overlay_tree": state["tree"], "files": files,
               "patch_bytes": len(patch), "patch_sha256": sha256(patch), "gzip_sha256": sha256(compressed),
               "generated_metadata_status": "official_fix_check_and_release_validation_pass",
               "qualification_state": "source_default_preflight_pass_final_browser_pending",
               "historical_browser_tree": CONFIG["historical_browser"]["tree"],
               "historical_browser_run": CONFIG["historical_browser"]["run_url"],
               "created_at_utc": now(), "production_accepted": False}
    (OUT / "source-overlay.patch.gz").write_bytes(compressed)
    write_json("source-overlay-manifest.json", overlay)
    verified = {"source_commit": state["head"], "source_tree": state["tree"], "source_parent": CONFIG["main"],
                "source_ref_updated": False, "retention_branch": CONFIG["transport_branch"],
                "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "generation": state["generation"], "preflight": receipt, "capability_impact": state["capability_impact"],
                "functional_hashes": state["functional_hashes"], "retained_at_utc": now(),
                "historical_browser_tree": CONFIG["historical_browser"]["tree"], "final_browser_measured": False,
                "gap_open": CONFIG["gap_id"], "production_accepted": False}
    write_json("verified-source.json", verified)
    names = ("verified-source.json", "build-state.json", "generation-receipt.json", "preflight-receipt.json",
             "source-overlay.patch.gz", "source-overlay-manifest.json", "functional-review-final.json",
             "exact-reconstruction.json", "merge-review.json", "brain-update-receipt.json",
             "generation-allowed-paths.json", "whitespace-policy.json", "capability-impact.json",
             "capability-impact-validated.json", "source-pr-body.md", "functional-review-original.json",
             "source-corrections.json", "source-corrections-receipt.json")
    for name in names:
        shutil.copyfile(OUT / name, WORK / name)
        git("add", "--", name, cwd=WORK)
    git("config", "user.name", "github-actions[bot]", cwd=WORK)
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=WORK)
    tree = gt("write-tree", cwd=WORK)
    tip = gt("commit-tree", tree, "-p", state["transport_sha"], "-p", state["head"],
             "-m", "Retain verified inspection candidate and evidence [skip ci]", cwd=WORK)
    # A normal fast-forward push fails if another actor advanced this branch.
    git("push", "origin", f"{tip}:refs/heads/{CONFIG['transport_branch']}", cwd=WORK)
    state.update(status="RETAINED_SOURCE_REF_UNCHANGED", retention_commit=tip, retained_at_utc=now())
    write_json("build-state.json", state)
    write_json("retention-receipt.json", {"status": "PASS", "retention_commit": tip, "candidate_head": state["head"],
               "candidate_tree": state["tree"], "transport_branch": CONFIG["transport_branch"],
               "source_ref_updated": False, "final_browser_measured": False, "production_accepted": False})
    print(json.dumps({"retention_commit": tip, "candidate_head": state["head"], "candidate_tree": state["tree"], "source_ref_updated": False}))


if __name__ == "__main__":
    require(len(sys.argv) == 2 and sys.argv[1] in {"prepare", "generate", "preflight", "retain"},
            "Expected prepare, generate, preflight, or retain")
    phase = sys.argv[1]
    try:
        globals()[phase]()
    except BaseException as exc:
        # Command receipts remain intact. No failed/interrupted attempt is recast as success.
        suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        write_json(f"phase-{phase}-failure-{suffix}.json", {"status": "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAIL",
                   "phase": phase, "exception_type": type(exc).__name__, "message": str(exc), "at_utc": now(),
                   "source_ref_updated": False, "production_accepted": False})
        raise
