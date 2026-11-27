"""The runtime guard must reject lost budgets, independently of source spelling."""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = Path("scripts/ci/irrigation_runtime_orchestrator_guard.py")
HOURLY = Path("services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py")
SERVICE = Path("services/sahool-platform/api/irrigation_runtime_orchestrator.py")
SOURCES = [
    GUARD,
    HOURLY,
    SERVICE,
    Path("services/sahool-platform/api/routers/irrigation_mpc.py"),
    Path("tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py"),
]


@pytest.fixture
def checkout(tmp_path):
    for relative in SOURCES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def run_guard(checkout):
    return subprocess.run(
        [sys.executable, str(checkout / GUARD)],
        cwd=checkout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class RemoveBudget(ast.NodeTransformer):
    def __init__(self, mutation):
        self.mutation = mutation
        self.changed = 0

    def visit_Call(self, node):
        self.generic_visit(node)
        if not isinstance(node.func, ast.Name) or node.func.id != "min":
            return node
        for argument in node.args:
            remove = (
                (
                    self.mutation == "event-ceiling"
                    and isinstance(argument, ast.Name)
                    and argument.id == "max_event_depth"
                )
                or (
                    self.mutation == "daily-cap"
                    and isinstance(argument, ast.Name)
                    and argument.id == "daily_remaining"
                )
                or (
                    self.mutation == "seasonal-cap"
                    and isinstance(argument, ast.BinOp)
                    and isinstance(argument.op, ast.Div)
                    and isinstance(argument.left, ast.Name)
                    and argument.left.id == "seasonal_volume_left"
                )
            )
            if remove:
                node.args.remove(argument)
                self.changed += 1
                break
        return node

    def visit_Assign(self, node):
        self.generic_visit(node)
        if self.mutation == "daily-debit" and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "daily_depth_left"
            for target in node.targets
        ):
            self.changed += 1
            return ast.Pass()
        if self.mutation == "pump-rest" and any(
            isinstance(target, ast.Name) and target.id == "off_time" for target in node.targets
        ):
            self.changed += 1
            node.value = ast.Name(id="elapsed", ctx=ast.Load())
        return node

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.target.id == "seasonal_volume_left":
            if self.mutation == "seasonal-debit":
                self.changed += 1
                return ast.Pass()
            if self.mutation == "seasonal-ceiling":
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Name) and child.id == "ROUND_CEILING":
                        child.id = "ROUND_DOWN"
                        self.changed += 1
        return node


def test_current_solver_passes_guard(checkout):
    result = run_guard(checkout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "irrigation runtime orchestrator guard: PASS" in result.stdout


def test_equivalent_source_formatting_passes_guard(checkout):
    path = checkout / HOURLY
    path.write_text(ast.unparse(ast.parse(path.read_text(encoding="utf-8"))), encoding="utf-8")
    result = run_guard(checkout)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ("event-ceiling", "hourly budget contract: event ceiling"),
        ("daily-cap", "hourly budget contract: cumulative daily ceiling"),
        ("daily-debit", "hourly budget contract: cumulative daily ceiling"),
        ("seasonal-cap", "hourly budget contract: cumulative seasonal ceiling"),
        ("seasonal-debit", "hourly budget contract: cumulative seasonal ceiling"),
        ("seasonal-ceiling", "hourly budget contract: published seasonal precision"),
        ("pump-rest", "hourly budget contract: rest starts after pump stops"),
    ],
)
def test_removed_limit_or_debit_fails_guard(checkout, mutation, diagnostic):
    path = checkout / HOURLY
    transform = RemoveBudget(mutation)
    tree = transform.visit(ast.parse(path.read_text(encoding="utf-8")))
    assert transform.changed == 1, "Mutation must remove exactly one live constraint"
    # The obsolete spelling in a comment must not satisfy the new behavioral guard.
    path.write_text(
        ast.unparse(ast.fix_missing_locations(tree))
        + "\n# event_limit = min(max_event_depth, max_daily_depth)\n",
        encoding="utf-8",
    )
    result = run_guard(checkout)
    assert result.returncode != 0, f"Guard accepted {mutation}"
    assert diagnostic in result.stderr, result.stdout + result.stderr


def test_governed_solver_argument_is_still_required(checkout):
    path = checkout / SERVICE
    text = path.read_text(encoding="utf-8")
    old = "irrigation_capability=capability"
    assert text.count(old) == 1
    path.write_text(text.replace(old, "irrigation_capability={}"), encoding="utf-8")
    result = run_guard(checkout)
    assert result.returncode != 0
    assert 'isinstance(kw["irrigation_capability"], ast.Name)' in result.stderr


def test_physical_dispatch_is_still_forbidden(checkout):
    with (checkout / SERVICE).open("a", encoding="utf-8") as stream:
        stream.write("\nmqtt.publish('command', {})\n")
    result = run_guard(checkout)
    assert result.returncode != 0
    assert "mqtt.publish" in result.stderr
