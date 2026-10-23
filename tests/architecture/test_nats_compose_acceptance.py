"""Exercise actual wire probes independently of Docker availability."""

import importlib.util
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[2] / "scripts" / "ci"
spec = importlib.util.spec_from_file_location("acceptance", HERE / "run_nats_compose_acceptance.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class AcceptanceTests(unittest.TestCase):
    def test_optimized_python_fails_closed(self):
        process = subprocess.run(
            [sys.executable, "-O", str(HERE / "run_nats_compose_acceptance.py"), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("disables acceptance assertions", process.stderr)

    def test_termination_raises_catchable_exception(self):
        with self.assertRaises(InterruptedError):
            acceptance.interrupted(signal.SIGTERM, None)

    def test_missing_tools_blocked_without_secret_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "acceptance",
                        "--repo",
                        directory,
                        "--expected-sha",
                        "a" * 40,
                        "--report",
                        str(report),
                    ],
                ),
                patch.object(acceptance.shutil, "which", return_value=None),
            ):
                self.assertEqual(acceptance.main(), 2)
            data = json.loads((report / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "BLOCKED")
            self.assertEqual(list(report.iterdir()), [report / "result.json"])

    def test_existing_report_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                sys,
                "argv",
                [
                    "acceptance",
                    "--repo",
                    directory,
                    "--expected-sha",
                    "a" * 40,
                    "--report",
                    directory,
                ],
            ):
                with self.assertRaises(FileExistsError):
                    acceptance.main()


class LiveNativeProtocolTests(unittest.TestCase):
    def test_sigterm_during_startup_runs_project_cleanup(self):
        repo = Path(__file__).resolve().parents[2]
        sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, encoding="utf-8"
        ).strip()
        original_command = acceptance.command
        cleanup = []

        def fake_command(argv, **kwargs):
            if argv[0] != "docker":
                return original_command(argv, **kwargs)
            if argv[1] == "context":
                return "unix:///var/run/docker.sock"
            if argv[1] == "version" or argv[1:4] == ["compose", "version", "--short"]:
                return "fixture"
            if "up" in argv:
                signal.raise_signal(signal.SIGTERM)
            if "down" in argv:
                cleanup.append(argv)
            return ""

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report"
            before = signal.getsignal(signal.SIGTERM)
            with (
                patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": ""}),
                patch.object(acceptance.shutil, "which", return_value="/fixture/tool"),
                patch.object(acceptance, "command", side_effect=fake_command),
                patch.object(
                    sys,
                    "argv",
                    [
                        "acceptance",
                        "--repo",
                        str(repo),
                        "--expected-sha",
                        sha,
                        "--report",
                        str(report),
                    ],
                ),
            ):
                self.assertEqual(acceptance.main(), 1)
            data = json.loads((report / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["reason"], "InterruptedError")
            self.assertEqual(data["cleanup"], "PASS")
            assert len(cleanup) == 1
            self.assertIn(data["project"], cleanup[0])
            self.assertEqual(signal.getsignal(signal.SIGTERM), before)
