"""F-R03: the opt-in model-lifecycle Compose block must pass what the adapter needs to start.

`services/model-registry-adapter/service.py` runs `validate_runtime()` and then builds
`LifecycleRuntime()` before it polls anything. With `SAHOOL_ENV=production` (the block's default)
that start-up refuses unless the registry URL, the registry token and an explicit
`MODEL_REGISTRY_DRY_RUN=false` are in the container. The block passed none of the three, so the
profile could not start from the committed file whatever the operator put in `.env`.

The required settings are not listed here by hand. They are measured: every environment name the
adapter reads is removed in turn from a complete production environment, and a name is required
when the start-up then refuses. A setting added to the adapter later is caught the same way.

Compose interpolates every service, profile or not, so a bare `${VAR:?}` in this block would make
the default stack demand a model registry it does not run. The tests below pin both sides: the
requirement fires once the adapter has an identity, and it stays silent in the default stack.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_EXAMPLE = ROOT / ".env.example"
ADAPTER_DIR = ROOT / "services" / "model-registry-adapter"
ADAPTER_SOURCES = ("adapter.py", "runtime.py", "service.py", "worker.py")
SERVICE = "sahool-model-lifecycle-adapter"
REGISTRY_SETTINGS = {"MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN", "MODEL_REGISTRY_DRY_RUN"}
REQUIRED_SYNTAX = ("MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN")
SAMPLE_SECRET = "test-only-not-a-real-credential-0000"


# ── Compose interpolation (the documented rules, evaluated lazily like Compose) ─────────────


class ComposeRequiredVariable(Exception):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"required variable {name} is missing a value: {message}")
        self.name = name


_OPERATORS = (":?", "?", ":-", "-", ":+", "+")


def _closing_brace(text: str, start: int) -> int:
    depth = 1
    i = start
    while i < len(text):
        if text.startswith("$$", i):
            i += 2
        elif text.startswith("${", i):
            depth += 1
            i += 2
        else:
            if text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
    raise ValueError(f"unterminated interpolation in {text!r}")


def interpolate(text: str, env: dict[str, str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("$$", i):
            out.append("$")
            i += 2
        elif text.startswith("${", i):
            end = _closing_brace(text, i + 2)
            body = text[i + 2 : end]
            j = 0
            while j < len(body) and (body[j].isalnum() or body[j] == "_"):
                j += 1
            name, rest = body[:j], body[j:]
            op = next((o for o in _OPERATORS if rest.startswith(o)), "")
            if rest and not op:
                raise ValueError(f"unsupported interpolation {body!r}")
            arg = rest[len(op) :]
            value = env.get(name)
            usable = value is not None and (value != "" or ":" not in op)
            if op.endswith("?"):
                if not usable:
                    raise ComposeRequiredVariable(name, interpolate(arg, env))
                out.append(value)
            elif op.endswith("-"):
                out.append(value if usable else interpolate(arg, env))
            elif op.endswith("+"):
                out.append(interpolate(arg, env) if usable else "")
            else:
                out.append(value or "")
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


@pytest.mark.parametrize(
    ("template", "env", "expected"),
    [
        ("${A}", {}, ""),
        ("${A:-d}", {"A": ""}, "d"),
        ("${A-d}", {"A": ""}, ""),
        ("${A:+x}", {"A": "1"}, "x"),
        ("${A:+x}", {"A": ""}, ""),
        ("${A:+${B:?b needed}}", {}, ""),
        ("${A:+${B:?b needed}}", {"A": "1", "B": "v"}, "v"),
        ("${A:-http://${B:-h}:1}", {}, "http://h:1"),
        ("${B:-${A:+${B:?b needed}}}", {}, ""),
        ("${B:-${A:+${B:?b needed}}}", {"B": "v"}, "v"),
        ("$${A}", {"A": "v"}, "${A}"),
    ],
)
def test_the_interpolation_model_follows_compose(template, env, expected):
    assert interpolate(template, env) == expected


@pytest.mark.parametrize("template", ["${A:+${B:?b needed}}", "${B:-${A:+${B:?b needed}}}"])
@pytest.mark.parametrize("env", [{"A": "1"}, {"A": "1", "B": ""}])
def test_the_interpolation_model_refuses_a_required_variable_like_compose(template, env):
    with pytest.raises(ComposeRequiredVariable) as refused:
        interpolate(template, env)
    assert refused.value.name == "B"


# ── The committed block and the adapter start-up ───────────────────────────────────────────


def block() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"][SERVICE]


def block_environment() -> dict[str, str]:
    env = block()["environment"]
    assert isinstance(env, dict), "the block declares its environment as a mapping"
    return {str(k): "" if v is None else str(v) for k, v in env.items()}


def render(host: dict[str, str]) -> dict[str, str]:
    """The container environment Compose builds for this service from a host environment."""
    return {key: interpolate(raw, host) for key, raw in block_environment().items()}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def startup_refusal(container: dict[str, str]) -> str | None:
    """Run the two start-up statements of service.main() in ``container``; return the refusal."""
    with mock.patch.dict(os.environ, container, clear=True):
        adapter = _load("f_r03_adapter", ADAPTER_DIR / "adapter.py")
        runtime = _load("f_r03_runtime", ADAPTER_DIR / "runtime.py")
        try:
            adapter.validate_runtime()
            runtime.LifecycleRuntime()
        except (adapter.RegistryError, runtime.RuntimeContractError) as exc:
            return str(exc)
    return None


def names_the_adapter_reads() -> set[str]:
    names: set[str] = set()
    for source in ADAPTER_SOURCES:
        tree = ast.parse((ADAPTER_DIR / source).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            reads_env = (isinstance(func, ast.Name) and func.id == "_env") or (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            )
            first = node.args[0]
            if reads_env and isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return names


def sample(name: str) -> str | None:
    """A valid operator-supplied value, or None to leave the adapter's own default in place."""
    if name == "SAHOOL_ENV":
        return "production"
    if name == "MODEL_REGISTRY_DRY_RUN":
        return "false"
    if name == "MODEL_REGISTRY_BACKEND":
        return "http"
    if name.endswith("_URL"):
        return "https://backend.invalid"
    if name.endswith(("_TOKEN", "_KEY", "_SECRET", "_ID")):
        return SAMPLE_SECRET
    return None


