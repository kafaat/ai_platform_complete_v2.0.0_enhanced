#!/usr/bin/env python3
"""Guard the pinned GitHub Actions static-analysis lane and its blocking thresholds."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/github-actions-security.yml"
INSTALLER = ROOT / "scripts/ci/install_pinned_actions_security_tools.sh"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"

TOOLS = {
    "actionlint": ("v1.7.12", "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"),
    "zizmor": ("v1.29.0", "dd96df044a6e8538d5f423790f453bdd03d49e5b2bcc38214acc41a2f1297839"),
    "pinact": ("v4.1.1", "d1cffebe5704b74e2e5f8a864efb9f7e54768972dc686188c008033fb1797841"),
    "poutine": ("v1.1.6", "abde716599a65608b023a69ed9316e5f083a7bca48612151c2720835883757ea"),
}


def evaluate(workflow_text: str, installer_text: str, ci_text: str) -> list[str]:
    errors: list[str] = []
    try:
        workflow = yaml.safe_load(workflow_text)
    except yaml.YAMLError as exc:
        return [f"workflow YAML invalid: {exc}"]
    if not isinstance(workflow, dict):
        return ["workflow must be a mapping"]
    if workflow.get("permissions") != {"contents": "read"}:
        errors.append("security workflow permissions must be contents:read only")
    jobs = workflow.get("jobs") or {}
    job = jobs.get("analyze") if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        return errors + ["security analyze job missing"]
    steps = job.get("steps") or []
    checkout = [
        s
        for s in steps
        if isinstance(s, dict) and str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    if (
        len(checkout) != 1
        or (checkout[0].get("with") or {}).get("persist-credentials") is not False
    ):
        errors.append("security checkout must disable persisted credentials")
    run_text = "\n".join(str(s.get("run")) for s in steps if isinstance(s, dict) and s.get("run"))
    required_commands = (
        "scripts/ci/install_pinned_actions_security_tools.sh",
        "actionlint -config-file .github/actionlint.yaml",
        "pinact run --fix=false --no-api",
        "zizmor --offline --strict-collection --min-severity high --min-confidence high .github",
        "poutine --allowed-rules injection --fail-on-violation --disable-version-check analyze_local .",
        "python scripts/ci/runtime_image_supply_chain_guard.py",
        "python scripts/ci/github_actions_security_guard.py",
    )
    for command in required_commands:
        if command not in run_text:
            errors.append(f"blocking security command missing: {command}")
    if "continue-on-error: true" in workflow_text:
        errors.append("security analysis may not continue on error")
    for name, (version, digest) in TOOLS.items():
        if version not in installer_text or digest not in installer_text:
            errors.append(f"{name} release or SHA-256 pin missing")
    if installer_text.count("sha256sum --check --strict -") != 1:
        errors.append("installer checksum verification helper drifted")
    for command in required_commands:
        if command not in ci_text:
            errors.append(f"required Security Scan enforcement missing: {command}")
    return errors


def main() -> int:
    errors = evaluate(
        WORKFLOW.read_text(encoding="utf-8"),
        INSTALLER.read_text(encoding="utf-8"),
        CI_WORKFLOW.read_text(encoding="utf-8"),
    )
    if errors:
        print("github_actions_security_guard_failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("github_actions_security_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
