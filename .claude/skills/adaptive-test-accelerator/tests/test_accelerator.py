"""Pure stdlib tests for the optional local planning/checkpoint implementation."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_module("ata_checkpoint_runner", ROOT / "scripts/checkpoint_runner.py")
planner = load_module("ata_duration_planner", ROOT / "scripts/duration_planner.py")


class DurationTests(unittest.TestCase):
    def test_exact_assignment_once_and_no_affinity_split(self):
        sample = {"schema": "ata/durations/v1", "groups": [
            {"id": "a", "seconds": 16, "affinity": "db"},
            {"id": "b", "seconds": 3, "affinity": "db"},
            {"id": "c", "seconds": 8}, {"id": "d", "seconds": 7},
            {"id": "e", "seconds": 4}, {"id": "f", "seconds": 1}]}
        parts = planner.assign(sample, 3)
        all_ids = [g for part in parts for g in part["groups"]]
        self.assertEqual(sorted(all_ids), ["a", "b", "c", "d", "e", "f"])
        self.assertEqual(next(i for i, s in enumerate(parts) if "a" in s["groups"]),
                         next(i for i, s in enumerate(parts) if "b" in s["groups"]))
        self.assertEqual(sum(p["estimated_seconds"] for p in parts), 39)

    def test_determinism(self):
        sample = {"schema": "ata/durations/v1", "groups": [
            {"id": str(i), "seconds": 1 + i} for i in range(10)]}
        self.assertEqual(planner.assign(sample, 3), planner.assign(sample, 3))

    def test_invalid_durations_and_ids_rejected(self):
        for val in [float("nan"), float("inf"), -1, 0, "slow", True]:
            with self.subTest(val=str(val)), self.assertRaises(ValueError):
                planner.assign({"schema": "ata/durations/v1", "groups": [{"id": "x", "seconds": val}]}, 1)
        with self.assertRaises(ValueError):
            planner.assign({"schema": "ata/durations/v1", "groups": [
                {"id": "x", "seconds": 1}, {"id": "x", "seconds": 1}]}, 2)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ata-local-tests-")
        self.base = Path(self._tmp.name)
        self.project = self.base / "src"
        self.project.mkdir()
        self.results = self.base / "result"
        self.results.mkdir()
        self.script = self.project / "fixture.py"
        self.script.write_text('''import os, pathlib, sys, xml.etree.ElementTree as ET
report, marker, mode = map(pathlib.Path, sys.argv[1:4])
with marker.open("a", encoding="utf-8") as o: o.write("X")
if str(mode) == "no-xml": sys.exit(0)
s = ET.Element("testsuite", tests="1", failures="0", errors="0", skipped="0")
ET.SubElement(s, "testcase", name="test_fixture", classname="fixture")
ET.ElementTree(s).write(report, encoding="utf-8", xml_declaration=True)
if str(mode) == "fail": sys.exit(1)
''', encoding="utf-8")
        self.marker = self.base / "counter.txt"
        self.plan = {"schema": "ata/plan/v1", "work_id": "test-one", "min_free_disk_mib": 0, "units": [
            {"id": "unit1", "kind": "test", "cwd": str(self.project), "junit": "report.xml",
             "timeout_seconds": 10, "argv": [sys.executable, "-B", str(self.script),
                                                   "{unit_dir}/report.xml", str(self.marker), "pass"]}]}
        self.context = {"schema": "ata/context/v1", "work_id": "test-one",
                        "identity": {"source_type": "declared_files", "collection_digest": "fixture", "env": "test"},
                        "verification": {"kind": "declared_files", "root": str(self.project),
                                         "files": {"fixture.py": runner.file_digest(self.script)}}}
        self.plan_path = self.base / "plan.json"
        self.context_path = self.base / "context.json"
        self.save()

    def tearDown(self):
        self._tmp.cleanup()

    def save(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    def cli(self, action, *extra):
        cmd = [sys.executable, "-B", str(ROOT / "scripts/checkpoint_runner.py"), action,
               "--plan", str(self.plan_path), "--context", str(self.context_path)]
        if action != "inspect":
            cmd += ["--results", str(self.results)]
        return subprocess.run(cmd + list(extra), capture_output=True, text=True, timeout=25)

    def approved(self, *args):
        return self.cli("run", "--approve-plan-sha", runner.digest(self.plan), *args)

    def unit_dir(self):
        return self.results / "test-one" / runner.digest(self.plan) / runner.effective_context_hash(self.plan, self.context) / "unit1"

    def test_plan_inspection_cannot_execute(self):
        proc = self.cli("inspect")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("verified declared local files", proc.stdout)
        self.assertIn("argv", proc.stdout)
        self.assertFalse(self.marker.exists())

    def test_explicit_digest_required(self):
        p = self.cli("run")
        self.assertEqual(p.returncode, 3)
        self.assertFalse(self.marker.exists())

    def test_run_and_resume_reuses_valid_pass_without_reexecution(self):
        p = self.approved()
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(self.marker.read_text(), "X")
        receipt = runner.read_json(self.unit_dir() / "receipt.json")
        self.assertEqual(receipt["payload"]["return_code"], 0)
        self.assertEqual(receipt["payload"]["junit_counts"]["tests"], 1)
        self.assertTrue((self.unit_dir().parent / "state.json").is_file())
        self.assertEqual(self.cli("status").returncode, 0)
        p2 = self.approved()
        self.assertEqual(p2.returncode, 0, p2.stderr + p2.stdout)
        self.assertIn("SKIP unit1", p2.stdout)
        self.assertEqual(self.marker.read_text(), "X")

    def test_declared_source_change_blocks_even_matching_old_receipt(self):
        self.assertEqual(self.approved().returncode, 0)
        self.script.write_text(self.script.read_text() + "\n# changed\n")
        status = self.cli("status")
        self.assertEqual(status.returncode, 3)
        self.assertIn("Declared file missing/changed", status.stderr)
        self.assertEqual(self.marker.read_text(), "X")

    def test_event_chain_reveals_tampering(self):
        self.assertEqual(self.approved().returncode, 0)
        ledger = self.unit_dir().parent / "transitions.jsonl"
        length, checksum = runner.verify_event_chain(ledger)
        self.assertGreaterEqual(length, 2)
        self.assertEqual(len(checksum), 64)
        ledger.write_text(ledger.read_text().replace("UNIT_FINISHED", "UNIT_ALTERED"), encoding="utf-8")
        self.assertEqual(self.cli("status").returncode, 3)

    def test_receipt_tamper_blocks_reuse(self):
        self.assertEqual(self.approved().returncode, 0)
        receipt = self.unit_dir() / "receipt.json"
        r = runner.read_json(receipt)
        r["payload"]["junit_sha256"] = "0" * 64
        runner.atomic_json(receipt, r)
        status = self.cli("status")
        self.assertEqual(status.returncode, 1)
        denied = self.approved()
        self.assertEqual(denied.returncode, 2)
        self.assertEqual(self.marker.read_text(), "X")

    def test_missing_junit_not_a_pass(self):
        self.plan["units"][0]["argv"][-1] = "no-xml"
        self.save()
        p = self.approved()
        self.assertEqual(p.returncode, 2, p.stderr + p.stdout)
        self.assertIn("EXIT_ZERO_UNVERIFIED", p.stdout)

    def test_nonzero_exit_is_fail_even_with_valid_junit(self):
        self.plan["units"][0]["argv"][-1] = "fail"
        self.save()
        p = self.approved()
        self.assertEqual(p.returncode, 2, p.stderr + p.stdout)
        self.assertIn("FAIL rc=1", p.stdout)

    def test_inflight_requires_explicit_resume(self):
        unit = self.unit_dir()
        unit.mkdir(parents=True)
        runner.atomic_json(unit / "inflight.json", {"status": "RUNNING", "pid": 1111111})
        blocked = self.approved()
        self.assertEqual(blocked.returncode, 2)
        self.assertFalse(self.marker.exists())
        resumed = self.approved("--resume-interrupted")
        self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
        self.assertEqual(self.marker.read_text(), "X")

    def test_existing_lock_fails_without_auto_reclaim(self):
        lock = self.results / "test-one" / "run.lock"
        lock.parent.mkdir(parents=True)
        runner.atomic_json(lock, {"pid": 11111, "token": "old"})
        p = self.approved()
        self.assertEqual(p.returncode, 3)
        self.assertIn("LOCKED", p.stderr)
        self.assertEqual(runner.read_json(lock)["token"], "old")

    def test_lock_is_removed_on_clean_exit(self):
        self.assertEqual(self.approved().returncode, 0)
        self.assertFalse((self.results / "test-one" / "run.lock").exists())

    def test_shell_script_unreviewed_and_sensitive_context_rejected(self):
        self.plan["units"][0]["argv"] = ["bash", "-c", "true"]
        with self.assertRaises(ValueError):
            runner.validate(self.plan, self.context)
        self.plan["units"][0]["argv"] = [sys.executable, "-B", str(self.script)]
        self.context["identity"]["api_key"] = "not-real"
        with self.assertRaises(ValueError):
            runner.validate(self.plan, self.context)

    def test_direct_mutating_cli_rejected(self):
        for command in [["git", "push", "origin", "main"], ["gh", "pr", "merge", "1"],
                        ["curl", "-X", "POST", "https://example.invalid"],
                        [r"C:\\Windows\\System32\\cmd.exe", "/c", "echo hi"]]:
            self.plan["units"][0]["argv"] = command
            with self.subTest(command=command), self.assertRaises(ValueError):
                runner.validate(self.plan, self.context)

    def test_runner_environment_scrubs_secret_values(self):
        token_name = "GH_TOKEN_ATA_TEST"
        old = os.environ.get(token_name)
        os.environ[token_name] = "fake-secret"
        try:
            env = runner.safe_environment(self.plan["units"][0], self.unit_dir())
            self.assertNotIn(token_name, env)
            self.plan["units"][0]["pass_env"] = [token_name]
            with self.assertRaises(ValueError):
                runner.validate(self.plan, self.context)
        finally:
            if old is None:
                del os.environ[token_name]
            else:
                os.environ[token_name] = old

    def test_resource_profile_rejects_nan_and_zero_budget(self):
        resources = load_module("ata_resource_profile", ROOT / "scripts/resource_profile.py")
        for invalid in [0, -1, float("nan"), float("inf")]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                resources.profile(self.results, worker_memory_gib=invalid)
        data = resources.profile(self.results, worker_memory_gib=10**9)
        self.assertEqual(data["starting_workers"], 0)
        self.assertFalse(data["can_start_by_budget"])

    def test_disk_budget_prevents_execution(self):
        self.plan["min_free_disk_mib"] = 102400
        self.save()
        if shutil.disk_usage(self.results).free >= 102400 * 1024 * 1024:
            self.skipTest("Host has >100GiB free; budget test not applicable")
        p = self.approved()
        self.assertEqual(p.returncode, 3, p.stderr + p.stdout)
        self.assertIn("INSUFFICIENT_DISK", p.stderr)
        self.assertFalse(self.marker.exists())

    def test_selected_test_count_must_match_report(self):
        self.plan["units"][0]["expected_tests"] = 2
        self.save()
        p = self.approved()
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("TEST_COUNT_MISMATCH", p.stdout)

    def test_unaccepted_skips_reject_mixed_report(self):
        p = self.script
        code = p.read_text(encoding="utf-8").replace('tests="1", failures=', 'tests="2", failures=')
        code = code.replace('ET.ElementTree(s).write(report', 'ET.SubElement(ET.SubElement(s, "testcase", name="skipped"), "skipped")\ns.set("skipped", "1")\nET.ElementTree(s).write(report')
        p.write_text(code, encoding="utf-8")
        self.context["verification"]["files"]["fixture.py"] = runner.file_digest(p)
        self.save()
        r = self.approved()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("UNACCEPTED_SKIPS", r.stdout)

    def test_invalid_junit_forged_counts_rejected(self):
        fake = self.base / "fake.xml"
        fake.write_text('<testsuite tests="1" errors="0" failures="0" skipped="0"/>')
        with self.assertRaises(ValueError):
            runner.report_counts(fake)

    @unittest.skipUnless(shutil.which("git"), "Git not installed")
    def test_git_base_update_invalidates_result_with_same_feature_tree(self):
        repo = self.project
        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()
        subprocess.run(["git", "-C", str(repo), "init", "-b", "main", "-q"], check=True)
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.invalid")
        git("add", "fixture.py")
        git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "feature")
        (repo / "feature.txt").write_text("hello")
        git("add", "feature.txt")
        git("commit", "-q", "-m", "feature")
        head, tree, base_sha, mergebase = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}"), git("rev-parse", "main"), git("merge-base", "HEAD", "main")
        self.context["identity"] = {"source_head": head, "source_tree": tree,
                                     "base_ref": "main", "base_head": base_sha,
                                     "merge_base": mergebase}
        self.context["verification"] = {"kind": "git", "root": str(repo)}
        self.save()
        self.assertEqual(self.cli("inspect").returncode, 0)
        self.assertEqual(self.approved().returncode, 0)
        self.assertEqual(self.marker.read_text(), "X")
        git("checkout", "-q", "main")
        (repo / "base.txt").write_text("new base without changing feature")
        git("add", "base.txt")
        git("commit", "-q", "-m", "base advanced")
        git("checkout", "-q", "feature")
        self.assertEqual(git("rev-parse", "HEAD"), head)
        self.assertEqual(git("rev-parse", "HEAD^{tree}"), tree)
        self.assertEqual(self.cli("status").returncode, 3)
        self.assertIn("base_head", self.cli("status").stderr)
        self.assertEqual(self.marker.read_text(), "X")


if __name__ == "__main__":
    unittest.main()