def complete_container() -> dict[str, str]:
    return {n: v for n in names_the_adapter_reads() if (v := sample(n)) is not None}


def required_at_startup() -> set[str]:
    full = complete_container()
    assert startup_refusal(full) is None, "the sample values no longer satisfy the adapter"
    return {
        name
        for name in full
        if startup_refusal({k: v for k, v in full.items() if k != name}) is not None
    }


def operator_host() -> dict[str, str]:
    """An operator who filled in every variable the block reads from the host."""
    host: dict[str, str] = {}
    for raw in block_environment().values():
        for name in _referenced(raw):
            if (value := sample(name)) is not None:
                host[name] = value
    for name in required_at_startup():
        host.setdefault(name, sample(name))
    host.pop("SAHOOL_ENV", None)  # the block's own default (production) applies
    return host


def _referenced(raw: str) -> set[str]:
    found: set[str] = set()
    i = raw.find("${")
    while i >= 0:
        j = i + 2
        while j < len(raw) and (raw[j].isalnum() or raw[j] == "_"):
            j += 1
        found.add(raw[i + 2 : j])
        i = raw.find("${", j)
    return found


def test_service_main_starts_with_the_two_statements_this_test_runs():
    tree = ast.parse((ADAPTER_DIR / "service.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [
        n.func.id
        for n in ast.walk(main)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls.index("validate_runtime") < calls.index("LifecycleRuntime")
    assert calls.index("LifecycleRuntime") < calls.index("serve_health")


def test_the_measured_requirements_include_the_registry_settings():
    assert REGISTRY_SETTINGS <= required_at_startup()


def test_the_block_passes_every_setting_the_adapter_requires_to_start():
    missing = sorted(required_at_startup() - set(block_environment()))
    assert not missing, (
        f"{SERVICE} does not pass {missing}: the adapter refuses to start in production "
        "without them, whatever the operator sets in .env"
    )


def test_the_adapter_starts_in_the_container_compose_builds_for_a_complete_host():
    container = render(operator_host())
    assert container["SAHOOL_ENV"] == "production"
    assert startup_refusal(container) is None


def test_the_profile_stays_opt_in():
    assert block()["profiles"] == ["model-lifecycle"]


# ── Required-variable syntax, without breaking the default stack ───────────────────────────


@pytest.mark.parametrize("name", REQUIRED_SYNTAX)
def test_the_registry_setting_uses_required_variable_syntax(name):
    assert f"${{{name}:?" in block_environment()[name]


@pytest.mark.parametrize("name", REQUIRED_SYNTAX)
@pytest.mark.parametrize("supplied", [None, ""])
def test_compose_refuses_an_adapter_with_an_identity_and_no_registry_setting(name, supplied):
    host = operator_host()
    assert host["REGISTRY_ADAPTER_ID"]
    host.pop(name)
    if supplied is not None:
        host[name] = supplied
    with pytest.raises(ComposeRequiredVariable) as refused:
        render(host)
    assert refused.value.name == name


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@pytest.mark.parametrize("host", [{}, _env_example()], ids=["empty-host", "env-example"])
def test_the_default_stack_is_not_asked_for_a_model_registry(host):
    """Compose interpolates this block even when the profile is off: it must still render."""
    container = render(dict(host))
    assert container["MODEL_REGISTRY_URL"] == ""
    assert container["MODEL_REGISTRY_TOKEN"] == ""


def test_no_registry_value_is_committed():
    container = render({})
    assert container["MODEL_REGISTRY_URL"] == ""
    assert container["MODEL_REGISTRY_TOKEN"] == ""
    assert container["MODEL_REGISTRY_DRY_RUN"] == "true"


# ── Refusal paths: the block must not turn a start-up refusal into a silent start ──────────


@pytest.mark.parametrize("supplied", [None, "", "true", "1"])
def test_dry_run_is_never_switched_off_by_the_block(supplied):
    """Unset or empty keeps the adapter's default (true), which production refuses."""
    host = operator_host()
    host.pop("MODEL_REGISTRY_DRY_RUN")
    if supplied is not None:
        host["MODEL_REGISTRY_DRY_RUN"] = supplied
    container = render(host)
    assert container["MODEL_REGISTRY_DRY_RUN"] != ""
    assert startup_refusal(container) == "MODEL_REGISTRY_DRY_RUN must be false in production"


def test_the_profile_without_an_adapter_identity_renders_and_the_adapter_refuses():
    host = operator_host()
    for name in ("REGISTRY_ADAPTER_ID", "MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN"):
        host.pop(name)
    assert startup_refusal(render(host)) == "MODEL_REGISTRY_URL is required"


def test_a_missing_adapter_identity_is_reported_as_itself_not_as_a_missing_registry():
    """The registry values the operator set still reach the adapter when the identity is absent."""
    host = operator_host()
    host.pop("REGISTRY_ADAPTER_ID")
    container = render(host)
    assert container["MODEL_REGISTRY_URL"] == host["MODEL_REGISTRY_URL"]
    assert container["MODEL_REGISTRY_TOKEN"] == host["MODEL_REGISTRY_TOKEN"]
    assert startup_refusal(container) == "REGISTRY_ADAPTER_ID is required in production"


def test_an_uncertified_backend_reaches_the_adapter_and_is_refused():
    host = operator_host() | {"MODEL_REGISTRY_BACKEND": "local"}
    assert startup_refusal(render(host)) == "only MODEL_REGISTRY_BACKEND=http is certified"


def test_the_decision_service_token_is_still_required_in_production():
    host = operator_host()
    host.pop("DECISION_SERVICE_AUTH_TOKEN")
    assert startup_refusal(render(host)) == "DECISION_SERVICE_TOKEN is required in production"
