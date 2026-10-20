"""GDAL's S3 variables have exactly two writers, and nothing configures or reads them raw.

env_compose_drift_allowlist.json classifies AWS_S3_ENDPOINT / AWS_HTTPS because the code
writes them; an allowlist entry is name-wide, so on its own it would also hide a new
consumer reading them raw or a Compose service setting them again (the legacy-TiTiler
bypass, TITILER-LEGACY-S3-BYPASSES-ENDPOINT-POLICY-01). This test pins the exemption to
the documented write path.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GDAL_S3_VARS = frozenset({"AWS_S3_ENDPOINT", "AWS_HTTPS", "AWS_VIRTUAL_HOSTING"})
WRITERS = {
    "services/raster-service/object_store.py",
    "shared/storage/gdal_s3_env_gate.py",
}
GATE = "/opt/sahool/storage/gdal_s3_env_gate.py"
PRODUCTION_DIRS = ("services", "shared", "agents", "bots", "apps")


def _production_python():
    for top in PRODUCTION_DIRS:
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            parts = set(path.relative_to(ROOT).parts)
            if parts & {"tests", "test", "node_modules", ".venv"} or path.name.startswith("test_"):
                continue
            yield rel, path


def _mentions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in GDAL_S3_VARS:
            yield node


def test_only_the_two_writers_name_the_gdal_s3_variables():
    offenders = []
    for rel, path in _production_python():
        if rel in WRITERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        offenders += [f"{rel}:{node.lineno}" for node in _mentions(tree)]
    assert not offenders, (
        "GDAL S3 variables must come from the endpoint decision "
        f"(object_store.gdal_configure or gdal_s3_env_gate), not be named here: {offenders}"
    )


def test_object_store_only_assigns_them():
    rel = "services/raster-service/object_store.py"
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and getattr(node.slice, "value", None) in GDAL_S3_VARS:
            assert isinstance(node.ctx, ast.Store), f"{rel}:{node.lineno} reads a GDAL S3 variable"
        if isinstance(node, ast.Call) and any(
            isinstance(arg, ast.Constant) and arg.value in GDAL_S3_VARS for arg in node.args
        ):
            raise AssertionError(f"{rel}:{node.lineno} passes a GDAL S3 variable to a call")


def test_gate_never_reads_them_from_the_environment():
    rel = "shared/storage/gdal_s3_env_gate.py"
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and getattr(node.slice, "value", None) in GDAL_S3_VARS:
            raise AssertionError(f"{rel}:{node.lineno} subscripts a GDAL S3 variable")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "getenv"}
            and any(isinstance(a, ast.Constant) and a.value in GDAL_S3_VARS for a in node.args)
        ):
            raise AssertionError(f"{rel}:{node.lineno} reads a GDAL S3 variable")


def _compose_files():
    for path in sorted(ROOT.rglob("*.y*ml")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".github/", "node_modules/")) or "/node_modules/" in rel:
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("services"), dict):
            yield rel, doc["services"]


def _env_keys(service: dict) -> set[str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        return {str(item).split("=", 1)[0] for item in env}
    return set(env)


def test_no_compose_service_sets_them_unless_the_gate_is_its_entrypoint():
    offenders = []
    for rel, services in _compose_files():
        for name, service in services.items():
            if not isinstance(service, dict) or not (_env_keys(service) & GDAL_S3_VARS):
                continue
            entrypoint = service.get("entrypoint") or []
            if GATE not in (entrypoint if isinstance(entrypoint, list) else [entrypoint]):
                offenders.append(f"{rel}:{name}")
    assert not offenders, f"raw GDAL S3 variables reach a service without the gate: {offenders}"


def test_env_example_does_not_offer_them():
    keys = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert not keys & GDAL_S3_VARS


def test_allowlist_exemption_names_the_write_path():
    allow = json.loads(
        (ROOT / "scripts/ci/env_compose_drift_allowlist.json").read_text(encoding="utf-8")
    )["intentional"]
    for key in sorted(GDAL_S3_VARS):
        why = allow[key]["why"]
        for writer in WRITERS:
            assert writer in why, (key, writer)
