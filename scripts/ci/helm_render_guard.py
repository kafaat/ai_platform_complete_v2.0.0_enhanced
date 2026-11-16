#!/usr/bin/env python3
"""Helm render guard: the pinned helm rendered the chart and no render test skipped.

Why it exists (HELM-RENDER-UNPINNED-RUNNER-BINARY-01): the chart's render tests ran on the helm
that the GitHub runner image ships, at a version nobody pinned or checked, and a runner without
helm skipped every one of them green. The helm-readiness job now installs a checksum-verified
helm, then runs lint, template and the ``helm_render`` tests with HELM_RENDER_REQUIRED=1. This
guard closes the step:

* the ``helm`` on PATH is the pinned binary at the expected version, not the runner's own;
* the junit report of the ``helm_render`` run has at least ``--min-tests`` tests, none skipped,
  failed or errored.

Exit 0 prints HELM_RENDER_OK; exit 1 prints each problem.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MIN_RENDER_TESTS = 14


def version_problems(expected: str, reported: str) -> list[str]:
    """``helm version --short`` prints e.g. ``v3.16.4+g7877b45``; the tag must match exactly."""
    tag = reported.strip().split("+", 1)[0]
    if tag != expected:
        return [f"helm on PATH reports {reported.strip()!r}, expected {expected}"]
    return []


def path_problems(expected_binary: str | None, resolved: str | None) -> list[str]:
    if resolved is None:
        return ["no helm on PATH"]
    if expected_binary and Path(resolved).resolve() != Path(expected_binary).resolve():
        return [f"helm on PATH is {resolved}, not the pinned {expected_binary}"]
    return []


def junit_problems(report: Path, min_tests: int = MIN_RENDER_TESTS) -> list[str]:
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"junit report unreadable: {exc}"]
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not suites:
        return ["junit report has no testsuite"]
    totals = {"tests": 0, "skipped": 0, "failures": 0, "errors": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key) or 0)
    problems = []
    if totals["tests"] < min_tests:
        problems.append(f"{totals['tests']} helm_render tests ran, at least {min_tests} expected")
    for key in ("skipped", "failures", "errors"):
        if totals[key]:
            problems.append(f"{totals[key]} helm_render tests {key}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-binary", default=None)
    parser.add_argument("--min-tests", type=int, default=MIN_RENDER_TESTS)
    args = parser.parse_args(argv)

    resolved = shutil.which("helm")
    problems = path_problems(args.expected_binary, resolved)
    if resolved is not None:
        reported = subprocess.run(
            [resolved, "version", "--short"], capture_output=True, text=True, check=False
        ).stdout
        problems += version_problems(args.expected_version, reported)
    problems += junit_problems(args.junit, args.min_tests)

    if problems:
        for problem in problems:
            print(f"HELM_RENDER_INCOMPLETE: {problem}")
        return 1
    print(f"HELM_RENDER_OK: helm {args.expected_version}, junit {args.junit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
