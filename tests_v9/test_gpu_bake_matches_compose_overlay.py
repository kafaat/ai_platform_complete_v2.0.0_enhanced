"""docker-bake.gpu.hcl must build exactly what the GPU Compose overlay builds.

GPU-BUILD-NEEDS-RUNTIME-SECRETS-01: `docker compose -f docker-compose.v9.yml -f
docker-compose.v9.gpu.yml --profile gpu build` interpolates every `${VAR:?}` of every service
before building, so a developer needed ~57 runtime secrets to build two images. The bake file is
the build-only path. It is a second copy of the build definitions, so this test pins it to the
overlay: same targets, context, dockerfile, args and `${VAR:-default}` defaults. A change to one
without the other fails here.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
BAKE = ROOT / "docker-bake.gpu.hcl"
BASE = ROOT / "docker-compose.v9.yml"
OVERLAY = ROOT / "docker-compose.v9.gpu.yml"

_COMPOSE_DEFAULT = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*):-([^${}]*)\}$")
_BAKE_DEFAULT = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*)\s*!=\s*""\s*\?\s*\1\s*:\s*"([^"$]*)"$'
)  # VAR != "" ? VAR : "default"   (the bake form of Compose's ${VAR:-default})
_BAKE_LITERAL = re.compile(r'^"([^"$]*)"$')


def _block_body(text: str, open_brace: int) -> tuple[str, int]:
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : i], i + 1
    raise AssertionError("unbalanced braces in docker-bake.gpu.hcl")


def _arg_value(expr: str) -> tuple[str, str] | str:
    """`("VAR", "default")` for the `${VAR:-default}` form, the plain string for a literal."""
    expr = expr.strip()
    if m := _BAKE_DEFAULT.match(expr):
        return (m.group(1), m.group(2))
    if m := _BAKE_LITERAL.match(expr):
        return m.group(1)
    raise AssertionError(
        f'unsupported bake arg expression {expr!r}: use a literal or VAR != "" ? VAR : "default"'
    )


def parse_bake(text: str) -> dict[str, dict]:
    """Parse the small HCL subset docker-bake.gpu.hcl uses; anything else fails loudly."""
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    targets: dict[str, dict] = {}
    for m in re.finditer(r'^target\s+"([^"]+)"\s*\{', text, re.M):
        body, _ = _block_body(text, m.end() - 1)
        target: dict = {"args": {}}
        args_m = re.search(r"^\s*args\s*=\s*\{", body, re.M)
        if args_m:
            args_body, args_end = _block_body(body, args_m.end() - 1)
            for line in args_body.splitlines():
                if not line.strip():
                    continue
                key, sep, expr = line.partition("=")
                assert sep, f"bad args line in target {m.group(1)}: {line!r}"
                target["args"][key.strip()] = _arg_value(expr)
            body = body[: args_m.start()] + body[args_end:]
        for key in ("context", "dockerfile"):
            km = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"\s*$', body, re.M)
            target[key] = km.group(1) if km else None
        targets[m.group(1)] = target
    return targets


def parse_bake_default_group(text: str) -> list[str]:
    m = re.search(r'group\s+"default"\s*\{\s*targets\s*=\s*\[([^\]]*)\]', text)
    assert m, 'docker-bake.gpu.hcl must define group "default"'
    return re.findall(r'"([^"]+)"', m.group(1))


def compose_gpu_builds(base: dict, overlay: dict) -> dict[str, dict]:
    """The build definition Compose merges for every service the GPU overlay builds."""
    out: dict[str, dict] = {}
    for name, svc in (overlay.get("services") or {}).items():
        if "build" not in svc:
            continue
        merged = dict((base["services"].get(name) or {}).get("build") or {})
        over = svc["build"]
        merged_args = {**(merged.get("args") or {}), **(over.get("args") or {})}
        merged.update({k: v for k, v in over.items() if k != "args"})
        args = {}
        for key, raw in merged_args.items():
            m = _COMPOSE_DEFAULT.match(str(raw))
            assert m or "$" not in str(raw), f"{name}.{key}: only ${{VAR:-default}} is mirrored"
            args[key] = (m.group(1), m.group(2)) if m else str(raw)
        out[name] = {
            "args": args,
            "context": merged.get("context"),
            "dockerfile": merged.get("dockerfile"),
        }
    return out


def drift(bake_text: str, base: dict, overlay: dict) -> list[str]:
    bake = parse_bake(bake_text)
    compose = compose_gpu_builds(base, overlay)
    problems = []
    if set(bake) != set(compose):
        problems.append(f"targets {sorted(bake)} != overlay builds {sorted(compose)}")
    for name in sorted(set(bake) & set(compose)):
        for key in ("context", "dockerfile", "args"):
            if bake[name][key] != compose[name][key]:
                problems.append(f"{name}.{key}: bake {bake[name][key]!r} != {compose[name][key]!r}")
    if sorted(parse_bake_default_group(bake_text)) != sorted(compose):
        problems.append("group default must build every GPU overlay image")
    return problems


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_bake_targets_match_the_gpu_overlay_build_definitions():
    problems = drift(BAKE.read_text(encoding="utf-8"), load_yaml(BASE), load_yaml(OVERLAY))
    assert not problems, (
        "docker-bake.gpu.hcl drifted from docker-compose.v9.gpu.yml:\n" + "\n".join(problems)
    )


def test_the_overlay_still_builds_the_two_gpu_images():
    builds = compose_gpu_builds(load_yaml(BASE), load_yaml(OVERLAY))
    assert sorted(builds) == ["sahool-edge", "sahool-sam2-inference"], (
        f"the drift check must compare real targets, got {sorted(builds)}"
    )
    assert builds["sahool-edge"]["args"]["EDGE_REQUIREMENTS"] == "requirements-gpu.txt", builds
    assert builds["sahool-sam2-inference"]["args"]["PYTORCH_CUDA_IMAGE"][0] == (
        "PYTORCH_CUDA_IMAGE"
    ), builds


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('EDGE_REQUIREMENTS = "requirements-gpu.txt"', 'EDGE_REQUIREMENTS = "requirements.txt"'),
        (
            'dockerfile = "services/sam2-inference/Dockerfile"',
            'dockerfile = "services/sam2-inference/Dockerfile.cpu"',
        ),
        ("cuda12.8-cudnn9-runtime", "cuda12.4-cudnn9-runtime"),
        ('"https://mirrors.aliyun.com/pypi/simple/"', '"https://pypi.org/simple"'),
        ('targets = ["sahool-edge", "sahool-sam2-inference"]', 'targets = ["sahool-edge"]'),
    ],
)
def test_negative_control_each_kind_of_drift_is_caught(old, new):
    text = BAKE.read_text(encoding="utf-8")
    assert old in text, f"negative control is stale: {old!r} no longer in the bake file"
    problems = drift(text.replace(old, new, 1), load_yaml(BASE), load_yaml(OVERLAY))
    assert problems, f"changing {old!r} -> {new!r} must be reported as drift"


def test_negative_control_an_overlay_arg_the_bake_file_lacks_is_caught():
    overlay = load_yaml(OVERLAY)
    overlay["services"]["sahool-edge"]["build"]["args"]["NEW_ARG"] = "x"
    problems = drift(BAKE.read_text(encoding="utf-8"), load_yaml(BASE), overlay)
    assert any("sahool-edge.args" in p for p in problems), problems


def test_the_bake_file_needs_no_runtime_secret():
    text = "\n".join(
        line
        for line in BAKE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    names = set(re.findall(r'^variable\s+"([^"]+)"', text, re.M))
    assert names == {"COMPOSE_PROJECT_NAME", "PIP_INDEX_URL", "PYTORCH_CUDA_IMAGE"}, (
        f"bake variables are build settings only, got {sorted(names)}"
    )
    for name in names:
        block = re.search(rf'variable\s+"{name}"\s*\{{([^}}]*)\}}', text)
        assert block and "default" in block.group(1), f"{name} must have a default"


def _buildx_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "buildx", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _buildx_available(), reason="docker buildx not installed")
@pytest.mark.parametrize(
    "overrides",
    [{}, {"PIP_INDEX_URL": "", "PYTORCH_CUDA_IMAGE": ""}, {"PIP_INDEX_URL": "https://m/simple"}],
)
def test_bake_resolves_args_like_compose_interpolates_them(overrides, tmp_path):
    """`docker buildx bake --print` (no daemon needed) against Compose's `${VAR:-default}`."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PIP_INDEX_URL", "PYTORCH_CUDA_IMAGE", "COMPOSE_PROJECT_NAME"}
    }
    env.update(overrides)
    env.setdefault("DOCKER_CONFIG", str(tmp_path))
    result = subprocess.run(
        ["docker", "buildx", "bake", "-f", str(BAKE), "--print"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    printed = json.loads(result.stdout)["target"]
    for name, build in compose_gpu_builds(load_yaml(BASE), load_yaml(OVERLAY)).items():
        expected = {
            key: (overrides.get(v[0]) or v[1]) if isinstance(v, tuple) else v
            for key, v in build["args"].items()
        }
        assert printed[name]["args"] == expected, f"{name}: {printed[name]['args']} != {expected}"
        assert printed[name]["dockerfile"] == build["dockerfile"], printed[name]
        assert printed[name]["tags"] == [f"sahool-{name}"], printed[name]
