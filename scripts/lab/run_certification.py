"""Run the restricted-role certification steps of the CI Integration Tests job.

The steps are read from .github/workflows/ci.yml at run time, not copied: every step
of the ``integration-tests`` job after the shared ``pytest -v -m integration`` run is
executed as CI executes it (``bash -eo pipefail`` on the step's own ``run`` text, with
exactly the step's ``env``), so the lab cannot drift from CI. Only two things differ:

* ``pytest`` on PATH is a shim that runs the lab venv's pytest and adds a per-call
  ``--junitxml`` and log, so each pytest call in a step is its own suite in the evidence;
* the environment run.sh exported for the shared suite (TEST_*, *_CERTIFICATION_REQUIRED,
  PG*, JWT_SECRET) is removed first, because in CI a step sees only its own env.

A step is refused, not approximated, when the lab cannot run it as written: it uses an
action (``uses``), a GitHub expression (``${{``), a ``shell``/``working-directory``/``if``
override, or has no ``run``. After the steps, the flags of every restricted role the
steps connect as are read from pg_roles; rolsuper or rolbypassrls true is a failure.

Usage: python scripts/lab/run_certification.py <evidence dir> <venv python>
Writes <evidence dir>/certification_steps.json, consumed by write_evidence.py.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import yaml

CI_WORKFLOW = Path(".github/workflows/ci.yml")
JOB = "integration-tests"
SHARED_RUN = "pytest -v -m integration --tb=short"
UNSUPPORTED_KEYS = ("uses", "shell", "working-directory", "if", "with")
_STRIP_PREFIXES = ("TEST_", "PG", "IRR_F01_")

SHIM = """#!/usr/bin/env bash
# Lab pytest shim: the CI command line unchanged, plus a JUnit report and log per call.
set -uo pipefail
n=$(( $(cat "$LAB_CERT_COUNTER") + 1 ))
echo "$n" >"$LAB_CERT_COUNTER"
stem=call
for a in "$@"; do case "$a" in *.py) stem="$(basename "$a" .py)" ;; esac; done
name="${LAB_CERT_PREFIX}_${n}_${stem}"
printf '%s\\t%s\\n' "$name" "pytest $*" >>"$LAB_CERT_CALLS"
"$LAB_VENV_PYTHON" -m pytest -p no:cacheprovider "$@" \\
  --junitxml="$LAB_CERT_OUT/$name.junit.xml" 2>&1 | tee "$LAB_CERT_OUT/$name.log"
exit "${PIPESTATUS[0]}"
"""


def certification_steps(workflow: Path = CI_WORKFLOW) -> list[dict]:
    """Return the CI steps after the shared integration run, validated as runnable."""
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = doc["jobs"][JOB]["steps"]
    shared = [i for i, s in enumerate(steps) if (s.get("run") or "").strip() == SHARED_RUN]
    if len(shared) != 1:
        raise SystemExit(f"LAB_CI_STEPS_UNREADABLE: {len(shared)} shared '{SHARED_RUN}' steps")
    selected = steps[shared[0] + 1 :]
    if not selected:
        raise SystemExit("LAB_CI_STEPS_UNREADABLE: no steps after the shared integration run")
    for step in selected:
        name = step.get("name", "<unnamed>")
        bad = [k for k in UNSUPPORTED_KEYS if k in step]
        if bad or not step.get("run") or not step.get("name"):
            raise SystemExit(f"LAB_CI_STEP_UNSUPPORTED: {name}: keys {bad or 'missing run/name'}")
        if "${{" in json.dumps(step):
            raise SystemExit(f"LAB_CI_STEP_UNSUPPORTED: {name}: GitHub expression")
    return selected


def pytest_calls(run: str) -> list[str]:
    """The pytest command lines of a step's run text (continuations joined)."""
    joined = re.sub(r"\\\n\s*", " ", run)
    return [m.group(0).strip() for m in re.finditer(r"(?<![\w-])pytest\b[^\n]*", joined)]


