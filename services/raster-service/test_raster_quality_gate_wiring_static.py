from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_raster_quality_gate_wires_required_checks() -> None:
    script = ROOT / "scripts" / "ci" / "raster_quality_gate.sh"
    text = script.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "python3 -m compileall -q services/raster-service" in text
    assert "python3 scripts/ci/raster_main_decomposition_gate.py" in text
    assert "python3 scripts/ci/raster_import_graph_gate.py" in text
    assert "python3 -m pytest -q" in text


def test_raster_quality_gate_is_wired_to_makefile_and_release_assets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    local_gate = (ROOT / "scripts" / "ci" / "local_quality_gate.sh").read_text(encoding="utf-8")
    release_builder = (ROOT / "scripts" / "release" / "build_release_bundle.py").read_text(
        encoding="utf-8"
    )
    assert "raster-ci" in makefile
    assert "bash scripts/ci/raster_quality_gate.sh" in makefile
    assert "bash scripts/ci/raster_quality_gate.sh" in local_gate
    workflow = (ROOT / ".github" / "workflows" / "raster-service-gates.yml").read_text(
        encoding="utf-8"
    )
    assert '"scripts/ci/raster_quality_gate.sh"' in release_builder
    assert "bash scripts/ci/raster_quality_gate.sh" in workflow
    assert "services/raster-service/**" in workflow
