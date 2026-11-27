"""Read-only unit diagnosis of one frozen source; never a source acceptance run."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET

WORK = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
TEMP = Path(os.environ["RUNNER_TEMP"]).resolve()
SOURCE = TEMP / "inspection-diagnose-source"
OUT = TEMP / "inspection-unit-diagnose-evidence"
CONFIG = json.loads((WORK / "diagnosis-config.json").read_text(encoding="utf-8"))
BRANCH = "ci/field-inspection-diagnose-0d601b-cda58496"
REPOSITORY = "kafaat/ai_platform_complete_v2.0.0_enhanced"
TRANSPORT = {"diagnose_unit.py", "diagnosis-config.json", "environment-constraints.txt",
             "original-preflight-receipt.json", "candidate-recovery.pack",
             ".github/workflows/inspection-unit-diagnose.yml"}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(*args, cwd=SOURCE, data=None):
    return subprocess.check_output(["git", "--no-replace-objects", *args], cwd=cwd, input=data)


def gt(*args, cwd=SOURCE):
    return git(*args, cwd=cwd).decode("utf-8").strip()


def commit_identity(oid, cwd=SOURCE):
    require(re.fullmatch(r"[a-f0-9]{40}", oid) is not None, "Malformed commit")
    raw = git("cat-file", "commit", oid, cwd=cwd)
    actual = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(actual == oid, "Raw commit object mismatch")
    headers = raw.split(b"\n\n", 1)[0].decode("utf-8").splitlines()
    return {"head": oid, "tree": next(x[5:] for x in headers if x.startswith("tree ")),
            "parents": [x[7:] for x in headers if x.startswith("parent ")]}


def source_hashes():
    result = {}
    for name in CONFIG["functional_hashes"]:
        path = PurePosixPath(name)
        target = SOURCE / name
        require(not path.is_absolute() and path.as_posix() == name and ".." not in path.parts
                and "\\" not in name and "\0" not in name, "Unsafe source identity path")
        require(target.is_file() and not target.is_symlink()
                and target.resolve().is_relative_to(SOURCE), "Non-regular source identity path")
        result[name] = digest(target.read_bytes())
    return result


def snapshot():
    return {**commit_identity(gt("rev-parse", "HEAD")),
            "origin_main": gt("rev-parse", "refs/remotes/origin/main"),
            "worktree_status": gt("status", "--porcelain", "--untracked-files=all"),
            "shallow": gt("rev-parse", "--is-shallow-repository"),
            "functional_hashes": source_hashes(),
            "private_attributes_sha256": digest((SOURCE / ".git/info/attributes").read_bytes())}


def expected_source(s):
    return (s["head"] == CONFIG["source_commit"] and s["tree"] == CONFIG["source_tree"]
            and s["parents"] == [CONFIG["source_parent"]] and s["origin_main"] == CONFIG["source_parent"]
            and s["shallow"] == "false" and s["worktree_status"] == ""
            and s["functional_hashes"] == CONFIG["functional_hashes"]
            and s["private_attributes_sha256"] == CONFIG["private_attributes_sha256"])


def constraints(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
        require(match is not None, "Non-pinned or non-registry environment entry")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        require(name not in result, "Duplicate environment distribution")
        result[name] = match[2]
    return result


def configure_csv_whitespace_policy():
    """Reproduce the original run's private Git CSV policy without changing source."""
    policy_path = SOURCE / ".gitattributes"
    require(policy_path.is_file() and not policy_path.is_symlink(), "Non-regular repository attributes")
    policy = policy_path.read_bytes()
    require(policy == git("show", CONFIG["source_parent"] + ":.gitattributes")
            and digest(policy) == CONFIG["repository_attributes_sha256"],
            "Repository attributes differ from the pinned base")
    require(any(line.split() == [b"*.csv", b"-text"] for line in policy.splitlines()),
            "Pinned repository does not preserve generator-owned CSV line endings")
    private = SOURCE / ".git"
    info = private / "info"
    attributes = info / "attributes"
    require(private.is_dir() and not private.is_symlink() and info.is_dir()
            and not info.is_symlink() and info.resolve() == info,
            "Private Git attributes must stay in the fresh owned clone")
    require(not attributes.is_symlink() and not attributes.exists(),
            "Unexpected inherited private Git attributes; review required")
    rule = "blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol"
    content = ("*.csv whitespace=" + rule + "\n").encode("utf-8")
    require(digest(content) == CONFIG["private_attributes_sha256"], "Private CSV rule identity differs")
    with attributes.open("xb") as stream:
        stream.write(content)
    csv = gt("check-attr", "whitespace", "--", "__inspection_policy_probe.csv")
    other = gt("check-attr", "whitespace", "--", "__inspection_policy_probe.py")
    require(csv.endswith(": " + rule) and other.endswith(": unspecified"),
            "Private whitespace policy must affect CSV only")
    dump("whitespace-policy.json", {
        "status": "APPLIED", "repository_policy_commit": CONFIG["source_parent"],
        "repository_policy_sha256": digest(policy),
        "scope": "Fresh owned SOURCE clone .git/info/attributes; *.csv only.",
        "attributes_relative_path": ".git/info/attributes",
        "original_attributes_existed": False, "applied_rule": content.decode("utf-8").rstrip("\n"),
        "applied_attributes_sha256": digest(content),
        "retained_checks": ["blank-at-eol", "blank-at-eof", "space-before-tab"],
        "csv_line_ending_recognition": "cr-at-eol", "non_csv_check_attr": other,
        "source_or_generated_bytes_modified": False,
        "source_preflight_status": "FAIL", "source_preflight_failed": True,
        "production_accepted": False})


