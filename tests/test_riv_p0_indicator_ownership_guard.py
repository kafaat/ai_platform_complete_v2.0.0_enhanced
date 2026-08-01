from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "shared/contracts/indicator_ownership.json"


def _literal_return(path: Path, function_name: str) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function_name
    )
    returned = next(item for item in ast.walk(node) if isinstance(item, ast.Return))
    value = ast.literal_eval(returned.value)
    assert isinstance(value, dict)
    return value


def test_canonical_indicator_ownership_manifest_has_single_owner_per_product():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    products = data["products"]
    ids = [p["id"] for p in products]
    assert len(ids) == len(set(ids))
    assert all(isinstance(p.get("owner"), str) and p["owner"] for p in products)
    for product in products:
        if product["kind"] == "observed_spectral":
            assert product["owner"] == "raster-service"


def test_platform_spatial_pipeline_has_no_ndvi_kernel():
    text = (ROOT / "services/sahool-platform/core/spatial/pipeline.py").read_text(encoding="utf-8")
    assert "def compute_ndvi_from_bands" not in text
    assert not re.search(r"\(\s*nir\s*-\s*red\s*\)\s*/\s*\(\s*nir\s*\+\s*red", text, re.I)


def test_spectral_formula_executables_are_inside_allowlist():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allowlist = tuple(data["policy"]["spectral_formula_allowlist"])
    patterns = [
        re.compile(r"\(\s*n(?:ir)?\s*-\s*r(?:ed)?\s*\)\s*/\s*\(\s*n(?:ir)?\s*\+\s*r(?:ed)?", re.I),
        re.compile(r"normalized_difference\s*\(", re.I),
    ]
    offenders: list[str] = []
    roots = [ROOT / "services", ROOT / "sentinel_hub"]
    for scan_root in roots:
        for path in scan_root.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if (
                rel.startswith(allowlist)
                or path.name.startswith("test_")
                or "/tests/" in f"/{rel}/"
                or rel.endswith("test_riv_p0_indicator_ownership_guard.py")
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            executable = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith(("#", '"', "'"))
            )
            if any(p.search(executable) for p in patterns):
                offenders.append(rel)
    assert offenders == []


def test_indicators_service_is_contract_only_not_spectral_owner():
    path = ROOT / "services/indicators-service/main.py"
    text = path.read_text(encoding="utf-8")
    root_contract = _literal_return(path, "root")
    assert root_contract["runtime_role"] == "canonical-observation-adapter"
    assert root_contract["spectral_compute"] is False
    assert "exclusively owned by raster-service" in text
