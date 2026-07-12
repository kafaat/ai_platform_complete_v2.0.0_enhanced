import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_artifacts_are_current():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/generate_indicator_artifacts.py"), "--check"],
        check=True,
    )


def test_single_observed_owner_and_complete_flow():
    own = json.loads((ROOT / "shared/contracts/indicator_ownership.json").read_text())
    assert own["policy"]["observed_spectral_owner"] == "raster-service"
    flow = json.loads((ROOT / "shared/contracts/indicator_product_flow.json").read_text())
    observed = next(f for f in flow["flows"] if f["product"] == "observed_indicator")
    assert (
        observed["producer"] == "raster-service"
        and "vegetation-analysis-service" in observed["consumers"]
    )


def test_canonical_observation_requires_lineage():
    schema = json.loads((ROOT / "shared/contracts/indicator_observation.schema.json").read_text())
    for key in ("scene_id", "acquisition_date", "algorithm_version", "product_version", "quality"):
        assert key in schema["required"]