def prepare():
    require(not OUT.exists() and not SOURCE.exists(), "Diagnostic directories must be fresh")
    OUT.mkdir()
    require(os.environ.get("GITHUB_REPOSITORY") == CONFIG["repository"] == REPOSITORY, "Wrong repository")
    require(os.environ.get("GITHUB_REF_NAME") == CONFIG["transport_branch"] == BRANCH, "Wrong diagnostic branch")
    require(gt("rev-parse", "HEAD", cwd=WORK) == os.environ["GITHUB_SHA"]
            and not gt("status", "--porcelain", cwd=WORK), "Controller checkout drift")
    require(set(gt("ls-files", cwd=WORK).splitlines()) == TRANSPORT, "Unexpected transport files")
    require(gt("rev-parse", "--is-shallow-repository", cwd=WORK) == "false", "Full history required")
    require(commit_identity(os.environ["GITHUB_SHA"], cwd=WORK)["parents"] == [CONFIG["transport_parent"]],
            "Unexpected controller parent")
    for name, expected in CONFIG["input_sha256"].items():
        require(digest((WORK / name).read_bytes()) == expected, "Transport bytes differ: " + name)
    require(CONFIG["source_preflight_status"] == "FAIL" and CONFIG["source_preflight_failed"] is True
            and CONFIG["production_accepted"] is False,
            "Diagnosis cannot grant source acceptance")
    old = json.loads((WORK / "original-preflight-receipt.json").read_text(encoding="utf-8"))
    require(old["status"] == "FAIL" and old["returncode"] == 1 and old["gate_failures"] == 3
            and old["gate_skips"] == 0 and old["head"] == CONFIG["source_commit"]
            and old["tree"] == CONFIG["source_tree"] and old["parent"] == CONFIG["source_parent"]
            and old["source_unchanged"] is True and old["functional_inputs_unchanged"] is True,
            "Historical failed receipt does not match frozen source")
    base = commit_identity(CONFIG["source_parent"], cwd=WORK)
    require(base["tree"] == CONFIG["source_base_tree"], "Pinned source base tree differs")
    pack = (WORK / "candidate-recovery.pack").read_bytes()
    require(len(pack) == CONFIG["pack_bytes"] and pack[:4] == b"PACK"
            and hashlib.sha1(pack[:-20]).digest() == pack[-20:], "Invalid frozen pack")
    git("index-pack", "--stdin", "--fix-thin", "--strict", cwd=WORK, data=pack)
    candidate = commit_identity(CONFIG["source_commit"], cwd=WORK)
    require(candidate["tree"] == CONFIG["source_tree"] and candidate["parents"] == [CONFIG["source_parent"]],
            "Imported candidate identity differs")
    git("clone", "--shared", "--no-checkout", str(WORK), str(SOURCE), cwd=WORK)
    git("config", "core.autocrlf", "false")
    git("config", "user.name", "Codex")
    git("config", "user.email", "codex@openai.com")
    git("remote", "set-url", "origin", "https://github.com/" + REPOSITORY + ".git")
    git("update-ref", "refs/remotes/origin/main", CONFIG["source_parent"])
    git("checkout", "--detach", CONFIG["source_commit"])
    configure_csv_whitespace_policy()
    before = snapshot()
    require(expected_source(before), "Prepared source is not exact or clean")
    constraints((WORK / "environment-constraints.txt").read_text(encoding="utf-8"))
    for name in ["diagnosis-config.json", "environment-constraints.txt", "original-preflight-receipt.json"]:
        shutil.copyfile(WORK / name, OUT / name)
    dump("prepare-receipt.json", {"status": "PREPARED_DIAGNOSIS_ONLY", "source": before,
         "pack_sha256": digest(pack), "controller": os.environ["GITHUB_SHA"],
         "source_preflight_status": "FAIL", "source_preflight_failed": True, "production_accepted": False, "at_utc": now()})


