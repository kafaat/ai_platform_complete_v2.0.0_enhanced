import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

file = Path(__file__).resolve().parents[1] / ".github/scripts/madar_ci.py"
spec = importlib.util.spec_from_file_location("madar_ci", file)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def step(name, result, number=1):
    return {"name": name, "conclusion": result, "number": number}


def job(result, steps=None):
    return {"id": 3, "run_id": 2, "name": "Web", "conclusion": result, "steps": steps or []}


def block(cmd, message, fails=True):
    return f"TIME ##[group]Run {cmd}\nTIME ##[endgroup]\nTIME {message}\n" + (
        "TIME ##[error]Process completed with exit code 1.\n" if fails else ""
    )


def show(entry, fetch):
    return bot.card("owner/project", 2, entry, fetch)


class Triage(unittest.TestCase):
    def test_install_failure_distinct_from_test_result(self):
        log = block(
            "npx playwright install chromium",
            "Playwright does not support chromium on ubuntu26.04-x64",
        )
        log += block("echo E2E tests failed", "Private value 1234", False)
        result = show(
            job(
                "failure",
                [
                    step("Install Playwright Browsers", "failure", 6),
                    step("Run E2E Tests", "skipped", 11),
                ],
            ),
            lambda _: log,
        )
        self.assertIn("تعذّر تثبيت Chromium", result)
        self.assertIn("تخطّى GitHub خطوة Run E2E Tests", result)
        self.assertIn("#step:6:1", result)
        self.assertNotIn("1234", result)

    def test_dependency_drift(self):
        log = block(
            "python3 check-drift.py", "pydantic: service has ==2.14.3, constraints.txt has ==2.14.2"
        )
        self.assertIn(
            "تعارضاً",
            show(job("failure", [step("Check dependency drift", "failure")]), lambda _: log),
        )

    def test_assertion_after_tests_start(self):
        log = block("python -m pytest tests", "FAILED tests/test_x.py::test_case")
        self.assertIn(
            "فشل حالة اختبار", show(job("failure", [step("Run tests", "failure")]), lambda _: log)
        )

    def test_unrelated_successful_block_not_used(self):
        log = block(
            "npx playwright install",
            "Playwright does not support chromium on ubuntu26.04-x64",
            False,
        )
        log += block("python tool.py", "unrelated")
        self.assertIn(
            "يحتاج مراجعة",
            show(job("failure", [step("Install Playwright Browsers", "failure")]), lambda _: log),
        )

    def test_multiple_failures_indeterminate(self):
        data = [step("Install Playwright", "failure"), step("Cleanup", "failure", 2)]
        self.assertIn("تعذّر إسناد", show(job("failure", data), lambda _: ""))

    def test_missing_log_is_unknown(self):
        def missing(_):
            raise HTTPError("https://api.github.com", 404, "expired", {}, None)

        result = show(job("failure", [step("Run tests", "failure")]), missing)
        self.assertIn("HTTP 404", result)
        self.assertIn("لم يُفحص", result)

    def test_skip_and_cancel_without_log(self):
        for state, text in [("skipped", "لم تُشغّل"), ("cancelled", "أُلغي التشغيل")]:
            self.assertIn(text, show(job(state), lambda _: self.fail("unexpected log download")))

    def test_redirect_removes_secret(self):
        req = Request(
            "https://api.github.com/jobs/3/logs", headers={"Authorization": "Bearer test"}
        )
        redirect = bot.LogRedirect()
        target = redirect.redirect_request(req, None, 302, "Found", {}, "https://blob.example/test")
        self.assertNotIn("Authorization", target.headers)
        with self.assertRaises(ValueError):
            redirect.redirect_request(req, None, 302, "Found", {}, "http://blob.example/test")

    def test_attempt_pagination_and_summary(self):
        calls = []

        class API:
            def metadata(self, path):
                calls.append(path)
                return {"jobs": [job("success")] * 100 if len(calls) == 1 else [job("skipped")]}

            def log(self, _):
                raise AssertionError("unexpected log download")

        lines = []
        run = {
            "id": 2,
            "name": "CI",
            "run_attempt": 3,
            "head_sha": "a" * 40,
            "conclusion": "success",
        }
        bot.run_report(API(), "owner/repo", run, lines.append)
        assert len(lines) == 102
        self.assertIn("/attempts/3/jobs?", calls[0])
        self.assertTrue(calls[1].endswith("page=2"))
        self.assertIn("لم تُشغّل", lines[-1])

    def test_head_mismatch_fails_closed(self):
        class API:
            def metadata(self, _):
                return {"jobs": [dict(job("success"), head_sha="b" * 40)]}

        run = {"id": 2, "name": "CI", "run_attempt": 1, "head_sha": "a" * 40}
        emitted = []
        with self.assertRaisesRegex(ValueError, "job identity mismatch"):
            bot.run_report(API(), "owner/repo", run, emitted.append)
        assert len(emitted) == 1  # Only the run header may precede the rejected job.

    def entrypoint(self, event, run):
        queried = []

        class API:
            def metadata(self, path):
                queried.append(path)
                return {"jobs": [job("skipped")]} if "/jobs?" in path else run

            def log(self, _):
                raise AssertionError("no job log needed")

        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory, "event.json")
            summary_path = Path(directory, "summary.md")
            event_path.write_text(json.dumps(event))
            env = {
                "GH_TOKEN": "test",
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_STEP_SUMMARY": str(summary_path),
            }
            with patch.dict(bot.os.environ, env), patch.object(bot, "GitHub", return_value=API()):
                code = bot.main()
            return code, summary_path.read_text(), queried

    def test_realistic_webhook_entry(self):
        run = {
            "id": 2,
            "name": "CI",
            "head_sha": "c" * 40,
            "run_attempt": 4,
            "repository": {"full_name": "owner/repo"},
            "status": "completed",
            "conclusion": "success",
        }
        code, text, paths = self.entrypoint({"workflow_run": run}, run)
        self.assertEqual(code, 0)
        self.assertEqual(paths, ["runs/2/attempts/4/jobs?per_page=100&page=1"])
        self.assertIn("لم تُشغّل", text)
        self.assertIn("c" * 40, text)

    def test_manual_dispatch_entry(self):
        run = {
            "id": 2,
            "name": "CI",
            "head_sha": "d" * 40,
            "run_attempt": 3,
            "status": "completed",
            "conclusion": "success",
        }
        code, text, paths = self.entrypoint({"inputs": {"run_id": "2"}}, run)
        self.assertEqual(code, 0)
        self.assertEqual(paths, ["runs/2", "runs/2/attempts/3/jobs?per_page=100&page=1"])
        self.assertIn("محاولة 3", text)

    def test_untrusted_name(self):
        item = dict(job("success"), name="<img src=x> [click](https://bad.example) @maintainers")
        result = show(item, None)
        for literal in ["<img", "[click]", "@maintainers", "https://bad.example"]:
            self.assertNotIn(literal, result)


if __name__ == "__main__":
    unittest.main()