def restricted_roles(steps: list[dict]) -> list[str]:
    roles = set()
    for step in steps:
        env = {str(k): str(v) for k, v in (step.get("env") or {}).items()}
        if env.get("APP_ROLE"):
            roles.add(env["APP_ROLE"])
        url = env.get("TEST_DATABASE_URL", "")
        if url.startswith("postgresql://") and urlsplit(url).username:
            roles.add(urlsplit(url).username)
    return sorted(roles)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48].rstrip("_")


def _base_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(_STRIP_PREFIXES)
        and not k.endswith("_CERTIFICATION_REQUIRED")
        and k != "JWT_SECRET"
    }


def _role_flags(role: str) -> dict:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
        return {"role": role, "exists": False, "raw": "unsafe role name", "ok": False}
    env = {**_base_env(), "PGPASSWORD": os.environ["LAB_PG_PASSWORD"]}
    sql = (
        "SELECT rolsuper::text || ':' || rolbypassrls::text || ':' || rolinherit::text"
        f" || ':' || rolcanlogin::text FROM pg_roles WHERE rolname = '{role}'"
    )
    cmd = ["psql", "-X", "-h", "127.0.0.1", "-p", os.environ["LAB_PG_PORT"]]
    cmd += ["-U", os.environ["LAB_PG_USER"], "-d", os.environ["LAB_PG_DB"], "-Atc", sql]
    raw = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    ).stdout.strip()
    parts = raw.split(":") if raw else []
    if len(parts) != 4:
        return {"role": role, "exists": False, "raw": raw, "ok": False}
    sup, bypass, inherit, login = (p == "true" for p in parts)
    return {
        "role": role,
        "exists": True,
        "rolsuper": sup,
        "rolbypassrls": bypass,
        "rolinherit": inherit,
        "rolcanlogin": login,
        "ok": not sup and not bypass,
    }


def main(out_dir: str, venv_python: str) -> int:
    out = Path(out_dir).resolve()
    steps = certification_steps()
    bin_dir = out / "cert_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "pytest"
    shim.write_text(SHIM, encoding="utf-8")
    shim.chmod(0o755)
    counter = out / ".cert_counter"
    results = []
    for index, step in enumerate(steps, start=1):
        prefix = f"cert{index:02d}"
        calls_file = out / f"{prefix}.calls.tsv"
        calls_file.write_text("", encoding="utf-8")
        counter.write_text("0", encoding="utf-8")
        step_env = {str(k): str(v) for k, v in (step.get("env") or {}).items()}
        env = {
            **_base_env(),
            **step_env,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "LAB_VENV_PYTHON": venv_python,
            "LAB_CERT_OUT": str(out),
            "LAB_CERT_PREFIX": prefix,
            "LAB_CERT_COUNTER": str(counter),
            "LAB_CERT_CALLS": str(calls_file),
        }
        log = out / f"{prefix}_{_slug(step['name'])}.step.log"
        start = time.monotonic()
        with log.open("w", encoding="utf-8") as fh:
            rc = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                env=env,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        seconds = round(time.monotonic() - start, 1)
        calls = [
            dict(zip(("suite", "command"), line.split("\t", 1), strict=True))
            for line in calls_file.read_text(encoding="utf-8").splitlines()
            if line
        ]
        calls_file.unlink()
        results.append(
            {
                "index": index,
                "ci_step": step["name"],
                "env_keys": sorted(step_env),
                "certification_switches": {
                    k: v for k, v in step_env.items() if k.endswith("_CERTIFICATION_REQUIRED")
                },
                "ci_pytest_calls": pytest_calls(step["run"]),
                "pytest_suites": calls,
                "rc": rc,
                "seconds": seconds,
                "log": log.name,
            }
        )
        print(f"{prefix} rc={rc} seconds={seconds} {step['name']}", flush=True)
    counter.unlink(missing_ok=True)
    roles = [_role_flags(role) for role in restricted_roles(steps)]
    doc = {
        "source": f"{CI_WORKFLOW} jobs.{JOB}: steps after '{SHARED_RUN}', read at run time",
        "steps": results,
        "restricted_roles": roles,
        "ok": bool(results)
        and all(r["rc"] == 0 for r in results)
        and bool(roles)
        and all(r["ok"] for r in roles),
    }
    (out / "certification_steps.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for role in roles:
        print(f"role {role['role']}: {role}", flush=True)
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
