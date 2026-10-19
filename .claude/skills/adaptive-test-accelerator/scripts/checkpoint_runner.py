#!/usr/bin/env python3
"""Conservative sequential test checkpoint runner (stdlib, no installs, no remote actions).

This tool does NOT certify mandatory gates or create distributed locks.
It executes only a locally reviewed JSON plan with an exact digest approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import shutil
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
FORBIDDEN_CONTEXT_FIELDS = re.compile(r"(?:secret|token|password|credential|dsn|api.?key|private.?key)", re.I)
GIT_REF = re.compile(r"^(?:refs/(?:heads|remotes)/)?[A-Za-z0-9][A-Za-z0-9_./-]*$")
SHELL_NAMES = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
EXTERNAL_MUTATORS = {"git", "git.exe", "gh", "gh.exe", "railway", "railway.exe",
                     "kubectl", "kubectl.exe", "ssh", "ssh.exe", "scp", "scp.exe",
                     "rm", "rmdir", "del", "curl", "wget"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_bytes(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(data: object) -> str:
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def effective_context_hash(plan: dict, context: dict) -> str:
    """Bind the declared context to the actual resolved working directories."""
    return digest({"declared_context": context,
                   "resolved_cwds": [str(Path(u.get("cwd", ".")).resolve()) for u in plan["units"]]})


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return data


def atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".atomic-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def verify_event_chain(path: Path) -> tuple[int, str]:
    """Check append-only local event checksums; NOT a signature or external timestamp."""
    if not path.is_file():
        return 0, "0" * 64
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Event ledger exceeds 16 MiB; archive under an approved policy")
    previous, n = "0" * 64, 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                if (row["seq"] != n + 1 or row["previous_sha256"] != previous
                        or not isinstance(row["payload"], dict)
                        or row["sha256"] != digest({k: row[k] for k in ("seq", "previous_sha256", "payload")})):
                    raise ValueError("Event chain mismatch")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid event ledger line {n + 1}: {exc}") from exc
            previous, n = row["sha256"], n + 1
    return n, previous


def append_event(path: Path, payload: dict) -> None:
    n, previous = verify_event_chain(path)
    core = {"seq": n + 1, "previous_sha256": previous, "payload": payload}
    row = {**core, "sha256": digest(core)}
    # All calls happen under the exclusive local lock; write-through and fsync.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def reject_sensitive_keys(value: object, path="context") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if FORBIDDEN_CONTEXT_FIELDS.search(str(k)):
                raise ValueError(f"{path}.{k}: potential secret key is not allowed in context")
            reject_sensitive_keys(v, path + "." + str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            reject_sensitive_keys(v, f"{path}[{i}]")


def validate(plan: dict, context: dict) -> None:
    if plan.get("schema") != "ata/plan/v1" or context.get("schema") != "ata/context/v1":
        raise ValueError("Unsupported schema (require ata/plan/v1 and ata/context/v1)")
    work_id = plan.get("work_id")
    if not isinstance(work_id, str) or not SAFE_ID.fullmatch(work_id):
        raise ValueError("Invalid work_id")
    if context.get("work_id") != work_id:
        raise ValueError("Plan/context work_id mismatch")
    identity = context.get("identity")
    if not isinstance(identity, dict) or not identity:
        raise ValueError("Context must provide a non-empty, verified identity object")
    reject_sensitive_keys(context)
    if "EXAMPLE" in json.dumps(identity):
        raise ValueError("Example placeholder context cannot be used to run tests")
    units = plan.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("A plan must contain at least one unit")
    seen = set()
    for unit in units:
        if not isinstance(unit, dict):
            raise ValueError("Unit must be an object")
        u_id = unit.get("id")
        if not isinstance(u_id, str) or not SAFE_ID.fullmatch(u_id) or u_id in seen:
            raise ValueError(f"Invalid or duplicate unit id: {u_id!r}")
        seen.add(u_id)
        if unit.get("kind") != "test":
            raise ValueError("Only test units are executable; other actions must use project-specific gates")
        argv = unit.get("argv")
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a.strip() for a in argv):
            raise ValueError(f"{u_id}: argv must be a nonempty array of strings")
        executable = ntpath.basename(argv[0].replace("/", "\\")).lower()
        if executable in SHELL_NAMES:
            raise ValueError(f"{u_id}: shell invocation is refused by this conservative runner")
        if executable in EXTERNAL_MUTATORS:
            raise ValueError(f"{u_id}: direct external/mutating CLI is not a test command; refused")
        junit = unit.get("junit")
        if not isinstance(junit, str) or not SAFE_ID.fullmatch(junit):
            raise ValueError(f"{u_id}: junit must be an output file basename")
        timeout = unit.get("timeout_seconds", 1800)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 86400:
            raise ValueError(f"{u_id}: timeout_seconds must be in (0, 86400]")
        cwd = unit.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError(f"{u_id}: invalid cwd")
        if (not isinstance(unit.get("max_skipped", 0), int) or isinstance(unit.get("max_skipped", 0), bool)
                or unit.get("max_skipped", 0) < 0):
            raise ValueError(f"{u_id}: max_skipped must be a nonnegative integer")
        if "expected_tests" in unit and (not isinstance(unit["expected_tests"], int)
                or isinstance(unit["expected_tests"], bool) or unit["expected_tests"] < 1):
            raise ValueError(f"{u_id}: expected_tests must be positive integer")
        pass_env = unit.get("pass_env", [])
        if not isinstance(pass_env, list) or any(not isinstance(k, str) or not k.isidentifier() or
                FORBIDDEN_CONTEXT_FIELDS.search(k) for k in pass_env):
            raise ValueError(f"{u_id}: pass_env may name only reviewed, non-sensitive environment variables")
    if "min_free_disk_mib" in plan:
        value = plan["min_free_disk_mib"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 102400:
            raise ValueError("Invalid min_free_disk_mib")


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, check=False, timeout=18)
    if result.returncode:
        raise ValueError(f"Local git verification failed for {args[0]} (exit {result.returncode})")
    return result.stdout.strip()


def verify_live_context(context: dict) -> str:
    """Compare identity claims with primary local file/Git sources; never trust JSON alone.

    Remote PR/CI status is deliberately NOT checked here. A local tracking branch
    can be stale, and a passed receipt cannot authorize a push or release.
    """
    v = context.get("verification")
    if not isinstance(v, dict):
        raise ValueError("Live source verification required: context.verification is missing")
    root_value = v.get("root")
    if not isinstance(root_value, str) or not Path(root_value).is_absolute():
        raise ValueError("verification.root must be an existing absolute path")
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise ValueError("verification.root does not exist")
    kind, identity = v.get("kind"), context["identity"]
    if kind == "git":
        expected = ["source_head", "source_tree", "base_ref", "base_head", "merge_base"]
        if any(not isinstance(identity.get(k), str) or not identity[k] for k in expected):
            raise ValueError("Git verification requires source_head/tree, base_ref/head, merge_base")
        base_ref = identity["base_ref"]
        if not GIT_REF.fullmatch(base_ref) or base_ref.startswith("-"):
            raise ValueError("Invalid base_ref")
        if run_git(root, "rev-parse", "--show-toplevel") != str(root):
            raise ValueError("verification.root is not the actual Git working tree root")
        actual = {
            "source_head": run_git(root, "rev-parse", "HEAD"),
            "source_tree": run_git(root, "rev-parse", "HEAD^{tree}"),
            "base_head": run_git(root, "rev-parse", f"{base_ref}^{{commit}}"),
            "merge_base": run_git(root, "merge-base", "HEAD", base_ref),
        }
        drift = [k for k, val in actual.items() if identity[k] != val]
        if drift:
            raise ValueError("Stale Git context (current source differs): " + ", ".join(drift))
        if run_git(root, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("Git working tree is dirty: no valid reusable HEAD/tree identity; use a clean tree or declared-files mode")
        return "verified local Git snapshot; remote base/CI are NOT checked"
    if kind == "declared_files":
        files = v.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("declared_files requires nonempty path->sha256 inventory")
        for relative, claimed_hash in files.items():
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Invalid declared-file relative path")
            if not isinstance(claimed_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", claimed_hash):
                raise ValueError("Invalid declared-file SHA256")
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file() or file_digest(target) != claimed_hash:
                raise ValueError(f"Declared file missing/changed: {relative}")
        return "verified declared local files ONLY (not proven exhaustive)"
    raise ValueError("verification.kind must be git or declared_files")


def check_disk_budget(path: Path, plan: dict) -> None:
    budget = plan.get("min_free_disk_mib", 128)
    if not isinstance(budget, int) or isinstance(budget, bool) or not 0 <= budget <= 102400:
        raise ValueError("min_free_disk_mib must be an integer from 0..102400")
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < budget * 1024 * 1024:
        raise RuntimeError(f"INSUFFICIENT_DISK: {free // 1048576} MiB free, need at least {budget} MiB")
    if os.name == "posix":
        fs = os.statvfs(path)
        if fs.f_favail < 64:
            raise RuntimeError("INSUFFICIENT_INODES: fewer than 64 writable inodes remain")


def safe_environment(unit: dict, unit_dir: Path) -> dict[str, str]:
    # No wholesale environment inheritance: tokens, cloud credentials, proxies may be present.
    allowed = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL",
               "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC", "VIRTUAL_ENV"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    passthrough = unit.get("pass_env", [])
    if not isinstance(passthrough, list) or any(not isinstance(k, str) or not k.isidentifier() or
            FORBIDDEN_CONTEXT_FIELDS.search(k) for k in passthrough):
        raise ValueError("Invalid or sensitive pass_env: only explicitly approved variable names are allowed")
    for key in passthrough:
        if key in os.environ:
            env[key] = os.environ[key]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ATR_UNIT_DIR"] = str(unit_dir)
    env["ATR_WORK_ID"] = unit["id"]
    return env


def report_counts(junit: Path) -> dict:
    if not junit.is_file() or junit.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("JUnit evidence missing or exceeds size budget (8 MiB)")
    root = ET.parse(junit).getroot()
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        raise ValueError("Not a JUnit test suite")
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if not suites:
        raise ValueError("JUnit contains no testsuites")
    for suite in suites:
        fallback = {
            "tests": len(suite.findall(".//testcase")),
            "failures": len(suite.findall(".//failure")),
            "errors": len(suite.findall(".//error")),
            "skipped": len(suite.findall(".//skipped")),
        }
        for k in counts:
            counts[k] += int(suite.attrib.get(k, fallback[k]))
    observed_cases = root.findall(".//testcase")
    if not observed_cases or counts["tests"] != len(observed_cases):
        raise ValueError("JUnit tests count must match actual testcase elements and be nonzero")
    observed = {"failures": len(root.findall(".//failure")),
                "errors": len(root.findall(".//error")),
                "skipped": len(root.findall(".//skipped"))}
    if any(counts[k] != observed[k] for k in observed):
        raise ValueError("JUnit status counts do not match testcase evidence")
    if counts["tests"] < counts["failures"] + counts["errors"] + counts["skipped"]:
        raise ValueError("Inconsistent JUnit counts")
    counts["executed"] = counts["tests"] - counts["skipped"]
    return counts


def receipt_envelope(payload: dict) -> dict:
    return {"payload": payload, "sha256": digest(payload)}


def verify_receipt(path: Path, *, plan_hash: str, context_hash: str, unit: dict) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        envelope = read_json(path)
        payload = envelope["payload"]
        if digest(payload) != envelope["sha256"]:
            return False, "receipt checksum mismatch"
        expected = (plan_hash, context_hash, digest(unit))
        observed = (payload.get("plan_hash"), payload.get("context_hash"), payload.get("unit_hash"))
        if observed != expected:
            return False, "stale input identity"
        if payload.get("unit_id") != unit["id"]:
            return False, "unit identity mismatch"
        if payload.get("status") != "PASS" or payload.get("return_code") != 0:
            return False, "not a verified pass"
        xml_path = path.parent / unit["junit"]
        if not xml_path.is_file() or file_digest(xml_path) != payload.get("junit_sha256"):
            return False, "JUnit report missing or changed"
        actual = report_counts(xml_path)
        if (actual != payload.get("junit_counts") or actual["executed"] < 1
                or actual["failures"] or actual["errors"]
                or actual["skipped"] > unit.get("max_skipped", 0)
                or ("expected_tests" in unit and actual["tests"] != unit["expected_tests"])):
            return False, "JUnit evidence no longer verifies"
        return True, "verified receipt (local integrity only)"
    except (ValueError, KeyError, OSError, ET.ParseError, TypeError) as exc:
        return False, f"invalid evidence: {exc}"


class ExclusiveLocalLock:
    """O_EXCL lock only. Never clear a stale lock automatically."""
    def __init__(self, path: Path):
        self.path = path
        self.token = uuid.uuid4().hex
        self.owned = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError(f"LOCKED: {self.path}. Check all hosts/sessions before manually releasing.") from exc
        self.owned = True
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"token": self.token, "pid": os.getpid(), "host": socket.gethostname(), "started": now()}, out)
            out.flush()
            os.fsync(out.fileno())
        return self

    def __exit__(self, *_):
        if self.owned:
            try:
                if read_json(self.path).get("token") == self.token:
                    self.path.unlink()
            except (FileNotFoundError, ValueError, OSError):
                pass


def collect_output(pipe, keep_bytes: int, captured: dict):
    h = hashlib.sha256()
    last = bytearray()
    total = 0
    try:
        while True:
            block = pipe.read(8192)
            if not block:
                break
            total += len(block)
            h.update(block)
            if keep_bytes > 0:
                last.extend(block)
                if len(last) > keep_bytes:
                    del last[:-keep_bytes]
    finally:
        pipe.close()
    captured.update({"output_sha256": h.hexdigest(), "output_bytes": total,
                     "output_tail": last.decode("utf-8", errors="replace") if keep_bytes else None,
                     "output_truncated": total > keep_bytes})


def run_unit(unit: dict, unit_dir: Path, plan_hash: str, context_hash: str, keep_output: int) -> dict:
    unit_dir.mkdir(parents=True, exist_ok=True)
    junit = unit_dir / unit["junit"]
    # Preserve evidence from prior failed / interrupted attempts before rerun.
    retained = [unit_dir / name for name in ("receipt.json", "inflight.json", unit["junit"]) if (unit_dir / name).exists()]
    if retained:
        history = unit_dir / "history" / uuid.uuid4().hex
        history.mkdir(parents=True, exist_ok=False)
        for old in retained:
            os.replace(old, history / old.name)
    started = now()
    monotonic = time.monotonic()
    atomic_json(unit_dir / "inflight.json", {"status": "STARTING", "unit_id": unit["id"],
                                               "plan_hash": plan_hash, "context_hash": context_hash, "started": started})
    cwd = Path(unit.get("cwd", ".")).resolve()
    if not cwd.is_dir():
        raise ValueError(f"Unit cwd does not exist: {cwd}")
    command = [argument.replace("{unit_dir}", str(unit_dir)) for argument in unit["argv"]]
    env = safe_environment(unit, unit_dir)
    output = {}
    timed_out = False
    cancelled = False
    result_code = None
    try:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=(os.name == "posix"))
        atomic_json(unit_dir / "inflight.json", {"status": "RUNNING", "unit_id": unit["id"],
                                                   "plan_hash": plan_hash, "context_hash": context_hash,
                                                   "pid": proc.pid, "host": socket.gethostname(), "started": started})
        reader = threading.Thread(target=collect_output, args=(proc.stdout, keep_output, output), daemon=True)
        reader.start()
        try:
            result_code = proc.wait(timeout=float(unit.get("timeout_seconds", 1800)))
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_group(proc)
            result_code = proc.wait()
        except KeyboardInterrupt:
            cancelled = True
            terminate_group(proc)
            proc.wait()
            raise
        finally:
            reader.join(timeout=10)
            if reader.is_alive():
                output["output_capture_incomplete"] = True
    except FileNotFoundError as exc:
        output.update({"error": f"Executable not available: {exc}", "output_sha256": None, "output_bytes": 0})
    if cancelled:
        raise KeyboardInterrupt
    evidence_error = None
    counts = None
    junit_sha = None
    if junit.exists():
        try:
            counts = report_counts(junit)
            junit_sha = file_digest(junit)
        except (OSError, ValueError, ET.ParseError) as exc:
            evidence_error = str(exc)
    else:
        evidence_error = "JUnit not produced"
    status = "TIMEOUT" if timed_out else "FAIL" if result_code != 0 else "EXIT_ZERO_UNVERIFIED"
    if (not timed_out and result_code == 0 and counts and counts["executed"] >= 1
            and counts["failures"] == 0 and counts["errors"] == 0
            and counts["skipped"] <= unit.get("max_skipped", 0)
            and ("expected_tests" not in unit or counts["tests"] == unit["expected_tests"])
            and not output.get("output_capture_incomplete")):
        status = "PASS"
    if result_code == 0 and counts and counts["skipped"] > unit.get("max_skipped", 0):
        status = "UNACCEPTED_SKIPS"
    if result_code == 0 and counts and "expected_tests" in unit and counts["tests"] != unit["expected_tests"]:
        status = "TEST_COUNT_MISMATCH"
    payload = {"schema": "ata/receipt/v1", "unit_id": unit["id"], "unit_hash": digest(unit),
               "plan_hash": plan_hash, "context_hash": context_hash, "started": started, "finished": now(),
               "elapsed_seconds": round(time.monotonic() - monotonic, 3), "return_code": result_code,
               "status": status, "timeout": timed_out, "junit_sha256": junit_sha,
               "junit_counts": counts, "evidence_error": evidence_error, **output}
    atomic_json(unit_dir / "receipt.json", receipt_envelope(payload))
    (unit_dir / "inflight.json").unlink(missing_ok=True)
    return payload


def terminate_group(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        proc.kill()  # Windows may have child processes; inspect before retry


def status(plan: dict, context: dict, root: Path, *, verbose=True) -> tuple[int, list]:
    plan_hash, context_hash = digest(plan), effective_context_hash(plan, context)
    out_dir = root / plan["work_id"] / plan_hash / context_hash
    states = []
    for unit in plan["units"]:
        location = out_dir / unit["id"]
        passed, reason = verify_receipt(location / "receipt.json", plan_hash=plan_hash,
                                        context_hash=context_hash, unit=unit)
        if passed:
            state = "PASS_VERIFIED"
        elif (location / "inflight.json").exists():
            state = "INTERRUPTED_OR_UNKNOWN"
        elif (location / "receipt.json").exists():
            state = "NOT_VERIFIED"
        else:
            state = "NOT_RUN"
        states.append({"id": unit["id"], "status": state, "detail": reason})
    if verbose:
        print(json.dumps({"plan_sha256": plan_hash, "context_sha256": context_hash,
                          "results_path": str(out_dir), "units": states,
                          "provenance": "local receipts only; not full continuous preflight; no remote CI truth"}, indent=2))
    return sum(s["status"] == "PASS_VERIFIED" for s in states), states


def git_root_for(path: Path) -> Path | None:
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "status", "run"])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--results", type=Path, help="Persistent-enough local scratch path OUTSIDE checkout")
    parser.add_argument("--approve-plan-sha", help="Exact SHA-256 from inspect, explicit command execution approval")
    parser.add_argument("--resume-interrupted", action="store_true", help="After checking no process still runs")
    parser.add_argument("--retry-failed", action="store_true", help="Explicitly permit retry of FAILED/TIMEOUT/UNVERIFIED")
    parser.add_argument("--save-output-tail-bytes", type=int, default=0, help="Sensitive local evidence; default zero")
    args = parser.parse_args(argv)
    plan, context = read_json(args.plan), read_json(args.context)
    validate(plan, context)
    plan_hash, context_hash = digest(plan), effective_context_hash(plan, context)
    live_proof = verify_live_context(context)
    if args.action == "inspect":
        print(json.dumps({"plan_sha256": plan_hash, "context_sha256": context_hash,
                          "context_is_bound_to_actual_working_directories": True,
                          "source_verification": live_proof,
                          "work_id": plan["work_id"], "units": [
                              {"id": u["id"], "argv": u["argv"], "cwd": u.get("cwd", "."),
                               "timeout_seconds": u.get("timeout_seconds", 1800)} for u in plan["units"]],
                          "permission": "No execution performed; to run, approve this exact plan digest"}, indent=2))
        return 0
    if not args.results:
        raise ValueError("--results required for status/run")
    results = args.results.resolve()
    if args.action == "status":
        verify_event_chain(results / plan["work_id"] / plan_hash / context_hash / "transitions.jsonl")
        matched, _ = status(plan, context, results)
        return 0 if matched == len(plan["units"]) else 1
    if args.approve_plan_sha != plan_hash:
        raise ValueError("Execution refused: missing/mismatched --approve-plan-sha from inspect")
    if args.save_output_tail_bytes < 0 or args.save_output_tail_bytes > 65536:
        raise ValueError("Output tail budget must be 0..65536 bytes")
    repo = git_root_for(results)
    if repo:
        raise ValueError(f"Results must be outside source checkout: {repo}")
    workdir = results / plan["work_id"]
    plan_dir = workdir / plan_hash / context_hash
    with ExclusiveLocalLock(workdir / "run.lock"):
        check_disk_budget(results, plan)
        plan_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in (("frozen_plan.json", plan), ("frozen_context.json", context)):
            dest = plan_dir / filename
            if dest.exists():
                if digest(read_json(dest)) != digest(data):
                    raise RuntimeError(f"Frozen input drift: {dest}")
            else:
                atomic_json(dest, data)
        event_file = plan_dir / "transitions.jsonl"
        append_event(event_file, {"event": "RUN_STARTED", "at": now(),
                    "plan_sha256": plan_hash, "context_sha256": context_hash})
        failures = 0
        _, startup_states = status(plan, context, results, verbose=False)
        atomic_json(plan_dir / "state.json", {"schema": "ata/state/v1", "saved_at": now(),
                     "plan_sha256": plan_hash, "context_sha256": context_hash,
                     "source_verification": live_proof, "units": startup_states,
                     "limits": "local checkpoint, not persisted backup or full preflight"})
        for unit in plan["units"]:
            location = plan_dir / unit["id"]
            receipt = location / "receipt.json"
            passed, reason = verify_receipt(receipt, plan_hash=plan_hash,
                                            context_hash=context_hash, unit=unit)
            if passed:
                print(f"SKIP {unit['id']}: existing matching verified PASS", flush=True)
                continue
            if (location / "inflight.json").exists():
                if not args.resume_interrupted:
                    print(f"BLOCK {unit['id']}: inflight marker exists; verify holder ended, pass --resume-interrupted", flush=True)
                    failures += 1
                    continue
                inflight = read_json(location / "inflight.json")
                pid = inflight.get("pid")
                if inflight.get("host") == socket.gethostname() and isinstance(pid, int) and pid > 0:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        print(f"BLOCK {unit['id']}: process {pid} might still be active", flush=True)
                        failures += 1
                        continue
                    else:
                        print(f"BLOCK {unit['id']}: process {pid} exists; holder not proven gone", flush=True)
                        failures += 1
                        continue
            if receipt.exists() and not args.retry_failed:
                print(f"BLOCK {unit['id']}: {reason}; pass --retry-failed after investigating", flush=True)
                failures += 1
                continue
            # Before each unit verify that Git/file inputs have not changed since inspect.
            verify_live_context(context)
            check_disk_budget(results, plan)
            print(f"RUN {unit['id']} (explicitly approved plan)", flush=True)
            outcome = run_unit(unit, location, plan_hash, context_hash, args.save_output_tail_bytes)
            print(f"END {unit['id']}: {outcome['status']} rc={outcome['return_code']}", flush=True)
            append_event(event_file, {"event": "UNIT_FINISHED", "at": now(),
                         "unit_id": unit["id"], "status": outcome["status"],
                         "exit_code": outcome["return_code"],
                         "receipt_sha256": file_digest(location / "receipt.json")})
            _, updated_states = status(plan, context, results, verbose=False)
            atomic_json(plan_dir / "state.json", {"schema": "ata/state/v1", "saved_at": now(),
                         "plan_sha256": plan_hash, "context_sha256": context_hash,
                         "source_verification": live_proof, "units": updated_states,
                         "limits": "local checkpoint, not persisted backup or full preflight"})
            if outcome["status"] != "PASS":
                failures += 1
        verify_live_context(context)
        verified, records = status(plan, context, results)
        return 0 if failures == 0 and verified == len(records) else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(3)
