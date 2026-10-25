"""Write lab_evidence.json for one scripts/lab/run.sh run.

The evidence binds what was measured: commit and tree (and whether the worktree was
dirty), the image digests and versions the containers actually ran, the dependency
versions of the test venv, and per-suite JUnit counts, durations and skipped tests.
The restricted-role certification steps (run_certification.py) add their CI step
names, switches, exit codes and the measured flags of the restricted role.
It is DEV evidence with independence none; it is not a CI or production result.

Usage: python scripts/lab/write_evidence.py <evidence dir>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

KEY_PACKAGES = (
    "asyncpg",
    "redis",
    "pytest",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "fastapi",
)


def _run(*cmd: str) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _lab_env() -> dict[str, str]:
    env = {}
    for line in Path("scripts/lab/lab.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"')
    return env


def _container(name: str, version_cmd: list[str]) -> dict:
    image = _run("docker", "inspect", name, "--format", "{{.Image}}")
    return {
        "container": name,
        "image_id": image,
        "repo_digests": json.loads(
            _run("docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}") or "[]"
        ),
        "version": _run("docker", "exec", name, *version_cmd),
    }


def _suite(junit: Path, log: Path) -> dict:
    if not junit.is_file():
        return {"junit": None, "error": "no JUnit report written", "log": log.name}
    root = ET.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    skipped = [
        {
            "test": f"{case.get('classname')}::{case.get('name')}",
            "reason": (case.find("skipped").get("message") or "")[:300],
        }
        for case in suite.iter("testcase")
        if case.find("skipped") is not None
    ]
    failed = [
        f"{case.get('classname')}::{case.get('name')}"
        for case in suite.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]
    tests = int(suite.get("tests", 0))
    return {
        "junit": junit.name,
        "log": log.name,
        "tests": tests,
        "passed": tests - len(failed) - len(skipped),
        "failed": failed,
        "skipped": skipped,
        "seconds": float(suite.get("time", 0.0)),
    }


def main(out_dir: str) -> int:
    out = Path(out_dir)
    env = _lab_env()
    freeze = (out / "pip_freeze.txt").read_text(encoding="utf-8").splitlines()
    versions = {}
    for line in freeze:
        name, sep, version = line.partition("==")
        if sep and name.lower() in KEY_PACKAGES:
            versions[name.lower()] = version
    suites = {
        junit.name.removesuffix(".junit.xml"): _suite(
            junit, out / junit.name.replace(".junit.xml", ".log")
        )
        for junit in sorted(out.glob("*.junit.xml"))
    }
    cert_file = out / "certification_steps.json"
    cert = json.loads(cert_file.read_text(encoding="utf-8")) if cert_file.is_file() else None
    doc = {
        "$comment": (
            "DEV evidence from scripts/lab/run.sh; independence none. It measures this "
            "container only; it is not a CI, staging or production result."
        ),
        "schema_version": "1.0.0",
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "binding": {
            "commit": _run("git", "rev-parse", "HEAD"),
            "tree": _run("git", "rev-parse", "HEAD^{tree}"),
            "worktree_dirty": bool(_run("git", "status", "--porcelain")),
        },
        "pinned": {
            "postgres": f"{env['LAB_PG_IMAGE_PATH']}@{env['LAB_PG_IMAGE_DIGEST']}",
            "redis": f"{env['LAB_REDIS_IMAGE_PATH']}@{env['LAB_REDIS_IMAGE_DIGEST']}",
            "ci_difference": (
                "CI builds postgres@sha256:d4a8e1f8... plus apt postgresql-15-postgis-3; "
                "the lab runs postgis/postgis:15-3.6 by digest (see scripts/lab/lab.env)."
            ),
        },
        "containers": {
            "postgres": _container(
                env["LAB_PG_CONTAINER"],
                [
                    "psql",
                    "-U",
                    env["LAB_PG_USER"],
                    "-d",
                    env["LAB_PG_DB"],
                    "-Atc",
                    "select version() || ' | postgis ' || postgis_lib_version()",
                ],
            ),
            "redis": _container(env["LAB_REDIS_CONTAINER"], ["redis-server", "--version"]),
        },
        "python": {
            "version": sys.version.split()[0],
            "packages": versions,
            "pip_freeze_sha256": hashlib.sha256("\n".join(freeze).encode()).hexdigest(),
        },
        "suites": suites,
        "ci_certification_steps": cert,
        "verdict": "PASS"
        if suites
        and all(s.get("junit") and not s["failed"] for s in suites.values())
        and cert is not None
        and cert["ok"]
        else "FAIL",
    }
    (out / "lab_evidence.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "verdict": doc["verdict"],
                "suites": {
                    k: {
                        key: (len(v[key]) if isinstance(v.get(key), list) else v.get(key))
                        for key in ("tests", "passed", "failed", "skipped", "seconds")
                    }
                    for k, v in suites.items()
                },
                "certification_steps_ok": bool(cert and cert["ok"]),
            },
            ensure_ascii=False,
        )
    )
    return 0 if doc["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
