import http.client
import importlib.util
import io
import json
import re
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

    def test_failing_test_is_named(self):
        log = block(
            "python -m pytest tests",
            "FAILED tests_v9/test_text_encoding_locale.py::test_no_new_file_decodes_text",
        )
        result = show(job("failure", [step("Run tests", "failure")]), lambda _: log)
        self.assertIn("أول حالة فاشلة", result)
        self.assertIn("test&#95;no&#95;new&#95;file&#95;decodes&#95;text", result)

    def test_long_log_keeps_its_tail(self):
        tail = block("python -m pytest tests", "FAILED tests/test_x.py::test_case").encode()
        body = b"x" * (bot.MAX_LOG + 1000) + tail
        text = bot.read_log_tail(io.BytesIO(body))
        self.assertTrue(text.truncated)
        self.assertEqual(len(text.encode()), bot.MAX_LOG)
        self.assertTrue(text.endswith(tail.decode()))
        result = show(job("failure", [step("Run tests", "failure")]), lambda _: text)
        self.assertIn("فشل حالة اختبار", result)
        self.assertIn("فُحص آخر 4 MiB", result)

    def test_short_log_is_whole(self):
        text = bot.read_log_tail(io.BytesIO(b"\xef\xbb\xbfshort"))
        self.assertFalse(text.truncated)
        self.assertEqual(text, "short")

    def test_oversized_log_is_reported_as_size_not_access(self):
        with self.assertRaises(bot.LogTooLarge):
            bot.read_log_tail(io.BytesIO(b"x" * 5000), keep=100, ceiling=4000)

        def huge(_):
            raise bot.LogTooLarge("too big")

        result = show(job("failure", [step("Run tests", "failure")]), huge)
        self.assertIn("أطول من 64 MiB", result)
        self.assertNotIn("تعذّر الوصول", result)
        self.assertIn("لم يُفحص", result)

    def test_monitored_workflows_exist(self):
        root = file.parents[2]
        bot_workflow = root / ".github/workflows/madar-ci-log-bot.yml"
        text = bot_workflow.read_text(encoding="utf-8")
        listed = re.search(r"(?m)^    workflows:\n((?:      - .+\n)+)", text).group(1)
        monitored = {line.split("- ", 1)[1].strip() for line in listed.splitlines()}
        names = set()
        for path in (root / ".github/workflows").glob("*.y*ml"):
            if path != bot_workflow:
                found = re.search(r"(?m)^name:\s*(.+?)\s*$", path.read_text(encoding="utf-8"))
                if found:
                    names.add(found.group(1).strip("\"'"))
        self.assertTrue(monitored)
        self.assertEqual(monitored - names, set())

    def test_dropped_log_stream_is_an_access_failure(self):
        def dropped(_):
            raise http.client.IncompleteRead(b"partial", 100)

        result = show(job("failure", [step("Run tests", "failure")]), dropped)
        self.assertIn("تعذّر الوصول", result)
        self.assertIn("لم يُفحص", result)

    def test_github_log_streams_the_tail(self):
        api = bot.GitHub("owner/repo", "test")
        body = b"y" * (bot.MAX_LOG + 10)
        with patch.object(api, "open", return_value=io.BytesIO(body)):
            text = api.log(3)
        self.assertTrue(text.truncated)
        self.assertEqual(len(text), bot.MAX_LOG)

    def test_cut_inside_a_character_is_replaced(self):
        text = bot.read_log_tail(io.BytesIO("aéé".encode()), keep=3)
        self.assertTrue(text.truncated)
        self.assertEqual(text, "\ufffdé")

    def test_whole_log_has_no_tail_note(self):
        log = bot.read_log_tail(io.BytesIO(block("python -m pytest t", "FAILED t.py::c").encode()))
        result = show(job("failure", [step("Run tests", "failure")]), lambda _: log)
        self.assertIn("فشل حالة اختبار", result)
        self.assertNotIn("فُحص آخر", result)

    def test_ceiling_boundary(self):
        self.assertEqual(len(bot.read_log_tail(io.BytesIO(b"z" * 40), keep=10, ceiling=40)), 10)
        with self.assertRaises(bot.LogTooLarge):
            bot.read_log_tail(io.BytesIO(b"z" * 41), keep=10, ceiling=40)

    def test_step_header_before_the_tail_still_frames_its_output(self):
        # SAHOOL run 45067849451: the unit step's header sat 4.7 MB before its FAILED line.
        log = (
            "T ##[group]Run actions/checkout\nT ##[endgroup]\nT done\n"
            "T ##[group]Run python -m pytest -m unit\nT ##[endgroup]\n"
            + "T PASSED tests/test_ok.py::test_ok\n"
            * 400
            + "T FAILED tests/test_x.py::test_case - AssertionError\n"
            "T ##[error]Process completed with exit code 1.\n"
        ).encode()
        text = bot.read_log_tail(io.BytesIO(log), keep=2000)
        self.assertTrue(text.truncated)
        self.assertTrue(
            text.startswith("T ##[group]Run python -m pytest -m unit\nT ##[endgroup]\n")
        )
        result = show(job("failure", [step("Run unit tests", "failure")]), lambda _: text)
        self.assertIn("test&#95;case", result)
        self.assertIn("فُحص آخر", result)

    def test_tail_starting_at_a_header_gets_no_extra_header(self):
        head = b"T ##[group]Run old\nT ##[endgroup]\n" + b"x\n" * 50
        tail = b"T ##[group]Run python -m pytest\nT ##[endgroup]\nT ok\n"
        text = bot.read_log_tail(io.BytesIO(head + tail), keep=len(tail))
        self.assertEqual(text, tail.decode())

    def test_routing_by_step_then_job_then_log(self):
        cases = [
            ("Security Scan", "pip-audit (gating)", "", "dependencies"),
            ("Security Scan", "bandit high", "", "security"),
            ("Frontend Typecheck", "Run tsc", "", "frontend"),
            ("Live PG Proofs (fake-connection debt)", "Run", "", "migrations"),
            (
                "Unit Tests",
                "Run pytest",
                'psycopg.errors.UndefinedTable: relation "x" does not exist',
                "migrations",
            ),
            ("Unit Tests", "Run pytest", "found CVE-2026-12345 in requests", "security"),
            ("Unit Tests", "Run pytest", "assert 1 == 2", "ci-quality"),
        ]
        for job_name, step_name, text, role in cases:
            self.assertEqual(bot.route(job_name, step_name, text), role, (job_name, step_name))

    def test_failed_card_hands_off_with_link_step_and_commit(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        entry = dict(job("failure", [step("Typecheck", "failure", 4)]), head_sha="e" * 40)
        result = show(entry, lambda _: log)
        self.assertIn(".claude/agents/frontend-reviewer.md", result)
        self.assertIn("ci-fixer", result)
        self.assertIn("#step:4:1", result.split("الإحالة")[1])
        self.assertIn("e" * 40, result)

    def test_routing_reads_only_the_failure_summary(self):
        # Megabytes of passed test names must not route the job (run 45067849451 named run_migrations).
        log = block(
            "python -m pytest -m unit",
            "PASSED tests_v9/test_run_migrations.py::test_ok\n" * 300
            + "T ===== short test summary info =====\nT FAILED tests_v9/test_x.py::test_y - AssertionError",
        )
        result = show(job("failure", [step("Run tests", "failure")]), lambda _: log)
        self.assertIn("ci-quality-triage", result)

    def test_unreadable_log_still_routed_by_name(self):
        def missing(_):
            raise HTTPError("https://api.github.com", 410, "gone", {}, None)

        entry = dict(job("failure", [step("bandit high severity", "failure")]))
        self.assertIn("security-reviewer", show(entry, missing))

    def test_every_route_has_an_agent_and_reviewers_cannot_edit(self):
        agents = file.parents[2] / ".claude/agents"
        for role, (_, agent) in bot.SPECIALISTS.items():
            text = (agents / f"{agent}.md").read_text(encoding="utf-8")
            tools = re.search(r"(?m)^tools:\s*(.+)$", text).group(1)
            self.assertIn(f"name: {agent}", text, role)
            self.assertNotRegex(tools, r"\b(Edit|Write|NotebookEdit)\b", role)
            self.assertIn("Read only", text, role)
        fixer = (agents / f"{bot.FIXER}.md").read_text(encoding="utf-8")
        self.assertIn("Never push to main, merge", fixer)
        self.assertEqual({r for r, *_ in bot.ROUTES} | {"ci-quality"}, set(bot.SPECIALISTS))

    def test_header_survives_many_trims(self):
        # Review gap (a): the carried header must outlive every chunk, not only the last one.
        class Chunky:
            def __init__(self, data):
                self.data, self.at = data, 0

            def read(self, size):
                piece = self.data[self.at : self.at + 300]
                self.at += len(piece)
                return piece

        log = (
            "T ##[group]Run python -m pytest -m unit\nT ##[endgroup]\n"
            + "T PASSED tests/test_ok.py::test_ok\n" * 600
            + "T FAILED tests/test_x.py::test_case\nT ##[error]Process completed with exit code 1.\n"
        ).encode()
        text = bot.read_log_tail(Chunky(log), keep=2000)
        self.assertTrue(text.startswith("T ##[group]Run python -m pytest -m unit\n"))

    def test_header_inside_the_tail_is_not_carried(self):
        # Review gap (b): only a header before the cut is carried.
        log = b"T ##[group]Run old\nT ##[endgroup]\n" + b"o\n" * 100
        log += b"mid output\nT ##[group]Run python -m pytest\nT ##[endgroup]\nT ok\n"
        keep = len(b"mid output\nT ##[group]Run python -m pytest\nT ##[endgroup]\nT ok\n")
        text = bot.read_log_tail(io.BytesIO(log), keep=keep)
        self.assertTrue(text.startswith("T ##[group]Run old\nT ##[endgroup]\nmid output"))

    def test_crlf_header_is_carried_without_carriage_return(self):
        # Review gap (c).
        log = b"T ##[group]Run python -m pytest\r\nT ##[endgroup]\r\n" + b"p\r\n" * 200
        text = bot.read_log_tail(io.BytesIO(log), keep=100)
        self.assertTrue(text.startswith("T ##[group]Run python -m pytest\nT ##[endgroup]\n"))

    def test_dropped_stream_while_listing_jobs_is_reported(self):
        # Review gap (d): main() keeps an HTTPException from becoming a traceback.
        class API:
            def metadata(self, _):
                raise http.client.IncompleteRead(b"", 10)

        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory, "event.json")
            summary = Path(directory, "summary.md")
            event.write_text(json.dumps({"inputs": {"run_id": "2"}}), encoding="utf-8")
            env = {
                "GH_TOKEN": "t",
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            with patch.dict(bot.os.environ, env), patch.object(bot, "GitHub", return_value=API()):
                self.assertEqual(bot.main(), 1)
            self.assertIn("تعذّر إكمال", summary.read_text(encoding="utf-8"))

    def test_pytest_named_whatever_the_step_is_called(self):
        # Devin on #1586: ci.yml's serial step has no "test" in its name.
        log = block("pytest -m 'unit and tree_writer'", "FAILED tests_v9/test_c.py::test_contract")
        name = "Unit suite \u2014 serial tree_writer half + coverage ratchet over both halves"
        result = show(job("failure", [step(name, "failure")]), lambda _: log)
        self.assertIn("test&#95;contract", result)

    def test_pytest_on_a_later_script_line(self):
        # Devin on #1586: a step that installs first and runs pytest on its second line.
        log = (
            "T ##[group]Run pip install -r requirements.txt\nT pip install -r requirements.txt\n"
            "T python -m pytest tests -q\nT shell: /usr/bin/bash -e {0}\nT ##[endgroup]\n"
            "T FAILED tests/test_s.py::test_service\nT ##[error]Process completed with exit code 1.\n"
        )
        result = show(job("failure", [step("Service-local tests", "failure")]), lambda _: log)
        self.assertIn("test&#95;service", result)

    def test_truncation_keeps_the_dropped_group_script(self):
        group = (
            b"T ##[group]Run pip install -r requirements.txt\nT python -m pytest tests -q\n"
            b"T ##[endgroup]\n"
        )
        log = group + b"T PASSED t.py::ok\n" * 300
        log += b"T FAILED tests/test_s.py::test_service\nT ##[error]Process completed with exit code 1.\n"
        text = bot.read_log_tail(io.BytesIO(log), keep=500)
        self.assertTrue(text.startswith(group.decode()))
        result = show(job("failure", [step("Service-local tests", "failure")]), lambda _: text)
        self.assertIn("test&#95;service", result)

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
            event_path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
            env = {
                "GH_TOKEN": "test",
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_STEP_SUMMARY": str(summary_path),
            }
            with patch.dict(bot.os.environ, env), patch.object(bot, "GitHub", return_value=API()):
                code = bot.main()
            return code, summary_path.read_text(encoding="utf-8"), queried

    def test_realistic_webhook_entry(self):
        run = {
            "id": 2,
            "name": "فحص CI",
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
