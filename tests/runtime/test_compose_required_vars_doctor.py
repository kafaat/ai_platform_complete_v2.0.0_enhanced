"""`env_doctor.py --mode compose-vars`: every missing `${VAR:?}` in one report.

COMPOSE-REQUIRED-VARS-ONE-AT-A-TIME-01: `docker compose ... build` interpolates every service of
every file first and stops at the first required variable with no value, so a fresh GPU build
failed once per secret (~57 tries). The doctor walks the same files with Compose's rules and
lists them all, without ever printing a value.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts/runtime/env_doctor.py"
SECRET = "s3cr3t-value-never-printed-7f1d"


def load_doctor():
    spec = importlib.util.spec_from_file_location("sahool_env_doctor_compose_vars", DOCTOR)
    assert spec and spec.loader, "env_doctor.py must be importable"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COMPOSE = """\
x-common: &common
  restart: unless-stopped
services:
  api:
    <<: *common
    image: ${API_IMAGE:?API_IMAGE required}
    environment:
      # ${IN_COMMENT:?a comment is not interpolated}
      TOKEN: ${API_TOKEN:?API_TOKEN required}  # trailing ${ALSO_COMMENT:?no}
      MAYBE_EMPTY: ${OPTIONAL_BUT_DECLARED?declare it, empty is fine}
      ESCAPED: "$${NOT_A_VAR:?escaped with $$}"
      DATABASE_URL: ${DATABASE_URL:-postgresql://app:${DB_PASSWORD:?DB_PASSWORD
        required}@db:5432/app}
      ALT: ${FEATURE_ON:+${FEATURE_KEY:?FEATURE_KEY required when FEATURE_ON}}
  gpu-only:
    profiles: ["gpu"]
    image: busybox
    environment:
      KEY: ${GPU_ONLY_KEY:?inactive profiles are interpolated too}