def junit_results(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    require(cases, "JUnit is empty")
    suites = list(root.iter("testsuite"))
    totals = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
              for key in ["tests", "failures", "errors", "skipped"]}
    failures = []
    for case in cases:
        for kind in ["failure", "error"]:
            for detail in case.findall(kind):
                failures.append({"kind": kind, "classname": case.attrib.get("classname"),
                     "name": case.attrib.get("name"), "file": case.attrib.get("file"),
                     "message": detail.attrib.get("message"), "traceback": detail.text})
    return {"suite_counters": totals, "testcase_elements": len(cases), "failed_cases": failures}


def run():
    require(sys.version_info[:3] == (3, 12, 14), "Wrong Python interpreter")
    before = snapshot()
    require(expected_source(before), "Source changed before diagnostic unit run")
    expected_env = constraints((WORK / "environment-constraints.txt").read_text(encoding="utf-8"))
    actual_env = constraints((OUT / "environment-current.txt").read_text(encoding="utf-8"))
    require(actual_env == expected_env, "Installed package versions differ from the failed run")
    argv = ["python3", "-m", "pytest", "-q", "-m", "unit", "--junitxml=" + str(OUT / "unit.xml")]
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING") or "utf-8"
    env["BASE"] = CONFIG["source_parent"]
    start = now()
    dump("run-start.json", {"status": "RUNNING_DIAGNOSIS", "argv": argv, "cwd": str(SOURCE),
         "source": before, "started_at_utc": start, "source_preflight_status": "FAIL", "source_preflight_failed": True})
    errors = []
    def drain(pipe, target, display):
        try:
            with target.open("xb") as output:
                for block in iter(pipe.readline, b""):
                    output.write(block)
                    output.flush()
                    display.buffer.write(block)
                    display.buffer.flush()
        except BaseException as exc:
            errors.append(repr(exc))
    process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    readers = [threading.Thread(target=drain, args=(process.stdout, OUT / "stdout.log", sys.stdout)),
               threading.Thread(target=drain, args=(process.stderr, OUT / "stderr.log", sys.stderr))]
    for reader in readers:
        reader.start()
    try:
        code = process.wait()
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    finally:
        for reader in readers:
            reader.join()
    after = snapshot()
    unchanged = expected_source(after) and before == after
    native = (OUT / "stdout.log").read_text(encoding="utf-8", errors="replace")
    native = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", native)
    summary_lines = [line for line in native.splitlines()
                     if re.search(r"\b\d+ (?:failed|passed|skipped|errors?)\b", line) and re.search(r"\bin \d+(?:\.\d+)?s", line)]
    native_failed = [line for line in native.splitlines() if re.match(r"^(?:FAILED|ERROR) ", line)]
    try:
        xml = junit_results(OUT / "unit.xml")
        xml_error = None
    except Exception as exc:
        xml, xml_error = None, repr(exc)
    valid = unchanged and not errors and xml is not None
    result = {"status": "UNIT_DIAGNOSTIC_PASS" if code == 0 and valid else "UNIT_DIAGNOSTIC_FAIL",
        "native_returncode": code, "argv": argv, "started_at_utc": start, "finished_at_utc": now(),
        "source_before": before, "source_after": after, "source_unchanged": unchanged,
        "environment_matches_failed_run": True, "native_summary_lines": summary_lines,
        "native_failed_lines": native_failed, "junit": xml, "junit_error": xml_error, "capture_errors": errors,
        "output_sha256": {name: digest((OUT / name).read_bytes())
                          for name in ["stdout.log", "stderr.log", "unit.xml"] if (OUT / name).is_file()},
        "historical_preflight_run": CONFIG["historical_preflight_run"], "source_preflight_status": "FAIL", "source_preflight_failed": True,
        "scope": "One full unit diagnostic with complete logs and JUnit; no generation, source repair, preflight rerun, retention or source acceptance.",
        "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "source_ref_updated": False, "browser_measured": False, "production_accepted": False}
    dump("diagnostic-receipt.json", result)
    print(json.dumps({"native_returncode": code, "source_unchanged": unchanged,
                      "junit_counters": xml["suite_counters"] if xml else None,
                      "source_preflight_status": "FAIL", "source_preflight_failed": True, "production_accepted": False}))
    return (code if code >= 0 else 128 - code) if code != 0 else (0 if valid else 1)


if __name__ == "__main__":
    require(len(sys.argv) == 2 and sys.argv[1] in {"prepare", "run"}, "Expected prepare or run")
    try:
        result = globals()[sys.argv[1]]()
    except BaseException as exc:
        dump("phase-failure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json",
             {"status": "FAIL", "phase": sys.argv[1], "message": str(exc),
              "source_preflight_status": "FAIL", "source_preflight_failed": True, "production_accepted": False, "at_utc": now()})
        raise
    sys.exit(result or 0)
