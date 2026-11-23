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


class Chunky:
    """A log response that hands out small pieces, as a slow stream would."""

    def __init__(self, data, size=300):
        self.data, self.at, self.size = data, 0, size

    def read(self, _):
        piece = self.data[self.at : self.at + self.size]
        self.at += len(piece)
        return piece


class HeadlessJobAPI:
    """One failed job without its own head_sha, and its log."""

    def __init__(self, log):
        self.text = log

    def metadata(self, _):
        entry = job("failure", [step("Typecheck", "failure")])
        entry.pop("head_sha", None)
        return {"jobs": [entry]}

    def log(self, _):
        return self.text


RUNNER_TS = "2026-11-22T20:46:23.4411059Z"


def runner_block(script, message):
    """A failed step as the runner writes it: every line timestamped, the script echoed."""
    first, *rest = script.split("\n")
    lines = [
        f"{RUNNER_TS} ##[group]Run {first}",
        *(f"{RUNNER_TS} {line}" for line in [first, *rest]),
    ]
    lines += [f"{RUNNER_TS} ##[endgroup]", f"{RUNNER_TS} {message}"]
    lines.append(f"{RUNNER_TS} ##[error]Process completed with exit code 1.")
    return "\n".join(lines) + "\n"


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
            front = text.split("---", 2)[1]
            tools = re.search(r"(?ms)^tools:(.*?)(?=^\w+:|\Z)", front).group(1)
            self.assertIn(f"name: {agent}", text, role)
            self.assertNotRegex(tools, r"\b(Edit|Write|NotebookEdit)\b", role)
            self.assertIn("Read only", text, role)
        fixer = (agents / f"{bot.FIXER}.md").read_text(encoding="utf-8")
        self.assertIn("Never push to main, merge", fixer)
        self.assertIn("Never on main.", fixer)
        self.assertEqual(set(bot.ROUTES) | {"ci-quality"}, set(bot.SPECIALISTS))
        self.assertEqual({r for r, _ in bot.LOG_SIGNS}, set(bot.ROUTES))
        self.assertLessEqual(set(bot.JOB_OWNERS.values()), set(bot.ROUTES))

    def test_header_survives_many_trims(self):
        # Review gap (a): the carried header must outlive every chunk, not only the last one.
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

    def test_generated_inventory_drift_is_not_a_dependency_failure(self):
        # Devin on #1588: ci.yml's structural lint uses "drift" for generated files.
        for step_name in [
            "service-inventory-drift-gate",
            "platform-main-subinventory-drift-gate",
            "route-mount-inventory-drift-gate",
            "platform-catalog-drift-gate",
        ]:
            self.assertEqual(bot.route("Repository Structural Lint", step_name), "ci-quality")
        self.assertEqual(bot.route("CI", "Check dependency-drift"), "dependencies")
        self.assertEqual(
            bot.route("CI", "Run pip install -c constraints-ci-tools.txt ruff"), "dependencies"
        )

    def test_npm_install_failures_reach_the_dependency_reviewer(self):
        # Devin on #1588: unnamed `npm ci` steps inside frontend jobs.
        step_name = "Run npm ci --ignore-scripts --no-audit --no-fund"
        for job_name in [
            "Frontend Typecheck",
            "Frontend E2E (Playwright \u00b7 MapLibre/WebGL QA)",
        ]:
            self.assertEqual(bot.route(job_name, step_name), "dependencies")
        self.assertEqual(
            bot.route("Frontend Typecheck", "Prepare the workspace", "npm ERR! code ERESOLVE"),
            "dependencies",
        )
        self.assertEqual(bot.route("Frontend Typecheck", "Run npm run typecheck", ""), "frontend")

    def test_pull_request_runs_say_ci_tested_the_merge(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        entry = dict(job("failure", [step("Typecheck", "failure")]), head_sha="f" * 40)
        merged = bot.card("o/r", 2, entry, lambda _: log, merge_tested=True)
        plain = bot.card("o/r", 2, entry, lambda _: log)
        self.assertIn("دمجه مع الفرع الأساسي", merged)
        self.assertNotIn("دمجه مع الفرع الأساسي", plain)

    def test_missing_or_bad_commit_is_unknown(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        for sha in [None, "not-a-sha`]", "a" * 39]:
            entry = dict(job("failure", [step("Typecheck", "failure")]), head_sha=sha)
            result = show(entry, lambda _: log)
            self.assertIn("الالتزام غير معلوم", result)
            self.assertNotIn("not-a-sha", result)

    def test_frontend_reviewer_installs_without_lifecycle_scripts(self):
        text = (file.parents[2] / ".claude/agents/frontend-reviewer.md").read_text(encoding="utf-8")
        self.assertIn("npm ci --ignore-scripts", text)
        self.assertNotRegex(text, r"`npm ci`(?! --ignore-scripts)")

    def test_descriptive_step_names_do_not_pick_a_specialist(self):
        # Independent review of #1588: real SAHOOL names that loose patterns misrouted.
        cases = [
            ("runtime-stack-e2e-chaos", "WX-10.6 crop-candidate downstream E2E (real Postgres)"),
            ("Integration Tests", "S3 Compose slice acceptance (real services, no database)"),
            ("Integration Tests", "Start isolated PostgreSQL 16 (no external secrets)"),
            ("Integration Tests", "MFA end-to-end via the real auth app (restricted role)"),
            ("Repository Structural Lint", "env-compose-drift-guard"),
            ("Repository Structural Lint", "dependency-conflict-inventory context guard"),
        ]
        for job_name, step_name in cases:
            self.assertEqual(bot.route(job_name, step_name), "ci-quality", step_name)

    def test_each_log_sign_routes(self):
        signs = {
            "security": "Found CVE-2026-12345 in urllib3",
            "migrations": "psycopg.errors.UndefinedTable: x  SQLSTATE 42P01",
            "dependencies": "npm ERR! code ERESOLVE",
            "frontend": "src/a.ts(3,5): error TS2322: bad",
        }
        for role, text in signs.items():
            self.assertEqual(bot.route("Unit Tests", "Run the suite", text), role)
        self.assertEqual(
            bot.route("Unit Tests", "Run the suite", "GHSA-abcd-1234-wxyz"), "security"
        )
        self.assertEqual(
            bot.route("Unit Tests", "Run the suite", "ERROR: SQLSTATE 42P01"), "migrations"
        )

    def test_card_routes_by_its_log(self):
        log = block(
            "pytest -m unit",
            'T E   asyncpg.exceptions.UndefinedTableError: relation "farm" does not exist',
        )
        result = show(job("failure", [step("Unit suite", "failure")]), lambda _: log)
        self.assertIn("migrations-reviewer", result)
        self.assertIn("الخطوة التالية", result)

    def test_ungrouped_gitleaks_alert_routes_independently_of_color(self):
        entry = dict(
            job("failure", [step("Scan complete Git history for secrets", "failure", 3)]),
            name="gitleaks-full-history",
        )
        for line, owner in (
            ("WRN leaks found: 1", "security-reviewer"),
            ("WRN \x1b[1mleaks found: 1\x1b[0m", "security-reviewer"),
            ("WRN \x1b[1mscan interrupted\x1b[0m", "ci-quality-triage"),
        ):
            with self.subTest(line=line):
                self.assertIn(owner, show(entry, lambda _, line=line: line))

    def test_several_failed_steps_go_to_ci_quality(self):
        steps = [step("Run npx tsc --noEmit", "failure"), step("Run bandit", "failure", 2)]
        result = show(job("failure", steps), lambda _: "")
        self.assertIn("ci-quality-triage", result)

    def test_bad_job_commit_falls_back_to_the_run_head(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        entry = dict(job("failure", [step("Typecheck", "failure")]), head_sha="bad")
        result = bot.card("o/r", 2, entry, lambda _: log, head="c" * 40)
        self.assertIn("c" * 40, result)

    def test_empty_failure_output_falls_back_to_the_log_end(self):
        self.assertEqual(bot.failing_output("x" * 9000 + "tail"), ("x" * 9000 + "tail")[-8192:])

    def test_group_closing_after_the_cut_carries_only_its_header(self):
        group = b"T ##[group]Run pip install x\nT python -m pytest\n"
        rest = b"T more script\n" * 50 + b"T ##[endgroup]\n" + b"T out\n" * 50
        text = bot.read_log_tail(io.BytesIO(group + rest), keep=400)
        self.assertTrue(text.startswith("T ##[group]Run pip install x\nT ##[endgroup]\n"))

    def test_oversized_group_carries_only_its_header(self):
        group = b"T ##[group]Run big\n" + b"T " + b"s" * 17000 + b"\nT ##[endgroup]\n"
        text = bot.read_log_tail(io.BytesIO(group + b"T out\n" * 100), keep=300)
        self.assertTrue(text.startswith("T ##[group]Run big\nT ##[endgroup]\n"))

    def test_echoed_endgroup_text_does_not_close_the_carried_group(self):
        group = (
            b"T ##[group]Run echo x\nT echo '##[endgroup]'\nT python -m pytest\nT ##[endgroup]\n"
        )
        text = bot.read_log_tail(io.BytesIO(group + b"T out\n" * 100), keep=300)
        self.assertTrue(text.startswith(group.decode()))

    def test_lab_1588_real_step_names(self):
        # Lab 1588: real runs 45066967613, 45051026057 and 45054521999.
        drift = block(
            "python scripts/ci/capability_mapping_engine.py --check",
            "T drift: run capability_mapping_engine.py --generate",
        )
        card = show(
            job("failure", [step("Validate forensic capability mapping drift", "failure")]),
            lambda _: drift,
        )
        self.assertIn("ci-quality-triage", card)
        oom = block("docker compose up minio-init", "T Killed mc admin policy attach")
        name = "S3 Compose slice acceptance (real services, no database)"
        self.assertIn(
            "ci-quality-triage", show(job("failure", [step(name, "failure")]), lambda _: oom)
        )

    def test_pip_audit_in_a_generic_step_of_the_security_job(self):
        log = block(
            "python -m pip_audit -r requirements.txt",
            "T Found 2 known vulnerabilities in 1 package\nT urllib3 2.0 CVE-2026-1",
        )
        entry = dict(job("failure", [step("Gate critical path", "failure")]), name="Security Scan")
        self.assertIn("dependency-reviewer", show(entry, lambda _: log))

    def test_tool_in_the_failed_script_routes(self):
        log = block("cd frontend && npx vitest run", "T FAIL src/a.test.ts")
        self.assertIn(
            "frontend-reviewer",
            show(job("failure", [step("Run the checks", "failure")]), lambda _: log),
        )
        log = block(
            "pip install -r r.txt\nT python -m pytest tests", "T FAILED tests/test_s.py::test_x"
        )
        result = show(job("failure", [step("Service-local tests", "failure")]), lambda _: log)
        self.assertIn("ci-quality-triage", result)

    def test_comments_and_install_lines_do_not_route(self):
        # Independent review of 43c0a99f: incidental tool names in the failed script.
        log = runner_block(
            "# mirrors tsc strictness\nnpx playwright install chromium\npython -m pytest t",
            "FAILED t.py::x",
        )
        self.assertIn(
            "ci-quality-triage",
            show(job("failure", [step("Backend checks", "failure")]), lambda _: log),
        )
        log = runner_block(
            "# bandit is run elsewhere\npython scripts/ci/workflow_guard.py", "unsafe pattern"
        )
        result = show(
            job("failure", [step("Detect unsafe workflow patterns", "failure")]), lambda _: log
        )
        self.assertIn("ci-quality-triage", result)
        self.assertNotIn("pip", bot.failing_command(block("pip install -r r.txt\nT pytest", "T x")))

    def test_every_security_tool_routes(self):
        for name in [
            "Run gitleaks detect",
            "Run trivy fs .",
            "Run secret-scan",
            "Run bandit -r services",
        ]:
            self.assertEqual(bot.route("Some job", name), "security", name)

    def test_run_report_falls_back_to_the_run_head(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        lines = []
        run = {"id": 2, "name": "CI", "run_attempt": 1, "head_sha": "d" * 40, "event": "push"}
        bot.run_report(HeadlessJobAPI(log), "owner/repo", run, lines.append)
        self.assertIn("d" * 40, lines[-1])
        self.assertNotIn("دمجه مع الفرع الأساسي", lines[-1])

    def test_migration_runners_and_psql_errors(self):
        # Devin on #1588: ci.yml's real migration steps.
        self.assertEqual(
            bot.route(
                "Integration Tests",
                "Apply migrations to test DB",
                "",
                "bash scripts/ci/apply_migration_manifest.sh --port 5433",
            ),
            "migrations",
        )
        self.assertEqual(
            bot.route(
                "Decision Service Tests",
                "Apply decision-service migrations",
                "",
                "python services/decision-service/migration_runner.py --apply",
            ),
            "migrations",
        )
        self.assertEqual(
            bot.route(
                "Integration Tests",
                "Run step",
                'psql:migrations/v288.sql:3: ERROR:  syntax error at or near "CREAT"',
            ),
            "migrations",
        )

    def test_standalone_dependency_install_steps(self):
        # Devin on #1588: "Install raster test dependencies" and pip's malformed requirement.
        self.assertEqual(
            bot.route("Raster Service Tests", "Install raster test dependencies"), "dependencies"
        )
        self.assertEqual(
            bot.route("Raster Service Tests", "Run step", "ERROR: Invalid requirement: 'numpy=='"),
            "dependencies",
        )
        self.assertEqual(
            bot.route(
                "Some job",
                "Run step",
                "ERROR: Could not find a version that satisfies the requirement x",
            ),
            "dependencies",
        )

    def test_timestamped_comment_lines_do_not_route(self):
        # Lab 1588-v3: real script lines carry the runner's timestamp, lowercased with the command.
        ts = "2026-11-22T20:46:23.4411059Z"
        log = (
            f"{ts} ##[group]Run python scripts/ci/workflow_guard.py\n"
            f"{ts} # mirrors bandit and tsc\n"
            f"{ts} python scripts/ci/workflow_guard.py\n"
            f"{ts} ##[endgroup]\n{ts} unsafe pattern found\n"
            f"{ts} ##[error]Process completed with exit code 1.\n"
        )
        self.assertNotIn("bandit", bot.failing_command(log))
        result = show(
            job("failure", [step("Detect unsafe workflow patterns", "failure")]), lambda _: log
        )
        self.assertIn("ci-quality-triage", result)

    def test_merge_note_is_conditional_on_the_checkout(self):
        log = block("npx tsc --noEmit", "src/a.ts(1,1): error TS2322: bad")
        entry = dict(job("failure", [step("Typecheck", "failure")]), head_sha="f" * 40)
        merged = bot.card("o/r", 2, entry, lambda _: log, merge_tested=True)
        self.assertIn("إن سحبت الوظيفة بالإعداد الافتراضي", merged)
        self.assertIn("checkout", merged)

    def test_only_install_subcommands_are_dropped(self):
        # Independent review of 53da5811: "install" elsewhere on a tool line must not drop it.
        for script, kept in [
            ("npx playwright test tests/install.spec.ts", "npx playwright"),
            ("npx tsc --noEmit && pip install -e .", "tsc"),
            ("pip install -e . && npx tsc --noEmit", "tsc"),
            ("npm run test -- install-flow", "npm run test"),
            ("npx vitest run src/install/", "vitest"),
        ]:
            self.assertIn(kept, bot.failing_command(runner_block(script, "failed")), script)
        for script in [
            "pip install -r r.txt",
            "python -m pip install x",
            "sudo apt-get -y install jq",
            "npx playwright install chromium",
            "npm ci",
        ]:
            self.assertEqual(bot.failing_command(runner_block(script, "failed")), "", script)

    def test_wrapped_and_rarer_install_forms_are_dropped(self):
        # #1588 follow-up: an install behind an env assignment, a wrapper or a shell keyword
        # still names a tool that did not fail.
        for script in [
            "CI=1 npm ci",
            "PIP_NO_CACHE_DIR=1 pip install -r r.txt",
            "sudo -E apt-get install -y jq",
            "env npm ci",
            "time pnpm install --frozen-lockfile",
            "npm i",
            "pnpm i",
            "flutter pub get",
            "dart pub get",
            "uv pip install -r r.txt",
            "python3 -m pip install -U pip",
        ]:
            self.assertEqual(bot.failing_command(runner_block(script, "failed")), "", script)

    def test_every_segment_separator_is_split(self):
        # Each separator alone, so a regression to splitting on `&&` only turns this red.
        for script, kept in [
            ("pip install -e . ; npx tsc --noEmit", "tsc"),
            ("npm ci || npx tsc --noEmit", "tsc"),
            ("pip install x && ruff check .", "ruff"),
            ("npx tsc --noEmit | tee out.txt", "tsc"),
            # Only a split on the single pipe separates this install from the tee.
            ("npm ci 2>&1 | tee npm.log", "tee npm.log"),
            ("if npm ci; then npx vitest run; fi", "vitest"),
        ]:
            out = bot.failing_command(runner_block(script, "failed"))
            self.assertIn(kept, out, script)
            self.assertNotIn("npm ci", out, script)
            self.assertNotIn("pip install", out, script)

    def test_install_words_inside_a_command_keep_the_command(self):
        # Anchored match, not search: a tool line that merely mentions an install stays.
        for script, kept in [
            ("python scripts/check.py --hint pip-install", "check.py"),
            ("echo run npm ci first", "echo"),
            ("ruff check scripts/pip_install_helper.py", "ruff"),
            # `i` is an install alias for npm and pnpm only, and only as a whole word.
            ("pip i foo", "pip i foo"),
            ("npm i18n-check", "npm i18n-check"),
            ("npm i-test", "npm i-test"),
            # The same whole-word rule for the spelled-out verbs: these run scripts.
            ("npm install-test", "npm install-test"),
            ("npm ci-info", "npm ci-info"),
            ("yarn add-deps-report", "yarn add-deps-report"),
        ]:
            self.assertIn(kept, bot.failing_command(runner_block(script, "failed")), script)

    def test_spelled_out_install_verbs_are_still_dropped_as_whole_words(self):
        for script in (
            "npm install",
            "npm ci",
            "pip install -r requirements.txt",
            "yarn add left-pad",
        ):
            with self.subTest(script=script):
                self.assertNotIn(
                    script.split()[0],
                    bot.failing_command(runner_block(script + " && pytest", "failed")),
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