"""


def write(tmp_path: Path, compose: str = COMPOSE, env: str = "") -> tuple[Path, Path]:
    compose_path = tmp_path / "compose.yml"
    compose_path.write_text(compose, encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(env, encoding="utf-8")
    return compose_path, env_path


def run_check(tmp_path: Path, environ: dict[str, str], env: str = "", compose: str = COMPOSE):
    doctor = load_doctor()
    compose_path, env_path = write(tmp_path, compose, env)
    checks: list = []
    doctor.check_compose_required_vars(
        tmp_path, checks, [str(compose_path)], str(env_path), environ=environ
    )
    assert len(checks) == 1, f"one check expected, got {checks!r}"
    return checks[0]


def test_every_missing_required_variable_is_reported_in_one_pass(tmp_path):
    check = run_check(tmp_path, environ={})
    assert check.status == "fail", f"missing secrets must fail the check: {check!r}"
    assert check.detail["missing_names"] == [
        "API_IMAGE",
        "API_TOKEN",
        "DB_PASSWORD",
        "GPU_ONLY_KEY",
        "OPTIONAL_BUT_DECLARED",
    ], "all required names with no value, sorted — not just the first one Compose would hit"


def test_comments_escapes_and_untaken_branches_are_not_required(tmp_path):
    check = run_check(tmp_path, environ={})
    names = set(check.detail["missing_names"])
    for name in ("IN_COMMENT", "ALSO_COMMENT", "NOT_A_VAR", "FEATURE_KEY"):
        assert name not in names, f"{name} is a comment, an escape or an untaken `:+` branch"


def test_a_nested_default_is_required_only_while_the_outer_variable_is_empty(tmp_path):
    check = run_check(tmp_path, environ={"DATABASE_URL": "postgresql://set-by-operator"})
    assert "DB_PASSWORD" not in check.detail["missing_names"], (
        "Compose evaluates `${DATABASE_URL:-...${DB_PASSWORD:?}...}` lazily; with DATABASE_URL "
        "set, DB_PASSWORD is not required"
    )
    check = run_check(tmp_path, environ={"DATABASE_URL": ""})
    assert "DB_PASSWORD" in check.detail["missing_names"], "`:-` treats an empty value as unset"


def test_a_taken_alternative_branch_makes_its_inner_variable_required(tmp_path):
    check = run_check(tmp_path, environ={"FEATURE_ON": "1"})
    assert "FEATURE_KEY" in check.detail["missing_names"], "`:+` branch taken when FEATURE_ON set"


def test_colon_question_rejects_empty_but_bare_question_accepts_it(tmp_path):
    check = run_check(tmp_path, environ={"API_TOKEN": "", "OPTIONAL_BUT_DECLARED": ""})
    names = check.detail["missing_names"]
    assert "API_TOKEN" in names, "`${VAR:?}` fails on an empty value"
    assert "OPTIONAL_BUT_DECLARED" not in names, "`${VAR?}` accepts an empty value"
    rules = {item["name"]: item["rule"] for item in check.detail["missing"]}
    assert rules["API_TOKEN"] == "unset-or-empty", f"rule must be reported: {rules!r}"


def test_env_file_is_read_like_compose_and_the_shell_wins(tmp_path):
    env = (
        "# comment\n"
        f"export API_IMAGE={SECRET}\n"
        f'API_TOKEN="{SECRET}"\n'
        "DB_PASSWORD=\n"
        f"GPU_ONLY_KEY='{SECRET}' # inline comment\n"
        "OPTIONAL_BUT_DECLARED= # Compose reads this value as '# Compose ...', not empty\n"
    )
    check = run_check(tmp_path, environ={"GPU_ONLY_KEY": ""}, env=env)
    assert check.detail["missing_names"] == ["DB_PASSWORD", "GPU_ONLY_KEY"], (
        "export/quotes are values, an empty value is missing, and an empty shell value overrides "
        f"the env file: {check.detail['missing_names']!r}"
    )


def test_all_set_passes(tmp_path):
    environ = {
        n: "x"
        for n in ("API_IMAGE", "API_TOKEN", "DB_PASSWORD", "GPU_ONLY_KEY", "OPTIONAL_BUT_DECLARED")
    }
    check = run_check(tmp_path, environ=environ)
    assert check.status == "pass", f"nothing is missing: {check!r}"
    assert check.detail["missing_names"] == [], "no names when every variable has a value"


def test_locations_name_the_file_line_and_service(tmp_path):
    check = run_check(tmp_path, environ={})
    where = {item["name"]: item["locations"] for item in check.detail["missing"]}
    assert where["API_TOKEN"] == ["compose.yml:9 (api)"], where
    assert where["DB_PASSWORD"] == ["compose.yml:12 (api)"], where
    assert where["GPU_ONLY_KEY"] == ["compose.yml:19 (gpu-only)"], where


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_cli_lists_every_name_and_never_prints_a_value(tmp_path, fmt):
    compose_path, env_path = write(tmp_path, env=f"API_IMAGE={SECRET}\nAPI_TOKEN={SECRET}\n")
    result = subprocess.run(
        [
            sys.executable,
            str(DOCTOR),
            "--root",
            str(ROOT),
            "--mode",
            "compose-vars",
            "-f",
            str(compose_path),
            "--env-file",
            str(env_path),
            "--format",
            fmt,
        ],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 1, f"missing variables block: {result.stdout}{result.stderr}"
    assert SECRET not in result.stdout + result.stderr, "a value from the env file was printed"
    for name in ("DB_PASSWORD", "GPU_ONLY_KEY", "OPTIONAL_BUT_DECLARED"):
        assert name in result.stdout, f"{name} missing from the {fmt} report"
    for name in ("API_IMAGE", "API_TOKEN"):
        assert not re.search(rf"^\s+{name}\s", result.stdout, re.M), f"{name} has a value"
    if fmt == "json":
        payload = json.loads(result.stdout)
        assert payload["summary"]["readiness"] == "blocked", payload["summary"]


COMPOSE_SET = ("docker-compose.v9.yml", "docker-compose.v9.gpu.yml")
_REQUIRED = r"\$\{([A-Za-z_][A-Za-z0-9_]*):?\?"
_GUARDED = r"\$\{([A-Za-z_][A-Za-z0-9_]*):?\+" + _REQUIRED  # `${GUARD:+${NAME:?…}}`


def _compose_set_text() -> str:
    lines: list[str] = []
    for rel in COMPOSE_SET:
        text = (ROOT / rel).read_text(encoding="utf-8")
        lines += [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def repo_guarded_requirements() -> dict[str, set[str]]:
    """`${GUARD:+${NAME:?…}}`: NAME is required only once GUARD has a value. NAME -> guards."""
    text = _compose_set_text()
    every = re.findall(_REQUIRED, text)
    guards: dict[str, set[str]] = {}
    occurrences: dict[str, int] = {}
    for guard, name in re.findall(_GUARDED, text):
        guards.setdefault(name, set()).add(guard)
        occurrences[name] = occurrences.get(name, 0) + 1
    # A name that is also required outside a guard is required unconditionally.
    return {n: g for n, g in guards.items() if every.count(n) == occurrences[n]}


def repo_required_names() -> set[str]:
    """Every `${VAR:?}` name Compose demands whatever else is set."""
    return set(re.findall(_REQUIRED, _compose_set_text())) - set(repo_guarded_requirements())


def _missing_names(tmp_path, environ: dict[str, str]) -> set[str]:
    doctor = load_doctor()
    checks: list = []
    doctor.check_compose_required_vars(
        ROOT, checks, list(COMPOSE_SET), str(tmp_path / "absent.env"), environ=environ
    )
    return set(checks[0].detail["missing_names"])


def test_the_gpu_compose_set_reports_every_required_name_at_once(tmp_path):
    expected = repo_required_names()
    assert len(expected) > 40, "the oracle collapsed; a check measured on nothing always passes"
    assert _missing_names(tmp_path, {}) == expected, (
        "with an empty environment every unguarded `${VAR:?}` of both files must be reported "
        "at once, and a guarded one must not be"
    )


def test_a_guarded_requirement_is_reported_once_its_guard_has_a_value(tmp_path):
    """`${GUARD:+${NAME:?…}}` (F-R03, the opt-in model-lifecycle adapter) is still a requirement."""
    guarded = repo_guarded_requirements()
    assert {"MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN"} <= set(guarded), (
        "the oracle no longer sees the guarded registry settings; this test would measure nothing"
    )
    environ = {guard: "set" for guards in guarded.values() for guard in guards}
    assert not set(environ) & set(guarded), "a guard that is itself guarded needs its own case"
    assert _missing_names(tmp_path, environ) == (repo_required_names() | set(guarded)) - set(
        environ
    )


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _docker_compose_available(), reason="docker compose CLI not installed")
def test_the_report_agrees_with_docker_compose_itself(tmp_path):
    """Setting exactly the reported names satisfies Compose; dropping any one breaks it again."""
    names = sorted(repo_required_names())
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)}
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(empty_env),
        "-f",
        str(ROOT / "docker-compose.v9.yml"),
        "-f",
        str(ROOT / "docker-compose.v9.gpu.yml"),
        "--profile",
        "gpu",
        "config",
        "--quiet",
    ]
    full = {**base, **{n: "dummy-value" for n in names}}
    ok = subprocess.run(
        cmd, env=full, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert ok.returncode == 0, f"the reported set must satisfy Compose: {ok.stderr[-2000:]}"
    for dropped in (names[0], names[len(names) // 2], names[-1]):
        env = {k: v for k, v in full.items() if k != dropped}
        bad = subprocess.run(
            cmd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        assert bad.returncode != 0 and dropped in bad.stderr, (
            f"Compose must stop on {dropped}: {bad.stderr[-2000:]}"
        )
    # A guarded name is not demanded until its guard has a value, then it is.
    for name, guards in sorted(repo_guarded_requirements().items()):
        assert name not in full, f"{name} must stay unset for this to measure anything"
        armed = {**full, **{guard: "dummy-value" for guard in guards}}
        bad = subprocess.run(
            cmd, env=armed, capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        assert bad.returncode != 0 and name in bad.stderr, (
            f"Compose must stop on {name} once {sorted(guards)} is set: {bad.stderr[-2000:]}"
        )
