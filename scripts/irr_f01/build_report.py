#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET


def cmd(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"unavailable: {exc}"


def junit_summary(path: Path) -> dict:
    if not path.exists():
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    out = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for k in out:
            out[k] += int(suite.attrib.get(k, 0))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--status", choices=["passed", "failed", "not-certified"], required=True)
    ap.add_argument("--stage", default="none")
    ap.add_argument("--exit-code", type=int, default=0)
    ns = ap.parse_args()
    d = Path(ns.report_dir)
    d.mkdir(parents=True, exist_ok=True)
    junit = junit_summary(d / "pytest-junit.xml")
    sqlstate = {}
    p = d / "failed-sql-state.json"
    if p.exists():
        try:
            sqlstate = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            sqlstate = {"parse_error": True}
    evidence = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": ns.status,
        "failure_stage": ns.stage,
        "exit_code": ns.exit_code,
        "git_sha": cmd("git", "rev-parse", "HEAD"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "postgres": os.getenv("IRR_F01_POSTGRES_VERSION", "unknown"),
        "junit": junit,
        "sql_failure": sqlstate,
        "certification": {
            "fresh_install": "PASS" if ns.status == "passed" else "FAIL/NOT_RUN",
            "upgrade_v194_to_v195": "NOT_CERTIFIED",
            "live_event_wiring": "NOT_CERTIFIED",
        },
    }
    (d / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    title = "IRR-F01 LOCAL GATE — " + ns.status.upper()
    lines = [
        f"# {title}",
        "",
        f"- Stage: `{ns.stage}`",
        f"- Exit code: `{ns.exit_code}`",
        f"- Git SHA: `{evidence['git_sha']}`",
        f"- Python: `{evidence['python']}`",
        f"- PostgreSQL: `{evidence['postgres']}`",
        "",
        "## Test summary",
        "",
        f"- Tests: {junit['tests']}",
        f"- Failures: {junit['failures']}",
        f"- Errors: {junit['errors']}",
        f"- Skipped: {junit['skipped']}",
        "",
        "## Certification boundary",
        "",
        "- Fresh installation through v195: " + evidence["certification"]["fresh_install"],
        "- Upgrade v194 → v195: NOT CERTIFIED",
        "- Live emit_event/worker/actuator wiring: NOT CERTIFIED",
        "",
    ]
    if sqlstate:
        lines += [
            "## Captured SQL failure",
            "",
            "```json",
            json.dumps(sqlstate, indent=2),
            "```",
            "",
        ]
    lines += [
        "## Artifacts",
        "",
        "- `pytest-output.log`",
        "- `pytest-junit.xml`",
        "- `postgres.log`",
        "- `migration-output.log`",
        "- `schema-snapshot.sql`",
        "- `failed-sql-state.json`",
        "- `evidence.json`",
        "",
    ]
    (
        d / ("IRR_F01_SUCCESS_REPORT.md" if ns.status == "passed" else "IRR_F01_FAILURE_REPORT.md")
    ).write_text("\n".join(lines))


if __name__ == "__main__":
    main()
