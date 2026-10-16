"""Replay frozen witnesses; explicit checkout/output paths avoid altering receipts."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--main", type=Path, required=True)
parser.add_argument("--fixed", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
evidence = Path(__file__).resolve().parent
temporary = tempfile.TemporaryDirectory(prefix="sahool-raster-witnesses-")
witnesses = []
for frozen in sorted((evidence / "witnesses").glob("*.py.txt")):
    path = Path(temporary.name) / frozen.name.removesuffix(".txt")
    path.write_bytes(frozen.read_bytes())
    witnesses.append(path)
results = {}
for label, checkout in [("red-main", args.main), ("green", args.fixed)]:
    checkout = checkout.resolve()
    command = [
        sys.executable,
        "-m",
        "pytest",
        *map(str, witnesses),
        "-q",
        "--override-ini",
        "addopts=",
    ]
    run = subprocess.run(
        command,
        cwd=checkout,
        env=dict(
            os.environ,
            PYTHONPATH=str(checkout / "services/raster-service"),
            PYTHONIOENCODING="utf-8",
        ),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (args.output / f"{label}.log").write_text(run.stdout, encoding="utf-8")
    results[label] = {"exit_code": run.returncode, "command": command, "checkout": str(checkout)}
(args.output / "replay-results.json").write_text(
    json.dumps(results, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(results, indent=2))
raise SystemExit(
    0 if results["red-main"]["exit_code"] == 1 and results["green"]["exit_code"] == 0 else 1
)
