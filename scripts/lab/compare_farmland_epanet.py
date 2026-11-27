"""Compare platform serial-pipe losses to the agricultural calculator's pinned EPANET oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

CALCULATOR_COMMIT = "10d2e0e9a543d95fffe0ad2610debd0e80059138"
BLOBS = {
    "public/catalog.mjs": "fcb0b81ec551be710b28a1c99643863bfbf2496e",
    "public/core.mjs": "88cd6e1bbcaca188854acd84729725cf614ea2ee",
    "hydraulic-oracle.py": "cccd5cc5bd108b5726d26ec0199a86e7480eed34",
}


def compare(calculator: Path):
    for path, sha in BLOBS.items():
        data = (calculator / path).read_bytes()
        if (
            hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False
            ).hexdigest()
            != sha
        ):
            raise ValueError(f"calculator source mismatch: {path}")
    # The pinned oracle executes the actual calculator JS and WNTR EPANET 2.2.
    oracle = subprocess.run(
        [sys.executable, str(calculator / "hydraulic-oracle.py")],
        capture_output=True,
        check=True,
        encoding="utf-8",
        timeout=180,
    )
    reference = json.loads(oracle.stdout)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/sahool-platform"))
    from api.irrigation_engineering_workspace import HydraulicSegmentInput, _segment_hazen_loss_m

    cases = []
    for record in reference["cases"]:
        pipe = record["input"]
        if pipe["kind"] != "pipe":
            continue
        segment = HydraulicSegmentInput(
            segment_id="main",
            from_node="pond",
            to_node="field",
            length_m=pipe["length"],
            internal_diameter_mm=pipe["id"],
            hazen_williams_c=pipe["c"],
        )
        _, loss = _segment_hazen_loss_m(pipe["q"], segment)
        relative = abs(loss - record["epanet_head_m"]) / record["epanet_head_m"]
        if not math.isfinite(relative) or relative >= record["limit"]:
            raise ValueError(f"EPANET mismatch in case {record['case']}")
        cases.append(
            {
                "case": record["case"],
                "platform_head_loss_m": loss,
                "epanet_head_loss_m": record["epanet_head_m"],
                "relative_error": relative,
            }
        )
    if len(cases) != 12 or reference["passed"] != reference["count"] or reference["count"] != 16:
        raise ValueError("unexpected calculator coverage")
    return {
        "calculator_sha": CALCULATOR_COMMIT,
        "engine": reference["engine"],
        "calculator_cases": reference["passed"],
        "platform_pipe_cases": cases,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calculator", type=Path)
    print(json.dumps(compare(parser.parse_args().calculator.resolve()), indent=2))
