"""Safe, synthetic, no-network tests for Adaptive Test Accelerator."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_at(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = import_at("checkpoint_runner")
planner = import_at("duration_planner")
resources = import_at("resource_profile")


class PlannerTests(unittest.TestCase):
    def test_balancing(self):
        data = {"schema": "ata/durations/v1", "groups": [{"id": "a", "seconds": 6},
                 {"id": "b", "seconds": 4}, {"id": "c", "seconds": 3}, {"id": "d", "seconds": 2}]}
        shards = planner.assign(data, 2)
        self.assertEqual(sorted(sum((s["groups"] for s in shards), [])), ["a", "b", "c", "d"])
        self.assertEqual([s["estimated_seconds"] for s in shards], [8, 7])

    def test_affinity(self):
        data = {"schema": "ata/durations/v1", "groups": [{"id": "db1", "seconds": 4, "affinity": "DB"},
                  {"id": "db2", "seconds": 7, "affinity": "DB"}, {"id": "api", "seconds": 6}]}
        shards = planner.assign(data, 2)
        self.assertTrue(any(set(["db1", "db2"]).issubset(set(s["groups"])) for s in shards))

    def test_stability(self):
        data = {"schema": "ata/durations/v1", "groups": [{"id": str(i), "seconds": (i % 7) + 1} for i in range(40)]}
        self.assertEqual(planner.assign(data, 4), planner.assign(data, 4))

    def test_reject_invalid_durations(self):
        for seconds in [0, -1, float("nan"), float("inf")]:
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                planner.assign({"schema": "ata/durations/v1", "groups": [{"id": "x", "seconds": seconds}]}, 2)

    def test_reject_duplicate_groups(self):
        with self.assertRaises(ValueError):
            planner.assign({"schema": "ata/durations/v1", "groups": [{"id": "x", "seconds": 1}, {"id": "x", "seconds": 2}]}, 2)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "repo"
        self.cwd.mkdir()
        (self.cwd / "tracked-test-input.txt").write_text("synthetic fixture only", encoding="utf-8")
        self.results = self.root / "outside-repo"
        self.plan_path = self.root / "plan.json"
        self.context_path = self.root / "context.json"
        self.plan = {"schema": "ata/plan/v1", "work_id": "trial", "units": [self.make_unit()]}
        self.context = {"schema": "ata/context/v1", "work_id": "trial", "identity": {
            "source_tree": "synthetic-tree-001", "base_head": "synthetic-base-001", "merge_base": "synthetic-mb-001",
            "environment_digest": "synthetic-env-001", "collection_digest": "synthetic-tests-001"},
            "verification": {"kind": "declared_files", "root": str(self.cwd),
                             "files": {"tracked-test-input.txt": runner.file_digest(self.cwd / "tracked-test-input.txt")}}}
        self.sync()

    def make_unit(self, extra_code="", code=0, junit=True, skip=False):
        report = '<testsuite tests="1" errors="0" failures="0" skipped="' + ('1' if skip else '0') + '"><testcase name="synthetic">' + ('<skipped />' if skip else '') + '</testcase></testsuite>'
        fragments = ["from pathlib import Path", "import os"]
        if junit:
            fragments.append("Path(os.environ['ATR_UNIT_DIR'],'junit.xml').write_text(" + repr(report) + ")")
        if extra_code:
            fragments.append(extra_code)
        fragments.append(f"raise SystemExit({code})")
        body = "; ".join(fragments)
        return {"id": "one", "kind": "test", "cwd": str(self.cwd),
                "argv": [sys.executable, "-c", body], "junit": "junit.xml", "timeout_seconds": 10}

    def sync(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    def cmd(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = runner.main([*args, "--plan", str(self.plan_path), "--context", str(self.context_path),
                                "--results", str(self.results)])
        return code, output.getvalue()

    def approval(self):
        return ["--approve-plan-sha", runner.digest(self.plan)]

    def result_dir(self):
        return self.results / "trial" / runner.digest(self.plan) / runner.effective_context_hash(self.plan, self.context) / "one"

    def test_inspect_only_no_run(self):
        code, result = self.cmd("inspect")
        self.assertEqual(code, 0)
        self.assertIn(runner.digest(self.plan), result)
        self.assertFalse(self.results.exists())

    def test_requires_approval(self):
        with self.assertRaisesRegex(ValueError, "Execution refused"):
            self.cmd("run")

    def test_pass_and_reuse(self):
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 0, logs)
        self.assertTrue((self.result_dir() / "receipt.json").is_file())
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 0, logs)
        self.assertIn("SKIP one", logs)
        self.assertEqual(self.cmd("status")[0], 0)

    def test_not_success_without_junit(self):
        self.plan["units"][0] = self.make_unit(junit=False)
        self.sync()
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 2, logs)
        self.assertEqual(self.cmd("status")[0], 1)

    def test_skipped_only_not_pass(self):
        self.plan["units"][0] = self.make_unit(skip=True)
        self.sync()
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 2, logs)

    def test_failed_receipt_not_reused(self):
        self.plan["units"][0] = self.make_unit(code=1)
        self.sync()
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 2, logs)
        code, logs = self.cmd("run", *self.approval())
        self.assertIn("BLOCK", logs)

    def test_failed_retry_archive(self):
        self.plan["units"][0] = self.make_unit(code=1)
        self.sync()
        self.cmd("run", *self.approval())
        code, logs = self.cmd("run", *self.approval(), "--retry-failed")
        self.assertEqual(code, 2, logs)
        self.assertEqual(len(list((self.result_dir() / "history").iterdir())), 1)

    def test_base_change_invalidates(self):
        self.cmd("run", *self.approval())
        old_path = self.result_dir()
        self.context["identity"]["base_head"] = "synthetic-base-002"
        self.sync()
        self.assertEqual(self.cmd("status")[0], 1)
        self.assertNotEqual(old_path, self.result_dir())

    def test_merge_base_change_invalidates(self):
        self.cmd("run", *self.approval())
        self.context["identity"]["merge_base"] = "synthetic-mb-002"
        self.sync()
        self.assertEqual(self.cmd("status")[0], 1)

    def test_argv_change_invalidates(self):
        self.cmd("run", *self.approval())
        self.plan["units"][0]["timeout_seconds"] = 11
        self.sync()
        self.assertEqual(self.cmd("status")[0], 1)

    def test_reject_stale_local_lock(self):
        lock = self.results / "trial" / "run.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text('{"token":"unknown"}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "LOCKED"):
            self.cmd("run", *self.approval())
        self.assertTrue(lock.exists())

    def test_corrupted_receipt_is_invalid(self):
        self.cmd("run", *self.approval())
        receipt = self.result_dir() / "receipt.json"
        data = json.loads(receipt.read_text())
        data["payload"]["status"] = "FAIL"
        receipt.write_text(json.dumps(data))
        self.assertEqual(self.cmd("status")[0], 1)

    def test_corrupted_junit_is_invalid(self):
        self.cmd("run", *self.approval())
        (self.result_dir() / "junit.xml").write_text("<broken />")
        self.assertEqual(self.cmd("status")[0], 1)

    def test_inflight_blocks_no_auto_resume(self):
        unit_dir = self.result_dir()
        unit_dir.mkdir(parents=True)
        runner.atomic_json(unit_dir / "inflight.json", {"status": "RUNNING", "pid": 34534, "host": "another-host"})
        code, logs = self.cmd("run", *self.approval())
        self.assertIn("BLOCK", logs)
        self.assertEqual(code, 2)
        code, logs = self.cmd("run", *self.approval(), "--resume-interrupted")
        self.assertEqual(code, 0, logs)
        self.assertTrue(list((unit_dir / "history").iterdir()))

    def test_reject_secrets_in_context_key(self):
        self.context["identity"]["api_key"] = "not-an-actual-key"
        with self.assertRaisesRegex(ValueError, "potential secret"):
            runner.validate(self.plan, self.context)

    def test_disallow_shell(self):
        self.plan["units"][0]["argv"] = ["bash", "-lc", "echo nope"]
        with self.assertRaisesRegex(ValueError, "shell invocation"):
            runner.validate(self.plan, self.context)

    def test_output_bounded_by_default(self):
        self.plan["units"][0] = self.make_unit(extra_code="print('z' * 90000)")
        self.sync()
        code, logs = self.cmd("run", *self.approval())
        self.assertEqual(code, 0, logs)
        receipt = json.loads((self.result_dir() / "receipt.json").read_text())
        self.assertIsNone(receipt["payload"]["output_tail"])
        self.assertGreater(receipt["payload"]["output_bytes"], 90000)


class ResourceTests(unittest.TestCase):
    def test_resource_profile_is_conservative(self):
        with tempfile.TemporaryDirectory() as d:
            data = resources.profile(Path(d))
        self.assertGreaterEqual(data["starting_workers"], 1)
        self.assertLessEqual(data["starting_workers"], 4)
        self.assertTrue(data["requires_review"])

    def test_reject_bad_memory_estimate(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                resources.profile(Path(d), worker_memory_gib=0)


if __name__ == "__main__":
    unittest.main()
